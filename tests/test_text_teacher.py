"""Text Teacher fixtures: no dataset, E2 reference, research artifacts or target-URL access."""
from pathlib import Path
import json,subprocess,sys
import joblib,numpy as np,pytest
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.feature_extraction.text import TfidfVectorizer
from phishguard_vn.teacher import Teacher,load_teacher,sha,feature_fingerprint,MODEL_VERSION,PREPROCESSING_VERSION

@pytest.fixture
def bundle():
    urls=["example.com/about","bank.example/home","safe.example/news","shop.example/info",
          "fake-login.example/verify","bank-confirm.evil/password","signin-fake.example/account","verify-fake.example/login"]*3
    pipeline=Pipeline([("tfidf",TfidfVectorizer(analyzer="char",ngram_range=(3,5),min_df=2,
       max_features=50000,lowercase=False,sublinear_tf=True)),("model",LinearSVC(C=.5,random_state=42,max_iter=10000))]).fit(urls,[0,0,0,0,1,1,1,1]*3)
    return dict(pipeline=pipeline,model_version=MODEL_VERSION,preprocessing_version=PREPROCESSING_VERSION,
                feature_fingerprint=feature_fingerprint(pipeline))

def test_raw_single_batch_reload_and_boundary(bundle,tmp_path,monkeypatch):
    teacher=Teacher(bundle)
    urls=["example.com","https://BÜCHER.de:8443/Case?Q=A","xn--bcher-kva.de","https://example.com/A?a=b"]
    before=teacher.predict_batch(urls)
    assert before==[teacher.predict_one(u) for u in urls]
    np.testing.assert_array_equal([r["class_id"] for r in before],bundle["pipeline"].predict(urls))
    np.testing.assert_allclose([r["margin"] for r in before],bundle["pipeline"].decision_function(urls),rtol=0,atol=1e-12)
    # A true zero margin must use estimator.predict's tie convention, not an invented >= rule.
    bundle["pipeline"].named_steps["model"].coef_[:]=0
    bundle["pipeline"].named_steps["model"].intercept_[:]=0
    assert teacher.predict_one(urls[0])["class_id"]==int(bundle["pipeline"].predict(urls[:1])[0])
    path=tmp_path/"bundle.joblib";joblib.dump(bundle,path)
    assert Teacher(joblib.load(path)).predict_batch(urls)==teacher.predict_batch(urls)

@pytest.mark.parametrize("value",[None,123,{},["nested"]])
def test_wrong_input_type(bundle,value):
    with pytest.raises(TypeError):Teacher(bundle).predict_one(value)

@pytest.mark.parametrize("value",["","   ","\x00"])
def test_blank_input(bundle,value):
    with pytest.raises(ValueError):Teacher(bundle).predict_one(value)

def test_no_normalization_or_fit(bundle,monkeypatch):
    pipeline=bundle["pipeline"]
    monkeypatch.setattr(pipeline,"fit",lambda *a,**k:pytest.fail("Inference must never fit"))
    text=" https://EXAMPLE.com/Case?Q=A "
    seen=[]
    original=pipeline.decision_function
    def track(values):
        seen.extend(values);return original(values)
    monkeypatch.setattr(pipeline,"decision_function",track)
    Teacher(bundle).predict_one(text)
    assert seen and all(s==text for s in seen)

def test_mismatched_model_rejected(bundle):
    bundle["pipeline"].named_steps["model"].C=2
    with pytest.raises(ValueError,match="config"):Teacher(bundle)

