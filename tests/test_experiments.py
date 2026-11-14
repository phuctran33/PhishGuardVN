"""Week-5 boundaries: nested selection, group calibration and held-out independence."""
from __future__ import annotations

from copy import deepcopy

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

import phishguard_vn.experiments as experiments
from phishguard_vn.features import CANDIDATE_FEATURES


def experiment_config():
    return {
        "experiment": {"name": "week5_lexical_models", "seed": 42, "feature_set": "lexical_12"},
        "evaluation": {"n_splits": 3, "inner_splits": 2, "calibration_splits": 2,
                       "primary_metric": "average_precision", "decision_threshold": 0.5,
                       "use_test": False, "validation_role": "supplementary"},
        "candidates": {
            "logistic_regression": [
                {"class_weight": "none", "C": 0.1, "max_iter": 2000},
                {"class_weight": "none", "C": 1.0, "max_iter": 2000},
            ],
        },
    }


@pytest.fixture
def experiment_inputs():
    """Each domain contains both labels; feature url_len uniquely identifies rows."""
    features, targets, folds = [], [], []
    for group in range(12):
        for label in range(2):
            row_id = f"train-{group:02d}-{label}"
            values = {column: float((group + index) % 5 + label)
                      for index, column in enumerate(CANDIDATE_FEATURES)}
            values.update(id=row_id, url_len=float(10 + group * 2 + label),
                          digit_cnt=float(label * 5), is_ip=0.0, under_cnt=0.0)
            features.append(values)
            targets.append(dict(id=row_id, label="phishing" if label else "benign", tier="gold",
                                split="train", registrable_domain=f"group-{group}.example"))
            folds.append(dict(id=row_id, fold_id=group % 3))
    for split, offset in [("val", 1000), ("test", 10000)]:
        for label in range(2):
            row_id = f"{split}-{label}"
            values = {column: float(label + 1) for column in CANDIDATE_FEATURES}
            values.update(id=row_id, url_len=float(offset + label), digit_cnt=float(label * 5),
                          is_ip=0.0, under_cnt=0.0)
            features.append(values)
            targets.append(dict(id=row_id, label="phishing" if label else "benign", tier="silver",
                                split=split, registrable_domain=f"{split}-{label}.example"))
    return pd.DataFrame(features), pd.DataFrame(targets), pd.DataFrame(folds), experiment_config()


def _fitting_frame(features, targets, folds):
    frame = features.merge(targets, on="id", validate="one_to_one").merge(
        folds, on="id", validate="one_to_one")
    frame["target"] = frame.label.eq("phishing").astype(int)
    return frame.sort_values("id").reset_index(drop=True)


def _predictions(frame):
    return frame.sort_values(["model", "id"]).reset_index(drop=True)


def test_every_scaler_fit_is_local_to_the_current_fitting_partition(experiment_inputs, monkeypatch):
    X, targets, folds, config = experiment_inputs
    names = list(CANDIDATE_FEATURES)
    allowed = []
    seen = []
    original_candidate = experiments.fit_candidate
    original_scaler = StandardScaler.fit

    def tracked_candidate(model_name, parameters, fitting_frame, feature_names, seed,
                          calibration_splits=2):
        allowed.append(set(fitting_frame.url_len))
        try:
            return original_candidate(model_name, parameters, fitting_frame, feature_names,
                                      seed, calibration_splits=calibration_splits)
        finally:
            allowed.pop()

    def tracked_scaler(self, values, *args, **kwargs):
        assert allowed, "Scaler fit occurred outside a declared fitting partition"
        assert list(values.columns) == names, "Metadata leaked into model input"
        actual = set(values.url_len)
        assert actual <= allowed[-1], "Scaler observed a held-out row"
        seen.append(actual)
        return original_scaler(self, values, *args, **kwargs)

    monkeypatch.setattr(experiments, "fit_candidate", tracked_candidate)
    monkeypatch.setattr(StandardScaler, "fit", tracked_scaler)
    result = experiments.run_experiments(X, targets, folds, config)
    train_values = set(X.merge(folds, on="id").url_len)
    assert seen and all(values <= train_values for values in seen)
    assert train_values in seen, "The final estimator must be refit on all eligible train"
    assert set(result["cv_predictions"].id) == set(folds.id)
    assert not set(result["cv_predictions"].id) & {"val-0", "val-1", "test-0", "test-1"}


