"""Kiểm tra notebook thật: không thêm một implementation train khác để test."""
from pathlib import Path
import json

import joblib
import nbformat
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler

from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.prediction import predict_url

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = nbformat.read(ROOT / "notebooks/05_advanced_models.ipynb", as_version=4)
CODE = {cell.metadata["tags"][0]: cell.source for cell in NOTEBOOK.cells if cell.cell_type == "code"}


@pytest.fixture
def notebook_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("# fixture", encoding="utf-8")
    (tmp_path / "notebooks").mkdir()
    nbformat.write(NOTEBOOK, tmp_path / "notebooks/05_advanced_models.ipynb")
    data = tmp_path / "data/interim"
    data.mkdir(parents=True)
    features, core, domains, folds = [], [], [], []
    for group in range(12):
        for target in range(2):
            row_id = f"train-{group:02d}-{target}"
            values = {name: float((group + i) % 5 + target) for i, name in enumerate(CANDIDATE_FEATURES)}
            values.update(id=row_id, url_len=float(10+2*group+target), digit_cnt=float(target*5))
            features.append(values)
            core.append(dict(id=row_id, label="phishing" if target else "benign", tier="gold", split="train",
                             source="fixture", url=f"https://g-{group}.example/{target}"))
            domains.append(dict(id=row_id, registrable_domain=f"g-{group}.example"))
            folds.append(dict(id=row_id, fold_id=group % 3))
    for split, offset in [("val", 1000), ("test", 10000)]:
        for target in range(2):
            row_id = f"{split}-{target}"
            values = {name: float(target+1) for name in CANDIDATE_FEATURES}
            values.update(id=row_id, url_len=float(offset+target))
            features.append(values)
            core.append(dict(id=row_id, label="phishing" if target else "benign", tier="silver", split=split,
                             source="fixture", url=f"https://{split}-{target}.example"))
            domains.append(dict(id=row_id, registrable_domain=f"{split}-{target}.example"))
    for name, rows in [("03_matrix_X_features.csv", features), ("core_gold_silver.csv", core),
                       ("03_registrable_domains.csv", domains), ("02_group_folds_train.csv", folds)]:
        pd.DataFrame(rows).to_csv(data / name, index=False)
    namespace = {}
    exec(CODE["setup"], namespace)
    yield namespace
    namespace["CPU_LIMIT"].restore_original_limits()
    namespace["plt"].close("all")


def run_small(namespace):
    for stage in ["data", "models", "metrics"]:
        exec(CODE[stage], namespace)
    # Bài test dùng LR và SVM nhỏ; notebook chạy thật vẫn có đủ năm cấu hình.
    namespace["models"] = {name: namespace["models"][name] for name in ["logistic_regression", "svm_rbf"]}
    namespace["param_grids"] = {"logistic_regression": {"model__C": [0.5, 1.0]}, "svm_rbf": {"model__C": [0.5, 1.0]}}
    for stage in ["cv", "comparison", "final_fit"]:
        namespace["_stage"] = stage
        exec(CODE[stage], namespace)
    return namespace


def test_notebook_scaler_and_search_are_local_to_training(notebook_run, monkeypatch):
    scope = notebook_run
    active, observed = [], []
    original_search, original_scaler = GridSearchCV.fit, StandardScaler.fit
    def tracked_search(self, X, y, **kwargs):
        if scope["_stage"] == "cv":
            allowed_rows = scope["train"].loc[scope["train"].fold_id.ne(scope["fold_id"])]
            assert set(X.url_len) == set(allowed_rows.url_len), "Outer held-out row entered tuning"
        groups = scope["train"].loc[X.index, "registrable_domain"]
        expected = [frozenset(X.iloc[a].url_len) for a, b in self.cv] + [frozenset(X.url_len)]
        for a, b in self.cv:
            assert set(groups.iloc[a]).isdisjoint(groups.iloc[b])
        batch = []
        active.append(batch)
        try:
            result = original_search(self, X, y, **kwargs)
            assert all(values in expected for values in batch)
            assert all(values in batch for values in expected)
            return result
        finally:
            active.pop()
    def tracked_scaler(self, X, *args, **kwargs):
        values = frozenset(X.url_len)
        observed.append(values)
        if active:
            active[-1].append(values)
        assert all(value < 1000 for value in values), "Validation/test used in fit"
        return original_scaler(self, X, *args, **kwargs)
    monkeypatch.setattr(GridSearchCV, "fit", tracked_search)
    monkeypatch.setattr(StandardScaler, "fit", tracked_scaler)
    run_small(scope)
    assert observed
    assert not set(scope["cv_predictions"].id) & {"test-0", "test-1", "val-0", "val-1"}
    svm = scope["cv_predictions"].loc[scope["cv_predictions"].model.eq("svm_rbf")]
    assert svm.score_kind.eq("decision_function").all() and svm.score.lt(0).any()


