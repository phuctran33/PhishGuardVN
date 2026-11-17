"""Bounded Student comparison. Read main(): data -> fit -> JSON parity -> rank.

No Teacher fitting, target regeneration, Test or external evaluation. Old Student
artifacts and notebook are preserved. Plan is configs/week7_student_comparison.json.
"""
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
import argparse
import gzip
import json
import subprocess
import sys
import time
import warnings

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"scripts"))
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, ExtraTreesClassifier
from threadpoolctl import threadpool_limits
from train_student import load_data, fit_student
from phishguard_vn.student import Student, metrics, choose_threshold, export_model, sha256
from phishguard_vn.student_comparison import E2Student, e2_matrix, weighted_copies, export_e2
from phishguard_vn.brand_features import load_reference

PLAN=ROOT/"configs/week7_student_comparison.json"


def write_json(path,value,compact=False):
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,
                    indent=None if compact else 2,separators=(",",":") if compact else None)+"\n",
                    encoding="utf-8",newline="\n")


def write_csv(path,frame):
    frame.to_csv(path,index=False,encoding="utf-8",lineterminator="\n")


def make_model(family,spec,seed):
    """Explicit constructors; no search framework or hidden model registry."""
    if family=="e2_lr":
        return LogisticRegression(C=spec["C"],max_iter=spec["max_iter"],
                                  solver="liblinear",random_state=seed)
    if family=="e2_mlp":
        return MLPClassifier(hidden_layer_sizes=tuple(spec["hidden_layer_sizes"]),
                 activation="relu",solver="adam",alpha=spec["alpha"],
                 learning_rate_init=spec["learning_rate_init"],max_iter=spec["epochs"],
                 early_stopping=False,n_iter_no_change=spec["epochs"]+1,tol=0,random_state=seed)
    if family=="e2_hist":
        return HistGradientBoostingClassifier(max_iter=spec["max_iter"],
                 max_leaf_nodes=spec["max_leaf_nodes"],learning_rate=spec["learning_rate"],
                 min_samples_leaf=spec["min_samples_leaf"],l2_regularization=spec["l2_regularization"],
                 early_stopping=False,random_state=seed)
    if family=="e2_extra":
        return ExtraTreesClassifier(n_estimators=spec["n_estimators"],max_depth=spec["max_depth"],
                 min_samples_leaf=spec["min_samples_leaf"],random_state=seed,n_jobs=1)
    raise ValueError("Unknown family")


