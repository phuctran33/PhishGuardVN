"""Requested LightGBM Student: verified fold Teachers -> 3-fold CV -> final bundle.

Teacher fitting is NEVER called. Historical fold Teachers are only loaded.
CV uses per-fold vocabulary; final model uses released Teacher Train targets.
"""
from pathlib import Path
from importlib.metadata import version
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"));sys.path.insert(0,str(ROOT/"scripts"))
import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix,hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from threadpoolctl import threadpool_limits
from lightgbm import LGBMRegressor
from train_student import load_data,fit_student
from compare_students import paired_bootstrap
from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.student import metrics,choose_threshold,sha256
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.student_lightgbm import export_features,export_booster,HybridLightGBMStudent

PLAN=ROOT/"configs/week7_lightgbm_student.json"
ART=ROOT/"artifacts/student_lightgbm"
OUT=ROOT/"reports/tables/student_lightgbm"
CACHE=ART/"cv_targets"


def write_json(path,value,compact=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,
        indent=None if compact else 2,separators=(",",":") if compact else None)+"\n",
        encoding="utf-8",newline="\n")


def write_csv(path,frame):
    path.parent.mkdir(parents=True,exist_ok=True)
    data=frame.to_csv(index=False,lineterminator="\n").encode("utf-8")
    path.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)


def id_hash(frame):
    return hashlib.sha256("\n".join(frame.id.astype(str)).encode()).hexdigest()


def load_inputs():
    train,val,excluded=load_data(ROOT)
    mapping=pd.read_csv(ROOT/"reports/tables/stacking/train_ids.csv.gz")
    if len(mapping)!=13078 or not mapping.id.is_unique:raise ValueError("Invalid fold map")
    train=train.merge(mapping,on="id",validate="one_to_one",suffixes=("","_fold"))
    if (len(train)!=13078 or not train.target.eq(train.target_fold).all()
            or not train.group.eq(train.registrable_domain).all()
            or not train.groupby("group").fold_id.nunique().eq(1).all()
            or set(train.fold_id)!={0,1,2}):
        raise ValueError("Fold IDs/labels/groups differ from frozen Train")
    return train.sort_values("id").reset_index(drop=True),val,excluded


def verify_cv_targets(train):
    path=CACHE/"manifest.json"
    if not path.exists():return None
    meta=json.loads(path.read_text(encoding="utf-8"))
    if meta["fold_map_sha256"]!=sha256(ROOT/"reports/tables/stacking/train_ids.csv.gz"):
        raise ValueError("Cached target folds changed")
    for p,digest in meta["files_sha256"].items():
        if sha256(CACHE/p)!=digest:raise ValueError("CV target artifact changed: "+p)
    for p,digest in meta["input_sha256"].items():
        if sha256(ROOT/p)!=digest:raise ValueError("CV target input changed: "+p)
    for fold,record in meta["folds"].items():
        fitting=train.loc[train.fold_id.ne(int(fold))]
        held=train.loc[train.fold_id.eq(int(fold))]
        if id_hash(fitting)!=record["fitting_ids_sha256"] or id_hash(held)!=record["held_ids_sha256"]:
            raise ValueError("CV target fitting/held IDs changed")
    return meta


