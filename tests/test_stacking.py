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


@pytest.fixture
def candidate_bundle():
    from importlib.metadata import version
    from phishguard_vn.brand_features import load_reference
    from phishguard_vn.stacking import source_hashes, reference_fingerprint, PREPROCESSING_VERSION
    from phishguard_vn.stacking_candidate import MODEL_VERSION
    frame, y = fixture_frame()
    bases = {"svm": make_base("svm").fit(frame, y),
             "hist": make_base("hist").set_params(model__early_stopping=False).fit(frame, y)}
    meta = make_meta(.1, True).fit(np.column_stack([y, y]), y)
    reference = load_reference()
    return dict(model=FittedStack(["svm", "hist"], bases, meta), reference=reference,
        model_version=MODEL_VERSION, candidate_only=True, promoted=False,
        preprocessing_version=PREPROCESSING_VERSION, selected_by="core_train_group_cv",
        primary_metric="mean_outer_average_precision", validation_used_for_selection=False,
        external_used_for_selection=False, official_test_evaluated=False,
        decision_rule="score >= threshold", operating_point_scope="full_train_group_oof_fpr_target_0.01",
        score_kind="probability", calibrated=False, feature_names=list(E2_FEATURES),
        class_mapping={"benign": 0, "phishing": 1}, threshold=.5,
        source_sha256=source_hashes(), reference_sha256=reference.sha256,
        reference_fingerprint=reference_fingerprint(reference),
        runtime_versions={p: version(p) for p in ["scikit-learn", "tldextract", "idna"]})


def save_candidate(root, bundle):
    import joblib
    from phishguard_vn.stacking_candidate import sha
    (root / "models").mkdir(exist_ok=True)
    (root / "configs").mkdir(exist_ok=True)
    path = root / "models/teacher_v2_candidate.joblib"
    joblib.dump(bundle, path)
    lock = {k: v for k, v in bundle.items() if k not in {"model", "reference"}}
    lock["bundle"] = {"path": "models/teacher_v2_candidate.joblib", "sha256": sha(path)}
    (root / "configs/teacher_v2_candidate_lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return lock


def test_candidate_single_batch_reload_boundary(candidate_bundle, tmp_path):
    import joblib
    from phishguard_vn.stacking_candidate import StackingCandidate, load_candidate
    save_candidate(tmp_path, candidate_bundle)
    loaded = load_candidate(tmp_path)
    urls = ["example.com", "https://EXAMPLE.com/A?Q=%2F"]
    assert loaded.predict_batch(urls) == [loaded.predict_one(u) for u in urls]
    # Explicit threshold rule, unlike the native LR rule, includes an equal score.
    candidate_bundle["model"].meta.named_steps["lr"].coef_[:] = 0
    candidate_bundle["model"].meta.named_steps["lr"].intercept_[:] = 0
    assert StackingCandidate(candidate_bundle).predict_one(urls[0])["class_id"] == 1


@pytest.mark.parametrize("field,value", [
    ("promoted", True), ("candidate_only", False), ("score_kind", "decision_function"),
    ("calibrated", True), ("primary_metric", "accuracy"), ("external_used_for_selection", True),
    ("validation_used_for_selection", True), ("official_test_evaluated", True),
    ("operating_point_scope", "external_tuned"), ("threshold", float("nan")),
    ("feature_names", list(reversed(E2_FEATURES))), ("source_sha256", {}),
])
def test_candidate_protocol_negative(candidate_bundle, tmp_path, field, value):
    from phishguard_vn.stacking_candidate import load_candidate
    candidate_bundle[field] = value
    save_candidate(tmp_path, candidate_bundle)
    with pytest.raises(ValueError):
        load_candidate(tmp_path)


def test_candidate_missing_reference_and_hash(candidate_bundle, tmp_path):
    from phishguard_vn.stacking_candidate import load_candidate
    candidate_bundle["reference"] = None
    save_candidate(tmp_path, candidate_bundle)
    with pytest.raises(ValueError, match="reference"):
        load_candidate(tmp_path)
    (tmp_path / "models/teacher_v2_candidate.joblib").write_bytes(b"changed")
    with pytest.raises(ValueError, match="bundle"):
        load_candidate(tmp_path)


def test_candidate_missing_dependency(candidate_bundle, tmp_path, monkeypatch):
    from importlib.metadata import PackageNotFoundError
    import phishguard_vn.stacking_candidate as adapter
    save_candidate(tmp_path, candidate_bundle)
    def missing(package):
        raise PackageNotFoundError(package)
    monkeypatch.setattr(adapter, "version", missing)
    with pytest.raises(RuntimeError, match="Missing"):
        adapter.load_candidate(tmp_path)


def test_portable_no_dataset_reports_or_reference_file(candidate_bundle, tmp_path):
    import shutil, subprocess, sys
    save_candidate(tmp_path, candidate_bundle)
    source = Path(__file__).resolve().parents[1] / "src/phishguard_vn"
    target = tmp_path / "src/phishguard_vn"
    target.mkdir(parents=True)
    for name in ["__init__.py", "stacking.py", "stacking_candidate.py", "url_parser.py",
                 "features.py", "brand_features.py"]:
        shutil.copyfile(source / name, target / name)
    code = ("import sys; sys.path.insert(0, 'src'); "
            "from phishguard_vn.stacking_candidate import load_candidate; "
            "c=load_candidate('.'); print(len(c.predict_batch(['example.com','https://EXAMPLE.com/A'])))")
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2"
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "reports").exists()
    assert not (target / "resources").exists()


