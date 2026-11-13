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
    urls=["example.com","https://B?CHER.de:8443/Case?Q=A","xn--bcher-kva.de","https://example.com/A?a=b"]
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
    value={"versions":{"scikit-learn":version("scikit-learn")},"teacher_finalized":True,"model_sha256":sha(model)}
    metadata.write_text(json.dumps(value))
    lock=dict(teacher_finalized=True,selected_by="core_train_group_cv",external_used_for_selection=False,
        feature_set="url_raw_char_3_5",threshold=0,decision_rule="estimator.predict",
        bundle={"path":"models/m.joblib","sha256":sha(model)},
        selection_record={"path":"metadata.json","sha256":sha(metadata)})
    assert load_teacher(tmp_path,lock).predict_one("example.com")["score_kind"]=="decision_function"
    value["versions"]["scikit-learn"]="0.invalid";metadata.write_text(json.dumps(value))
    lock["selection_record"]["sha256"]=sha(metadata)
    with pytest.raises(RuntimeError,match="scikit-learn"):load_teacher(tmp_path,lock)
    lock["bundle"]["sha256"]="bad"
    with pytest.raises(ValueError,match="bundle"):load_teacher(tmp_path,lock)
