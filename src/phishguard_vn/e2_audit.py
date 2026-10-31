"""Adapters and fail-closed E2 evidence checks; no advanced-model training.

Claims about training lineage require producer manifests, not inference from scores.
Passing these checks does not establish semantic absence of leakage by itself.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from phishguard_vn.evaluation_audit import check_ids, metrics_table, validate_predictions
from phishguard_vn.features import CANDIDATE_FEATURES

FORBIDDEN = {"id", "label", "target", "true_label", "predicted_label", "source", "tier", "split", "status",
             "scenario", "abuse_type", "is_https", "fold_id", "registrable_domain", "label_source", "collected_at", "scraped_at"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adapt_predictions(frame, column_map=None, partition_map=None, model=None):
    """Explicit producer-column -> canonical-column and partition-value mappings.

    Numeric labels/scores required: never guess a class order or invert scores.
    """
    mapping = column_map or {}
    if not set(mapping).issubset(frame.columns) or len(set(mapping.values())) != len(mapping):
        raise ValueError("Invalid prediction column adapter")
    renamed = [mapping.get(c, c) for c in frame]
    if len(renamed) != len(set(renamed)):
        raise ValueError("Adapter creates duplicate columns")
    frame = frame.rename(columns=mapping).copy()
    if partition_map:
        frame["evaluation_partition"] = frame.evaluation_partition.map(partition_map)
    if model is not None:
        if "model" in frame and not frame.model.eq(model).all():
            raise ValueError("Adapter model contradicts artifact")
        frame["model"] = model
    return frame


def assemble_brand_features(matrix, feature_names, metadata):
    """Explicit brand-only adapter; preserve incoming context/ID order and join E1 by ID."""
    keys = ["id", "fold_id"] if "fold_id" in matrix else ["id"]
    brands = [name for name in feature_names if name not in CANDIDATE_FEATURES]
    if list(matrix) != [*keys, *brands]:
        raise ValueError("Brand-only feature order/schema mismatch")
    if not set(matrix.id).issubset(set(metadata.id)):
        raise ValueError("Brand matrix contains ineligible IDs")
    merged = matrix.merge(metadata[["id", *CANDIDATE_FEATURES]], on="id", validate="many_to_one", sort=False)
    return merged[[*keys, *feature_names]]


def _contexts(metadata, folds):
    train = set(metadata.loc[metadata.split.eq("train"), "id"])
    return {**{str(f): train - set(folds.loc[folds.fold_id.eq(f), "id"]) for f in (0, 1, 2)}, "-1": train}


def validate_lineage(lineage, metadata, folds):
    """Reject declared held-out leakage and absent/incomplete training-ID evidence."""
    if lineage.get("hyperparameter_selection") != "inner_train_only" or lineage.get("threshold_selection") != "train_only":
        raise ValueError("Hyperparameter/threshold selection must be train-only inside each outer fold")
    expected = _contexts(metadata, folds)
    contexts = lineage.get("contexts", {})
    if set(contexts) != set(expected):
        raise ValueError("Require fold 0/1/2 and full-train (-1) lineage contexts")
    for context, ids in expected.items():
        record = contexts[context]
        fit = record.get("fit_ids", [])
        if len(fit) != len(set(fit)) or set(fit) != ids:
            raise ValueError(f"Training leakage/coverage in context {context}")
        if not record.get("config_sha256") or not record.get("producer_revision"):
            raise ValueError("Missing config hash/producer revision")
    return expected


def validate_feature_matrix(matrix, feature_names, dictionary, references, metadata, folds):
    """Accept frozen external references or explicit fold-local matrices.

    Fold-local rows: each context 0/1/2 covers all eligible train IDs, context -1
    covers train+val. Matrix contains id,fold_id,then feature_names in exact order.
    No label-informed globally computed brand-reference matrix is accepted.
    """
    if not feature_names or any(not isinstance(n, str) or not n.strip() for n in feature_names) or len(feature_names) != len(set(feature_names)):
        raise ValueError("Missing/duplicate feature order")
    if any(name.lower() in FORBIDDEN or any(token in name.lower() for token in
           ("label", "source", "tier", "split", "target", "scraped", "collected", "https")) for name in feature_names):
        raise ValueError("Forbidden metadata/post-hoc feature")
    if not set(CANDIDATE_FEATURES).issubset(feature_names):
        raise ValueError("E2 must declare the unchanged E1 lexical feature contract")
    if len(feature_names) <= len(CANDIDATE_FEATURES):
        raise ValueError("E2 brand experiment requires at least one additional feature")
    if not {"feature", "definition", "inputs", "version"}.issubset(dictionary.columns):
        raise ValueError("Incomplete feature dictionary")
    if dictionary.feature.duplicated().any() or list(dictionary.feature) != feature_names:
        raise ValueError("Dictionary feature order mismatch")
    if dictionary[["definition", "inputs", "version"]].isna().any().any() or dictionary[["definition", "inputs", "version"]].astype(str).apply(lambda x: x.str.strip().eq("")).any().any():
        raise ValueError("Blank dictionary definitions/lineage")
    for inputs in dictionary.inputs:
        if set(re.findall(r"[a-z_]+", str(inputs).lower())) & FORBIDDEN:
            raise ValueError("Dictionary declares forbidden metadata inputs")
    scope = references.get("scope")
    if scope not in ("frozen_external", "fold_local") or not references.get("version"):
        raise ValueError("Missing/unsupported brand reference scope/version")
    records = references.get("records", [])
    required = {"reference_id", "source", "sha256", "obtained_at"}
    if not records or any(not required.issubset(r) or any(not r[k] for k in required) for r in records):
        raise ValueError("Missing reference evidence")
    if any(not re.fullmatch(r"[0-9a-fA-F]{64}", r["sha256"]) for r in records):
        raise ValueError("Reference SHA256 must be 64 hexadecimal characters")
    if pd.to_datetime([r["obtained_at"] for r in records], errors="coerce", utc=True).isna().any():
        raise ValueError("Invalid reference collection date")
    if len({r["reference_id"] for r in records}) != len(records):
        raise ValueError("Duplicate reference IDs")
    if scope == "frozen_external":
        if references.get("selection_scope") != "external_fixed" or references.get("independent_of_dataset") is not True:
            raise ValueError("Global brand references must be independent and frozen externally")
        if any(record.get("dataset_ids") for record in records):
            raise ValueError("Frozen external references declare dataset-derived selection")
        expected_columns = ["id", *feature_names]
        check_ids(matrix, "E2 features")
        if set(matrix.id) != set(metadata.id):
            raise ValueError("Feature eligibility/coverage mismatch")
    else:
        expected_columns = ["id", "fold_id", *feature_names]
        expected = _contexts(metadata, folds)
        if "fold_id" not in matrix or not pd.api.types.is_integer_dtype(matrix.fold_id) or set(matrix.fold_id) != {0, 1, 2, -1}:
            raise ValueError("Missing fold-local feature contexts")
        contexts = references.get("contexts", {})
        if set(contexts) != set(expected):
            raise ValueError("Missing reference fit contexts")
        reference_ids = {r["reference_id"] for r in records}
        for key, fit_ids in expected.items():
            evidence = contexts[key]
            supplied = evidence.get("fit_ids", [])
            if len(supplied) != len(set(supplied)) or set(supplied) != fit_ids:
                raise ValueError("Brand reference selection includes held-out IDs or has incomplete coverage")
            selected_refs = evidence.get("reference_ids", [])
            if not selected_refs or not set(selected_refs).issubset(reference_ids):
                raise ValueError("Unknown/missing context reference IDs")
            block = matrix.loc[matrix.fold_id.eq(int(key))]
            check_ids(block, "fold-local features")
            ids = set(metadata.id) if key == "-1" else set(metadata.loc[metadata.split.eq("train"), "id"])
            if set(block.id) != ids:
                raise ValueError("Fold-local feature coverage mismatch")
    if list(matrix.columns) != expected_columns:
        raise ValueError("Feature order/schema mismatch")
    if not all(pd.api.types.is_numeric_dtype(matrix[c]) for c in feature_names) or not np.isfinite(matrix[feature_names].to_numpy(dtype=float)).all():
        raise ValueError("Non-numeric or NaN/Inf E2 features")
    return {"feature_scope": scope, "rows": len(matrix), "features": len(feature_names),
            "limitation": "Producer reference independence/semantics still require code and data-owner review."}


def validate_source_evidence(evidence, metadata):
    """Optional Khiêm evidence; keep pilot/source findings out of model inputs.

    JSON records are observations, never automatically verified causal findings.
    External pilot IDs must be disjoint from the official evaluation population.
    """
    required = {"producer_revision", "population", "collection_protocol", "label_policy", "records"}
    if not required.issubset(evidence) or any(not evidence[k] for k in required):
        raise ValueError("Incomplete source/pilot provenance")
    if evidence.get("official_test_used") is not False:
        raise ValueError("Source evidence must explicitly exclude official Test")
    if evidence["population"] not in ("official_train_val", "external_pilot"):
        raise ValueError("Unknown source evidence population")
    records = pd.DataFrame(evidence["records"])
    if not {"source", "observation", "review_status"}.issubset(records):
        raise ValueError("Source evidence missing observations/review status")
    if evidence["population"] == "external_pilot":
        check_ids(records, "external pilot")
        if set(records.id) & set(metadata.id):
            raise ValueError("Pilot reuses official population IDs")
        if not {"label", "collected_at", "label_provenance"}.issubset(records):
            raise ValueError("Pilot labels lack provenance")
        if not records.label.isin(["benign", "phishing"]).all():
            raise ValueError("Unknown pilot label")
        if records[["collected_at", "label_provenance"]].isna().any().any():
            raise ValueError("Missing pilot dates/label provenance")
    elif not set(records.source).issubset(set(metadata.source)):
        raise ValueError("Source audit names outside official train/validation population")
    return {"population": evidence["population"], "records": len(records),
            "status": "provenance schema checked; findings need analyst review; no pilot model metrics computed"}


def paired_comparison(e1, e2):
    """Compare all supplied candidates on identical IDs/labels/folds, threshold pre-fixed."""
    rows = []
    for name, candidate in e2.groupby("model"):
        keys = ["id", "evaluation_partition"]
        if e1.duplicated(keys).any() or candidate.duplicated(keys).any():
            raise ValueError("Choose one E1 reference; duplicate comparison keys")
        joined = e1.merge(candidate, on=keys, suffixes=("_e1", "_e2"), validate="one_to_one", how="outer", indicator=True)
        if not joined._merge.eq("both").all() or not joined.true_label_e1.eq(joined.true_label_e2).all():
            raise ValueError("Unmatched paired IDs/labels")
        if not joined.fold_id_e1.fillna(-1).eq(joined.fold_id_e2.fillna(-1)).all():
            raise ValueError("Paired folds disagree")
        for partition in candidate.evaluation_partition.unique():
            left = e1.loc[e1.evaluation_partition.eq(partition)]
            right = candidate.loc[candidate.evaluation_partition.eq(partition)]
            for fold in ([None, 0, 1, 2] if partition == "group_cv" else [None]):
                a = left if fold is None else left.loc[left.fold_id.eq(fold)]
                b = right if fold is None else right.loc[right.fold_id.eq(fold)]
                ma = metrics_table(a, ["evaluation_partition"]).iloc[0]
                mb = metrics_table(b, ["evaluation_partition"]).iloc[0]
                record = {"model": name, "evaluation_partition": partition, "fold_id": fold,
                          "aggregation": "pooled" if fold is None else "per_fold", "n_paired": len(a)}
                for metric in ["precision_phishing", "recall_phishing", "f1_phishing", "pr_auc", "false_positive_rate", "fp_per_1000_benign"]:
                    record.update({metric + "_e1": ma[metric], metric + "_e2": mb[metric], metric + "_delta": mb[metric] - ma[metric]})
                rows.append(record)
    return pd.DataFrame(rows)


def load_e2_bundle(manifest_path, metadata, folds, e1, *, threshold=0.5):
    """JSON manifest paths are relative to the manifest; verify every artifact SHA256."""
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1 or not manifest.get("feature_version") or not manifest.get("producer_revision"):
        raise ValueError("Missing E2 schema/feature version/producer revision")
    if manifest.get("threshold") != threshold or manifest.get("score_definition") != "phishing_probability":
        raise ValueError("Incompatible E2 threshold or class-score definition")
    artifacts = manifest.get("artifacts", {})
    required = {"features", "dictionary", "references", "predictions", "folds", "lineage", "configs"}
    if not required.issubset(artifacts):
        raise ValueError(f"Missing E2 artifacts: {sorted(required - set(artifacts))}")
    files = {}
    for key, record in artifacts.items():
        target = path.parent / record["path"]
        if not target.is_file() or sha256(target) != record["sha256"]:
            raise ValueError(f"Missing artifact or SHA256 mismatch: {key}")
        files[key] = target
    incoming_folds = pd.read_csv(files["folds"], dtype={"id": "string"})
    check_ids(incoming_folds, "E2 folds")
    pd.testing.assert_frame_equal(incoming_folds.sort_values("id").reset_index(drop=True),
                                  folds.sort_values("id").reset_index(drop=True), check_dtype=False)
    dictionary = pd.read_csv(files["dictionary"])
    references = json.loads(files["references"].read_text())
    matrix = pd.read_csv(files["features"], dtype={"id": "string"})
    layout = manifest.get("feature_layout", "combined")
    if layout == "brand_only":
        matrix = assemble_brand_features(matrix, manifest["feature_names"], metadata)
    elif layout != "combined":
        raise ValueError("Unknown feature_layout; expected combined or brand_only")
    feature_check = validate_feature_matrix(matrix, manifest["feature_names"], dictionary, references, metadata, folds)
    # Detect drift in the lexical block, even if brand columns look valid.
    for _, block in matrix.groupby("fold_id") if "fold_id" in matrix else [(None, matrix)]:
        canonical = metadata.set_index("id").loc[block.id, list(CANDIDATE_FEATURES)].to_numpy(dtype=float)
        if not np.allclose(block[list(CANDIDATE_FEATURES)].to_numpy(dtype=float), canonical, rtol=0, atol=1e-10):
            raise ValueError("E1 lexical features changed under E2 contract")
    predictions = adapt_predictions(pd.read_csv(files["predictions"], dtype={"id": "string"}), **manifest.get("adapter", {}))
    predictions = validate_predictions(predictions, metadata, folds, threshold=threshold)
    configs = json.loads(files["configs"].read_text())
    lineage = json.loads(files["lineage"].read_text())
    if set(configs) != set(predictions.model) or set(lineage) != set(predictions.model):
        raise ValueError("Model/config/lineage mismatch")
    candidates = manifest.get("teacher_candidates", [])
    if len(candidates) > 2 or len(set(candidates)) != len(candidates) or not set(candidates).issubset(configs):
        raise ValueError("Teacher candidate list must contain at most two supplied models")
    for name in configs:
        if (configs[name].get("feature_names") != manifest["feature_names"]
                or configs[name].get("feature_version") != manifest["feature_version"]
                or configs[name].get("reference_version") != references["version"]):
            raise ValueError("Model config feature order/version/reference version mismatch")
        expected_hash = hashlib.sha256(json.dumps(configs[name], sort_keys=True).encode()).hexdigest()
        validate_lineage(lineage[name], metadata, folds)
        if any(v["config_sha256"] != expected_hash for v in lineage[name]["contexts"].values()):
            raise ValueError("Lineage config hash mismatch")
    source_checks = {key: validate_source_evidence(json.loads(files[key].read_text()), metadata)
                     for key in ("source_bias", "external_pilot") if key in files}
    return {"manifest": manifest, "predictions": predictions, "feature_check": feature_check,
            "source_evidence": source_checks,
            "comparison": paired_comparison(e1, predictions),
            "status": "E2 metrics verified; robustness requires a supplied local predictor adapter"}