def prepare_cv_targets(train,E):
    meta=verify_cv_targets(train)
    if meta is not None:
        print("Reuse verified fold targets: no Teacher fitting or scoring.",flush=True)
        return meta
    CACHE.mkdir(parents=True,exist_ok=True)
    X=train[["url"]].copy()
    for i,name in enumerate(E2_FEATURES):X[name]=E[:,i]
    ledger=pd.read_csv(ROOT/"reports/tables/stacking/fit_ledger.csv")
    records,files={},{}
    for fold in (0,1,2):
        fitting=train.loc[train.fold_id.ne(fold)]
        held=train.loc[train.fold_id.eq(fold)]
        if set(fitting.group)&set(held.group):raise ValueError("Domain leakage")
        record_path=ROOT/f"reports/tables/stacking/stack_hist_outer{fold}.json"
        record=json.loads(record_path.read_text(encoding="utf-8"))
        if (id_hash(fitting)!=record["fitting_ids_sha256"]
                or id_hash(held)!=record["held_ids_sha256"]):
            raise ValueError("Historical Teacher fitting IDs mismatch")
        lineage=ledger.loc[(ledger.context==f"outer{fold}/refit")&
                           (ledger.model=="stack_hist")&(ledger.stage=="meta_lr")]
        if lineage.empty or not lineage.training_ids_sha256.eq(id_hash(fitting)).all():
            raise ValueError("Historical Teacher fit ledger mismatch")
        model_path=ROOT/f"data/interim/stacking/stack_hist_outer{fold}.joblib"
        if not model_path.exists():
            raise FileNotFoundError("Need historical fold Teacher or already-exported cv_targets: "+str(model_path))
        model=joblib.load(model_path)
        hist=model.bases["hist"].named_steps["model"]
        if (model.members!=["svm","hist"] or hist.do_early_stopping_ or hist.n_iter_!=300
                or model.meta.named_steps["lr"].C!=record["params"]["C"]):
            raise ValueError("Unexpected fold Teacher architecture")
        teacher_fit=model.predict_proba(X.loc[fitting.index])[:,1]
        teacher_held=model.predict_proba(X.loc[held.index])[:,1]
        saved=pd.read_csv(ROOT/f"reports/tables/stacking/stack_hist_outer{fold}_oof.csv.gz",
                          float_precision="round_trip")
        saved=held[["id"]].merge(saved,on="id",validate="one_to_one")
        np.testing.assert_allclose(teacher_held,saved.score,rtol=0,atol=1e-12)
        if not np.isfinite(teacher_fit).all() or ((teacher_fit<0)|(teacher_fit>1)).any():
            raise ValueError("Invalid fold Teacher targets")
        target=fitting[["id","target"]].copy()
        target["teacher_score"]=teacher_fit
        target["outer_fold"]=fold
        name=f"outer{fold}_fitting_targets.csv.gz"
        write_csv(CACHE/name,target);files[name]=sha256(CACHE/name)
        reference=held[["id","target","fold_id"]].copy()
        reference["teacher_score"]=teacher_held
        name=f"outer{fold}_held_reference.csv.gz"
        write_csv(CACHE/name,reference);files[name]=sha256(CACHE/name)
        records[str(fold)]=dict(fitting_ids_sha256=id_hash(fitting),held_ids_sha256=id_hash(held),
            teacher_model_sha256=sha256(model_path),historical_record_sha256=sha256(record_path),
            teacher_path=str(model_path.relative_to(ROOT)).replace("\\","/"),
            parameters=record["params"],domain_overlap=0,held_prediction_parity_max_diff=float(
                np.max(np.abs(teacher_held-saved.score))),
            targets_scope="in-sample within outer fitting only, no outer-held labels seen by Teacher",
            teacher_retrained=False)
        print("Verified historical Teacher fold",fold,"targets",len(target),"held",len(reference),flush=True)
    inputs=["data/splits/url_train.csv","reports/tables/stacking/train_ids.csv.gz",
            "reports/tables/stacking/fit_ledger.csv","configs/teacher_v2_candidate_lock.json",
            "src/phishguard_vn/stacking.py","src/phishguard_vn/features.py",
            "src/phishguard_vn/brand_features.py","src/phishguard_vn/url_parser.py"]
    for fold in (0,1,2):
        inputs += [f"reports/tables/stacking/stack_hist_outer{fold}.json",
                   f"reports/tables/stacking/stack_hist_outer{fold}_oof.csv.gz"]
    meta=dict(folds=records,files_sha256=files,
        fold_map_sha256=sha256(ROOT/"reports/tables/stacking/train_ids.csv.gz"),
        input_sha256={p:sha256(ROOT/p) for p in inputs},teacher_retrained=False,
        scope="Archived fold Teachers, not released full-Train weights; Student final uses release")
    write_json(CACHE/"manifest.json",meta)
    return meta


def vectorizer(plan):
    config=dict(plan["text"]);config["ngram_range"]=tuple(config["ngram_range"])
    return TfidfVectorizer(**config)


def fit_pair(family,X,q,seed,plan):
    if family=="text_lr":
        return fit_student(X,q,dict(C=plan["lr"]["C"],max_iter=plan["lr"]["max_iter"],seed=seed))
    # cross_entropy accepts fractional labels q in [0,1] natively; no duplicated rows.
    model=LGBMRegressor(**plan["lightgbm"],random_state=seed)
    model.fit(X,q)
    if model.booster_.num_trees()!=400:raise ValueError("Requested 400-tree budget not reached")
    return model