def test_validation_test_changes_do_not_select_model(notebook_run):
    scope = run_small(notebook_run)
    first = scope["cv_predictions"].copy()
    winner = scope["selected_model"]
    core_path = scope["DATA"] / "core_gold_silver.csv"
    core = pd.read_csv(core_path)
    mask = core.split.ne("train")
    core.loc[mask, "label"] = core.loc[mask, "label"].map({"benign": "phishing", "phishing": "benign"})
    core.to_csv(core_path, index=False)
    run_small(scope)
    pd.testing.assert_frame_equal(first, scope["cv_predictions"])
    assert winner == scope["selected_model"]


@pytest.mark.parametrize("problem", ["duplicate_id", "test_in_folds", "metadata_in_X"])
def test_bad_handoff_stops_before_training(notebook_run, problem):
    scope = notebook_run
    if problem == "duplicate_id":
        path = scope["FEATURE_FILE"]
        frame = pd.read_csv(path)
        frame.loc[1, "id"] = frame.loc[0, "id"]
    elif problem == "test_in_folds":
        path = scope["DATA"] / "02_group_folds_train.csv"
        frame = pd.read_csv(path)
        frame.loc[0, "id"] = "test-0"
    else:
        path = scope["FEATURE_FILE"]
        frame = pd.read_csv(path).assign(source="leak")
    frame.to_csv(path, index=False)
    with pytest.raises(AssertionError):
        exec(CODE["data"], scope)


def test_raw_margin_metrics_and_reload_prediction(notebook_run, tmp_path):
    scope = run_small(notebook_run)
    measured = scope["calculate_metrics"]([0, 1, 1, 0], [0, 1, 1, 0], [-4, 3, 2, -1])
    assert measured["pr_auc"] == 1 and measured["f1_phishing"] == 1
    bundle = {"models": scope["trained_models"], "selected_model": "svm_rbf",
              "feature_names": scope["FEATURES"], "feature_set": "lexical_12",
              "score_kinds": {"logistic_regression": "probability", "svm_rbf": "decision_function"},
              "protocol": "week5_readable_v2"}
    path = tmp_path / "model.joblib"
    joblib.dump(bundle, path)
    before = predict_url("https://example.com/a", bundle)
    after = predict_url("https://example.com/a", joblib.load(path))
    assert before == after and after["score_kind"] == "decision_function"
    with pytest.raises(ValueError, match="không hợp lệ"):
        predict_url("https://example.com:bad", bundle)

    # CLI phải in được tiếng Việt ngay cả khi stdout Windows mặc định cp1252.
    import os
    import subprocess
    import sys
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "predict_week5.py").write_text((ROOT / "scripts/predict_week5.py").read_text(encoding="utf-8"), encoding="utf-8")
    joblib.dump(bundle, tmp_path / "models/week5_readable_models.joblib")
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONPATH=str(ROOT / "src"))
    completed = subprocess.run([sys.executable, str(scripts / "predict_week5.py"), "https://example.com/a"],
                               env=env, capture_output=True, encoding="utf-8", check=True)
    assert json.loads(completed.stdout)["score_kind"] == "decision_function"


def test_outer_held_out_answers_do_not_change_its_predictions(notebook_run):
    scope = run_small(notebook_run)
    before = scope["cv_predictions"].loc[scope["cv_predictions"].fold_id.eq(0)].reset_index(drop=True)
    held_ids = set(scope["train"].loc[scope["train"].fold_id.eq(0), "id"])
    path = scope["DATA"] / "core_gold_silver.csv"
    core = pd.read_csv(path)
    mask = core.id.isin(held_ids)
    core.loc[mask, "label"] = core.loc[mask, "label"].map({"benign": "phishing", "phishing": "benign"})
    core.to_csv(path, index=False)
    run_small(scope)
    after = scope["cv_predictions"].loc[scope["cv_predictions"].fold_id.eq(0)].reset_index(drop=True)
    pd.testing.assert_frame_equal(before.drop(columns="true_label"), after.drop(columns="true_label"))