@pytest.mark.parametrize("name", ["svm", "hist", "extra", "lgbm", "hybrid_lr", "hybrid_svm"])
def test_actual_base_estimators(name):
    frame, y = fixture_frame()
    model = make_base(name).fit(frame, y)
    assert score_model(model, frame).shape == (len(frame),)
    assert model.predict(frame).shape == (len(frame),)


def test_stress_keeps_path_query_userinfo_fragment():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("stacking_summary_fixture", root / "scripts/summarize_stacking.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    url = "https://user:pass@Example.com:8443/Case%2F?Q=Ab#Frag"
    assert module.transform_url(url, "uppercase_hostname") == "https://user:pass@EXAMPLE.COM:8443/Case%2F?Q=Ab#Frag"
    assert module.transform_url(url, "remove_scheme") == "user:pass@Example.com:8443/Case%2F?Q=Ab#Frag"
    assert module.transform_url("example.com/Case?Q=Ab", "add_https") == "https://example.com/Case?Q=Ab"


def test_candidate_hist_uses_explicit_fixed_budget():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("candidate_pack_fixture", root / "scripts/package_stacking_candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hist = module.candidate_base("hist").named_steps["model"]
    assert hist.early_stopping is False and hist.max_iter == 300


def test_domain_bootstrap_matches_weighted_sklearn_ap(tmp_path):
    from sklearn.metrics import average_precision_score
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bootstrap_fixture", root / "scripts/summarize_stacking.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = tmp_path
    train = pd.DataFrame([
        dict(id=fold * 8 + group * 2 + y, fold_id=fold, target=y,
             registrable_domain=f"f{fold}g{group}")
        for fold in range(3) for group in range(4) for y in [0, 1]])
    names = ["raw_svm", "canonical_svm", "stack_hist"]
    scores = {
        "raw_svm": np.tile([.1, .9, .6, .6, .2, .8, .7, .3], 3),
        "canonical_svm": np.tile([.2, .8, .3, .7, .4, .6, .6, .6], 3),
        "stack_hist": np.tile([.1, .8, .4, .9, .6, .6, .2, .7], 3)}
    oof = pd.concat([train.assign(experiment=name, score=scores[name], y_true=train.target) for name in names])
    draws = 30
    module.bootstrap(train, oof, names, draws)
    rng = np.random.default_rng(42)
    expected = np.zeros((draws, 3))
    for fold in range(3):
        g = train.loc[train.fold_id.eq(fold)]
        codes, unique = pd.factorize(g.registrable_domain)
        for draw in range(draws):
            counts = np.bincount(rng.integers(0, len(unique), len(unique)), minlength=len(unique))
            for j, name in enumerate(names):
                expected[draw, j] += average_precision_score(g.target, scores[name][g.index],
                    sample_weight=counts[codes]) / 3
    saved = pd.read_csv(tmp_path / "paired_bootstrap.csv")
    for base in names:
        for j, name in enumerate(names):
            row = saved.loc[saved.baseline.eq(base) & saved.experiment.eq(name)].iloc[0]
            delta = expected[:, j] - expected[:, names.index(base)]
            np.testing.assert_allclose([row.ci_low, row.ci_high], np.quantile(delta, [.025, .975]), atol=1e-12)


def test_cli_example_urls_pass_official_parser():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("candidate_cli_fixture", root / "scripts/predict_stacking_candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.EXAMPLES) >= 5
    validate_urls(module.EXAMPLES)