def test_lock_hash_and_dependency_errors(bundle,tmp_path):
    from importlib.metadata import version
    (tmp_path/"models").mkdir()
    model=tmp_path/"models/m.joblib";joblib.dump(bundle,model)
    metadata=tmp_path/"metadata.json"
    value={"versions":{"scikit-learn":version("scikit-learn")},"teacher_finalized":True,"model_sha256":sha(model),"primary_metric":"mean_outer_average_precision","test_evaluated":False,"selected_by":"core_train_group_cv","external_used_for_selection":False,"score_kind":"decision_function","operating_point_scope":"fixed_core_protocol","decision_rule":"estimator.predict","threshold":0}
    metadata.write_text(json.dumps(value))
    lock=dict(teacher_finalized=True,selected_by="core_train_group_cv",external_used_for_selection=False,
        feature_set="url_raw_char_3_5",threshold=0,decision_rule="estimator.predict",score_kind="decision_function",operating_point_scope="fixed_core_protocol",
        bundle={"path":"models/m.joblib","sha256":sha(model)},
        selection_record={"path":"metadata.json","sha256":sha(metadata)})
    assert load_teacher(tmp_path,lock).predict_one("example.com")["score_kind"]=="decision_function"
    value["versions"]["scikit-learn"]="0.invalid";metadata.write_text(json.dumps(value))
    lock["selection_record"]["sha256"]=sha(metadata)
    with pytest.raises(RuntimeError,match="scikit-learn"):load_teacher(tmp_path,lock)
    lock["bundle"]["sha256"]="bad"
    with pytest.raises(ValueError,match="bundle"):load_teacher(tmp_path,lock)

@pytest.mark.parametrize("location,field,value",[
    ("lock","score_kind","probability"),("lock","operating_point_scope","external_tuned"),
    ("metadata","primary_metric","accuracy"),("metadata","test_evaluated",True),
    ("metadata","score_kind","probability"),("metadata","operating_point_scope","external_tuned"),
    ("metadata","selected_by","external"),("metadata","external_used_for_selection",True)])
def test_protocol_mismatch_rejected_even_with_valid_hashes(bundle,tmp_path,location,field,value):
    from importlib.metadata import version
    model=tmp_path/"m.joblib";joblib.dump(bundle,model)
    metadata=tmp_path/"meta.json"
    data=dict(versions={"scikit-learn":version("scikit-learn")},teacher_finalized=True,
      model_sha256=sha(model),primary_metric="mean_outer_average_precision",test_evaluated=False,
      selected_by="core_train_group_cv",external_used_for_selection=False,score_kind="decision_function",
      operating_point_scope="fixed_core_protocol",decision_rule="estimator.predict",threshold=0)
    lock=dict(teacher_finalized=True,selected_by="core_train_group_cv",external_used_for_selection=False,
      feature_set="url_raw_char_3_5",threshold=0,decision_rule="estimator.predict",
      score_kind="decision_function",operating_point_scope="fixed_core_protocol",
      bundle={"path":"m.joblib","sha256":sha(model)},selection_record={"path":"meta.json"})
    if location=="metadata":data[field]=value
    else:lock[field]=value
    metadata.write_text(json.dumps(data));lock["selection_record"]["sha256"]=sha(metadata)
    with pytest.raises(ValueError,match="protocol"):
        load_teacher(tmp_path,lock)

def test_external_lineage_allows_only_recorded_code_not_changed_data(tmp_path):
    from phishguard_vn.external_provenance import validate_audit_manifest
    import hashlib
    def h(b):return hashlib.sha256(b).hexdigest()
    source=tmp_path/"src/phishguard_vn/external_pilot.py";source.parent.mkdir(parents=True)
    source.write_bytes(b"new adapter")
    data=tmp_path/"ledger.csv";data.write_bytes(b"frozen labels")
    manifest={"inputs_sha256":{"src/phishguard_vn/external_pilot.py":h(b"old adapter"),"ledger.csv":h(b"frozen labels")},"outputs_sha256":{}}
    with pytest.raises(ValueError,match="Stale"):validate_audit_manifest(tmp_path,manifest)
    path=tmp_path/"reports/tables/teacher_release/external_adapter_lineage.json";path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"path":"src/phishguard_vn/external_pilot.py","historical_sha256":h(b"old adapter"),
      "current_sha256":h(b"new adapter"),"change":"text_teacher_dispatch_only"}))
    validate_audit_manifest(tmp_path,manifest)
    data.write_bytes(b"changed labels")
    with pytest.raises(ValueError,match="ledger.csv"):validate_audit_manifest(tmp_path,manifest)
    data.write_bytes(b"frozen labels");source.write_bytes(b"unreviewed change")
    with pytest.raises(ValueError,match="external_pilot.py"):validate_audit_manifest(tmp_path,manifest)