def test_validation_and_test_do_not_change_cv_or_model_selection(experiment_inputs):
    X, targets, folds, config = experiment_inputs
    first = experiments.run_experiments(X, targets, folds, config)
    changed_targets = targets.copy()
    mask = changed_targets.split.ne("train")
    changed_targets.loc[mask, "label"] = changed_targets.loc[mask, "label"].map(
        {"benign": "phishing", "phishing": "benign"})
    changed_features = X.copy()
    nontrain = changed_features.id.isin(changed_targets.loc[mask, "id"])
    changed_features.loc[nontrain, list(CANDIDATE_FEATURES)] = 9876.0
    second = experiments.run_experiments(
        changed_features.sample(frac=1, random_state=9), changed_targets, folds, config)
    assert first["selected_model"] == second["selected_model"]
    pd.testing.assert_frame_equal(_predictions(first["cv_predictions"]),
                                  _predictions(second["cv_predictions"]))


def test_outer_holdout_labels_never_select_that_folds_configuration(experiment_inputs):
    X, targets, folds, config = experiment_inputs
    first = experiments.run_experiments(X, targets, folds, config)
    changed = targets.copy()
    held_ids = set(folds.loc[folds.fold_id.eq(0), "id"])
    mask = changed.id.isin(held_ids)
    changed.loc[mask, "label"] = changed.loc[mask, "label"].map(
        {"benign": "phishing", "phishing": "benign"})
    second = experiments.run_experiments(X, changed, folds, config)
    columns = ["id", "model", "fold_id", "predicted_label", "score"]
    a = first["cv_predictions"].loc[first["cv_predictions"].fold_id.eq(0), columns]
    b = second["cv_predictions"].loc[second["cv_predictions"].fold_id.eq(0), columns]
    pd.testing.assert_frame_equal(_predictions(a), _predictions(b))


def test_reported_cv_ap_matches_saved_predictions(experiment_inputs):
    X, targets, folds, config = experiment_inputs
    result = experiments.run_experiments(X, targets, folds, config)
    for (model, fold), predictions in result["cv_predictions"].groupby(["model", "fold_id"]):
        measured = result["cv_metrics"].loc[
            result["cv_metrics"].model.eq(model) & result["cv_metrics"].fold_id.eq(fold)]
        assert len(measured) == 1
        assert measured.iloc[0].pr_auc == pytest.approx(
            average_precision_score(predictions.true_label, predictions.score))
    assert len(result["cv_predictions"]) == len(folds)
    assert set(result["validation_predictions"].id) == {"val-0", "val-1"}


def test_primary_selection_uses_ap_even_when_f1_prefers_another_family(
        experiment_inputs, monkeypatch):
    X, targets, folds, config = experiment_inputs
    config = deepcopy(config)
    config["candidates"]["logistic_regression"] = [
        {"class_weight": "none", "C": 1.0, "max_iter": 2000}]
    config["candidates"]["logistic_regression_balanced"] = [
        {"class_weight": "balanced", "C": 1.0, "max_iter": 2000}]

    class ControlledScores:
        classes_ = np.array([0, 1])

        def __init__(self, model):
            self.model = model

        def predict_proba(self, values):
            lengths = values.url_len.to_numpy()
            positive = lengths.astype(int) % 2 == 1
            if self.model == "logistic_regression":
                # Perfect ordering but every score is below the fixed threshold.
                score = np.where(positive, 0.4, 0.1)
            else:
                # Nonzero F1, but one high-scoring negative in each outer fold.
                group = (lengths.astype(int) - 10) // 2
                score = np.where(positive, 0.8, np.where(group < 3, 0.9, 0.1))
            return np.column_stack([1-score, score])

    def controlled_fit(model_name, parameters, fitting_frame, feature_names, seed,
                       calibration_splits=2):
        return ControlledScores(model_name), {
            "fit_seconds": 0.0, "converged": True,
            "convergence_warnings": [], "calibration_audit": [],
        }

    monkeypatch.setattr(experiments, "fit_candidate", controlled_fit)
    result = experiments.run_experiments(X, targets, folds, config)
    metrics = result["cv_metrics"].groupby("model")[["pr_auc", "f1_phishing"]].mean()
    assert metrics.loc["logistic_regression", "pr_auc"] > metrics.loc[
        "logistic_regression_balanced", "pr_auc"]
    assert metrics.loc["logistic_regression", "f1_phishing"] < metrics.loc[
        "logistic_regression_balanced", "f1_phishing"]
    assert result["selected_model"] == "logistic_regression"


