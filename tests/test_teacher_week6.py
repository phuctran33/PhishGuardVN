"""Kiểm tra chính code cell tuần 6 trên dữ liệu nhỏ; không retrain model đồ án."""
from pathlib import Path
import json

import nbformat
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = nbformat.read(ROOT / "notebooks/06_teacher_v1.ipynb", as_version=4)
CODE = {c.metadata["tags"][0]: c.source for c in NOTEBOOK.cells if c.cell_type == "code"}


@pytest.fixture
def teacher_scope(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("# fixture", encoding="utf-8")
    for package in ["lightgbm", "xgboost", "catboost", "imblearn"]:
        pytest.importorskip(package, reason="Install .[teacher] to test the expanded notebook")
    scope = {}
    exec(CODE["setup"], scope)
    exec(CODE["models"], scope)
    exec(CODE["helpers"], scope)
    rows = []
    for group in range(12):
        for target in [0, 1]:
            values = {name: float(target + group % 3) for name in scope["FEATURES"]}
            values.update(id=f"train-{group}-{target}", target=target, fold_id=group % 3,
                          registrable_domain=f"g{group}.example", url_len=float(10 + group * 3 + target))
            rows.append(values)
    scope["train"] = pd.DataFrame(rows)
    scope["validation"] = scope["train"].iloc[:2].copy()
    scope["validation"]["url_len"] = [99999., 99998.]
    scope["models"] = {k: scope["models"][k] for k in ["logistic_regression", "random_forest"]}
    scope["models"]["random_forest"].set_params(n_estimators=8)
    scope["param_grids"] = {"logistic_regression": {"model__C": [0.5, 1.]},
                            "random_forest": {"max_depth": [2, None]}}
    yield scope
    scope["CPU_LIMIT"].restore_original_limits()
    scope["plt"].close("all")


def test_scaler_and_search_only_see_fitting_partition(teacher_scope, monkeypatch):
    scope = teacher_scope
    original_search, original_scaler = GridSearchCV.fit, StandardScaler.fit
    seen = []

    def tracked_search(self, X, y, **kwargs):
        fitting = scope["train"].loc[scope["train"].fold_id.ne(scope["fold_id"])]
        assert set(X.url_len) == set(fitting.url_len)
        groups = fitting.registrable_domain
        for a, b in self.cv:
            assert set(groups.iloc[a]).isdisjoint(groups.iloc[b])
        return original_search(self, X, y, **kwargs)

    def tracked_scaler(self, X, y=None, **kwargs):
        allowed = set(scope["train"].loc[scope["train"].fold_id.ne(scope["fold_id"]), "url_len"])
        assert set(X.url_len).issubset(allowed)
        seen.append(len(X))
        return original_scaler(self, X, y, **kwargs)

    monkeypatch.setattr(GridSearchCV, "fit", tracked_search)
    monkeypatch.setattr(StandardScaler, "fit", tracked_scaler)
    exec(CODE["cv"], scope)
    assert seen and len(scope["oof"]) == 48
    assert not scope["oof"].duplicated(["model", "id"]).any()


def test_holdout_answers_do_not_change_their_own_predictions(teacher_scope):
    scope = teacher_scope
    exec(CODE["cv"], scope)
    before = scope["oof"].copy()
    # Các đáp án outer fold 0 không được đi vào fit/tuning của chính fold đó.
    mask = scope["train"].fold_id.eq(0)
    scope["train"].loc[mask, "target"] = 1 - scope["train"].loc[mask, "target"]
    exec(CODE["cv"], scope)
    columns = [c for c in before.columns if c != "true_label"]
    pd.testing.assert_frame_equal(before.loc[before.fold_id.eq(0), columns].reset_index(drop=True),
        scope["oof"].loc[scope["oof"].fold_id.eq(0), columns].reset_index(drop=True))


def test_validation_answers_do_not_change_cv_or_candidate_ranking(teacher_scope):
    scope = teacher_scope
    exec(CODE["cv"], scope)
    exec(CODE["selection"], scope)
    before = scope["oof"].copy()
    teacher = scope["candidate_name"]
    scope["validation"]["target"] = 1 - scope["validation"]["target"]
    exec(CODE["cv"], scope)
    exec(CODE["selection"], scope)
    pd.testing.assert_frame_equal(before, scope["oof"])
    assert teacher == scope["candidate_name"]


def test_v0_matrix_is_rejected_before_training(teacher_scope):
    scope = teacher_scope
    data = scope["DATA"]
    data.mkdir(parents=True, exist_ok=True)
    train = scope["train"]
    core = train[["id"]].assign(split="train")
    core.to_csv(data / "core_gold_silver.csv", index=False)
    train[["id", *scope["FEATURES"]]].to_csv(data / "05_matrix_X_brand_trainval.csv", index=False)
    train[["id", "registrable_domain"]].to_csv(data / "03_registrable_domains.csv", index=False)
    train[["id", "fold_id"]].to_csv(data / "02_group_folds_train.csv", index=False)
    (data / "05_matrix_X_brand_trainval.manifest.json").write_text(
        json.dumps({"feature_schema_version": "e2-brand-v0"}), encoding="utf-8")
    with pytest.raises(AssertionError):
        exec(CODE["data"], scope)

def test_tfidf_vocabulary_only_sees_fitting_urls(teacher_scope, monkeypatch):
    from sklearn.feature_extraction.text import TfidfVectorizer
    scope = teacher_scope
    scope["models"] = {"tfidf_linear_svm": scope["text_svm"]}
    scope["param_grids"] = {"tfidf_linear_svm": {"model__C": [0.5, 2.0]}}
    markers = {0: "zzzzz", 1: "yyyyy", 2: "xxxxx"}
    scope["train"]["url"] = [
        f"https://{markers[row.fold_id]}.example/g{row.id}/" + ("verify" if row.target else "about")
        for row in scope["train"].itertuples()
    ]
    original = TfidfVectorizer.fit_transform
    seen = []

    def tracked_fit(self, documents, y=None):
        fitting = scope["train"].loc[scope["train"].fold_id.ne(scope["fold_id"])]
        assert set(documents).issubset(set(fitting.url))
        result = original(self, documents, y)
        assert markers[scope["fold_id"]] not in self.vocabulary_
        seen.append(len(documents))
        return result

    monkeypatch.setattr(TfidfVectorizer, "fit_transform", tracked_fit)
    exec(CODE["cv"], scope)
    assert seen and len(scope["oof"]) == len(scope["train"])
    assert scope["oof"]["score_kind"].eq("decision_function").all()

def test_low_fpr_threshold_uses_only_inner_fitting_predictions(teacher_scope, monkeypatch):
    from sklearn.model_selection import cross_val_predict
    scope = teacher_scope
    original = cross_val_predict
    seen = []

    def tracked_predict(model, X, y, **kwargs):
        fitting = scope["train"].loc[scope["train"].fold_id.ne(scope["fold_id"])]
        assert set(X.url_len) == set(fitting.url_len)
        assert list(y) == list(fitting.target)
        for a, b in kwargs["cv"]:
            assert set(fitting.iloc[a].registrable_domain).isdisjoint(fitting.iloc[b].registrable_domain)
        seen.append(len(X))
        return original(model, X, y, **kwargs)

    monkeypatch.setitem(scope, "cross_val_predict", tracked_predict)
    exec(CODE["cv"], scope)
    assert len(seen) == 6
    assert scope["low_fpr_metrics"].calibration_fpr.le(0.02).all()
    assert set(scope["low_fpr_metrics"].fold_id) == {0, 1, 2}

def test_low_fpr_threshold_handles_ties(teacher_scope):
    scope = teacher_scope
    for negatives in [np.zeros(100), np.repeat(np.arange(10), 10), np.linspace(-5, 5, 101)]:
        y = np.r_[np.zeros(len(negatives)), np.ones(5)]
        scores = np.r_[negatives, np.ones(5)]
        threshold = scope["threshold_at_train_fpr"](y, scores)
        assert np.mean(negatives >= threshold) <= 0.02

def test_ranking_keeps_e2_and_raw_url_candidates_distinct(teacher_scope):
    scope = teacher_scope
    rows = []
    for name, score in [("tfidf_linear_svm", 0.99), ("mlp", 0.72), ("lightgbm", 0.73)]:
        for fold in [0, 1, 2]:
            rows.append({"model": name, "fold_id": fold, "pr_auc": score,
                         "recall_phishing": 0.5, "false_positive_rate": 0.02,
                         "f1_phishing": 0.6, "precision_phishing": 0.8})
    scope["cv_metrics"] = pd.DataFrame(rows)
    scope["low_fpr_metrics"] = scope["cv_metrics"]
    exec(CODE["selection"], scope)
    assert scope["candidate_name"] == "lightgbm"
    assert scope["raw_candidate_name"] == "tfidf_linear_svm"
    assert scope["teacher_finalized"] is False


def test_unfinalized_teacher_is_blocked_before_loading_any_model(tmp_path):
    from phishguard_vn.external_pilot import load_locked_teacher
    with pytest.raises(ValueError, match="Teacher must be finalized"):
        load_locked_teacher(tmp_path, {"teacher_finalized": False, "status": "awaiting_team_decision"})
