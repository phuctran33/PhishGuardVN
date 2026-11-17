"""Small synthetic tests, plus audit of saved comparison artifacts when present."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import json
import warnings
import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

from phishguard_vn.student import sha256,metrics
from phishguard_vn.student_comparison import E2Student,export_e2,weighted_copies,load_comparison_student

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("compare_students",ROOT/"scripts/compare_students.py")
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)
PLAN=json.loads((ROOT/"configs/week7_student_comparison.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("family",["e2_lr","e2_mlp","e2_hist","e2_extra"])
def test_json_scores_match_sklearn_for_soft_targets(family):
    rng=np.random.default_rng(42)
    X=rng.normal(size=(80,20))
    q=np.where(X[:,0]>0,.85,.1)
    params=deepcopy(PLAN["families"][family])
    if family=="e2_mlp":params["epochs"]=5
    if family=="e2_hist":params["max_iter"]=3
    if family=="e2_extra":params["n_estimators"]=3
    scaler=StandardScaler().fit(X) if family in ("e2_lr","e2_mlp") else None
    Z=scaler.transform(X) if scaler is not None else X
    model=run.make_model(family,params,42)
    duplicate,y,w=weighted_copies(Z,q)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(duplicate,y,sample_weight=w)
    portable=E2Student(export_e2(model,scaler,family,.5))
    unseen=rng.normal(size=(30,20))
    expected=model.predict_proba(scaler.transform(unseen) if scaler is not None else unseen)[:,1]
    np.testing.assert_allclose(portable.score_features(unseen),expected,rtol=0,atol=1e-12)
    np.testing.assert_allclose(portable.score_features(X[:1]),
                              portable.score_features(X)[:1],rtol=0,atol=1e-12)


def test_soft_target_copies_keep_total_weight():
    X=np.ones((4,20));q=np.array([0.,.1,.9,1.])
    duplicated,y,w=weighted_copies(X,q)
    assert duplicated.shape==(8,20)
    np.testing.assert_array_equal(w[:4]+w[4:],np.ones(4))
    assert np.sum(w*y)==pytest.approx(q.sum())
    for invalid in ([np.nan]*4,[1.1]*4,[0]*3):
        with pytest.raises(ValueError):weighted_copies(X,invalid)


def test_bootstrap_is_paired_and_reproducible():
    y=np.tile([0,1],20)
    groups=np.repeat(np.arange(20),2)
    scores=np.tile(np.linspace(.1,.9,40)[:,None],(1,3))
    result=run.paired_bootstrap(y,groups,scores,scores,20,42)
    assert result["delta_mean_AP"]==result["ci_low"]==result["ci_high"]==0
    assert result==run.paired_bootstrap(y,groups,scores,scores,20,42)


def test_e2_order_and_scaler_corruption_rejected():
    X=np.random.default_rng(42).normal(size=(40,20))
    scaler=StandardScaler().fit(X)
    model=run.make_model("e2_lr",PLAN["families"]["e2_lr"],42).fit(scaler.transform(X),np.tile([0,1],20))
    bundle=export_e2(model,scaler,"e2_lr",.5)
    for k,v in (("feature_order",list(reversed(bundle["feature_order"]))),
                ("scale",[0]*20),("threshold",float("nan"))):
        changed=deepcopy(bundle);changed[k]=v
        with pytest.raises(ValueError):E2Student(changed)


def test_saved_research_outputs():
    import pandas as pd
    manifest_path=ROOT/"artifacts/student_comparison/manifest.json"
    if not manifest_path.exists():
        pytest.skip("Run compare_students.py to produce research artifacts")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["official_test_evaluated"] is False
    assert manifest["teacher_retrained"] is False
    assert manifest["android_verified"] is False
    assert manifest["export_seed"]==42
    for relative,digest in manifest["output_sha256"].items():
        assert sha256(ROOT/relative)==digest
    runs=pd.read_csv(ROOT/"reports/tables/student_comparison/runs.csv")
    predictions=pd.read_csv(ROOT/"reports/tables/student_comparison/validation_predictions.csv.gz",float_precision="round_trip")
    assert len(runs)==5*2*3*2
    for candidate in manifest["models"]:
        saved=predictions.loc[predictions.candidate.eq(candidate)]
        for seed in PLAN["seeds"]:
            batch=saved.loc[saved.seed.eq(seed)]
            assert len(batch)==1585 and batch.id.is_unique
            record=runs.loc[(runs.candidate==candidate)&(runs.seed==seed)&
                            (runs.operating_point=="validation_fpr_budget")].iloc[0]
            actual=metrics(batch.y_true,batch.score,record.threshold)
            for key in ("ap","f1","fpr","recall","tp","fp","tn","fn"):
                assert actual[key]==pytest.approx(record[key],abs=1e-12)
        assert manifest["parity"][candidate]["labels_equal"] is True
        assert manifest["parity"][candidate]["max_abs_diff"]<1e-12
    # Runtime load checks source, feature assets and model hashes.
    student=load_comparison_student(ROOT)
    assert student.predict_one("example.com")["android_verified"] is False
