"""Week-4 baselines on supplied train-only domain folds; test is never scored."""
from __future__ import annotations

from pathlib import Path
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from phishguard_vn.data import LABEL_MAP
from phishguard_vn.evaluation import summarize_predictions
from phishguard_vn.features import CANDIDATE_FEATURES, extract_features_from_parsed
from phishguard_vn.splits import audit_domain_overlap
from phishguard_vn.url_parser import parse_url

METRICS = ("accuracy", "precision_phishing", "recall_phishing", "f1_phishing",
           "pr_auc", "false_positive_rate")


def build_dummy_baseline():
    return DummyClassifier(strategy="most_frequent")


def build_logistic_baseline(seed: int = 42, class_weight: str | None = None,
                            max_iter: int = 2000):
    if class_weight not in (None, "balanced"):
        raise ValueError("class_weight must be None or balanced.")
    return Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(random_state=seed, class_weight=class_weight,
                                     max_iter=max_iter, solver="lbfgs", C=1.0)),
    ])


def _check_ids(frame: pd.DataFrame, name: str):
    if "id" not in frame or frame["id"].isna().any() or not frame["id"].is_unique:
        raise ValueError(f"{name}: missing or duplicate id.")
    if not frame["id"].map(lambda v: isinstance(v, str) and bool(v.strip())).all():
        raise ValueError(f"{name}: id must be non-blank strings.")


def load_baseline_inputs(project_root: str | Path):
    """Read the exact handoff files; no raw data re-splitting or parser fallback."""
    interim = Path(project_root) / "data" / "interim"
    names = ["03_matrix_X_features.csv", "core_gold_silver.csv",
             "03_registrable_domains.csv", "02_group_folds_train.csv"]
    for name in names:
        if not (interim / name).is_file():
            raise FileNotFoundError(f"Missing {interim / name}. Run notebooks 01 -> 03 -> 02.")
    features, core, domains, folds = [pd.read_csv(interim / name, dtype={"id": "string"},
                                                low_memory=False) for name in names]
    for frame, name in [(features, names[0]), (core, names[1]),
                        (domains, names[2]), (folds, names[3])]:
        _check_ids(frame, name)
    if set(core.id) != set(domains.id):
        raise ValueError("Domain metadata must cover exactly the core IDs.")
    targets = core[["id", "label", "tier", "split"]].merge(
        domains[["id", "registrable_domain"]], on="id", validate="one_to_one")
    return features, targets, folds


def _prepare_inputs(features, targets, folds, config):
    names = list(CANDIDATE_FEATURES)
    for frame, name in [(features, "features"), (targets, "targets"), (folds, "folds")]:
        _check_ids(frame, name)
    if set(features.columns) != {"id", *names}:
        raise ValueError("X must contain only id and the agreed 12 features; metadata is forbidden.")
    required = {"id", "label", "tier", "split", "registrable_domain"}
    if not required.issubset(targets.columns):
        raise ValueError(f"Missing target columns: {sorted(required - set(targets.columns))}")
    if not targets.label.isin(LABEL_MAP).all() or not targets.tier.isin(["gold", "silver"]).all():
        raise ValueError("Targets must be Gold/Silver core with known string labels.")
    if not targets.split.isin(["train", "val", "test"]).all():
        raise ValueError("Unknown official split.")
    if not set(features.id).issubset(targets.id):
        raise ValueError("X contains IDs outside the core.")
    if not all(pd.api.types.is_numeric_dtype(features[c]) for c in names):
        raise ValueError("Features must be numeric.")
    if not np.isfinite(features[names].to_numpy(dtype=float)).all():
        raise ValueError("Features contain NaN or Inf; inspect the excluded-row handoff.")
    audit = audit_domain_overlap(targets)
    if audit["unknown_domain_rows"] != int(targets.registrable_domain.isna().sum()):
        raise ValueError("Noncanonical/invalid domain metadata; rebuild the reviewed handoff.")
    if audit["status"] == "overlap_detected":
        raise ValueError("Domain leakage between official splits; resolve before modeling.")
    work = features.merge(targets, on="id", validate="one_to_one").sort_values("id").reset_index(drop=True)
    train = work.loc[work.split.eq("train")].copy()
    validation = work.loc[work.split.eq("val")].copy()
    expected_train = targets.loc[targets.split.eq("train") & targets.registrable_domain.notna(), "id"]
    if set(train.id) != set(expected_train) or train.registrable_domain.isna().any():
        raise ValueError("Training features must cover exactly the resolved core train IDs.")
    if list(folds.columns) != ["id", "fold_id"] or set(folds.id) != set(train.id):
        raise ValueError("Folds must contain exactly the eligible train IDs; no val/test or missing IDs.")
    n_splits = config.get("evaluation", {}).get("n_splits", 3)
    if not pd.api.types.is_integer_dtype(folds.fold_id) or set(folds.fold_id) != set(range(n_splits)):
        raise ValueError("fold_id must contain the configured integer folds starting from 0.")
    expected_val = targets.loc[targets.split.eq("val") & targets.registrable_domain.notna(), "id"]
    if set(validation.id) != set(expected_val):
        raise ValueError("Validation features do not cover the resolved validation IDs.")
    train = train.merge(folds, on="id", validate="one_to_one")
    if not train.groupby("registrable_domain").fold_id.nunique().eq(1).all():
        raise ValueError("The same domain appears in more than one CV fold.")
    for frame in [train, validation]:
        frame["target"] = frame.label.map(LABEL_MAP).astype(int)
    if not train.target.isin([0, 1]).all() or train.target.nunique() != 2:
        raise ValueError("Training requires both classes.")
    for fold in range(n_splits):
        if any(train.loc[mask, "target"].nunique() != 2 for mask in
               [train.fold_id.eq(fold), train.fold_id.ne(fold)]):
            raise ValueError(f"Fold {fold} does not have both classes on each side.")
    if config.get("evaluation", {}).get("use_test", False):
        raise ValueError("Week-4 baseline does not support test evaluation.")
    return train, validation, names, audit