def score(model,X,family):
    values=model.predict_proba(X)[:,1] if family=="text_lr" else model.predict(X)
    if not np.isfinite(values).all() or ((values<0)|(values>1)).any():
        raise ValueError("Invalid Student scores")
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-targets",action="store_true")
    args=parser.parse_args()
    ART.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    train,val,excluded=load_inputs()
    print("Preparing frozen E2; no Teacher fitting.",flush=True)
    E=e2_matrix(train.url);V=e2_matrix(val.url)
    target_meta=prepare_cv_targets(train,E)
    if args.prepare_targets:return
    source_paths=["configs/week7_lightgbm_student.json","scripts/train_lightgbm_student.py",
        "src/phishguard_vn/student_lightgbm.py","src/phishguard_vn/student.py",
        "src/phishguard_vn/student_comparison.py","src/phishguard_vn/stacking.py",
        "src/phishguard_vn/features.py","src/phishguard_vn/brand_features.py",
        "src/phishguard_vn/url_parser.py","scripts/train_student.py"]
    input_paths=["data/splits/url_train.csv","data/splits/url_val.csv",
        "reports/tables/stacking/train_ids.csv.gz","configs/teacher_lock.json",
        "configs/teacher_v2_candidate_lock.json","models/teacher_v2_candidate.joblib",
        "artifacts/student_week7/teacher_targets.csv.gz","artifacts/student_week7/manifest.json"]
    source_hashes={p:sha256(ROOT/p) for p in source_paths}
    input_hashes={p:sha256(ROOT/p) for p in input_paths}
    frozen=json.loads((ROOT/"configs/teacher_v2_candidate_lock.json").read_text(encoding="utf-8"))
    for name,digest in frozen["source_sha256"].items():
        if sha256(ROOT/"src/phishguard_vn"/name)!=digest:raise ValueError("Frozen source changed")
    runs,predictions=[],[]
    with threadpool_limits(limits=1):
        # 1. Exact frozen 3 domain folds. Vocabulary is fit AGAIN inside each fitting set.
        for fold in plan["outer_folds"]:
            fit=train.loc[train.fold_id.ne(fold)]
            held=train.loc[train.fold_id.eq(fold)]
            tf=vectorizer(plan)
            T=tf.fit_transform(fit.text)
            H=tf.transform(held.text)
            hybrid_T=hstack([T,csr_matrix(E[fit.index])],format="csr")
            hybrid_H=hstack([H,csr_matrix(E[held.index])],format="csr")
            targets=pd.read_csv(CACHE/f"outer{fold}_fitting_targets.csv.gz",float_precision="round_trip")
            targets=fit[["id","target"]].merge(targets,on="id",validate="one_to_one",suffixes=("","_cache"))
            if len(targets)!=len(fit) or targets.teacher_score.isna().any() or not targets.target.eq(targets.target_cache).all():
                raise ValueError("Incomplete/misaligned fold targets")
            for family in plan["models"]:
                for mode in plan["modes"]:
                    q=(fit.target.to_numpy() if mode=="hard_only" else
                       (1-plan["alpha"])*fit.target.to_numpy()+plan["alpha"]*targets.teacher_score.to_numpy())
                    for seed in plan["seeds"]:
                        started=time.perf_counter()
                        model=fit_pair(family,T if family=="text_lr" else hybrid_T,q,seed,plan)
                        scores=score(model,H if family=="text_lr" else hybrid_H,family)
                        row=dict(family=family,mode=mode,fold=fold,seed=seed,
                                 fit_seconds=time.perf_counter()-started,
                                 **metrics(held.target,scores,plan["cv_threshold"]))
                        runs.append(row)
                        pred=held[["id","target","fold_id"]].rename(columns={"target":"y_true"}).copy()
                        pred["family"],pred["mode"],pred["seed"]=family,mode,seed
                        pred["score"],pred["prediction"]=scores,(scores>=plan["cv_threshold"]).astype(int)
                        predictions.append(pred)
                        print("CV",family,mode,"fold",fold,"seed",seed,"AP",round(row["ap"],5),flush=True)
        cv=pd.DataFrame(runs);oof=pd.concat(predictions,ignore_index=True)
        write_csv(OUT/"cv_metrics.csv",cv);write_csv(OUT/"cv_predictions.csv.gz",oof)
        # Average folds first per seed; seeds are not additional independent datasets.
        per_seed=cv.groupby(["family","mode","seed"]).agg(ap=("ap","mean"),recall=("recall","mean"),
            fpr=("fpr","mean"),f1=("f1","mean"),precision=("precision","mean")).reset_index()
        summary=per_seed.groupby(["family","mode"]).agg(ap_mean=("ap","mean"),ap_seed_sd=("ap","std"),
            recall_mean=("recall","mean"),fpr_mean=("fpr","mean"),f1_mean=("f1","mean"),
            precision_mean=("precision","mean")).reset_index()
        write_csv(OUT/"cv_summary.csv",summary)
        ranking=summary.loc[summary.family.eq("hybrid_lightgbm")].sort_values(["ap_mean","mode"],ascending=[False,True])
        selected=str(ranking.iloc[0]["mode"])

        # 2. Threshold/choice frozen from Train OOF BEFORE supplementary Validation.
        thresholds={}
        for mode in plan["modes"]:
            s=oof.loc[oof.family.eq("hybrid_lightgbm")&oof["mode"].eq(mode)&oof.seed.eq(plan["export_seed"])]
            s=train[["id","target"]].merge(s,on="id",validate="one_to_one")
            if len(s)!=len(train):raise ValueError("Incomplete Train OOF threshold data")
            thresholds[mode]=choose_threshold(s.target,s.score,plan["fpr_budget"])
        write_json(OUT/"selection.json",dict(selected_mode=selected,thresholds=thresholds,
            selected_by="Train domain Group CV AP",validation_used_for_selection=False,
            official_test_evaluated=False,threshold_scope="pooled Train Student OOF; final deployment only"))

        # 3. Fit final Student on full Train using UNCHANGED released Teacher cached targets.
        baseline=json.loads((ROOT/"artifacts/student_week7/manifest.json").read_text(encoding="utf-8"))
        for p in ["data/splits/url_train.csv","data/splits/url_val.csv","configs/teacher_lock.json",
                  "models/teacher_v2_candidate.joblib"]:
            if input_hashes[p]!=baseline["input_sha256"][p]:raise ValueError("Released targets stale: "+p)
        if sha256(ROOT/baseline["teacher_targets"]["path"])!=baseline["teacher_targets"]["sha256"]:
            raise ValueError("Released targets changed")
        full=vectorizer(plan)
        full_T=full.fit_transform(train.text);full_V=full.transform(val.text)
        hybrid_T=hstack([full_T,csr_matrix(E)],format="csr")
        hybrid_V=hstack([full_V,csr_matrix(V)],format="csr")
        full_targets=pd.read_csv(ROOT/baseline["teacher_targets"]["path"],float_precision="round_trip")
        full_targets=train[["id"]].merge(full_targets,on="id",validate="one_to_one")
        if len(full_targets)!=len(train) or full_targets.teacher_score.isna().any():
            raise ValueError("Missing final Teacher targets")
        write_json(ART/"features.json",export_features(full),compact=True)
        models,parity,validation,final_rows={},{},[],[]
        for mode in plan["modes"]:
            q=(train.target.to_numpy() if mode=="hard_only" else
               (1-plan["alpha"])*train.target.to_numpy()+plan["alpha"]*full_targets.teacher_score.to_numpy())
            for seed in plan["seeds"]:
                model=fit_pair("hybrid_lightgbm",hybrid_T,q,seed,plan)
                scores=score(model,hybrid_V,"hybrid_lightgbm")
                final_rows.append(dict(mode=mode,seed=seed,**metrics(val.target,scores,thresholds[mode])))
                pred=val[["id","target"]].rename(columns={"target":"y_true"}).copy()
                pred["mode"],pred["seed"],pred["score"]=mode,seed,scores
                pred["prediction"]=(scores>=thresholds[mode]).astype(int)
                validation.append(pred)
                if seed==plan["export_seed"]:
                    model.booster_.save_model(str(ART/(mode+".model.txt")))
                    bundle=export_booster(model,thresholds[mode],mode)
                    write_json(ART/(mode+".json"),bundle,compact=True)
                    portable=HybridLightGBMStudent(export_features(full),bundle)
                    actual=np.array([portable.score_row(portable.vector(url,e2)) for url,e2 in zip(val.url,V)])
                    np.testing.assert_allclose(actual,scores,rtol=0,atol=1e-12)
                    np.testing.assert_array_equal(actual>=thresholds[mode],scores>=thresholds[mode])
                    parity[mode]=dict(inputs=len(val),max_abs_diff=float(np.max(np.abs(actual-scores))),labels_equal=True)
                    models[mode]=dict(json=mode+".json",native=mode+".model.txt",
                        json_sha256=sha256(ART/(mode+".json")),threshold=thresholds[mode],
                        tree_count=len(bundle["trees"]),seed=seed)
                print("FINAL",mode,"seed",seed,"Validation AP",round(final_rows[-1]["ap"],5),flush=True)
    write_csv(OUT/"validation_metrics.csv",pd.DataFrame(final_rows))
    write_csv(OUT/"validation_predictions.csv.gz",pd.concat(validation,ignore_index=True))
    # Conditional uncertainty on pooled OOF; distinguish from mean-fold selection AP.
    def scores_by_seed(mode):
        f=oof.loc[oof.family.eq("hybrid_lightgbm")&oof["mode"].eq(mode)]
        return np.column_stack([f.loc[f.seed.eq(s)].set_index("id").loc[train.id,"score"] for s in plan["seeds"]])
    bootstrap=paired_bootstrap(train.target.to_numpy(),train.group.to_numpy(),
        scores_by_seed("kd_mixed"),scores_by_seed("hard_only"),1000,42)
    write_json(OUT/"paired_bootstrap.json",bootstrap)
    # 4. Pack feature/reference assets and static Python fixtures for Hy/Khiem.
    assets={"brand_reference_v1.csv":"src/phishguard_vn/resources/brand_reference_v1.csv",
            "psl_icann_tldextract_5.4.0.txt":"mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt"}
    for name,path in assets.items():shutil.copyfile(ROOT/path,ART/name)
    examples=["example.com","https://EXAMPLE.com/Login?Q=%2F","https://www.hcmus.edu.vn",
        "https://example.com:8443/path","https://bücher.de/","http://127.0.0.1/",
        "http://[2001:db8::1]/","//example.com/A","https://user:pass@example.com/a#fragment",
        "https://example.com/a?x=1&y=2","https://example.com/"+("a"*200)]
    features=export_features(full)
    portable=HybridLightGBMStudent(features,json.loads((ART/(selected+".json")).read_text(encoding="utf-8")))
    fixtures=[dict(url=u,e2=e2_matrix([u])[0].tolist(),**portable.predict_one(u)) for u in examples]
    write_json(ART/"python_reference.json",dict(scope="synthetic valid URLs, no accuracy labels",cases=fixtures))
    # Source/environment/lineage stay inspectable; no adapter or Android success claimed.
    inference_paths=["src/phishguard_vn/student_lightgbm.py","src/phishguard_vn/student.py",
        "src/phishguard_vn/student_comparison.py","src/phishguard_vn/stacking.py",
        "src/phishguard_vn/features.py","src/phishguard_vn/brand_features.py","src/phishguard_vn/url_parser.py"]
    inference_files=["features.json",*[mode+".json" for mode in plan["modes"]],*assets.keys()]
    manifest=dict(plan=plan,created_utc=datetime.now(timezone.utc).isoformat(),
        producer_revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        source_sha256=source_hashes,input_sha256=input_hashes,
        inference_source_sha256={p:source_hashes[p] for p in inference_paths},
        inference_files_sha256={p:sha256(ART/p) for p in inference_files},
        runtime_assets_sha256={p:sha256(ROOT/p) for p in assets.values()},
        cv_targets_manifest_sha256=sha256(CACHE/"manifest.json"),models=models,parity=parity,
        selected_mode=selected,selected_by="Train domain Group CV; Validation supplementary",
        teacher_release_unchanged=True,teacher_retrained=False,official_test_evaluated=False,
        external_evaluated=False,android_verified=False,student_default=False,
        environment={p:version(p) for p in ["lightgbm","scikit-learn","numpy","scipy","pandas","tldextract","idna"]},
        output_sha256={str(p.relative_to(ROOT)).replace("\\","/"):sha256(p) for p in OUT.glob("*") if p.is_file()})
    for p,h in {**source_hashes,**input_hashes}.items():
        if sha256(ROOT/p)!=h:raise ValueError("Protected input/source changed: "+p)
    write_json(ART/"manifest.json",manifest)
    print("CV selected mode:",selected,"(not default Android engine)",flush=True)
    print(summary.to_string(index=False))


if __name__=="__main__":
    main()
