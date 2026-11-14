"""Run the registered research plan. Fit/selection loops are explicit and train-only."""
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import argparse, hashlib, json, sys, time, warnings, subprocess, traceback
import numpy as np
import pandas as pd
import joblib
from sklearn.base import clone
from sklearn.model_selection import StratifiedGroupKFold, ParameterGrid
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import average_precision_score, precision_score, recall_score, f1_score, confusion_matrix
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from phishguard_vn.brand_features import E2_FEATURES, load_reference
from phishguard_vn.research_preprocessing import make_linear, feature_counts, frame_from_urls

OUT = ROOT/"reports/tables/url_research"
LOCAL = ROOT/"data/interim/url_research"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def metrics(y,predicted,score):
    tn,fp,fn,tp = confusion_matrix(y,predicted,labels=[0,1]).ravel()
    return dict(ap=average_precision_score(y,score),precision=precision_score(y,predicted,zero_division=0),
        recall=recall_score(y,predicted,zero_division=0),f1=f1_score(y,predicted,zero_division=0),
        fpr=fp/(fp+tn),tn=int(tn),fp=int(fp),fn=int(fn),tp=int(tp))

def load_train():
    meta = json.loads((ROOT/"reports/tables/week6/teacher_selection.json").read_text(encoding="utf-8"))
    for path,digest in meta["input_sha256"].items():
        assert sha(ROOT/path)==digest,path
    assert load_reference().sha256==meta["reference"]["sha256"]
    core = pd.read_csv(ROOT/"data/interim/core_gold_silver.csv")
    core = core.loc[core.split.eq("train"),["id","url","label","source"]]
    matrix = pd.read_csv(ROOT/"data/interim/05_matrix_X_brand_trainval.csv",float_precision="round_trip")
    domains = pd.read_csv(ROOT/"data/interim/03_registrable_domains.csv")
    folds = pd.read_csv(ROOT/"data/interim/02_group_folds_train.csv")
    frame = core.merge(matrix,on="id",validate="one_to_one").merge(folds,on="id",validate="one_to_one")
    frame = frame.merge(domains[["id","registrable_domain"]],on="id",validate="one_to_one").sort_values("id").reset_index(drop=True)
    frame["target"] = frame.label.map({"benign":0,"phishing":1})
    assert len(frame)==13078 and frame.id.is_unique and frame.target.notna().all()
    assert list(matrix.columns)==["id",*E2_FEATURES]
    assert frame.groupby("registrable_domain").fold_id.nunique().eq(1).all()
    return frame

def input_frame(frame):
    return frame[["url",*E2_FEATURES]]  # No ID/source/label metadata enters a model.

def group_splits(frame):
    splits = list(StratifiedGroupKFold(2,shuffle=True,random_state=42).split(
        frame,frame.target,frame.registrable_domain))
    for a,b in splits:
        assert set(frame.iloc[a].registrable_domain).isdisjoint(frame.iloc[b].registrable_domain)
        assert frame.iloc[a].target.nunique()==frame.iloc[b].target.nunique()==2
    return splits

def scores_for(model,X):
    return model.predict_proba(X)[:,1] if hasattr(model,"predict_proba") else model.decision_function(X)

def make_model(spec,params,checkpoint):
    if spec["group"]=="neural":
        from phishguard_vn.research_neural import NeuralURLClassifier
        return NeuralURLClassifier(spec["id"],epochs=2,learning_rate=0.001,
                     checkpoint=str(checkpoint)).set_params(**params)
    model=make_linear(spec)
    if spec["id"]=="baseline_tfidf_svm":
        from sklearn.svm import LinearSVC
        model.set_params(model=LinearSVC(max_iter=10000,random_state=42))
    return model.set_params(**{"model__"+k:v for k,v in params.items()})