def _scores(estimator, X):
    classes = list(estimator.classes_)
    if 1 not in classes:
        raise ValueError("The fitted estimator has no phishing class.")
    scores = estimator.predict_proba(X)[:, classes.index(1)]
    if not np.isfinite(scores).all():
        raise ValueError("Non-finite model score.")
    return scores


def _fit(estimator, X, y):
    with warnings.catch_warnings(record=True) as messages:
        warnings.simplefilter("always", ConvergenceWarning)
        estimator.fit(X, y)
    if any(issubclass(m.category, ConvergenceWarning) for m in messages):
        raise RuntimeError("Logistic Regression did not converge; inspect the configuration.")
    return estimator



def _validate_config(config):
    """Reject unsupported choices rather than silently running another experiment."""
    fixed = {
        "model": {"baseline": "logistic_regression", "reference": "dummy_most_frequent",
                  "scaling": "standard_scaler_within_fold",
                  "selection_metric": "mean_group_cv_f1_phishing"},
        "evaluation": {"strategy": "group_cv_on_official_train",
                       "group_column": "registrable_domain", "validation_role": "supplementary"},
        "data": {"positive_label": "phishing", "negative_label": "benign", "id_column": "id",
                 "url_column": "url", "label_column": "label", "split_column": "split"},
    }
    for section, choices in fixed.items():
        for key, expected in choices.items():
            actual = config.get(section, {}).get(key, expected)
            if actual != expected:
                raise ValueError(f"Unsupported {section}.{key}={actual!r}; expected {expected!r}.")
    allowed_model = {*fixed["model"], "compare_balanced", "max_iter"}
    unknown = set(config.get("model", {})) - allowed_model
    if unknown:
        raise ValueError(f"Unsupported model settings: {sorted(unknown)}")
    if "core_tiers" in config.get("data", {}) and set(config["data"]["core_tiers"]) != {"gold", "silver"}:
        raise ValueError("Unsupported core_tiers; the baseline requires gold/silver.")
    if not isinstance(config.get("model", {}).get("compare_balanced", True), bool):
        raise ValueError("compare_balanced must be a boolean.")


