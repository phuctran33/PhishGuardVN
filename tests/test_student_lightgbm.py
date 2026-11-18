"""LightGBM soft-target / portable-JSON tests; no project Teacher fitting."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from scipy.sparse import csr_matrix,hstack
from sklearn.feature_extraction.text import TfidfVectorizer

lgb=pytest.importorskip("lightgbm")
from phishguard_vn.student import student_text,metrics,sha256
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.student_lightgbm import export_features,export_booster,HybridLightGBMStudent,load_lightgbm_student
ROOT=Path(__file__).resolve().parents[1]


def test_fractional_cross_entropy_and_portable_hybrid():
    urls=["https://example.com/a","https://example.org/b","https://bank-login.net/A",
          "https://bücher.de/","http://127.0.0.1/","https://example.com/login?Q=%2F",
          "https://www.hcmus.edu.vn","https://secure-check.example.net/x"]
    vectorizer=TfidfVectorizer(analyzer="char",ngram_range=(3,5),lowercase=False,
                              sublinear_tf=True,min_df=1)
    T=vectorizer.fit_transform([student_text(u) for u in urls])
    E=e2_matrix(urls)
    X=hstack([T,csr_matrix(E)],format="csr")
    # Fractional q directly supported by LightGBM cross_entropy, not binary labels.
    q=np.array([.1,.2,.8,.15,.2,.9,.05,.85])
    model=lgb.LGBMRegressor(objective="cross_entropy",n_estimators=5,num_leaves=3,
        min_child_samples=1,min_data_in_bin=1,verbosity=-1,deterministic=True,
        force_col_wise=True,n_jobs=1,random_state=42).fit(X,q)
    portable=HybridLightGBMStudent(export_features(vectorizer),export_booster(model,.5,"fixture"))
    actual=np.array([r["score"] for r in portable.predict_batch(urls)])
    np.testing.assert_allclose(actual,model.predict(X),rtol=0,atol=1e-12)
    assert np.isfinite(actual).all() and ((actual>=0)&(actual<=1)).all()
    assert portable.bundle["tree_count"]==5
    with pytest.raises(ValueError):portable.predict_one("https://example.com:bad")


def test_saved_lightgbm_study_and_fold_boundaries():
    folder=ROOT/"artifacts/student_lightgbm"
    if not (folder/"manifest.json").exists():
        pytest.skip("Run requested LightGBM study first")
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    assert manifest["teacher_retrained"] is False
    assert manifest["teacher_release_unchanged"] is True
    assert manifest["official_test_evaluated"] is False
    assert manifest["android_verified"] is False
    for p,digest in manifest["output_sha256"].items():assert sha256(ROOT/p)==digest
    target_meta=json.loads((folder/"cv_targets/manifest.json").read_text(encoding="utf-8"))
    assert sha256(folder/"cv_targets/manifest.json")==manifest["cv_targets_manifest_sha256"]
    mapping=pd.read_csv(ROOT/"reports/tables/stacking/train_ids.csv.gz")
    for fold in (0,1,2):
        fit=pd.read_csv(folder/f"cv_targets/outer{fold}_fitting_targets.csv.gz")
        held=pd.read_csv(folder/f"cv_targets/outer{fold}_held_reference.csv.gz")
        assert set(fit.id)==set(mapping.loc[mapping.fold_id.ne(fold),"id"])
        assert set(held.id)==set(mapping.loc[mapping.fold_id.eq(fold),"id"])
        assert set(fit.id).isdisjoint(held.id)
        assert "url" not in fit and "url" not in held
        assert target_meta["folds"][str(fold)]["domain_overlap"]==0
    runs=pd.read_csv(ROOT/"reports/tables/student_lightgbm/cv_metrics.csv")
    preds=pd.read_csv(ROOT/"reports/tables/student_lightgbm/cv_predictions.csv.gz",float_precision="round_trip")
    assert len(runs)==2*2*3*3
    for _,row in runs.iterrows():
        batch=preds.loc[preds.family.eq(row.family)&preds["mode"].eq(row["mode"])&
                        preds.seed.eq(row.seed)&preds.fold_id.eq(row.fold)]
        result=metrics(batch.y_true,batch.score,.5)
        for key in ("ap","precision","recall","f1","fpr","tp","fp","tn","fn"):
            assert result[key]==pytest.approx(row[key],abs=1e-12)
    raw=pd.read_csv(ROOT/"data/splits/url_val.csv",usecols=["id","url"])
    saved=pd.read_csv(ROOT/"reports/tables/student_lightgbm/validation_predictions.csv.gz",float_precision="round_trip")
    for mode in ("hard_only","kd_mixed"):
        predictor=load_lightgbm_student(ROOT,mode)
        assert predictor.bundle["tree_count"]==400
        selected=saved.loc[saved["mode"].eq(mode)&saved.seed.eq(42)].merge(raw,on="id",validate="one_to_one")
        assert len(selected)==1585
        # Real raw-URL -> TF-IDF/E2 -> JSON trees matches saved native predictions.
        actual=predictor.predict_batch(selected.url.tolist())
        np.testing.assert_allclose([r["score"] for r in actual],selected.score,rtol=0,atol=1e-12)
        np.testing.assert_array_equal([r["class_id"] for r in actual],selected.prediction)


def test_published_reference_fixtures_and_complete_hashes():
    folder=ROOT/"artifacts/student_lightgbm"
    if not (folder/"manifest.json").exists():
        pytest.skip("Run LightGBM study first")
    m=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    for name,digest in m["bundle_files_sha256"].items():
        assert sha256(folder/name)==digest
    fixture=json.loads((folder/"python_reference.json").read_text(encoding="utf-8"))
    assert sum(c["status"]=="classified" for c in fixture["cases"])>=30
    assert any(c["status"]=="rejected" for c in fixture["cases"])
    for mode in ("hard_only","kd_mixed"):
        model=load_lightgbm_student(ROOT,mode)
        for case in fixture["cases"]:
            if case["status"]=="rejected":
                with pytest.raises((ValueError,TypeError)):
                    model.predict_one(case["url"])
            else:
                actual=model.predict_one(case["url"])
                expected=case["expected"][mode]
                assert actual["score"]==pytest.approx(expected["score"],abs=1e-12)
                assert actual["class_id"]==expected["class_id"]
