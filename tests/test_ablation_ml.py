"""Exercise actual ablation notebook cells: paired rows, nested fitting, score semantics."""
from pathlib import Path
import hashlib
import shutil

import joblib
import nbformat
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler

from phishguard_vn.brand_features import (E2_FEATURES, REFERENCE_PATH, FEATURE_SCHEMA_VERSION,
                                         extract_e2_features, load_reference)
from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.prediction import predict_url

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = nbformat.read(ROOT / "notebooks/05_e2_ablation.ipynb", as_version=4)
CODE = {c.metadata["tags"][0]: c.source for c in NOTEBOOK.cells if c.cell_type == "code"}


@pytest.fixture
def ablation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("# fixture", encoding="utf-8")
    data = tmp_path / "data/interim"
    data.mkdir(parents=True)
    package = tmp_path / "src/phishguard_vn"
    package.mkdir(parents=True)
    for name in ["features.py", "url_parser.py", "brand_features.py"]:
        shutil.copyfile(ROOT / "src/phishguard_vn" / name, package / name)
    core, features, domains, folds = [], [], [], []
    for group in range(14):
        split = "train" if group < 12 else "val" if group == 12 else "test"
        for target in [0, 1]:
            rid = f"{split}-{group:02d}-{target}"
            url = f"https://group-{group}.com/" + ("login/vietcombank" if target else "")
            values = extract_e2_features(url)
            # Unique first column identifies training rows in the scaler spy.
            values["url_len"] = 10 + group * 2 + target if split == "train" else 1000 + group * 2 + target
            features.append({"id": rid, **values})
            core.append(dict(id=rid, url=url, label="phishing" if target else "benign",
                             source="fixture", tier="gold", split=split))
            domains.append(dict(id=rid, registrable_domain=f"group-{group}.com"))
            if split == "train":
                folds.append(dict(id=rid, fold_id=group % 3))
    core = pd.DataFrame(core)
    features = pd.DataFrame(features)[["id", *E2_FEATURES]]
    core.to_csv(data / "core_gold_silver.csv", index=False)
    features[["id", *CANDIDATE_FEATURES]].to_csv(data / "03_matrix_X_features.csv", index=False)
    e2 = features.loc[features.id.isin(core.loc[core.split.ne("test"), "id"])]
    e2.to_csv(data / "05_matrix_X_brand_trainval.csv", index=False)
    pd.DataFrame(domains).to_csv(data / "03_registrable_domains.csv", index=False)
    pd.DataFrame(folds).to_csv(data / "02_group_folds_train.csv", index=False)
    import json
    manifest = dict(partition="trainval", test_excluded_from_this_artifact=True,
                    feature_schema_version=FEATURE_SCHEMA_VERSION, columns=["id", *E2_FEATURES],
                    brand_reference=load_reference().summary(), rows_x=len(e2),
                    e1_columns_verified_identical_to_e1_matrix=True, frozen=False)
    (data / "05_matrix_X_brand_trainval.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    scope = {}
    exec(CODE["setup"], scope)
    yield scope
    scope["CPU_LIMIT"].restore_original_limits()
    scope["plt"].close("all")


def run_small(scope):
    for stage in ["data", "models", "partitions", "metrics"]:
        exec(CODE[stage], scope)
    scope["models"] = {k: scope["models"][k] for k in ["logistic_regression", "svm_rbf"]}
    scope["param_grids"] = {"logistic_regression": {"model__C": [0.5, 1]}, "svm_rbf": {"model__C": [0.5, 1]}}
    for stage in ["cv", "comparison", "final_fit"]:
        scope["_stage"] = stage
        exec(CODE[stage], scope)
    return scope


def test_e1_e2_share_rows_and_nested_fitting(ablation, monkeypatch):
    scope = ablation
    active, fitted_rows = [], []
    original_search, original_scaler = GridSearchCV.fit, StandardScaler.fit
    def search_fit(self, X, y, **kwargs):
        allowed = scope["train"]
        if scope["_stage"] == "cv":
            allowed = allowed.loc[allowed.fold_id.ne(scope["fold_id"])]
        assert set(X.url_len) == set(allowed.url_len)
        groups = scope["train"].loc[X.index, "registrable_domain"]
        expected = [frozenset(X.iloc[a].url_len) for a, b in self.cv] + [frozenset(X.url_len)]
        for a, b in self.cv:
            assert set(groups.iloc[a]).isdisjoint(groups.iloc[b])
        actual = []
        active.append(actual)
        try:
            result = original_search(self, X, y, **kwargs)
            assert all(rows in expected for rows in actual)
            assert all(rows in actual for rows in expected)
            return result
        finally:
            active.pop()
    def scaler_fit(self, X, *args, **kwargs):
        rows = frozenset(X.url_len)
        assert max(rows) < 1000, "Validation/Test entered fit"
        fitted_rows.append(rows)
        if active:
            active[-1].append(rows)
        return original_scaler(self, X, *args, **kwargs)
    monkeypatch.setattr(GridSearchCV, "fit", search_fit)
    monkeypatch.setattr(StandardScaler, "fit", scaler_fit)
    run_small(scope)
    assert fitted_rows
    p = scope["cv_predictions"]
    assert p.groupby("candidate").size().eq(24).all()
    assert p.loc[p.model.eq("svm_rbf"), "score_kind"].eq("decision_function").all()
    assert p.loc[p.feature_set.eq("E1"), "id"].tolist() == p.loc[p.feature_set.eq("E2"), "id"].tolist()
    partitions = scope["training_partitions"]
    assert set(partitions.id) == set(scope["train"].id)
    assert not set(p.id) & set(scope["validation"].id)
    paired = scope["paired"]
    np.testing.assert_allclose(paired.delta_pr_auc, paired.pr_auc_e2 - paired.pr_auc_e1)


@pytest.mark.parametrize("problem", ["mismatched_id", "changed_lexical", "metadata_feature", "test_in_x", "test_in_folds"])
def test_invalid_pairing_stops_before_fit(ablation, problem):
    data = ablation["DATA"]
    path = data / ("02_group_folds_train.csv" if problem == "test_in_folds" else "05_matrix_X_brand_trainval.csv")
    frame = pd.read_csv(path)
    if problem == "changed_lexical":
        frame.loc[0, "url_len"] += 1
    elif problem == "metadata_feature":
        frame["source"] = "leak"
    else:
        frame.loc[0, "id"] = "test-13-0" if problem.startswith("test_") else "missing"
    frame.to_csv(path, index=False)
    with pytest.raises(AssertionError):
        exec(CODE["data"], ablation)


def test_answers_outside_fit_do_not_affect_oof_or_selection(ablation):
    scope = run_small(ablation)
    before = scope["cv_predictions"].copy()
    shortlist = scope["shortlist"].candidate.tolist()
    path = scope["DATA"] / "core_gold_silver.csv"
    core = pd.read_csv(path)
    mask = core.split.ne("train")
    core.loc[mask, "label"] = core.loc[mask, "label"].map({"benign": "phishing", "phishing": "benign"})
    core.to_csv(path, index=False)
    run_small(scope)
    pd.testing.assert_frame_equal(before, scope["cv_predictions"])
    assert shortlist == scope["shortlist"].candidate.tolist()
    # Flipping outer held-out labels must not change that fold's predictions/scores.
    held_ids = set(scope["train"].loc[scope["train"].fold_id.eq(0), "id"])
    core.loc[core.id.isin(held_ids), "label"] = core.loc[core.id.isin(held_ids), "label"].map(
        {"benign": "phishing", "phishing": "benign"})
    core.to_csv(path, index=False)
    run_small(scope)
    after = scope["cv_predictions"]
    columns = [c for c in before if c != "true_label"]
    pd.testing.assert_frame_equal(before.loc[before.fold_id.eq(0), columns].reset_index(drop=True),
                                  after.loc[after.fold_id.eq(0), columns].reset_index(drop=True))


def test_e2_reload_matches_extraction_and_reference_is_snapshot(ablation, tmp_path, monkeypatch):
    scope = run_small(ablation)
    bundle = scope["bundles"]["E2"]
    path = tmp_path / "model.joblib"
    joblib.dump(bundle, path)
    url = "https://vietcombank-login.example.com/xacminh"
    values = extract_e2_features(url)
    X = pd.DataFrame([[values[c] for c in E2_FEATURES]], columns=E2_FEATURES)
    for name, model in bundle["models"].items():
        result = predict_url(url, joblib.load(path), name)
        assert result["label"] == ("phishing" if model.predict(X)[0] else "benign")
        expected = model.decision_function(X)[0] if name == "svm_rbf" else model.predict_proba(X)[0, 1]
        assert result["score"] == pytest.approx(expected)
    # Inference uses the embedded reference; changing the default loader cannot silently alter features.
    import phishguard_vn.brand_features as brand
    monkeypatch.setattr(brand, "load_reference", lambda: (_ for _ in ()).throw(AssertionError("live reference used")))
    predict_url(url, bundle)
    with pytest.raises(ValueError, match="không hợp lệ"):
        predict_url("https://example.com:bad", bundle)
    bundle["extractor_source_sha256"]["brand_features.py"] = "wrong"
    with pytest.raises(ValueError, match="Extractor"):
        predict_url(url, bundle)
