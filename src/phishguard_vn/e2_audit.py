"""Adapters and fail-closed E2 evidence checks; no advanced-model training.

Claims about training lineage require producer manifests, not inference from scores.
Passing these checks does not establish semantic absence of leakage by itself.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold

from phishguard_vn.evaluation_audit import check_ids, metrics_table, validate_predictions
from phishguard_vn.features import CANDIDATE_FEATURES

FORBIDDEN = {"id", "label", "target", "true_label", "predicted_label", "source", "tier", "split", "status",
             "scenario", "abuse_type", "is_https", "fold_id", "registrable_domain", "label_source", "collected_at", "scraped_at"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_native_predictions(frame, metadata, folds, partition, models):
    """Phúc's native predict labels: probabilities > .5; signed SVC margins > 0.

    Native estimators choose class 0 on a probability tie. Exact SVC zero-margin
    labels are solver dependent, so reject ties for explicit producer review.
    """
    expected = metadata.loc[metadata.split.eq("train" if partition == "group_cv" else "val")].set_index("id")
    candidates = {f"{arm}__{model}" for arm in ("E1", "E2") for model in models}
    if (set(frame.candidate) != candidates or frame.duplicated(["candidate", "id"]).any()
            or not frame.evaluation_partition.eq(partition).all()):
        raise ValueError("Native candidate/partition/duplicate ID mismatch")
    for candidate, rows in frame.groupby("candidate"):
        if set(rows.id) != set(expected.index):
            raise ValueError("Native missing/unexpected IDs (including Test)")
        truth = expected.label.map({"benign": 0, "phishing": 1}).reindex(rows.id).to_numpy()
        if not np.array_equal(rows.true_label, truth):
            raise ValueError("Native label mismatch")
        if partition == "group_cv":
            if not np.array_equal(rows.fold_id, folds.set_index("id").fold_id.reindex(rows.id)):
                raise ValueError("Native fold mismatch")
        elif "fold_id" in rows and not rows.fold_id.isna().all():
            raise ValueError("Native Validation must not have outer folds")
        model = candidate.split("__", 1)[1]
        margin = model == "svm_rbf"
        if (not rows.candidate.eq(rows.feature_set + "__" + rows.model).all()
                or not rows.decision_rule.eq("estimator.predict").all()
                or not rows.score_kind.eq("decision_function" if margin else "probability").all()
                or not np.isfinite(rows.score).all()
                or (margin and rows.score.eq(0).any())
                or (not margin and not rows.score.between(0, 1).all())
                or not np.array_equal(rows.predicted_label, rows.score.gt(0 if margin else .5).astype(int))):
            raise ValueError("Native score semantics/predicted label mismatch")


def _native_metrics(rows):
    """Use ranking scores directly for AP, including unbounded SVM margins."""
    y, pred = rows.true_label, rows.predicted_label
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"accuracy": (tn + tp) / len(rows), "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "precision_phishing": precision_score(y, pred, zero_division=0),
            "recall_phishing": recall_score(y, pred, zero_division=0), "f1_phishing": f1_score(y, pred, zero_division=0),
            "pr_auc": average_precision_score(y, rows.score), "false_positive_rate": fp / (fp + tn)}


def audit_native_model_handoff(producer_root, metadata, folds, root):
    """Read native gzip handoff from a clean producer checkout; never fit/load models.

    Recheck IDs, outer/inner domain partitions and published metrics. Original
    training execution is supported by the separate PR code review, not proved
    from prediction files alone. Windows raw input hashes are retained without
    claiming byte equality to regenerated local CSVs.
    """
    from phishguard_vn.brand_features import E2_FEATURES, FEATURE_SCHEMA_VERSION

    producer_root, root = Path(producer_root).resolve(), Path(root).resolve()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=producer_root, text=True).strip()
    revision = git("rev-parse", "HEAD")
    # Separate worktree is read-only. A merged/current checkout may contain Hung edits.
    if producer_root != root and git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Native producer checkout has modified tracked files")
    tables = producer_root / "reports/tables"
    read = lambda name: pd.read_csv(tables / name, dtype={"id": "string"})
    meta = json.loads((tables / "06_ablation_metadata.json").read_text())
    if (meta.get("protocol") != "week5_e1_e2_readable_v1" or meta.get("feature_schema_version") != FEATURE_SCHEMA_VERSION
            or meta.get("feature_sets") != {"E1": list(CANDIDATE_FEATURES), "E2": list(E2_FEATURES)}
            or meta.get("class_order") != [0, 1] or meta.get("decision_rule") != "estimator.predict"
            or meta.get("boundaries") != {"svm_rbf": 0., "other_models": .5}
            or meta.get("seed") != 42 or meta.get("outer_folds") != 3 or meta.get("inner_folds") != 2
            or meta.get("test_evaluated") is not False):
        raise ValueError("Native provenance/schema/score contract mismatch")
    lf_sha = lambda path: hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    for name in ("features.py", "url_parser.py", "brand_features.py"):
        expected = meta["extractor_source_lf_sha256"][name]
        if any(lf_sha(base / "src/phishguard_vn" / name) != expected for base in (root, producer_root)):
            raise ValueError("Native extractor hash mismatch")
    reference = "src/phishguard_vn/resources/brand_reference_v1.csv"
    if any(lf_sha(base / reference) != meta["reference_lf_sha256"] for base in (root, producer_root)):
        raise ValueError("Native reference hash mismatch")
    notebook = json.loads((producer_root / "notebooks/05_e2_ablation.ipynb").read_text())
    code = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code")
    if hashlib.sha256(code.encode()).hexdigest() != meta["notebook_code_sha256"]:
        raise ValueError("Native notebook code hash mismatch")
    artifacts = ("06_oof_predictions.csv.gz", "06_validation_predictions.csv.gz", "06_training_partitions.csv.gz")
    if any(sha256(tables / n) != meta["artifact_sha256"].get("reports/tables/" + n) for n in artifacts):
        raise ValueError("Native compressed artifact hash mismatch")
    oof, validation, partitions = map(read, artifacts)
    models = ("logistic_regression", "logistic_regression_balanced", "svm_rbf", "mlp", "hist_gradient_boosting")
    if meta.get("score_kinds") != {m: "decision_function" if m == "svm_rbf" else "probability" for m in models}:
        raise ValueError("Native metadata score semantics mismatch")
    for frame, partition in ((oof, "group_cv"), (validation, "official_validation")):
        _validate_native_predictions(frame, metadata, folds, partition, models)
    train = metadata.loc[metadata.split.eq("train")].sort_values("id").set_index("id")
    val = metadata.loc[metadata.split.eq("val")]
    if (len(train) != meta["train_rows"] or len(val) != meta["validation_rows"]
            or not set(train.registrable_domain).isdisjoint(val.registrable_domain)):
        raise ValueError("Native Train/Validation supports or domain overlap")
    if (partitions.duplicated(["context", "id"]).any() or set(partitions.context.astype(str)) != {"0", "1", "2", "full_train"}
            or not partitions.role.isin(["fitting", "held_out"]).all()):
        raise ValueError("Native partition coverage/roles mismatch")
    supports = []
    for context, rows in partitions.groupby("context"):
        held_ids = set() if context == "full_train" else set(folds.loc[folds.fold_id.eq(int(context)), "id"])
        fitting, held = rows.loc[rows.role.eq("fitting")], rows.loc[rows.role.eq("held_out")]
        if (set(rows.id) != set(train.index) or set(held.id) != held_ids
                or set(fitting.id) != set(train.index) - held_ids or not held.inner_fold_id.eq(-1).all()):
            raise ValueError("Native outer fitting/held-out leakage or coverage mismatch")
        fit = train.loc[sorted(fitting.id)]
        if not set(fit.registrable_domain).isdisjoint(train.loc[sorted(held_ids)].registrable_domain):
            raise ValueError("Native outer domain leakage")
        if not set(fitting.inner_fold_id).issubset({0, 1}):
            raise ValueError("Native inner fold mismatch")
        inner = StratifiedGroupKFold(n_splits=2, shuffle=True, random_state=42)
        for j, (a, b) in enumerate(inner.split(np.zeros(len(fit)), fit.label, fit.registrable_domain)):
            if (set(fitting.loc[fitting.inner_fold_id.eq(j), "id"]) != set(fit.iloc[b].index)
                    or not set(fit.iloc[a].registrable_domain).isdisjoint(fit.iloc[b].registrable_domain)):
                raise ValueError("Native inner fitting/selection leakage or fold mismatch")
        supports.append({"context": str(context), "fitting": len(fitting), "held_out": len(held)})
    cv = pd.DataFrame([{"candidate": c, "fold_id": f, **_native_metrics(r)} for (c, f), r in oof.groupby(["candidate", "fold_id"])])
    supplementary = pd.DataFrame([{"candidate": c, **_native_metrics(r)} for c, r in validation.groupby("candidate")])
    metric_names = ["pr_auc", "precision_phishing", "recall_phishing", "f1_phishing", "false_positive_rate"]
    summary = cv.groupby("candidate")[metric_names].agg(["mean", "std"])
    summary.columns = ["_".join(c) for c in summary.columns]
    summary = summary.reset_index()
    cv["model"] = cv.candidate.str.split("__").str[1]
    paired = cv.loc[cv.candidate.str.startswith("E1__")].merge(cv.loc[cv.candidate.str.startswith("E2__")], on=["model", "fold_id"], suffixes=("_e1", "_e2"), validate="one_to_one")
    for metric in metric_names:
        paired["delta_" + metric] = paired[metric + "_e2"] - paired[metric + "_e1"]
    errors = {}
    all_metrics = ["accuracy", "tn", "fp", "fn", "tp", *metric_names]
    for name, actual, keys, columns in [
        ("06_cv_metrics.csv", cv, ["candidate", "fold_id"], all_metrics),
        ("06_validation.csv", supplementary, ["candidate"], all_metrics),
        ("06_comparison.csv", summary, ["candidate"], list(summary.columns[1:])),
        ("06_paired_folds.csv", paired, ["model", "fold_id"], [m + s for m in metric_names for s in ("_e1", "_e2")] + ["delta_" + m for m in metric_names])]:
        joined = actual.merge(read(name), on=keys, how="outer", suffixes=("_audit", "_reported"), indicator=True, validate="one_to_one")
        a, b = (joined[[c + suffix for c in columns]].to_numpy(dtype=float) for suffix in ("_audit", "_reported"))
        if not joined._merge.eq("both").all() or not np.allclose(a, b, atol=1e-12, rtol=0):
            raise ValueError("Native published metric mismatch: " + name)
        errors[name] = float(np.max(np.abs(a - b)))
    summary["family"] = summary.candidate.str.split("__").str[1].replace({"logistic_regression_balanced": "logistic_regression"})
    shortlist = summary.sort_values(["pr_auc_mean", "f1_phishing_mean", "false_positive_rate_mean", "candidate"], ascending=[False, False, True, True]).drop_duplicates("family").head(2).candidate.tolist()
    if shortlist != meta["teacher_candidates"]:
        raise ValueError("Native Train-only shortlist mismatch")
    names = [*artifacts, "06_ablation_metadata.json", "06_comparison.csv", "06_paired_folds.csv", "06_cv_metrics.csv", "06_validation.csv", "06_verification.json"]
    audit = {"status": "PASS", "feature_status": meta["status"], "producer_revision": revision,
             "producer_runtime_base_revision": meta["runtime_git_revision"], "producer_runtime_dirty": meta["runtime_git_dirty"],
             "protocol": meta["protocol"], "feature_schema_version": meta["feature_schema_version"], "producer_versions": meta["versions"],
             "artifact_sha256": {"reports/tables/" + n: sha256(tables / n) for n in names},
             "reference_lf_sha256": meta["reference_lf_sha256"], "producer_reference": meta["reference"],
             "producer_raw_input_sha256": meta["input_sha256"], "extractor_source_lf_sha256": meta["extractor_source_lf_sha256"],
             "notebook_code_sha256": meta["notebook_code_sha256"], "rows": dict(zip(("oof", "validation", "training_partitions"), map(len, (oof, validation, partitions)))),
             "partition_supports": supports, "table_max_abs_errors": errors, "teacher_candidates_train_only": shortlist,
             "summary": summary.to_dict("records"), "validation": supplementary.to_dict("records"),
             "e2_robustness": "E2_ROBUSTNESS_PENDING_MODEL_ARTIFACT",
             "limitations": "Prediction/partition and committed-code audit; original fitting execution/weights not replayed. Raw Windows input hashes are not asserted equal to regenerated local CSV bytes. Draft reference; source-label confounding; 24 Validation positives; one seed and 3 correlated folds."}
    return audit, paired.drop(columns=["candidate_e1", "candidate_e2"])


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
    if any(name.lower() in FORBIDDEN or re.search(
           r"(^|_)(label|source|tier|split|target|scraped|collected|https)(_|$)", name.lower()) for name in feature_names):
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
        if references.get("selection_scope") != "train_only":
            raise ValueError("Fold-local references must declare train-only selection")
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
                values = sorted(b.decision_threshold.unique().tolist()) if "decision_threshold" in b else [0.5]
                record.update(e1_threshold=0.5, e2_thresholds=json.dumps(values),
                              operating_point="fixed_0.5" if values == [0.5] else "candidate_train_selected")
                for metric in ["precision_phishing", "recall_phishing", "f1_phishing", "pr_auc", "false_positive_rate", "fp_per_1000_benign"]:
                    record.update({metric + "_e1": ma[metric], metric + "_e2": mb[metric], metric + "_delta": mb[metric] - ma[metric]})
                rows.append(record)
    return pd.DataFrame(rows)


def validate_candidate_thresholds(manifest, models, metadata, folds, verified_artifacts):
    """Optional outer-context operating points; E1 reference always remains 0.5.

    Check declared inner-OOF selection IDs and hashed producer evidence. The
    producer's optimization algorithm and evidence still require semantic review.
    """
    records = manifest.get("decision_thresholds")
    if records is None:
        return {name: {key: 0.5 for key in _contexts(metadata, folds)} for name in models}
    if set(records) != set(models):
        raise ValueError("Threshold records must cover exactly the candidate models")
    expected = _contexts(metadata, folds)
    thresholds = {}
    for name in models:
        if set(records[name]) != set(expected):
            raise ValueError("Missing threshold-selection context")
        thresholds[name] = {}
        for key, allowed in expected.items():
            record = records[name][key]
            value = record.get("value")
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or not 0 < value < 1:
                raise ValueError("Invalid candidate threshold")
            selected = record.get("selection_ids", [])
            if not selected or len(selected) != len(set(selected)) or not set(selected).issubset(allowed):
                raise ValueError("Threshold selection includes held-out/Validation IDs or lacks evidence")
            if record.get("selection_scope") != "inner_train_only" or record.get("prediction_kind") != "inner_oof":
                raise ValueError("Candidate thresholds require inner train-only OOF selection")
            artifact = record.get("evidence_artifact", "")
            if not artifact.startswith("threshold_") or artifact not in verified_artifacts or not isinstance(record.get("method"), str) or not record["method"].strip():
                raise ValueError("Missing hashed threshold-selection evidence/method")
            evidence = pd.read_csv(verified_artifacts[artifact], dtype={"id": "string", "context": "string"})
            required = {"id", "model", "context", "true_label", "score", "inner_fold_id"}
            if not required.issubset(evidence):
                raise ValueError("Threshold evidence must contain inner-OOF predictions")
            block = evidence.loc[evidence.model.eq(name) & evidence.context.eq(key)]
            check_ids(block, "threshold selection predictions")
            if set(block.id) != set(selected):
                raise ValueError("Threshold evidence/selection ID mismatch")
            labels = metadata.set_index("id").label.map({"benign": 0, "phishing": 1}).reindex(block.id).to_numpy()
            if (not np.array_equal(block.true_label.to_numpy(), labels) or not pd.api.types.is_numeric_dtype(block.score)
                    or not np.isfinite(block.score).all() or not block.score.between(0, 1).all()):
                raise ValueError("Threshold evidence label/score mismatch")
            if not pd.api.types.is_integer_dtype(block.inner_fold_id) or block.inner_fold_id.lt(0).any() or block.inner_fold_id.nunique() < 2:
                raise ValueError("Threshold evidence requires multiple inner folds")
            inner_fit = record.get("inner_fit_ids", {})
            if set(inner_fit) != {str(int(f)) for f in block.inner_fold_id.unique()}:
                raise ValueError("Missing inner threshold-model fit lineage")
            domains = metadata.set_index("id").registrable_domain
            calibration = block.assign(domain=domains.reindex(block.id).to_numpy())
            if calibration.groupby("domain").inner_fold_id.nunique().gt(1).any():
                raise ValueError("Domain crosses inner threshold folds")
            for inner, held_out in calibration.groupby("inner_fold_id"):
                fit_ids = inner_fit[str(int(inner))]
                if not fit_ids or len(fit_ids) != len(set(fit_ids)) or not set(fit_ids).issubset(allowed):
                    raise ValueError("Invalid inner threshold fit IDs")
                if set(domains.reindex(fit_ids)) & set(held_out.domain):
                    raise ValueError("Inner threshold model trained on held-out domain")
            thresholds[name][key] = float(value)
    return thresholds


def load_e2_bundle(manifest_path, metadata, folds, e1, *, threshold=0.5):
    """JSON manifest paths are relative to the manifest; verify every artifact SHA256."""
    path = Path(manifest_path)
    if threshold != 0.5 or not e1.predicted_label.eq(e1.score.ge(0.5).astype(int)).all():
        raise ValueError("E1 reference threshold must remain fixed at 0.5")
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
    thresholds = validate_candidate_thresholds(manifest, configs, metadata, folds, files)
    predictions = validate_predictions(predictions, metadata, folds, threshold=threshold, thresholds=thresholds)
    fixed = predictions.copy()
    fixed["predicted_label"] = fixed.score.ge(0.5).astype(int)
    fixed["decision_threshold"] = 0.5
    source_checks = {key: validate_source_evidence(json.loads(files[key].read_text()), metadata)
                     for key in ("source_bias", "external_pilot") if key in files}
    return {"manifest": manifest, "predictions": predictions, "feature_check": feature_check,
            "source_evidence": source_checks,
            "thresholds": thresholds,
            "comparison": paired_comparison(e1, fixed),
            "operating_point_comparison": paired_comparison(e1, predictions),
            "status": "E2 metrics verified; robustness requires a supplied local predictor adapter"}


def audit_native_brand_features(manifest_path, metadata, folds, exclusions, root, report_path):
    """Audit Hy's native trainval artifacts without requiring models or predictions.

    Keep the producer's schema/reference/dictionaries unchanged. A technical PASS
    with draft references is PRELIMINARY, never a frozen/verified E2 result.
    """
    from datetime import datetime, timezone
    from phishguard_vn.brand_features import BRAND_FEATURES, E2_FEATURES, FEATURE_SCHEMA_VERSION, REFERENCE_PATH, load_reference
    root, path, report_path = Path(root), Path(manifest_path), Path(report_path)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "FAIL", "checks": {},
              "model_comparison_status": "PENDING_PRODUCER_E2_PREDICTIONS",
              "limitations": "Feature checks do not verify reference truth or model training; no E2 metrics calculated."}

    def check(name, passed, detail):
        report["checks"][name] = {"status": "PASS" if passed else "FAIL", "detail": detail}
        if not passed:
            raise ValueError(f"Native E2 audit: {name}: {detail}")

    try:
        native = json.loads(path.read_text())
        matrix_path = path.with_name(path.name.replace(".manifest.json", ".csv"))
        excluded_path = path.parent / "05_excluded_rows_trainval.csv"
        matrix = pd.read_csv(matrix_path, dtype={"id": "string"})
        excluded = pd.read_csv(excluded_path, dtype={"id": "string"})
        check("partition_version", native.get("partition") == "trainval" and native.get("test_excluded_from_this_artifact") is True
              and native.get("feature_schema_version") == FEATURE_SCHEMA_VERSION, "Require native trainval / e2-brand-v0 contract")
        check_ids(metadata, "eligible metadata"); check_ids(folds, "folds"); check_ids(matrix, "native E2")
        check("schema_order", list(matrix) == ["id", *E2_FEATURES] and native.get("columns") == list(matrix)
              and native.get("e1_columns") == list(CANDIDATE_FEATURES) and native.get("brand_columns") == list(BRAND_FEATURES),
              "Exactly id + unchanged 12 lexical + 8 brand columns; metadata excluded")
        check("eligible_ids", metadata.split.isin(["train", "val"]).all() and metadata.tier.isin(["gold", "silver"]).all()
              and set(matrix.id) == set(metadata.id), "Exact eligible Core Train/Validation IDs; Test rejected by Train/Validation whitelist")
        check("numeric_finite", all(pd.api.types.is_numeric_dtype(matrix[c]) for c in E2_FEATURES)
              and np.isfinite(matrix[list(E2_FEATURES)].to_numpy(dtype=float)).all(), "All 20 features numeric; no NaN/Inf")
        binary = [c for c in BRAND_FEATURES if c not in ("brand_typo_score", "susp_token_cnt")]
        check("brand_value_contract", matrix[binary].isin([0, 1]).all().all() and matrix.brand_typo_score.between(0, 1).all()
              and matrix.susp_token_cnt.ge(0).all() and matrix.susp_token_cnt.mod(1).eq(0).all(), "Native binary flags, typo range and nonnegative integer token counts")
        check("excluded_ids", {"id", "error_reason"}.issubset(excluded) and excluded.id.is_unique
              and set(excluded.id) == set(exclusions.id) and set(matrix.id).isdisjoint(excluded.id)
              and excluded.error_reason.notna().all() and excluded.error_reason.astype(str).str.strip().ne("").all(),
              "Excluded IDs exactly match E1 exclusions and have nonblank reasons")
        reasons = exclusions.set_index("id").error_reason.reindex(excluded.id)
        check("excluded_reasons", np.array_equal(reasons.to_numpy(), excluded.error_reason.to_numpy()), "E2 exclusion reasons match the unchanged E1 parser policy")
        a = metadata.set_index("id").loc[matrix.id, list(CANDIDATE_FEATURES)].to_numpy(float)
        b = matrix[list(CANDIDATE_FEATURES)].to_numpy(float)
        check("lexical_parity_by_id", np.allclose(a, b, rtol=0, atol=1e-10), "Compare 12 E1 columns by ID, absolute tolerance 1e-10")
        train = metadata.loc[metadata.split.eq("train")]
        check("fold_ids", set(folds.id) == set(train.id) and set(folds.fold_id) == {0, 1, 2}, "Same three eligible domain folds")
        grouped = train.merge(folds, on="id", validate="one_to_one")
        check("domain_groups", grouped.registrable_domain.notna().all() and grouped.groupby("registrable_domain").fold_id.nunique().eq(1).all()
              and set(train.registrable_domain).isdisjoint(metadata.loc[metadata.split.eq("val"), "registrable_domain"]),
              "No domain crosses outer folds or official Train/Validation")
        counts = {s: {"x": int(metadata.split.eq(s).sum()), "excluded": int(exclusions.split.eq(s).sum())} for s in ("train", "val")}
        id_hash = lambda values: hashlib.sha256("\n".join(sorted(map(str, values))).encode()).hexdigest()
        check("manifest_counts_ids", native.get("rows_x") == len(matrix) and native.get("rows_excluded") == len(excluded)
              and native.get("rows_by_split") == counts and native.get("ids_sha256_x") == id_hash(matrix.id)
              and native.get("ids_sha256_excluded") == id_hash(excluded.id), "Native counts, split supports and ID digests agree")
        brand_dict = root / "reports/templates/brand_feature_dictionary.csv"
        e1_dict = root / "reports/templates/feature_dictionary.csv"
        dictionary = pd.read_csv(brand_dict)
        check("dictionary", list(dictionary.feature) == list(BRAND_FEATURES) and dictionary.schema_version.eq(FEATURE_SCHEMA_VERSION).all()
              and dictionary[["formula", "count_scope"]].notna().all().all()
              and native.get("brand_feature_dictionary_sha256") == sha256(brand_dict)
              and native.get("e1_feature_dictionary_sha256") == sha256(e1_dict), "Native brand definitions/order/version and both dictionary hashes match")
        reference = load_reference(REFERENCE_PATH)
        check("reference_hash", native.get("brand_reference") == reference.summary(), "Reference summary/hash matches the actual packaged reference")
        input_path = path.parent / native["input_file"]
        check("input_provenance", native.get("input_sha256") == sha256(input_path)
              and all(native.get("splits_sha256", {}).get(f"url_{s}.csv") == sha256(root / f"data/splits/url_{s}.csv") for s in ("train", "val")),
              "Input and Train/Validation split-file hashes match; no Test file opened")
        check("freeze_claim", not native.get("frozen") or reference.is_fully_verified, "A draft reference cannot claim frozen/verified status")
        report.update(status="PASS", feature_status="PRELIMINARY" if not native.get("frozen") else "FROZEN",
                      feature_schema_version=FEATURE_SCHEMA_VERSION, n_features=len(E2_FEATURES), rows_by_split=counts,
                      rows_x=len(matrix), rows_excluded=len(excluded), excluded_reasons=excluded.error_reason.value_counts().to_dict(),
                      brand_reference=reference.summary(), producer_git_commit=native.get("git_commit"), producer_git_dirty=native.get("git_dirty"),
                      artifact_sha256={str(p.relative_to(root) if p.is_relative_to(root) else p): sha256(p)
                                       for p in [path, matrix_path, excluded_path, brand_dict, e1_dict, REFERENCE_PATH]},
                      pending={"reference_review": "PENDING_HY_REFERENCE_REVIEW" if not reference.is_fully_verified else "source records reviewed by producer; independent review still needed",
                               "e2_predictions": "PENDING_PRODUCER_E2_PREDICTIONS"})
    except (ValueError, KeyError, FileNotFoundError, TypeError, AssertionError) as exc:
        report["error"] = str(exc)
        raise
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return report