def test_svm_calibration_folds_are_domain_disjoint_and_scaler_is_inside(experiment_inputs, monkeypatch):
    X, targets, folds, _ = experiment_inputs
    frame = _fitting_frame(X, targets, folds)
    names = list(CANDIDATE_FEATURES)
    seen = []
    original = StandardScaler.fit

    def tracked(self, values, *args, **kwargs):
        seen.append(frozenset(values.url_len))
        return original(self, values, *args, **kwargs)

    monkeypatch.setattr(StandardScaler, "fit", tracked)
    estimator, info = experiments.fit_candidate(
        "svm_rbf", {"C": 1.0, "gamma": "scale", "class_weight": "none"},
        frame, names, 42, calibration_splits=2)
    assert isinstance(estimator, CalibratedClassifierCV)
    assert estimator.ensemble is False
    base = estimator.estimator
    assert isinstance(base.named_steps["scaler"], StandardScaler)
    assert base.named_steps["model"].probability is False
    expected_scaler_rows = [frozenset(frame.url_len)]
    held = []
    for train_index, held_index in estimator.cv:
        fitting, holdout = frame.iloc[train_index], frame.iloc[held_index]
        assert set(fitting.registrable_domain).isdisjoint(holdout.registrable_domain)
        assert set(fitting.target) == {0, 1} and set(holdout.target) == {0, 1}
        expected_scaler_rows.append(frozenset(fitting.url_len))
        held.extend(held_index)
    assert sorted(held) == list(range(len(frame)))
    assert sorted(seen, key=lambda group: sorted(group)) == sorted(
        expected_scaler_rows, key=lambda group: sorted(group))
    probabilities = estimator.predict_proba(frame[names])
    assert probabilities.shape == (len(frame), 2)
    assert np.isfinite(probabilities).all()
    assert np.allclose(probabilities.sum(axis=1), 1)


@pytest.mark.parametrize("model,parameters", [
    ("mlp", {"hidden_layer_sizes": [8], "alpha": 0.01, "max_iter": 600}),
    ("hist_gradient_boosting", {"max_iter": 20, "max_leaf_nodes": 7,
                                "learning_rate": 0.1, "l2_regularization": 1.0}),
])
def test_neural_and_tree_models_disable_random_validation_early_stopping(
        experiment_inputs, model, parameters):
    X, targets, folds, _ = experiment_inputs
    frame = _fitting_frame(X, targets, folds)
    estimator, info = experiments.fit_candidate(model, parameters, frame,
                                               list(CANDIDATE_FEATURES), 42)
    model_estimator = estimator.named_steps["model"] if hasattr(estimator, "named_steps") else estimator
    assert model_estimator.early_stopping is False


def test_final_estimator_reload_preserves_predictions(experiment_inputs, tmp_path):
    X, targets, folds, config = experiment_inputs
    result = experiments.run_experiments(X, targets, folds, config)
    estimator = result["estimators"][result["selected_model"]]
    values = X.loc[X.id.isin(folds.id), list(CANDIDATE_FEATURES)]
    path = tmp_path / "week5.joblib"
    joblib.dump(estimator, path)
    restored = joblib.load(path)
    np.testing.assert_allclose(estimator.predict_proba(values), restored.predict_proba(values),
                               rtol=0, atol=0)


