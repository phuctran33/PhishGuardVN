"""Package the explicitly selected candidate; evaluate only after parity and locking."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from importlib.metadata import version
import sys,json,hashlib,subprocess
import numpy as np
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.metrics import average_precision_score,precision_score,recall_score,f1_score,confusion_matrix
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from phishguard_vn.teacher import (Teacher,load_teacher,validate_pipeline,feature_fingerprint,sha,
                                   MODEL_VERSION,PREPROCESSING_VERSION)
from phishguard_vn.external_provenance import validate_audit_manifest
from phishguard_vn.external_pilot import evaluate_verified

def metrics(y,pred,score):
    tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return dict(n=len(y),positive=int(np.sum(y==1)),negative=int(np.sum(y==0)),
        ap=float(average_precision_score(y,score)),precision=float(precision_score(y,pred,zero_division=0)),
        recall=float(recall_score(y,pred,zero_division=0)),f1=float(f1_score(y,pred,zero_division=0)),
        fpr=float(fp/(fp+tn)),tn=int(tn),fp=int(fp),fn=int(fn),tp=int(tp))

def main():
    out=ROOT/"reports/tables/teacher_release";out.mkdir(parents=True,exist_ok=True)
    proposal=json.loads((ROOT/"reports/tables/url_research/candidate_proposal.json").read_text())
    selected=next(r for r in proposal["candidates"] if r["role"]=="main")
    assert selected["experiment"]=="tfidf_linear_svm" and selected["full_train_parameters"]=={"C":0.5}
    path=ROOT/selected["model_path"]
    if not path.exists():raise FileNotFoundError("Selected candidate absent; refit only the fixed C=0.5 pipeline before packaging")
    assert sha(path)==selected["sha256"]
    for name,digest in proposal["source_sha256"].items():assert sha(ROOT/name)==digest
    original=joblib.load(path)
    branch=original.named_steps["features"].named_transformers_["text"]
    assert branch.named_steps["normalize"].mode=="raw"
    pipeline=Pipeline([("tfidf",deepcopy(branch.named_steps["vectorizer"])),
                       ("model",deepcopy(original.named_steps["model"]))])
    validate_pipeline(pipeline)
    core=pd.read_csv(ROOT/"data/interim/core_gold_silver.csv")
    core=core.loc[core.split.isin(["train","val"])].copy()
    folds=pd.read_csv(ROOT/"data/interim/02_group_folds_train.csv")
    train=core.loc[core.id.isin(folds.id)].copy()
    assert len(train)==13078 and train.label.value_counts().to_dict()=={"benign":11004,"phishing":2074}
    assert set(train.id)==set(folds.id) and train.id.is_unique
    examples=["example.com","https://example.com/Case?Q=A","https://EXAMPLE.com:8080/a",
              "https://b?cher.de/A","xn--bcher-kva.de"]
    urls=train.url.tolist()+examples
    frame=pd.DataFrame({"url":urls})
    before=original.decision_function(frame);after=pipeline.decision_function(urls)
    np.testing.assert_allclose(before,after,rtol=0,atol=1e-12)
    np.testing.assert_array_equal(original.predict(frame),pipeline.predict(urls))
    model_path=ROOT/"models/teacher_tfidf_svm_v1.joblib"
    bundle={"pipeline":pipeline,"model_version":MODEL_VERSION,"preprocessing_version":PREPROCESSING_VERSION,
            "class_mapping":{"benign":0,"phishing":1},"feature_fingerprint":feature_fingerprint(pipeline),
            "decision_rule":"estimator.predict","score_kind":"decision_function"}
    joblib.dump(bundle,model_path)
    loaded=Teacher(joblib.load(model_path))
    results=loaded.predict_batch(examples)
    np.testing.assert_allclose([r["score"] for r in results],pipeline.decision_function(examples),rtol=0,atol=1e-12)
    assert results==[loaded.predict_one(u) for u in examples]
    metadata={"teacher_finalized":True,"candidate":"tfidf_linear_svm","candidate_role":"main",
        "candidate_config":{"C":0.5},"candidate_sha256":selected["sha256"],
        "candidate_record_sha256":sha(ROOT/"reports/tables/url_research/candidate_proposal.json"),
        "model_version":MODEL_VERSION,"preprocessing_version":PREPROCESSING_VERSION,
        "selected_by":"core_train_group_cv","primary_metric":"mean_outer_average_precision",
        "outer_mean_ap_of_procedure":0.9256282836988817,
        "selection_scope":"User explicitly selected candidate; full-Train C selected previously by inner Group CV; outer mean is not an independent score of C=0.5.",
        "input_contract":"Nonempty raw strings; no strip/lower/normalization/scheme addition/truncation. Missing scheme accepted. Reject wrong type/blank/NUL only.",
        "output_contract":"benign=0, phishing=1; signed SVM margin, NOT probability; label from estimator.predict including ties",
        "decision_rule":"estimator.predict","threshold":0,"external_used_for_selection":False,
        "score_kind":"decision_function","operating_point_scope":"fixed_core_protocol",
        "train_rows":13078,"class_counts":{"benign":11004,"phishing":2074},"test_evaluated":False,
        "vectorizer_parameters":{k:pipeline.named_steps["tfidf"].get_params()[k] for k in
            ["analyzer","ngram_range","min_df","max_df","max_features","lowercase","sublinear_tf","use_idf","smooth_idf","norm","binary","strip_accents"]},
        "classifier_parameters":pipeline.named_steps["model"].get_params(),
        "n_features":len(pipeline.named_steps["tfidf"].vocabulary_),
        "feature_fingerprint":feature_fingerprint(pipeline),
        "versions":{n:version(n) for n in ["scikit-learn","numpy","scipy","joblib"]},
        "input_sha256":{str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in [ROOT/"data/interim/core_gold_silver.csv",ROOT/"data/interim/02_group_folds_train.csv"]},
        "adapter_sha256":sha(ROOT/"src/phishguard_vn/teacher.py"),
        "runtime_git_revision":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        "runtime_git_dirty":bool(subprocess.check_output(["git","status","--porcelain"],text=True).strip()),
        "model_sha256":sha(model_path),"packaged_utc":datetime.now(timezone.utc).isoformat(),
        "parity":{"inputs":len(urls),"margin_max_abs_error":float(np.max(abs(before-after))),"labels_equal":True,"single_batch_equal":True,"candidate_reused":True}}
    meta_path=out/"metadata.json";meta_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    lock={"teacher_finalized":True,"selected_by":"core_train_group_cv","external_used_for_selection":False,
          "model_name":"tfidf_linear_svm","feature_set":"url_raw_char_3_5","score_kind":"decision_function",
          "decision_rule":"estimator.predict","threshold":0,"operating_point_scope":"fixed_core_protocol",
          "bundle":{"path":model_path.relative_to(ROOT).as_posix(),"sha256":sha(model_path)},
          "selection_record":{"path":meta_path.relative_to(ROOT).as_posix(),"sha256":sha(meta_path)}}
    (ROOT/"configs/week6_teacher_lock.json").write_text(json.dumps(lock,indent=2)+"\n",encoding="utf-8",newline="\n")
    teacher=load_teacher(ROOT)
    eligible=pd.read_csv(ROOT/"data/interim/05_matrix_X_brand_trainval.csv",usecols=["id"])
    val=core.loc[core.split.eq("val")&core.id.isin(eligible.id)].sort_values("id")
    assert len(val)==1585
    r=teacher.predict_batch(val.url.tolist())
    vp=pd.DataFrame({"id":val.id.to_numpy(),"y_true":val.label.map({"benign":0,"phishing":1}).to_numpy(),
                     "prediction":[x["class_id"] for x in r],"score":[x["score"] for x in r]})
    vp.to_csv(out/"validation_predictions.csv",index=False,lineterminator="\n")
    saved=pd.read_csv(out/"validation_predictions.csv",float_precision="round_trip")
    evaluation={"bundle_sha256":sha(model_path),"preprocessing_version":PREPROCESSING_VERSION,
                "decision_rule":"estimator.predict","validation_previously_observed":True,
                "validation":metrics(saved.y_true.to_numpy(),saved.prediction.to_numpy(),saved.score.to_numpy()),
                "official_test_evaluated":False}
    # Preserve strict external ledger eligibility and review-scope checks.
    manifest=json.loads((ROOT/"reports/tables/external_pilot/manifest.json").read_text())
    validate_audit_manifest(ROOT,manifest)
    ledger=pd.read_csv(ROOT/"data/external/derived/k53_candidates.csv",keep_default_na=False)
    recall,rp=evaluate_verified(ledger,teacher.predict_one,representation="host_only")
    both,ep=evaluate_verified(ledger,teacher.predict_one,representation="host_only",two_class=True)
    ep.to_csv(out/"external_predictions.csv",index=False,lineterminator="\n")
    external_saved=pd.read_csv(out/"external_predictions.csv",float_precision="round_trip")
    evaluation["external_two_class_recomputed"]=metrics(external_saved.label.map({"benign":0,"phishing":1}).to_numpy(),external_saved.prediction.map({"benign":0,"phishing":1}).to_numpy(),external_saved.score.to_numpy())
    evaluation.update(external_recall=recall,external_two_class=both,pending_not_ground_truth=int(ledger.review_status.eq("pending").sum()),
                      external_scope="Same overlapping cohorts: 92 positives inside 99 two-class; historical hostnames only, NOT independent datasets")
    (out/"evaluation.json").write_text(json.dumps(evaluation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    oof=pd.read_csv(ROOT/"reports/tables/week6/oof_predictions.csv.gz",float_precision="round_trip")
    wrong=oof.loc[oof.model.eq("tfidf_linear_svm")&oof.true_label.ne(oof.predicted_label)].copy()
    wrong["error"]=np.where(wrong.true_label.eq(0),"FP","FN")
    cases=wrong.sort_values("id").groupby(["fold_id","error"]).head(2).merge(core[["id","url"]],on="id",validate="one_to_one")
    assert len(cases)>=10 and set(cases.fold_id)=={0,1,2}
    cases["url"]=cases.url.str.replace(".","[.]",regex=False)
    cases["observation"]=cases.apply(lambda r:f"{r.error}; fold={r.fold_id}; margin={r.score:.6f}; estimator label={r.predicted_label}, source label={r.true_label}",axis=1)
    cases["hypothesis"]="Character n-gram patterns may overlap across classes or encode source/format cues; this is not an attribution of the full-Train coefficients to an OOF model."
    cases["next_check"]="Inspect the corresponding fold fitting corpus and its n-grams/source/format distribution; do not visit URL, change labels or tune to this case."
    cases.to_csv(out/"oof_error_cases.csv",index=False,lineterminator="\n")
    print(json.dumps({"model_sha256":sha(model_path),"parity":metadata["parity"],"validation":evaluation["validation"],
                      "external":both["metrics"],"errors":len(cases)},indent=2))
if __name__=="__main__":main()