def fit_record(model,frame,details,ledger):
    start=time.perf_counter()
    from importlib.metadata import version
    row={"sklearn_version":version("scikit-learn"),"numpy_version":version("numpy"),
         "pandas_version":version("pandas"),**details,"training_rows":len(frame),"training_ids_sha256":hashlib.sha256(
        "\n".join(frame.id.astype(str)).encode()).hexdigest()}
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warnings.simplefilter("error",ConvergenceWarning)
            model.fit(input_frame(frame),frame.target)
        row.update(status="success",warnings=json.dumps(sorted(set(str(w.message) for w in caught))))
        if hasattr(model,"loss_history_"):
            row["loss_history"]=json.dumps(model.loss_history_)
            row["training_stop"]="fixed_epoch_budget_not_convergence_claim"
        return model
    except Exception as exc:
        row.update(status="failed",error=type(exc).__name__+": "+str(exc)[:1000])
        raise
    finally:
        row["fit_seconds"]=time.perf_counter()-start
        ledger.append(row)
        pd.DataFrame(ledger).to_csv(OUT/"fit_ledger.csv",index=False,encoding="utf-8",lineterminator="\n")

def select_fit(spec,frame,context,checkpoint,ledger):
    splits=group_splits(frame)
    results=[]
    for config_id,params in enumerate(ParameterGrid(spec["grid"])):
        scores=[]
        for inner,(a,b) in enumerate(splits):
            print(spec["id"],context,"config",config_id,"inner",inner,flush=True)
            detail=dict(experiment=spec["id"],context=str(context),stage="inner",
                        config_id=config_id,inner_fold=inner,parameters=json.dumps(params,sort_keys=True))
            try:
                model=fit_record(make_model(spec,params,checkpoint),frame.iloc[a],detail,ledger)
                score=scores_for(model,input_frame(frame.iloc[b]))
                ap=average_precision_score(frame.iloc[b].target,score)
                scores.append(float(ap))
                ledger[-1]["heldout_ap"]=float(ap)
            except Exception:
                scores.append(float("nan"))
            pd.DataFrame(ledger).to_csv(OUT/"fit_ledger.csv",index=False,encoding="utf-8",lineterminator="\n")
        results.append((float(np.mean(scores)),config_id,params))
    valid=[r for r in results if np.isfinite(r[0])]
    if not valid:
        raise ValueError("No configuration succeeded in both inner folds")
    best=sorted(valid,key=lambda r:(-r[0],r[1]))[0]
    detail=dict(experiment=spec["id"],context=str(context),stage="refit",
                config_id=best[1],inner_fold=-1,parameters=json.dumps(best[2],sort_keys=True))
    model=fit_record(make_model(spec,best[2],checkpoint),frame,detail,ledger)
    return model,best

def measure(model,spec,urls):
    # Same scope: offline raw URL -> required feature extraction -> predict_proba.
    def call():
        X=frame_from_urls(urls,spec)
        return scores_for(model,X)
    durations=[]
    for i in range(7):
        start=time.perf_counter(); call()
        if i>=2:durations.append((time.perf_counter()-start)*1000)
    stream=BytesIO();joblib.dump(model,stream)
    return dict(model_bytes=stream.tell(),latency_p50_ms=float(np.median(durations)),
                latency_p95_ms=float(np.quantile(durations,.95)),batch_size=len(urls),
                latency_scope="CPU offline URL-to-score incl required extraction; threads=2; warmup2/repeats5")

