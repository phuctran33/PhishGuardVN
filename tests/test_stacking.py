"""Real small fixtures: no project dataset, no target-website calls."""
import importlib.util
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin
from phishguard_vn.stacking import (
    canonical_url, CanonicalText, make_base, make_meta, FittedStack,
    choose_threshold, raw_frame, validate_urls, score_model,
)
from phishguard_vn.brand_features import E2_FEATURES


@pytest.mark.parametrize("raw,expected", [
    ("https://EXAMPLE.com:443/A%2Fb?Q=Z#frag", "example.com/A%2Fb?Q=Z"),
    ("http://user:pass@EXAMPLE.com:80/A?Q=a#login", "example.com/A?Q=a"),
    ("https://EXAMPLE.com:8443/Case", "example.com:8443/Case"),
    ("https://B\u00dcCHER.de/A", "xn--bcher-kva.de/A"),
    ("//EXAMPLE.com/A", "example.com/A"),
    ("example.com/A?Q=%2F", "example.com/A?Q=%2F"),
    ("http://[::1]:80/A", "[::1]/A"),
])
def test_canonical_contract(raw, expected):
    assert canonical_url(raw) == expected


@pytest.mark.parametrize("value", [None, 42, {}, ["nested"]])
def test_wrong_type(value):
    with pytest.raises(TypeError):
        validate_urls([value])


@pytest.mark.parametrize("value", ["", " ", "\x00", "bad host", "https://example.com:invalid",
    "https://[bad", " example.com", "example.com\n"])
def test_invalid_url(value):
    with pytest.raises(ValueError):
        raw_frame([value])


def test_raw_numeric_not_canonical_numeric():
    frame = raw_frame(["https://EXAMPLE.com/A", "example.com/A"])
    assert list(frame) == ["url", *E2_FEATURES]
    assert frame.url.tolist() == ["https://EXAMPLE.com/A", "example.com/A"]
    assert CanonicalText().transform(frame.url) == ["example.com/A", "example.com/A"]


def fixture_frame():
    urls = [f"safe{i}.example/about" for i in range(8)] + [f"fake{i}.example/login" for i in range(8)]
    frame = pd.DataFrame({"url": urls})
    for j, name in enumerate(E2_FEATURES):
        frame[name] = np.arange(16) + j
    return frame, np.r_[np.zeros(8, int), np.ones(8, int)]


def test_vocabulary_and_scaler_fitting_only():
    frame, y = fixture_frame()
    model = make_base("hybrid_svm").fit(frame, y)
    features = model.named_steps["features"]
    vectorizer = features.named_transformers_["text"].named_steps["tfidf"]
    before = dict(vectorizer.vocabulary_)
    mean = features.named_transformers_["e2"].mean_.copy()
    held = frame.iloc[:1].copy()
    held["url"] = "unseenzzzz.example/NEW"
    held.loc[:, list(E2_FEATURES)] = 999999
    model.predict(held)
    assert vectorizer.vocabulary_ == before
    assert "zzz" not in vectorizer.vocabulary_
    np.testing.assert_array_equal(mean, features.named_transformers_["e2"].mean_)
    np.testing.assert_allclose(mean, frame[list(E2_FEATURES)].mean())


@pytest.mark.parametrize("target", [.01, .02, .25])
def test_threshold_ties_and_constraint(target):
    y = np.array([1, 0, 1, 0, 0, 0])
    score = np.array([.9, .9, .8, .7, .6, .5])
    t = choose_threshold(y, score, target)
    pred = score >= t
    assert pred[y == 0].mean() <= target
    possible = np.r_[np.nextafter(score.max(), np.inf), np.unique(score)]
    achievable = [(score >= v)[y == 1].mean() for v in possible if (score >= v)[y == 0].mean() <= target]
    assert pred[y == 1].mean() == max(achievable)
    if target < .25:
        assert not pred.any()  # positive and negative at .9 cannot be split


def test_native_and_threshold_ties_differ():
    frame, y = fixture_frame()
    base = make_base("svm").fit(frame, y)
    meta = make_meta(1, True).fit(np.column_stack([y, y]), y)
    meta.named_steps["lr"].coef_[:] = 0
    meta.named_steps["lr"].intercept_[:] = 0
    stack = FittedStack(["svm"], {"svm": base}, make_meta(1, True).fit(y.reshape(-1, 1), y))
    stack.meta.named_steps["lr"].coef_[:] = 0
    stack.meta.named_steps["lr"].intercept_[:] = 0
    assert not stack.predict(frame).any()  # native LR at .5 uses its own tie
    assert (score_model(stack, frame) >= .5).all()


def runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts/run_stacking.py"
    spec = importlib.util.spec_from_file_location("stacking_fixture_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingModel(ClassifierMixin, BaseEstimator):
    seen = []

    def fit(self, X, y):
        self.training_urls_ = set(X.url)
        self.classes_ = np.array([0, 1])
        self.seen.append(self.training_urls_)
        return self

    def predict_proba(self, X):
        # Crossfit outputs must NEVER be generated on rows in this base's fit set.
        overlap = set(X.url) & self.training_urls_
        assert not overlap, overlap
        p = np.array([.7 if "fake" in u else .3 for u in X.url])
        return np.column_stack([1 - p, p])


def test_meta_group_crossfit_and_threshold_subsetting(tmp_path, monkeypatch):
    run = runner_module()
    frame, y = fixture_frame()
    frame["id"], frame["target"] = np.arange(len(frame)), y
    # Two URLs per group, including both labels, makes group leakage detectable.
    frame["registrable_domain"] = [f"group{i % 4}" for i in range(len(frame))]
    run.OUT, run.LOCAL = tmp_path / "out", tmp_path / "local"
    run.OUT.mkdir(); run.LOCAL.mkdir()
    run.LEDGER, run.PARTITIONS, run.BASE_CACHE = [], [], {}
    RecordingModel.seen = []
    monkeypatch.setattr(run, "make_base", lambda *a, **k: RecordingModel())
    value = run.base_data(frame.iloc[:12], "outer0/inner0")
    assert np.isfinite(value["oof"]).all()
    assert all(len(s) <= 12 for s in RecordingModel.seen)
    assert value["ids"] == frame.iloc[:12].id.tolist()
    partitions = pd.read_csv(run.OUT / "partitions.csv.gz")
    assert partitions.groupby("registrable_domain").held_fold.nunique().eq(1).all()
    assert not set(partitions.id) & set(frame.iloc[12:].id)
    # Actual estimator receives already-subset rows/groups in threshold crossfit too.
    small = dict(id="fixture", kind="stack", members=["svm", "hist"], grid={})
    score = run.fitting_oof(small, dict(C=1, scale=True), frame, "outer0")
    assert score.shape == (len(frame),) and np.isfinite(score).all()
    for rows in run.PARTITIONS:
        assert rows.groupby("registrable_domain").held_fold.nunique().eq(1).all()


def test_registered_grid_is_finite():
    from sklearn.model_selection import ParameterGrid
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "configs/teacher_v2_plan.json").read_text(encoding="utf-8"))
    assert len(plan["experiments"]) == 11
    assert sum(len(ParameterGrid(s["grid"])) for s in plan["experiments"]) == 53
