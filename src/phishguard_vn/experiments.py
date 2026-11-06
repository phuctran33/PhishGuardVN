"""Week-5 lexical experiments: nested group selection, group-safe SVM calibration.

E1 files remain immutable. Official validation is supplementary; test is never scored.
"""
from __future__ import annotations

import hashlib
import json
from numbers import Real, Integral
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from phishguard_vn.evaluation import summarize_predictions
from phishguard_vn.modeling import METRICS, _prepare_inputs, _scores

MODEL_PARAMETERS = {
    "logistic_regression": {"C", "class_weight", "max_iter"},
    "logistic_regression_balanced": {"C", "class_weight", "max_iter"},
    "svm_rbf": {"C", "gamma", "class_weight"},
    "mlp": {"hidden_layer_sizes", "alpha", "max_iter"},
    "hist_gradient_boosting": {"max_iter", "max_leaf_nodes", "learning_rate", "l2_regularization"},
}


def _integer(value, minimum=1):
    return isinstance(value, Integral) and not isinstance(value, bool) and value >= minimum


def _positive(value, allow_zero=False):
    return (isinstance(value, Real) and not isinstance(value, bool) and np.isfinite(value)
            and (value >= 0 if allow_zero else value > 0))


def validate_experiment_config(config):
    allowed = {
        "experiment": {"name", "seed", "feature_set", "threads"},
        "evaluation": {"n_splits", "inner_splits", "calibration_splits", "primary_metric",
                       "decision_threshold", "use_test", "validation_role"},
        "candidates": set(MODEL_PARAMETERS),
    }
    if set(config) != set(allowed):
        raise ValueError("Unsupported or missing config sections; expected experiment/evaluation/candidates")
    for section, keys in allowed.items():
        if not isinstance(config[section], dict) or set(config[section]) - keys:
            raise ValueError(f"Unsupported {section} settings")
    experiment, evaluation = config["experiment"], config["evaluation"]
    if experiment.get("feature_set") != "lexical_12":
        raise ValueError("Only lexical_12 is implemented; brand features are pending Hy")
    if not isinstance(experiment.get("name"), str) or not experiment["name"].strip():
        raise ValueError("Experiment name must be a nonblank string")
    if not _integer(experiment.get("seed"), 0) or experiment["seed"] >= 2**32:
        raise ValueError("seed must be an integer in [0, 2**32)")
    if not _integer(experiment.get("threads", 1)) or experiment.get("threads", 1) != 1:
        raise ValueError("This protocol requires threads=1")
    if not _integer(evaluation.get("n_splits"), 2):
        raise ValueError("n_splits must be an integer")
    fixed = {"n_splits": 3, "primary_metric": "average_precision", "decision_threshold": 0.5,
             "use_test": False, "validation_role": "supplementary"}
    for key, value in fixed.items():
        if evaluation.get(key) != value or (key == "use_test" and evaluation[key] is not False):
            raise ValueError(f"Unsupported evaluation.{key}; expected {value!r}")
    for key in ("inner_splits", "calibration_splits"):
        if not _integer(evaluation.get(key), 2):
            raise ValueError(f"{key} must be an integer >= 2")
    if not config["candidates"]:
        raise ValueError("At least one model family is required")
    for name, candidates in config["candidates"].items():
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(f"{name}: nonempty candidate list required")
        seen = set()
        for params in candidates:
            if not isinstance(params, dict) or set(params) != MODEL_PARAMETERS[name]:
                raise ValueError(f"Unsupported/missing parameters for {name}")
            for key in ("max_iter", "max_leaf_nodes"):
                if key in params and not _integer(params[key], 2 if key == "max_leaf_nodes" else 1):
                    raise ValueError(f"{key} must be a positive integer")
            for key in ("C", "alpha", "learning_rate", "l2_regularization"):
                if key in params and not _positive(params[key], key in ("alpha", "l2_regularization")):
                    raise ValueError(f"Invalid {key}")
            if "class_weight" in params and params["class_weight"] not in ("none", "balanced"):
                raise ValueError("class_weight must be none/balanced")
            if name == "logistic_regression" and params["class_weight"] != "none":
                raise ValueError("Standard LR requires class_weight=none")
            if name == "logistic_regression_balanced" and params["class_weight"] != "balanced":
                raise ValueError("Balanced LR requires class_weight=balanced")
            if name == "svm_rbf" and params["gamma"] not in ("scale", "auto"):
                raise ValueError("SVM gamma must be scale/auto")
            if name == "mlp":
                layers = params["hidden_layer_sizes"]
                if not isinstance(layers, list) or not layers or not all(_integer(x) for x in layers):
                    raise ValueError("hidden_layer_sizes must be positive integers")
            encoded = json.dumps(params, sort_keys=True, allow_nan=False)
            if encoded in seen:
                raise ValueError(f"Duplicate candidates in {name}")
            seen.add(encoded)