def run_baseline(features: pd.DataFrame, targets: pd.DataFrame,
                 folds: pd.DataFrame, config: dict) -> dict:
    """CV is primary; official validation is supplementary; test is not predicted.

    Select between LR configurations by mean CV phishing F1 (tie: CV AP).
    Threshold is fixed in advance. Scaler is fit anew inside each fold.
    """
    _validate_config(config)
    train, validation, names, audit = _prepare_inputs(features, targets, folds, config)
    seed = int(config.get("experiment", {}).get("seed", 42))
    settings = config.get("model", {})
    threshold = float(config.get("evaluation", {}).get("decision_threshold", 0.5))
    if not 0 < threshold < 1:
        raise ValueError("decision_threshold must be strictly between 0 and 1.")
    models = {
        "dummy_most_frequent": build_dummy_baseline(),
        "logistic_regression": build_logistic_baseline(seed, max_iter=int(settings.get("max_iter", 2000))),
    }
    if settings.get("compare_balanced", True):
        models["logistic_regression_balanced"] = build_logistic_baseline(
            seed, "balanced", int(settings.get("max_iter", 2000)))
    rows, cv_predictions = [], []
    for name, prototype in models.items():
        for fold in sorted(train.fold_id.unique()):
            fitting = train.loc[train.fold_id.ne(fold)]
            held_out = train.loc[train.fold_id.eq(fold)]
            start = time.perf_counter()
            estimator = _fit(clone(prototype), fitting[names], fitting.target)
            elapsed = time.perf_counter() - start
            scores = _scores(estimator, held_out[names])
            predictions = (scores >= threshold).astype(int)
            rows.append({"model": name, "evaluation_partition": "group_cv",
                         "fold_id": int(fold), "threshold": threshold, "fit_seconds": elapsed,
                         **summarize_predictions(held_out.target.to_numpy(), predictions, scores)})
            cv_predictions.append(pd.DataFrame({
                "id": held_out.id.to_numpy(), "model": name, "fold_id": int(fold),
                "evaluation_partition": "group_cv", "true_label": held_out.target.to_numpy(),
                "predicted_label": predictions, "score": scores,
            }))
    cv_metrics = pd.DataFrame(rows)
    summary = cv_metrics.groupby("model", sort=False)[list(METRICS)].agg(["mean", "std"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    summary = summary.reset_index()
    ranking = summary.loc[summary.model.str.startswith("logistic_regression")].sort_values(
        ["f1_phishing_mean", "pr_auc_mean", "model"], ascending=[False, False, True])
    selected = ranking.iloc[0]["model"]
    validation_rows, validation_predictions, fitted = [], [], {}
    # Fit only core TRAIN, even though validation labels are available for reporting.
    for name, prototype in models.items():
        estimator = _fit(clone(prototype), train[names], train.target)
        fitted[name] = estimator
        if len(validation):
            scores = _scores(estimator, validation[names])
            predictions = (scores >= threshold).astype(int)
            validation_rows.append({"model": name, "evaluation_partition": "official_validation",
                                    "threshold": threshold,
                                    **summarize_predictions(validation.target.to_numpy(), predictions, scores)})
            validation_predictions.append(pd.DataFrame({
                "id": validation.id.to_numpy(), "model": name,
                "evaluation_partition": "official_validation", "true_label": validation.target.to_numpy(),
                "predicted_label": predictions, "score": scores,
            }))
    excluded = targets.loc[~targets.id.isin(features.id), ["id", "label", "split"]].copy()
    return {
        "cv_metrics": cv_metrics, "cv_summary": summary,
        "cv_predictions": pd.concat(cv_predictions, ignore_index=True),
        "validation_metrics": pd.DataFrame(validation_rows),
        "validation_predictions": pd.concat(validation_predictions, ignore_index=True)
            if validation_predictions else pd.DataFrame(),
        "selected_model": selected, "pipeline": fitted[selected],
        "feature_names": names, "decision_threshold": threshold,
        "selection_rule": "highest mean group-CV phishing F1; tie: average precision, then name",
        "scope": {"train_rows": len(train), "train_phishing": int(train.target.sum()),
                  "validation_rows": len(validation), "validation_phishing": int(validation.target.sum()),
                  "test_evaluated": False, "excluded_ids": excluded.to_dict("records"),
                  "domain_audit_status": audit["status"]},
    }


def predict_url(raw_url: str, pipeline, feature_names: list[str], threshold: float = 0.5) -> dict:
    parsed = parse_url(raw_url)
    if not parsed.is_valid:
        raise ValueError(f"URL cannot be analyzed: {parsed.error_reason}")
    values = extract_features_from_parsed(parsed)
    if len(feature_names) != len(set(feature_names)) or set(feature_names) != set(values):
        raise ValueError("Artifact feature schema does not match the extractor.")
    if not 0 < threshold < 1:
        raise ValueError("threshold must be strictly between 0 and 1.")
    X = pd.DataFrame([[values[c] for c in feature_names]], columns=feature_names)
    score = float(_scores(pipeline, X)[0])
    return {"label": "phishing" if score >= threshold else "benign", "score": score,
            "threshold": threshold, "score_definition": "uncalibrated model predict_proba for phishing"}