def export_partitions(train):
    rows=[]
    for context in ["0","1","2","full_train"]:
        fit=train if context=="full_train" else train.loc[train.fold_id.ne(int(context))]
        held=train.iloc[:0] if context=="full_train" else train.loc[train.fold_id.eq(int(context))]
        assignments=pd.DataFrame({"id":fit.id.to_numpy(),"context":context,"role":"fitting","inner_fold":-1})
        for inner,(_,b) in enumerate(group_splits(fit)):
            assignments.loc[b,"inner_fold"]=inner
        rows.extend([assignments,pd.DataFrame({"id":held.id.to_numpy(),"context":context,"role":"held_out","inner_fold":-1})])
    pd.concat(rows,ignore_index=True).to_csv(OUT/"partitions.csv.gz",index=False,
        compression={"method":"gzip","mtime":0},lineterminator="\n")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume",action="store_true",help="Reuse completed families only under identical code/data")
    parser.add_argument("--classical-only",action="store_true",help="Run A-F first; leave neural groups pending")
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/"configs/url_research_plan.json").read_text(encoding="utf-8"))
    train=load_train()
    inputs={name:sha(ROOT/name) for name in [
        "configs/url_research_plan.json","src/phishguard_vn/research_preprocessing.py",
        "src/phishguard_vn/research_neural.py","scripts/run_url_research.py",
        "data/interim/core_gold_silver.csv","data/interim/05_matrix_X_brand_trainval.csv",
        "data/interim/02_group_folds_train.csv"]}
    manifest_path=OUT/"execution_manifest.json"
    if manifest_path.exists() and args.resume:
        assert json.loads(manifest_path.read_text())["input_sha256"]==inputs,"Research code/data changed; do not mix runs."
    else:
        assert not (OUT/"fit_ledger.csv").exists(),"Use --resume or a separate output directory"
        manifest_path.write_text(json.dumps({"created_utc":datetime.now(timezone.utc).isoformat(),
            "git_revision":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "input_sha256":inputs,"train_rows":len(train),"teacher_finalized":False},indent=2)+"\n",encoding="utf-8")
    export_partitions(train)
    checkpoint=LOCAL/"pretrained"
    ledger=pd.read_csv(OUT/"fit_ledger.csv").to_dict("records") if args.resume and (OUT/"fit_ledger.csv").exists() else []
    statuses=[]
    for spec in plan["experiments"]:
        name=spec["id"]
        if args.classical_only and spec["group"]=="neural":
            statuses.append({"experiment":name,"status":"not_run","note":"neural runtime pending"})
            pd.DataFrame(statuses).to_csv(OUT/"experiment_status.csv",index=False)
            continue
        output=OUT/(name+"_oof.csv.gz");fold_path=OUT/(name+"_folds.csv")
        if args.resume and output.exists() and fold_path.exists():
            statuses.append({"experiment":name,"status":"completed","note":"resumed persisted family"});continue
        predictions=[];fold_rows=[]
        try:
            for fold in [0,1,2]:
                fitting=train.loc[train.fold_id.ne(fold)]
                held=train.loc[train.fold_id.eq(fold)]
                assert set(fitting.registrable_domain).isdisjoint(held.registrable_domain)
                model,best=select_fit(spec,fitting,fold,checkpoint,ledger)
                scores=scores_for(model,input_frame(held))
                assert np.isfinite(scores).all()
                pred=np.asarray(model.predict(input_frame(held))).ravel()
                predictions.append(pd.DataFrame({"experiment":name,"config_id":best[1],
                    "parameters":json.dumps(best[2],sort_keys=True),"id":held.id.to_numpy(),"fold":fold,
                    "y_true":held.target.to_numpy(),"score":scores,"prediction":pred}))
                fold_rows.append({"experiment":name,"group":spec["group"],"fold":fold,
                    "config_id":best[1],"parameters":json.dumps(best[2],sort_keys=True),
                    "inner_ap":best[0],**metrics(held.target,pred,scores),
                    **feature_counts(model,input_frame(held)),**measure(model,spec,held.url.iloc[:16].tolist())})
                print(name,"OUTER",fold,"AP",fold_rows[-1]["ap"],flush=True)
            pd.concat(predictions,ignore_index=True).to_csv(output,index=False,
                compression={"method":"gzip","mtime":0},lineterminator="\n")
            pd.DataFrame(fold_rows).to_csv(fold_path,index=False,encoding="utf-8",lineterminator="\n")
            statuses.append({"experiment":name,"status":"completed"})
        except Exception as exc:
            traceback.print_exc()
            statuses.append({"experiment":name,"status":"blocked_or_failed","error":type(exc).__name__+": "+str(exc)})
        pd.DataFrame(statuses).to_csv(OUT/"experiment_status.csv",index=False)
    print("Completed research families; summarize using scripts/summarize_url_research.py",flush=True)

if __name__=="__main__":
    with threadpool_limits(limits=2):
        main()