def _group_splits(frame, n_splits, seed):
    """Indices are relative to this exact fitting frame; never reuse on other subsets."""
    if frame.target.nunique() != 2 or frame.registrable_domain.isna().any():
        raise ValueError("Group splitting requires two classes and resolved domains")
    if frame.groupby("target").registrable_domain.nunique().min() < n_splits:
        raise ValueError("Insufficient class-domain support for group split")
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    pairs = list(splitter.split(np.zeros((len(frame), 1)), frame.target, frame.registrable_domain))
    for fitting, held in pairs:
        left, right = frame.iloc[fitting], frame.iloc[held]
        if left.target.nunique() != 2 or right.target.nunique() != 2:
            raise ValueError("Group split produced a one-class partition; no seed retries")
        if set(left.registrable_domain) & set(right.registrable_domain):
            raise ValueError("Domain overlap in group split")
    return pairs


def _digest(values):
    return hashlib.sha256("\n".join(sorted(map(str, values))).encode()).hexdigest()


def _audit_split(frame, fitting, held, split_id):
    left, right = frame.iloc[fitting], frame.iloc[held]
    return {"split_id": int(split_id), "fitting_rows": len(left), "held_rows": len(right),
            "fitting_phishing": int(left.target.sum()), "held_phishing": int(right.target.sum()),
            "fitting_groups": int(left.registrable_domain.nunique()),
            "held_groups": int(right.registrable_domain.nunique()),
            "overlap_groups": len(set(left.registrable_domain) & set(right.registrable_domain)),
            "fitting_ids_sha256": _digest(left.id), "held_ids_sha256": _digest(right.id)}


def fit_candidate(model_name, parameters, fitting_frame, feature_names, seed, calibration_splits=2):
    """Fit only this frame. Return warnings explicitly; caller decides eligibility."""
    frame = fitting_frame.sort_values("id").reset_index(drop=True)
    p = parameters
    weight = None if p.get("class_weight", "none") == "none" else "balanced"
    calibration_audit = []
    if model_name.startswith("logistic_regression"):
        estimator = Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(C=p["C"], class_weight=weight, max_iter=p["max_iter"],
                                         solver="lbfgs", random_state=seed))])
    elif model_name == "svm_rbf":
        splits = _group_splits(frame, calibration_splits, seed)
        calibration_audit = [_audit_split(frame, a, b, i) for i, (a, b) in enumerate(splits)]
        base = Pipeline([
            ("scaler", StandardScaler()),
            ("model", SVC(C=p["C"], gamma=p["gamma"], class_weight=weight, kernel="rbf",
                          probability=False, cache_size=256, random_state=seed))])
        estimator = CalibratedClassifierCV(base, method="sigmoid", cv=splits, ensemble=False, n_jobs=1)
    elif model_name == "mlp":
        estimator = Pipeline([
            ("scaler", StandardScaler()),
            ("model", MLPClassifier(hidden_layer_sizes=tuple(p["hidden_layer_sizes"]), alpha=p["alpha"],
                                    max_iter=p["max_iter"], batch_size=min(256, len(frame)),
                                    learning_rate_init=0.001, n_iter_no_change=20, tol=1e-4,
                                    early_stopping=False, random_state=seed))])
    elif model_name == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(**p, early_stopping=False, random_state=seed)
    else:
        raise ValueError(f"Unsupported model: {model_name}")
    start = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimator.fit(frame[feature_names], frame.target)
    convergence = [str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)]
    return estimator, {"fit_seconds": time.perf_counter()-start, "converged": not convergence,
                       "convergence_warnings": convergence,
                       "other_warnings": [str(w.message) for w in caught if not issubclass(w.category, ConvergenceWarning)],
                       "calibration_audit": calibration_audit}


def run_experiments(features, targets, folds, config, progress=None):
    """Primary AP nested group comparison; fixed 0.5 threshold, no test predictions."""
    validate_experiment_config(config)
    with threadpool_limits(limits=1):
        return _run_experiments(features, targets, folds, config, progress or (lambda _: None))