@pytest.mark.parametrize("problem", ["metadata", "missing_train", "duplicate_id", "test_in_fold", "domain_split"])
def test_invalid_handoffs_fail_before_training(experiment_inputs, monkeypatch, problem):
    X, targets, folds, config = experiment_inputs
    if problem == "metadata":
        X = X.assign(source="must-not-be-a-feature")
    elif problem == "missing_train":
        X = X.loc[X.id.ne("train-00-0")]
    elif problem == "duplicate_id":
        X = pd.concat([X, X.iloc[[0]]], ignore_index=True)
    elif problem == "test_in_fold":
        folds = pd.concat([folds, pd.DataFrame([{"id": "test-0", "fold_id": 0}])], ignore_index=True)
    else:
        folds = folds.copy()
        folds.loc[folds.id.eq("train-00-1"), "fold_id"] = 1

    def forbidden_fit(*args, **kwargs):
        pytest.fail("Invalid input reached model fitting")

    monkeypatch.setattr(experiments, "fit_candidate", forbidden_fit)
    with pytest.raises(ValueError):
        experiments.run_experiments(X, targets, folds, config)


@pytest.mark.parametrize("section,key,value", [
    ("evaluation", "use_test", True),
    ("evaluation", "primary_metric", "accuracy"),
    ("evaluation", "n_splits", 3.0),
    ("experiment", "threads", True),
    ("evaluation", "inner_splits", 1),
    ("evaluation", "calibration_splits", 1),
    ("experiment", "feature_set", "lexical_plus_unreviewed_brand"),
])
def test_unsupported_protocol_cannot_silently_run(experiment_inputs, section, key, value):
    _, _, _, config = experiment_inputs
    config = deepcopy(config)
    config[section][key] = value
    with pytest.raises(ValueError):
        experiments.validate_experiment_config(config)


@pytest.mark.parametrize("model,key,value", [
    ("logistic_regression", "made_up_setting", 1),
    ("svm_rbf", "probability", True),
    ("mlp", "early_stopping", True),
    ("hist_gradient_boosting", "early_stopping", True),
])
def test_unknown_or_unsafe_model_settings_are_rejected(model, key, value):
    config = experiment_config()
    parameters = {
        "logistic_regression": {"class_weight": "none", "C": 1.0, "max_iter": 2000},
        "svm_rbf": {"C": 1.0, "gamma": "scale", "class_weight": "none"},
        "mlp": {"hidden_layer_sizes": [8], "alpha": 0.01, "max_iter": 600},
        "hist_gradient_boosting": {"max_iter": 20, "max_leaf_nodes": 7,
                                   "learning_rate": 0.1, "l2_regularization": 1.0},
    }[model]
    config["candidates"] = {model: [{**parameters, key: value}]}
    with pytest.raises(ValueError):
        experiments.validate_experiment_config(config)


@pytest.mark.parametrize("all_failed", [False, True])
def test_nonconverged_candidate_is_never_selected(experiment_inputs, monkeypatch, all_failed):
    X, targets, folds, config = experiment_inputs

    class Scores:
        classes_ = np.array([0, 1])

        def predict_proba(self, values):
            positive = values.url_len.to_numpy().astype(int) % 2 == 1
            score = np.where(positive, 0.8, 0.2)
            return np.column_stack([1-score, score])

    def controlled_fit(model_name, parameters, fitting_frame, feature_names, seed,
                       calibration_splits=2):
        converged = not all_failed and parameters["C"] == 1.0
        return Scores(), {"fit_seconds": 0.0, "converged": converged,
                          "convergence_warnings": [] if converged else ["synthetic nonconvergence"],
                          "calibration_audit": []}

    monkeypatch.setattr(experiments, "fit_candidate", controlled_fit)
    if all_failed:
        with pytest.raises(RuntimeError, match="No converged candidate"):
            experiments.run_experiments(X, targets, folds, config)
    else:
        result = experiments.run_experiments(X, targets, folds, config)
        assert set(result["selections"].candidate_id) == {"logistic_regression_01"}
        rejected = result["inner_search"].loc[
            result["inner_search"].candidate_id.eq("logistic_regression_00")]
        assert not rejected.empty and rejected.status.eq("ineligible").all()
