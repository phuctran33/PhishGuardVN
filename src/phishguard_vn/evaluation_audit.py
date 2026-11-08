"""ID-aligned audit of held-out predictions. No model/threshold selection here."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phishguard_vn.data import LABEL_MAP
from phishguard_vn.evaluation import summarize_predictions

PREDICTION_COLUMNS = {"id", "model", "evaluation_partition", "true_label", "predicted_label", "score"}


def check_ids(frame, name="table"):
    if "id" not in frame or frame.empty:
        raise ValueError(f"{name}: missing id or empty table")
    if frame.id.isna().any() or not frame.id.is_unique or not frame.id.map(
        lambda x: isinstance(x, str) and bool(x.strip())
    ).all():
        raise ValueError(f"{name}: duplicate, missing or invalid IDs")


def validate_predictions(predictions, metadata, folds, *, threshold=0.5, thresholds=None):
    """Require exact eligible coverage per model/partition; reject test and bad joins.

    Metadata contains only eligible core train/val rows. Fold mapping is authoritative.
    This validates structure, not proof of a third party's training provenance.
    """
    missing = PREDICTION_COLUMNS - set(predictions)
    if missing:
        raise ValueError(f"Missing prediction columns: {sorted(missing)}")
    if not 0 < threshold < 1:
        raise ValueError("Invalid threshold")
    check_ids(metadata, "metadata")
    check_ids(folds, "folds")
    if not metadata.split.isin(["train", "val"]).all() or not metadata.tier.isin(["gold", "silver"]).all():
        raise ValueError("Only eligible core train/val metadata accepted; test forbidden")
    if not metadata.label.isin(LABEL_MAP).all() or metadata.registrable_domain.isna().any():
        raise ValueError("Unknown label or unresolved domain")
    train_ids = set(metadata.loc[metadata.split.eq("train"), "id"])
    if set(folds.id) != train_ids or not pd.api.types.is_integer_dtype(folds.fold_id):
        raise ValueError("Fold eligibility/coverage or dtype mismatch")
    if set(folds.fold_id) != {0, 1, 2}:
        raise ValueError("Expected the agreed three folds: 0,1,2")
    groups = metadata.loc[metadata.split.eq("train")].merge(folds, on="id", validate="one_to_one")
    if groups.groupby("registrable_domain").fold_id.nunique().gt(1).any():
        raise ValueError("Domain crosses folds")
    if set(groups.registrable_domain) & set(metadata.loc[metadata.split.eq("val"), "registrable_domain"]):
        raise ValueError("Domain crosses official train/validation")
    if predictions.empty or predictions.model.isna().any() or predictions.model.astype(str).str.strip().eq("").any():
        raise ValueError("Missing predictions or model")
    if thresholds is not None and set(thresholds) != set(predictions.model):
        raise ValueError("Candidate threshold/model mismatch")
    partitions = {"group_cv": "train", "official_validation": "val"}
    if not predictions.evaluation_partition.isin(partitions).all():
        raise ValueError("Unknown partition; test/in-sample predictions forbidden")
    joined = []
    for model, model_rows in predictions.groupby("model"):
        expected_parts = {p for p, s in partitions.items() if metadata.split.eq(s).any()}
        if set(model_rows.evaluation_partition) != expected_parts:
            raise ValueError(f"{model}: missing evaluation partition")
        for partition, rows in model_rows.groupby("evaluation_partition"):
            check_ids(rows, f"{model}/{partition}")
            expected = metadata.loc[metadata.split.eq(partitions[partition])]
            if set(rows.id) != set(expected.id):
                raise ValueError(f"{model}/{partition}: coverage mismatch")
            # Ignore no overlapping columns silently: metadata/fold collisions would hide drift.
            if (set(rows) & set(metadata)) - {"id"}:
                raise ValueError("Prediction schema collides with metadata; use explicit adapter")
            block = rows.merge(expected, on="id", validate="one_to_one")
            if not block.true_label.eq(block.label.map(LABEL_MAP)).all():
                raise ValueError("Label mismatch by ID")
            summarize_predictions(block.true_label, block.predicted_label, block.score)
            if not pd.api.types.is_numeric_dtype(block.score):
                raise ValueError("Prediction scores must be numeric")
            if partition == "group_cv":
                if "fold_id" not in block or not pd.api.types.is_integer_dtype(block.fold_id):
                    # A concatenated CV/val frame promotes fold_id to float; integral values are allowed.
                    if "fold_id" not in block or block.fold_id.isna().any() or not block.fold_id.mod(1).eq(0).all():
                        raise ValueError("Missing/integral fold_id required")
                canonical = folds.set_index("id").fold_id.reindex(block.id).to_numpy()
                if not np.array_equal(block.fold_id.to_numpy(), canonical):
                    raise ValueError("Fold mismatch by ID")
            elif "fold_id" in block and block.fold_id.notna().any():
                raise ValueError("Validation must not have a CV fold")
            if thresholds is None:
                decisions = threshold
            else:
                contexts = block.fold_id.astype(int).astype(str) if partition == "group_cv" else pd.Series("-1", index=block.index)
                decisions = contexts.map(thresholds[model])
                if decisions.isna().any() or not decisions.between(0, 1, inclusive="neither").all():
                    raise ValueError("Missing/invalid candidate context threshold")
                block["decision_threshold"] = decisions
            if not block.predicted_label.eq(block.score.ge(decisions).astype(int)).all():
                raise ValueError("Prediction/threshold mismatch")
            block["outcome"] = np.select(
                [block.true_label.eq(1) & block.predicted_label.eq(1),
                 block.true_label.eq(0) & block.predicted_label.eq(1),
                 block.true_label.eq(0) & block.predicted_label.eq(0)], ["TP", "FP", "TN"], default="FN")
            joined.append(block)
    return pd.concat(joined, ignore_index=True).sort_values(["model", "evaluation_partition", "id"]).reset_index(drop=True)


def metrics_table(frame, dimensions):
    rows = []
    for keys, block in frame.groupby(dimensions, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        metric = summarize_predictions(block.true_label, block.predicted_label, block.score)
        metric["fp_per_1000_benign"] = 1000 * metric["false_positive_rate"] if metric["n_benign"] else None
        rows.append({**dict(zip(dimensions, keys)), **metric})
    return pd.DataFrame(rows)


def stratified_metrics(frame):
    """Fixed descriptive bins; never tuned on validation or used to fit models."""
    work = frame.copy()
    work["url_length_bin"] = pd.cut(work.url_len, [-np.inf, 20, 40, 80, 160, np.inf], right=True).astype(str)
    work["entropy_bin"] = pd.cut(work.entropy, [-np.inf, 3, 4, 5, np.inf], right=True).astype(str)
    tables = []
    for dimension in ["fold_id", "source", "tier", "url_length_bin", "entropy_bin", "registrable_domain"]:
        table = metrics_table(work, ["model", "evaluation_partition", dimension])
        table = table.rename(columns={dimension: "stratum"})
        table.insert(2, "dimension", dimension)
        tables.append(table)
    return pd.concat(tables, ignore_index=True)


def distribution_shift(metadata):
    rows = []
    for dimension in ["source", "tier", "label"]:
        counts = pd.crosstab(metadata[dimension].fillna("(missing)"), metadata.split).reindex(columns=["train", "val"], fill_value=0)
        shares = counts.div(counts.sum(axis=0), axis=1)
        for value in counts.index:
            rows.append({"dimension": dimension, "stratum": value,
                         "train_n": int(counts.loc[value, "train"]), "val_n": int(counts.loc[value, "val"]),
                         "train_share": shares.loc[value, "train"], "val_share": shares.loc[value, "val"],
                         "share_delta_val_minus_train": shares.loc[value, "val"] - shares.loc[value, "train"]})
    return pd.DataFrame(rows)