def _run_experiments(features, targets, folds, config, progress):
    train, validation, names, audit = _prepare_inputs(features, targets, folds, config)
    seed = config["experiment"]["seed"]
    evaluation = config["evaluation"]
    threshold = evaluation["decision_threshold"]
    inner_search, selections, fit_log, split_audit = [], [], [], []
    metrics, predictions = [], []
    calibration_splits = evaluation["calibration_splits"]

    def attempt(name, params, frame, phase, outer_fold, inner_fold, candidate_id):
        progress(f"{phase}: {name} outer={outer_fold} inner={inner_fold} candidate={candidate_id} rows={len(frame)}")
        context = {"model": name, "outer_fold": outer_fold, "inner_fold": inner_fold,
                   "candidate_id": candidate_id, "phase": phase}
        started = time.perf_counter()
        try:
            estimator, info = fit_candidate(name, params, frame, names, seed, calibration_splits)
        except (ValueError, RuntimeError, FloatingPointError) as exc:
            fit_log.append({**context, "fit_seconds": time.perf_counter()-started, "converged": False,
                            "warnings": "", "error": str(exc), "status": "fit_failed"})
            return None, {"fit_seconds": time.perf_counter()-started, "converged": False,
                          "convergence_warnings": [str(exc)]}
        for entry in info["calibration_audit"]:
            split_audit.append({**context, "kind": "calibration", **entry})
        fit_log.append({**context, "fit_seconds": info["fit_seconds"], "converged": info["converged"],
                        "warnings": json.dumps(info["convergence_warnings"]+info.get("other_warnings", [])),
                        "error": "", "status": "ok" if info["converged"] else "not_converged"})
        return (estimator if info["converged"] else None), info

    def select(name, fitting, outer_fold):
        fitting = fitting.sort_values("id").reset_index(drop=True)
        candidates = config["candidates"][name]
        if len(candidates) == 1:
            candidate_id = f"{name}_00"
            selections.append({"model": name, "outer_fold": outer_fold, "candidate_id": candidate_id,
                               "parameters_json": json.dumps(candidates[0], sort_keys=True),
                               "mean_inner_ap": None, "status": "fixed_config"})
            return candidates[0], candidate_id
        splits = _group_splits(fitting, evaluation["inner_splits"], seed)
        for i, (a, b) in enumerate(splits):
            split_audit.append({"model": name, "outer_fold": outer_fold, "kind": "inner_selection",
                                "phase": "inner", "inner_fold": i, "candidate_id": "all",
                                **_audit_split(fitting, a, b, i)})
        ranking = []
        for index, params in enumerate(candidates):
            candidate_id = f"{name}_{index:02d}"
            scores = []
            valid = True
            for inner_fold, (a, b) in enumerate(splits):
                estimator, info = attempt(name, params, fitting.iloc[a], "inner", outer_fold, inner_fold, candidate_id)
                ap = None
                if estimator is not None:
                    ap = float(average_precision_score(fitting.iloc[b].target, _scores(estimator, fitting.iloc[b][names])))
                    scores.append(ap)
                else:
                    valid = False
                inner_search.append({"model": name, "outer_fold": outer_fold, "candidate_id": candidate_id,
                                     "inner_fold": inner_fold, "pr_auc": ap,
                                     "parameters_json": json.dumps(params, sort_keys=True),
                                     "fit_seconds": info["fit_seconds"],
                                     "convergence_warnings": json.dumps(info["convergence_warnings"]),
                                     "status": "ok" if estimator is not None else "ineligible"})
            if valid:
                ranking.append((float(np.mean(scores)), candidate_id, params))
        if not ranking:
            raise RuntimeError(f"No converged candidate for {name}, outer={outer_fold}; inspect fit warnings before changing protocol")
        ranking.sort(key=lambda row: (-row[0], row[1]))
        ap, candidate_id, params = ranking[0]
        selections.append({"model": name, "outer_fold": outer_fold, "candidate_id": candidate_id,
                           "parameters_json": json.dumps(params, sort_keys=True),
                           "mean_inner_ap": ap, "status": "selected_by_inner_ap"})
        return params, candidate_id

    for fold in sorted(train.fold_id.unique()):
        a = np.flatnonzero(train.fold_id.ne(fold).to_numpy())
        b = np.flatnonzero(train.fold_id.eq(fold).to_numpy())
        split_audit.append({"model": "all", "outer_fold": int(fold), "kind": "outer_evaluation",
                            "phase": "outer", "inner_fold": -1, "candidate_id": "all",
                            **_audit_split(train, a, b, fold)})
    for name in config["candidates"]:
        for fold in sorted(train.fold_id.unique()):
            fitting = train.loc[train.fold_id.ne(fold)]
            held = train.loc[train.fold_id.eq(fold)]
            params, candidate_id = select(name, fitting, int(fold))
            estimator, info = attempt(name, params, fitting, "outer_refit", int(fold), -1, candidate_id)
            if estimator is None:
                raise RuntimeError(f"Outer refit did not converge: {name}, fold={fold}")
            scores = _scores(estimator, held[names])
            pred = (scores >= threshold).astype(int)
            metrics.append({"model": name, "evaluation_partition": "group_cv", "fold_id": int(fold),
                            "candidate_id": candidate_id, "threshold": threshold, "fit_seconds": info["fit_seconds"],
                            **summarize_predictions(held.target.to_numpy(), pred, scores)})
            predictions.append(pd.DataFrame({"id": held.id.to_numpy(), "model": name, "fold_id": int(fold),
                                             "evaluation_partition": "group_cv", "true_label": held.target.to_numpy(),
                                             "predicted_label": pred, "score": scores}))
    cv_metrics = pd.DataFrame(metrics)
    cv_summary = cv_metrics.groupby("model", sort=False)[list(METRICS)].agg(["mean", "std"])
    cv_summary.columns = [f"{metric}_{stat}" for metric, stat in cv_summary.columns]
    cv_summary = cv_summary.reset_index()
    ranking = cv_summary.sort_values(["pr_auc_mean", "f1_phishing_mean", "false_positive_rate_mean", "model"],
                                     ascending=[False, False, True, True])
    selected_model = ranking.iloc[0].model
    progress(f"Outer CV complete; AP-primary provisional lexical winner: {selected_model}")
    estimators, validation_metrics, validation_predictions = {}, [], []
    for name in config["candidates"]:
        params, candidate_id = select(name, train, -1)
        estimator, info = attempt(name, params, train, "full_train_refit", -1, -1, candidate_id)
        if estimator is None:
            raise RuntimeError(f"Full-train refit did not converge: {name}")
        estimators[name] = estimator
        if len(validation):
            scores = _scores(estimator, validation[names])
            pred = (scores >= threshold).astype(int)
            validation_metrics.append({"model": name, "evaluation_partition": "official_validation",
                                       "candidate_id": candidate_id, "threshold": threshold,
                                       **summarize_predictions(validation.target.to_numpy(), pred, scores)})
            validation_predictions.append(pd.DataFrame({"id": validation.id.to_numpy(), "model": name,
                "evaluation_partition": "official_validation", "true_label": validation.target.to_numpy(),
                "predicted_label": pred, "score": scores}))
    scope = {"train_rows": len(train), "train_phishing": int(train.target.sum()),
             "validation_rows": len(validation), "validation_phishing": int(validation.target.sum()),
             "test_evaluated": False, "domain_audit_status": audit["status"],
             "excluded_ids": targets.loc[~targets.id.isin(features.id), ["id", "label", "split"]].to_dict("records"),
             "feature_set": "lexical_12", "brand_ablation_status": "pending_Hy",
             "teacher_status": "provisional_lexical_comparison_only"}
    return {"cv_metrics": cv_metrics, "cv_summary": cv_summary,
            "cv_predictions": pd.concat(predictions, ignore_index=True),
            "validation_metrics": pd.DataFrame(validation_metrics),
            "validation_predictions": pd.concat(validation_predictions, ignore_index=True) if validation_predictions else pd.DataFrame(),
            "inner_search": pd.DataFrame(inner_search, columns=["model", "outer_fold", "candidate_id", "inner_fold", "pr_auc", "parameters_json", "fit_seconds", "convergence_warnings", "status"]),
            "selections": pd.DataFrame(selections), "fit_log": pd.DataFrame(fit_log), "split_audit": pd.DataFrame(split_audit),
            "selected_model": selected_model, "estimators": estimators, "feature_names": names,
            "decision_threshold": threshold, "scope": scope, "runtime": {"threadpool_limit": 1},
            "selection_rule": "mean outer AP; tie mean F1, lower mean FPR, model name; final hyperparameters from full-train inner group AP"}