def paired_bootstrap(y,groups,score_a,score_b,repeats,seed):
    """Difference of mean seed AP, paired resampling of Validation domains."""
    from sklearn.metrics import average_precision_score
    rng=np.random.default_rng(seed)
    _,codes=np.unique(groups,return_inverse=True)
    blocks=[np.flatnonzero(codes==i) for i in range(codes.max()+1)]
    deltas=[]
    undefined=0
    for _ in range(repeats):
        indices=np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))])
        if len(np.unique(y[indices]))<2:
            undefined+=1
            continue
        delta=np.mean([average_precision_score(y[indices],score_a[indices,j])
                     -average_precision_score(y[indices],score_b[indices,j])
                       for j in range(score_a.shape[1])])
        deltas.append(delta)
    return dict(delta_mean_AP=float(np.mean([
            average_precision_score(y,score_a[:,j])-average_precision_score(y,score_b[:,j])
            for j in range(score_a.shape[1])])),
                ci_low=float(np.quantile(deltas,.025)),ci_high=float(np.quantile(deltas,.975)),
                valid=len(deltas),undefined=undefined,replicates=repeats,
                scope="conditional paired domain bootstrap, not selection-adjusted")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root",type=Path,default=ROOT)
    args=parser.parse_args()
    output=args.output_root.resolve()
    artifacts=output/"artifacts/student_comparison"
    tables=output/"reports/tables/student_comparison"
    for p in (artifacts,tables):p.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    source_paths=["configs/week7_student_comparison.json","scripts/compare_students.py",
        "scripts/train_student.py","src/phishguard_vn/student_comparison.py",
        "src/phishguard_vn/student.py","src/phishguard_vn/stacking.py",
        "src/phishguard_vn/features.py","src/phishguard_vn/brand_features.py",
        "src/phishguard_vn/url_parser.py","requirements-teacher.txt"]
    input_paths=["data/splits/url_train.csv","data/splits/url_val.csv",
        "artifacts/student_week7/teacher_targets.csv.gz","artifacts/student_week7/manifest.json",
        "reports/tables/student_week7/hard_only_validation.csv",
        "configs/teacher_lock.json","configs/teacher_v2_candidate_lock.json",
        "models/teacher_v2_candidate.joblib"]
    source_hashes={p:sha256(ROOT/p) for p in source_paths}
    input_hashes={p:sha256(ROOT/p) for p in input_paths}
    revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    baseline=json.loads((ROOT/"artifacts/student_week7/manifest.json").read_text(encoding="utf-8"))
    if sha256(ROOT/baseline["teacher_targets"]["path"])!=baseline["teacher_targets"]["sha256"]:
        raise ValueError("Historical Teacher targets changed")
    # Ensure frozen targets still correspond to the released bundle and data snapshot.
    for p in ("data/splits/url_train.csv","data/splits/url_val.csv","configs/teacher_lock.json",
              "models/teacher_v2_candidate.joblib"):
        if baseline["input_sha256"][p]!=input_hashes[p]:
            raise ValueError("Targets no longer match current release/data: "+p)

    lock=json.loads((ROOT/"configs/teacher_v2_candidate_lock.json").read_text(encoding="utf-8"))
    for name,digest in lock["source_sha256"].items():
        if sha256(ROOT/"src/phishguard_vn"/name)!=digest:
            raise ValueError("Frozen Teacher/E2 source changed: "+name)
    if load_reference().sha256!=lock["reference_sha256"]:
        raise ValueError("Frozen brand reference changed")

    # 1. No interim files. Reuse identical eligibility; Teacher outputs are cache, not OOF.
    train,val,excluded=load_data(ROOT)
    if (len(train),len(val))!=(13078,1585):
        raise ValueError("Data snapshot changed")
    targets=pd.read_csv(ROOT/baseline["teacher_targets"]["path"],float_precision="round_trip")
    targets=train[["id"]].merge(targets,on="id",validate="one_to_one")
    if len(targets)!=len(train) or targets.teacher_score.isna().any():
        raise ValueError("Incomplete Teacher targets")
    np.testing.assert_array_equal(targets.target,train.target)
    saved=pd.read_csv(ROOT/"reports/tables/student_week7/hard_only_validation.csv",float_precision="round_trip")
    saved=val[["id","target"]].merge(saved,on="id",validate="one_to_one")
    if len(saved)!=len(val) or saved.teacher_score.isna().any():
        raise ValueError("Incomplete Validation Teacher references")
    np.testing.assert_array_equal(saved.target,saved.y_true)
    teacher_scores=saved.teacher_score.to_numpy()
    teacher_labels=saved.teacher_prediction.to_numpy()
    write_csv(tables/"source_label_counts.csv",
        pd.concat([train,val]).groupby(["split","source","label"]).size().reset_index(name="count"))
    write_csv(tables/"exclusions.csv",excluded)

    # 2. Both inputs fit/derive from Train only; frozen E2 source never changes.
    print("Preparing frozen E2 and Train-only text vocabulary...",flush=True)
    e2_train,e2_val=e2_matrix(train.url),e2_matrix(val.url)
    scaler=StandardScaler().fit(e2_train)
    vec=TfidfVectorizer(analyzer="char",ngram_range=(3,5),max_features=8192,min_df=2,
                        lowercase=False,sublinear_tf=True,norm="l2")
    text_train=vec.fit_transform(train.text)
    text_val=vec.transform(val.text)
    q_by_mode={"hard_only":train.target.to_numpy(),
               "kd_mixed":(1-plan["kd_alpha"])*train.target.to_numpy()
                          +plan["kd_alpha"]*targets.teacher_score.to_numpy()}
    rows,predictions,records,parity=[],[],{},{}
    with threadpool_limits(limits=1):
        for family,spec in plan["families"].items():
            for mode in plan["modes"]:
                candidate=family+"__"+mode
                for seed in plan["seeds"]:
                    start=time.perf_counter()
                    scale=scaler if family in ("e2_lr","e2_mlp") else None
                    q=q_by_mode[mode]
                    if family=="text_lr":
                        model=fit_student(text_train,q,dict(C=1,max_iter=2000,seed=seed))
                        scores=model.predict_proba(text_val)[:,1]
                        caught=[]
                    else:
                        X_train=scaler.transform(e2_train) if scale is not None else e2_train
                        X_val=scaler.transform(e2_val) if scale is not None else e2_val
                        model=make_model(family,spec,seed)
                        X,y,w=weighted_copies(X_train,q)
                        with warnings.catch_warnings(record=True) as caught:
                            warnings.simplefilter("always")
                            model.fit(X,y,sample_weight=w)
                        scores=model.predict_proba(X_val)[:,1]
                    fit_seconds=time.perf_counter()-start
                    threshold=choose_threshold(val.target,scores,plan["fpr_budget"])
                    pred=val[["id","target"]].rename(columns={"target":"y_true"}).copy()
                    pred["candidate"],pred["seed"]=candidate,seed
                    pred["score"],pred["prediction"]=scores,(scores>=threshold).astype(int)
                    pred["teacher_prediction"]=teacher_labels
                    predictions.append(pred)
                    record=dict(candidate=candidate,family=family,mode=mode,seed=seed,
                        **metrics(val.target,scores,threshold),fit_seconds=fit_seconds,
                        agreement=float(np.mean((scores>=threshold)==teacher_labels)),
                        score_mae=float(np.mean(np.abs(scores-teacher_scores))),
                        warning_count=len(caught),warnings=" | ".join(sorted(set(str(w.message) for w in caught))),
                        iterations=int(np.asarray(getattr(model,"n_iter_",getattr(model,"max_iter",0))).max()))
                    fixed=metrics(val.target,scores,.5)
                    rows.append({**record,"operating_point":"validation_fpr_budget"})
                    rows.append({**record,**fixed,"agreement":float(np.mean((scores>=.5)==teacher_labels)),
                                 "operating_point":"fixed_0.5"})
                    print(candidate,"seed",seed,"AP",round(record["ap"],5),
                          "fit",round(fit_seconds,2),"s",flush=True)
                    # Export a PREDECLARED seed, not the best seed. Check every Val score.
                    if seed==plan["export_seed"]:
                        bundle=(export_model(vec,model,threshold,candidate,dict(ngram_range=[3,5]))
                                if family=="text_lr" else export_e2(model,scale,family,threshold))
                        bundle["model_version"]="student-comparison-"+candidate
                        path=artifacts/(candidate+".json")
                        write_json(path,bundle,compact=True)
                        portable=Student(bundle) if family=="text_lr" else E2Student(bundle)
                        actual=(np.array([portable.score_one(u) for u in val.url]) if family=="text_lr"
                                else portable.score_features(e2_val))
                        np.testing.assert_allclose(actual,scores,rtol=0,atol=1e-12)
                        np.testing.assert_array_equal(actual>=threshold,scores>=threshold)
                        parity[candidate]=dict(inputs=len(val),max_abs_diff=float(np.max(np.abs(actual-scores))),
                                               labels_equal=True)
                        records[candidate]=dict(path=str(path.relative_to(output)).replace("\\","/"),
                            sha256=sha256(path),family=family,threshold=threshold,model_bytes=path.stat().st_size)

    # 3. Persist every run, including weak results and fixed-budget warnings.
    runs=pd.DataFrame(rows)
    write_csv(tables/"runs.csv",runs)
    prediction_frame=pd.concat(predictions,ignore_index=True)
    (tables/"validation_predictions.csv.gz").write_bytes(gzip.compress(
        prediction_frame.to_csv(index=False,lineterminator="\n").encode("utf-8"),mtime=0))
    dev=runs.loc[runs.operating_point.eq("validation_fpr_budget")]
    summary=dev.groupby(["candidate","family","mode"]).agg(
        ap_mean=("ap","mean"),ap_sd=("ap","std"),recall_mean=("recall","mean"),
        fpr_mean=("fpr","mean"),f1_mean=("f1","mean"),agreement_mean=("agreement","mean"),
        fit_seconds_mean=("fit_seconds","mean"),seeds=("seed","nunique")).reset_index()
    asset_paths=["mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt",
                 "src/phishguard_vn/resources/brand_reference_v1.csv"]
    assets={p:dict(sha256=sha256(ROOT/p),bytes=(ROOT/p).stat().st_size) for p in asset_paths}
    for name,record in records.items():
        record["assets"]=asset_paths[:1] if record["family"]=="text_lr" else asset_paths
        record["package_bytes"]=record["model_bytes"]+sum(assets[p]["bytes"] for p in record["assets"])
    summary["model_bytes"]=summary.candidate.map(lambda c:records[c]["model_bytes"])
    summary["package_bytes"]=summary.candidate.map(lambda c:records[c]["package_bytes"])
    summary["within_budget"]=summary.package_bytes<=plan["package_budget_bytes"]

    # Same CPU runtime; extraction and model costs separated, batch-one sequential.
    timing=[]
    sample=val.iloc[:300]
    with threadpool_limits(limits=1):
        for name,record in records.items():
            start=time.perf_counter()
            b=json.loads((output/record["path"]).read_text(encoding="utf-8"))
            model=Student(b) if record["family"]=="text_lr" else E2Student(b)
            load_ms=(time.perf_counter()-start)*1000
            full,extraction,inference=[],[],[]
            for i,url in enumerate(sample.url.tolist()):
                start=time.perf_counter()
                if record["family"]=="text_lr":
                    # Text predictor includes canonicalization, TF-IDF and linear score.
                    model.score_one(url)
                    total=(time.perf_counter()-start)*1000
                    extract_ms=infer_ms=None
                else:
                    X=e2_matrix([url])
                    middle=time.perf_counter()
                    model.score_features(X)
                    end=time.perf_counter()
                    total=(end-start)*1000
                    extract_ms,infer_ms=(middle-start)*1000,(end-middle)*1000
                if i>=50:
                    full.append(total)
                    if extract_ms is not None:
                        extraction.append(extract_ms);inference.append(infer_ms)
            timing.append(dict(candidate=name,json_load_ms=load_ms,warmup=50,requests=len(full),
                p50_ms=float(np.median(full)),p95_ms=float(np.quantile(full,.95)),
                extraction_p50_ms=float(np.median(extraction)) if extraction else None,
                inference_p50_ms=float(np.median(inference)) if inference else None,
                scope="desktop single URL to score, same 250 URLs, threads=1",android_measured=False))
    timings=pd.DataFrame(timing)
    write_csv(tables/"latency.csv",timings)
    summary=summary.merge(timings[["candidate","p50_ms","p95_ms"]],on="candidate",validate="one_to_one")
    summary=summary.sort_values(["within_budget","ap_mean","recall_mean","package_bytes","candidate"],
                                ascending=[False,False,False,True,True]).reset_index(drop=True)
    write_csv(tables/"summary.csv",summary)
    eligible=summary.loc[summary.within_budget]
    if eligible.empty:
        raise ValueError("No model within predeclared research budget")
    selected=str(eligible.iloc[0].candidate)

    # 4. Conditional uncertainty: paired domain bootstrap, not independent test evidence.
    def score_matrix(candidate):
        f=prediction_frame.loc[prediction_frame.candidate.eq(candidate)]
        return np.column_stack([f.loc[f.seed.eq(s)].set_index("id").loc[val.id,"score"] for s in plan["seeds"]])
    comparisons=["text_lr__hard_only",selected.split("__")[0]+"__hard_only"]
    bootstrap=[]
    for other in sorted(set(comparisons)):
        if other==selected:continue
        result=paired_bootstrap(val.target.to_numpy(),val.group.to_numpy(),score_matrix(selected),
            score_matrix(other),plan["bootstrap"]["replicates"],plan["bootstrap"]["seed"])
        bootstrap.append(dict(candidate=selected,comparator=other,**result))
    write_csv(tables/"paired_bootstrap.csv",pd.DataFrame(bootstrap))
    hard=summary.loc[summary["mode"].eq("hard_only"),["family","ap_mean"]].rename(columns={"ap_mean":"hard_AP"})
    kd=summary.loc[summary["mode"].eq("kd_mixed"),["family","ap_mean"]].rename(columns={"ap_mean":"kd_AP"})
    delta=hard.merge(kd,on="family");delta["kd_minus_hard_AP"]=delta.kd_AP-delta.hard_AP
    write_csv(tables/"kd_effect.csv",delta)

    # No changes to historical Student/Teacher. New manifest is independent.
    inference_paths=["src/phishguard_vn/student_comparison.py","src/phishguard_vn/student.py",
        "src/phishguard_vn/stacking.py","src/phishguard_vn/url_parser.py",
        "src/phishguard_vn/features.py","src/phishguard_vn/brand_features.py"]
    for p,h in {**source_hashes,**input_hashes}.items():
        if sha256(ROOT/p)!=h:raise ValueError("Protected input changed: "+p)
    manifest=dict(plan=plan,producer_revision=revision,
        producer_source_dirty=subprocess.run(["git","diff","--quiet","HEAD","--",*source_paths],cwd=ROOT).returncode!=0,
        created_utc=datetime.now(timezone.utc).isoformat(),source_sha256=source_hashes,input_sha256=input_hashes,
        inference_source_sha256={p:source_hashes[p] for p in inference_paths},
        required_assets=assets,models=records,parity=parity,selected_candidate=selected,
        export_seed=plan["export_seed"],train_rows=len(train),validation_rows=len(val),
        validation_positives=int(val.target.sum()),official_test_evaluated=False,
        external_evaluated=False,teacher_retrained=False,android_verified=False,
        targets_scope="released Teacher in-sample Train; no OOF/nested claim",
        selection_scope="development Validation, reused after initial LR study; no global optimum claim",
        go_no_go="Research candidate only; no default replacement without independent and Android checks",
        environment={p:version(p) for p in ["numpy","scipy","pandas","scikit-learn","idna","tldextract"]},
        output_sha256={str(p.relative_to(output)).replace("\\","/"):sha256(p)
                       for p in sorted(tables.glob("*")) if p.is_file()})
    write_json(artifacts/"manifest.json",manifest)
    print("Selected research candidate:",selected,flush=True)
    print(summary[["candidate","ap_mean","ap_sd","recall_mean","package_bytes","within_budget"]].to_string(index=False))


if __name__=="__main__":
    main()
