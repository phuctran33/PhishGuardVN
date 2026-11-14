"""Research pipeline fixtures; never train project data or download models in unit tests."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
import pytest
pytest.importorskip("tokenizers",reason="Install .[research] for research fixtures")
torch=pytest.importorskip("torch",reason="Install .[research] for neural fixtures")
from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.research_preprocessing import (normalize_url,regex_tokens,LearnedSubwords,
    make_linear,feature_counts,frame_from_urls)
from phishguard_vn.research_neural import NeuralURLClassifier

PLAN=json.loads((Path(__file__).resolve().parents[1]/"configs/url_research_plan.json").read_text())
LINEAR=[s for s in PLAN["experiments"] if s["group"]!="neural"]

def fixture_frame(n=120):
    y=np.arange(n)%2
    rng=np.random.default_rng(42)
    X=pd.DataFrame(rng.normal(size=(n,20))+y[:,None],columns=E2_FEATURES)
    X["url"]=[f"https://g{i//2}.example/"+("verify-login" if t else "about-home") for i,t in enumerate(y)]
    return X,y

def test_normalization_rules_and_loss_are_explicit():
    value="http://ExAmPle.COM:80/Case%2FPath?Q=UP#part"
    assert normalize_url(value,"raw")==value
    assert normalize_url(value,"canonical")=="example.com/Case%2FPath?Q=UP"
    assert normalize_url(value,"canonical_lower")=="example.com/case%2fpath?q=up"
    assert normalize_url(value,"host_only")=="example.com"
    assert normalize_url("https://u:p@EXAMPLE.com:444/Path","canonical")=="example.com:444/Path"
    assert normalize_url("http://example.com:bad/x","canonical")=="http://example.com:bad/x"

def test_regex_keeps_components_and_delimiters():
    tokens=regex_tokens("https://login.example.com/verify?id=123&next=home")
    assert {"scheme:https","host:login","host:.","path:/","path:verify","query:=","query:&","query:id"}<=set(tokens)

@pytest.mark.parametrize("kind",["bpe","wordpiece","unigram"])
def test_subword_training_does_not_see_transform_inputs(kind):
    texts=["https://train.example/login","https://train.example/about"]*5
    transformer=LearnedSubwords(kind).fit(texts)
    before=transformer.tokenizer_.get_vocab()
    encoded=transformer.transform(["https://unseen-Ω.example/new"])
    assert encoded[0] and transformer.training_rows_==10
    assert transformer.tokenizer_.get_vocab()==before

@pytest.mark.parametrize("spec",LINEAR,ids=[s["id"] for s in LINEAR])
def test_linear_pipeline_fit_reload_and_feature_counts(spec,tmp_path):
    X,y=fixture_frame()
    model=make_linear(spec).fit(X,y)
    score=model.predict_proba(X.iloc[:4])[:,1]
    assert score.shape==(4,) and np.isfinite(score).all()
    path=tmp_path/"pipeline.joblib";joblib.dump(model,path)
    np.testing.assert_allclose(joblib.load(path).predict_proba(X.iloc[:4])[:,1],score,rtol=0,atol=1e-12)
    counts=feature_counts(model,X)
    assert 0<counts["features_after"]<=counts["features_before"]
    if spec["representation"]=="l1":
        assert counts["features_after"]<counts["features_before"]

@pytest.mark.parametrize("kind",["char_cnn","fasttext_style","ft_transformer","pretrained_url_transformer"])
def test_neural_training_encoding_and_reload(kind,tmp_path):
    X,y=fixture_frame(24)
    checkpoint=""
    if kind=="pretrained_url_transformer":
        # Small random fixture checks model plumbing, NOT a research pretrained result.
        from transformers import BertConfig,BertModel
        checkpoint=str(tmp_path/"bert")
        Path(checkpoint).mkdir()
        Path(checkpoint,"vocab.txt").write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nhttps\nexample\nlogin\n",encoding="utf-8")
        BertModel(BertConfig(vocab_size=8,hidden_size=16,num_hidden_layers=1,
                            num_attention_heads=2,intermediate_size=32)).save_pretrained(checkpoint)
    model=NeuralURLClassifier(kind,epochs=1,checkpoint=checkpoint).fit(X,y)
    assert model.training_rows_==24 and model.n_iter_==1 and np.isfinite(model.loss_history_).all()
    before=model.predict_proba(X.iloc[:3])
    assert before.shape==(3,2) and np.isfinite(before).all()
    if kind=="ft_transformer":
        np.testing.assert_allclose(model.scaler_.mean_,X[list(E2_FEATURES)].mean())
    if kind in {"char_cnn","fasttext_style"}:
        vocab=model.vocabulary_.copy()
        extra=X.iloc[:1].copy();extra["url"]="https://Ω-UNSEEN.invalid"
        model.predict_proba(extra)
        assert model.vocabulary_==vocab
    path=tmp_path/"model.joblib";joblib.dump(model,path)
    np.testing.assert_allclose(joblib.load(path).predict_proba(X.iloc[:3]),before,rtol=0,atol=1e-7)


def test_nested_selection_fits_only_the_supplied_fitting_groups(tmp_path,monkeypatch):
    import importlib.util
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location("research_runner_fixture",root/"scripts/run_url_research.py")
    run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
    X,y=fixture_frame(36)
    data=X.assign(id=[f"id-{i}" for i in range(len(X))],target=y,
                  registrable_domain=[f"g{i//2}.example" for i in range(len(X))])
    fitting=data.iloc[:24].copy()
    seen=[]
    original=run.make_model
    def tracked_builder(spec,params,checkpoint):
        model=original(spec,params,checkpoint)
        fit=model.fit
        def tracked_fit(features,labels):
            assert list(features.columns)==["url",*E2_FEATURES]
            assert set(features.url)<=set(fitting.url)
            seen.append(len(features))
            return fit(features,labels)
        model.fit=tracked_fit
        return model
    monkeypatch.setattr(run,"OUT",tmp_path)
    monkeypatch.setattr(run,"make_model",tracked_builder)
    ledger=[]
    run.select_fit({"id":"fixture","group":"F","representation":"char","grid":{"C":[.5,2]}},
                   fitting,"0",tmp_path,ledger)
    assert sorted(seen)==[12,12,12,12,24]
    assert len(ledger)==5 and all(r["status"]=="success" for r in ledger)
