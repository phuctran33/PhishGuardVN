"""Week-5 evaluation orchestration; all new outputs stay separate from Week 4."""
from __future__ import annotations

import hashlib
import importlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import tomllib
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from phishguard_vn.data import load_dataset, prepare_core
from phishguard_vn.evaluation_audit import check_ids, distribution_shift, metrics_table, stratified_metrics, validate_predictions
from phishguard_vn.error_analysis import apply_case_reviews, explain_error_cases, sample_errors, taxonomy_summary
from phishguard_vn.e2_audit import load_e2_bundle, sha256
from phishguard_vn.features import CANDIDATE_FEATURES, build_feature_table
from phishguard_vn.modeling import predict_url, run_baseline
from phishguard_vn.robustness import explain_lexical_shifts, run_robustness, robustness_summary
from phishguard_vn.splits import make_group_folds


def _json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _markdown(frame, columns=None):
    frame = frame[columns] if columns else frame
    def fmt(value):
        if pd.isna(value):
            return "undefined"
        if isinstance(value, (float, np.floating)):
            return f"{value:.4f}"
        return str(value).replace("|", "/").replace("\n", " ")
    return "\n".join(["| " + " | ".join(frame.columns) + " |", "|" + "---|" * len(frame.columns),
                      *["| " + " | ".join(fmt(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None)]])


def _input_fingerprint(root, config_path, dataset_path, baseline_path):
    paths = [dataset_path, config_path, baseline_path, root / "pyproject.toml", root / "requirements.txt",
             root / "reports/templates/feature_dictionary.csv", root / "scripts/run_week5_evaluation.py"]
    paths += sorted((root / "src/phishguard_vn").glob("*.py"))
    reviews = root / "reports/annotations/week5_error_reviews.json"
    if reviews.is_file():
        paths.append(reviews)
    files = {str(p.relative_to(root) if p.is_relative_to(root) else p): sha256(p) for p in paths}
    versions = {p: version(p) for p in ["numpy", "pandas", "scipy", "scikit-learn", "tldextract", "idna", "joblib", "matplotlib"]}
    value = {"files_sha256": files, "versions": versions, "python": platform.python_version()}
    value["fingerprint"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


def _baseline_cache_matches(prior, current, dataset_key, config_key):
    """Analysis/report/E2 edits must not retrain an unchanged E1 experiment."""
    modules = ["__init__", "data", "features", "url_parser", "splits", "modeling", "evaluation"]
    keys = {dataset_key, config_key, *[f"src/phishguard_vn/{name}.py" for name in modules]}
    return (prior.get("versions") == current["versions"] and prior.get("python") == current["python"]
            and all(k in current["files_sha256"] and prior.get("files_sha256", {}).get(k) == current["files_sha256"][k] for k in keys))


def prepare_inputs(root, dataset_path, config, output):
    # No features/predictions/metrics are computed for official test.
    raw = prepare_core(load_dataset(dataset_path))
    core = raw.loc[raw.split.isin(["train", "val"])].copy()
    check_ids(core, "core train/val")
    parsed = build_feature_table(core[["id", "url"]])
    eligible = parsed.is_valid & parsed.registrable_domain.notna()
    exclusions = parsed.loc[~eligible, ["id", "error_reason"]].merge(core[["id", "split", "label"]], on="id", validate="one_to_one")
    features = parsed.loc[eligible, ["id", *CANDIDATE_FEATURES]].copy()
    metadata = core[["id", "url", "label", "source", "tier", "split"]].merge(
        parsed.loc[eligible, ["id", "registrable_domain"]], on="id", validate="one_to_one").merge(features, on="id", validate="one_to_one")
    train = metadata.loc[metadata.split.eq("train")]
    folds = make_group_folds(train, n_splits=3, seed=config["audit"]["seed"])
    for split, setting in [("train", "expected_train_rows"), ("val", "expected_validation_rows")]:
        if int(metadata.split.eq(split).sum()) != config["audit"][setting]:
            raise ValueError(f"Dataset snapshot changed: {split} support; explicitly review the config")
    # Validate any available Week-4 handoffs; never assume ignored files exist.
    comparisons = {}
    for name, fresh, columns in [
        ("02_group_folds_train.csv", folds, ["fold_id"]),
        ("03_matrix_X_features.csv", features, list(CANDIDATE_FEATURES)),
        ("03_registrable_domains.csv", metadata[["id", "registrable_domain"]], ["registrable_domain"]),
    ]:
        path = root / "data/interim" / name
        if not path.is_file():
            comparisons[name] = "absent; regenerated from merged pipeline"
            continue
        prior = pd.read_csv(path, dtype={"id": "string"})
        check_ids(prior, name)
        prior = prior.loc[prior.id.isin(fresh.id), ["id", *columns]]
        pd.testing.assert_frame_equal(fresh[["id", *columns]].sort_values("id").reset_index(drop=True),
                                      prior.sort_values("id").reset_index(drop=True), check_dtype=False, atol=1e-10, rtol=0)
        comparisons[name] = {"status": "exact eligible-ID match", "sha256": sha256(path)}
    for name, frame in [("metadata", metadata), ("features", features), ("folds", folds), ("exclusions", exclusions)]:
        frame.to_csv(output / f"{name}.csv", index=False)
    return features, metadata, folds, exclusions, comparisons


def _plots(predictions, selected, robustness, shift, figures):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, precision_recall_curve
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (partition, group) in zip(axes, predictions.loc[predictions.model.eq(selected)].groupby("evaluation_partition", sort=True)):
        precision, recall, _ = precision_recall_curve(group.true_label, group.score)
        ax.step(recall, precision, where="post", label="E1")
        ax.axhline(group.true_label.mean(), linestyle="--", color="gray", label="positive prevalence")
        ax.set(xlim=(0, 1), ylim=(0, 1.02), xlabel="Recall", ylabel="Precision", title=partition)
        ax.legend()
    fig.tight_layout(); fig.savefig(figures / "precision_recall.png", dpi=140); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, (partition, group) in zip(axes, predictions.loc[predictions.model.eq(selected)].groupby("evaluation_partition", sort=True)):
        ConfusionMatrixDisplay.from_predictions(group.true_label, group.predicted_label, labels=[0, 1], display_labels=["benign", "phishing"], ax=ax, colorbar=False)
        ax.set_title(partition)
    fig.tight_layout(); fig.savefig(figures / "confusion_matrices.png", dpi=140); plt.close(fig)
    source = shift.loc[shift.dimension.eq("source")].set_index("stratum")
    fig, ax = plt.subplots(figsize=(9, 4))
    source[["train_share", "val_share"]].plot.bar(ax=ax)
    ax.set(ylabel="Fraction within split", xlabel="Source", title="Eligible core source composition")
    fig.tight_layout(); fig.savefig(figures / "source_shift.png", dpi=140); plt.close(fig)
    paired = robustness.loc[robustness.paired_predictions.gt(0)].sort_values("mean_abs_score_shift")
    if len(paired):
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh(paired.transformation, paired.mean_abs_score_shift)
        ax.set(xlabel="Mean absolute phishing score shift", title="Static E1 stress cases; no transformed ground truth")
        fig.tight_layout(); fig.savefig(figures / "robustness_shift.png", dpi=140); plt.close(fig)


def _robustness_report(root, summary, predictor_name, stress, feature_deltas):
    top = summary.loc[summary.paired_predictions.gt(0)].sort_values("prediction_flip_rate", ascending=False).head(3)
    equivalent = stress.loc[stress.label_policy.eq("conditional-label-preserving") & stress.prediction_status.eq("paired")].copy()
    mechanisms = []
    for name, block in equivalent.groupby("transformation"):
        changed = feature_deltas.loc[feature_deltas.transformation.eq(name)]
        mechanisms.append({"transformation": name, "changed_features": ", ".join(sorted(changed.feature.unique())),
                           "paired_cases": len(block), "flips": int(block.flip.sum()),
                           "max_abs_score_shift": block.score_shift.abs().max()})
    examples = equivalent.assign(_abs=equivalent.score_shift.abs()).sort_values("_abs", ascending=False).groupby("transformation", sort=False).head(1)
    flip_examples = stress.loc[stress.flip.eq(True)].assign(_abs=lambda x: x.score_shift.abs()).sort_values("_abs", ascending=False).head(3)
    report = ["# Week 5 — Static URL robustness", "", f"Predictor: {predictor_name}.", "",
              "Six static reserved-example URLs × 24 deterministic transformations; no network requests. No ground-truth labels are assigned to stress strings.", "",
              "Host case and scheme-default ports are **conditional-label-preserving**, under ASCII HTTP(S) URI normalization with unchanged userinfo/path/query/fragment. Equivalence checks are syntactic, not observations of live server behavior or verified label invariance. Non-default ports are not rewritten. All other transformations are label-unknown, including fragments (client-side routing may change semantics).",
              "HTTP host case and default-port normalization follow [RFC 9110 §4.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.3) and [RFC 3986 §6.2.2.1](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.2.1). No server was contacted to test routing or content equivalence.", "",
              "Validity is the existing parser/extractor contract, not browser acceptance or an RFC compliance claim. IPv4/IPv6 are feature-valid although domain-group training excluded IPs.", "",
              _markdown(summary), "",
              "## Equivalent URI spellings, changed lexical features", "",
              _markdown(pd.DataFrame(mechanisms)), "",
              "The extractor computes entropy and counts on the raw string after stripping only the scheme. Uppercasing the host can separate characters previously shared with lowercase path/query text, changing the entropy histogram even when length and character counts stay equal. On host-only strings an alphabet relabeling can instead leave entropy unchanged. Default ports add colon/digits/length and alter entropy; parsed registrable domain and path remain unchanged.", "",
              "For the fixed StandardScaler + LR, Δlogit = Σ coefficient[j] × Δfeature[j] / fitting_scale[j]. Intercept cancels; applying sigmoid to before/after logits reproduces both saved scores. All changed-feature terms are in robustness_feature_deltas.csv. Correlated features must be read together; individual terms are not independent causal importances.", "",
              "Largest shift within each conditional-equivalence transformation:", "",
              _markdown(examples, ["base_id", "transformation", "original_url", "transformed_url", "original_score", "transformed_score", "score_shift", "flip"]), "",
              "These deterministic changes are expected sensitivity of the declared raw lexical representation and a lack of invariance to equivalent URI spellings. They are not stochastic/numerical model instability: the same feature vector always gives the same score. A preserved decision on these six bases does not guarantee threshold stability on other inputs or establish a correct original label.", "",
              "## Actual prediction-flip examples (label-unknown)", "",
              _markdown(flip_examples, ["base_id", "transformation", "original_url", "transformed_url", "original_score", "transformed_score", "score_shift"]), "",
              "Largest observed flip rates (small unlabeled suite; not error rates):", "",
              _markdown(top, ["transformation", "paired_predictions", "prediction_flip_rate", "mean_abs_score_shift"]), "",
              "Finite-feature coverage uses all transformed cases as denominator; malformed cases correctly yield missing features. Expected-validity pass rate distinguishes intended rejection from failures. Paired-prediction denominators are explicit; undefined flip/shift means no valid prediction pair.", "",
              "Flip rate is threshold stability, not classification error. Scores are uncalibrated and no accuracy/F1 is computed. Six synthetic bases are a small stress suite, not an estimate of real-world robustness. Some malformed transformations generate the same string for multiple bases, so 144 rows are not 144 independent inputs. Long paths and IPs probe inputs uncommon or absent in E1 training. Encoding may change server routing; no label preservation is asserted for it.", "",
              "Full specifications, safe strings, parser reasons and paired scores: tables/week5/robustness_cases.csv. Reuse run_robustness(predictor) with any local E2 score adapter; do not perform network lookups.", ""]
    (root / "reports/week5_robustness.md").write_text("\n".join(report), encoding="utf-8")


def _report(root, metrics, folds_metric, cases, taxonomy, robust, shift, numerical_shift, manifest, e2_status):
    selected = manifest["selected_model"]
    chosen = metrics.loc[metrics.model.eq(selected)]
    cv = chosen.loc[chosen.evaluation_partition.eq("group_cv")].iloc[0]
    val = chosen.loc[chosen.evaluation_partition.eq("official_validation")].iloc[0]
    fold_summary = folds_metric.groupby("model")[["pr_auc", "f1_phishing", "recall_phishing", "false_positive_rate"]].agg(["mean", "std"]).reset_index()
    fold_summary.columns = ["_".join(c).rstrip("_") for c in fold_summary.columns]
    support = cases.groupby(["evaluation_partition", "fold_id", "outcome"], dropna=False).size().reset_index(name="cases")
    archived_path = root / "reports/tables/week5/archived_e1_comparison.csv"
    archive_note = "No archived Week-4 metric comparison available."
    if archived_path.is_file() and archived_path.stat().st_size > 1:
        archived_delta = pd.read_csv(archived_path)
        ap_delta = archived_delta.pr_auc_delta.abs().max()
        counts_same = archived_delta[[m + "_delta" for m in ["tn", "fp", "fn", "tp"]]].eq(0).all().all()
        archive_note = (f"Archived Week-4 comparison: identical confusion counts={bool(counts_same)}; maximum absolute per-fold AP difference={ap_delta:.9f}. "
                        "Current runtime versions differ from the archived environment; the AP difference is recorded, not silently replaced by old metrics or attributed to a verified cause. See archived_e1_comparison.csv.")
    readiness = ("H5.4 PREPARED for E2 and KD; actual E2 audit BLOCKED until producer artifacts arrive."
                 if "BLOCKED" in e2_status else "H5.4 supplied E2 metrics audited; KD protocol PREPARED; predictor and semantic review status below.")
    source_path = root / "reports/tables/week5/source_audit_review.json"
    source_note = "No supporting source-audit snapshot has been reviewed in this checkout."
    if source_path.is_file():
        source_review = json.loads(source_path.read_text())
        source_note = (f"Khiêm's unmerged source audit reviewed at `{source_review['producer_revision']}`; frozen file links/hashes and local corroboration are in [source audit review](tables/week5/source_audit_review.json). "
                       f"{source_review['limitations']} {source_review['parser_reconciliation']} {source_review['external_pilot_status']}")
    lines = ["# PhishGuardVN — Week 5 evaluation (Hưng)", "",
             "## Status and provenance", "",
             "H5.1 DONE; H5.2 DONE for reproducible static review (human semantic checks pending); H5.3 DONE. " + readiness, "",
             f"Published upstream snapshot: `{manifest['published_commit']}` on week5/hung-evaluation-robustness. Current audit runtime base: `{manifest['audit_runtime_base_revision']}`; original E1 generation base: `{manifest['e1_runtime_base_revision']}`. Runtime source state: `{manifest['runtime_source_state']}`. Source/config/annotation hashes identify the working sources; the published SHA is a separate snapshot and does not identify uncommitted edits. No commit/push/merge is performed by this review.", "",
             "Exact input/source hashes, versions, analysis fingerprint, immutable E1 generation provenance and artifact hashes: tables/week5/run_manifest.json. E1 cache reuse checks actual dataset, training-source/config/environment and model/lineage hashes; analysis/report changes do not force retraining. Original archived Week-4 tables are unchanged.", "",
             "12 lexical features; 13,078 eligible core train IDs; 3 unchanged domain folds; seed=42; scaler fit separately on each fitting fold; threshold=0.5. Two unresolved train/phishing URLs remain in the raw dataset, excluded with reasons. No official test features or predictions generated. Metadata (including source/tier) stays outside X.", "",
             f"Selected E1: **{selected}** by existing mean-CV-F1 rule, AP tie-break. Reconstructed predictions cover every eligible ID once per model/partition and pass label/fold/group/threshold checks. All available local Week-4 feature/domain/fold handoffs match by ID.", "",
             "## H5.1 — measured evaluation", "",
             "PR-AUC below means average precision (AP). Pooled OOF AP is a separate calculation from mean per-fold AP; AP depends on prevalence. P/R/F1 refer to phishing=1. Undefined recall/F1/AP in zero-positive strata remain missing.", "",
             _markdown(metrics, ["model", "evaluation_partition", "n_rows", "n_phishing", "tn", "fp", "fn", "tp", "precision_phishing", "recall_phishing", "f1_phishing", "pr_auc", "false_positive_rate", "fp_per_1000_benign"]), "",
             "Mean and sample standard deviation across three folds (descriptive; not a confidence interval):", "", _markdown(fold_summary), "",
             archive_note, "",
             "![PR curves](figures/week5/precision_recall.png)", "", "![Confusion matrices](figures/week5/confusion_matrices.png)", "",
             f"Observation: selected E1 pooled OOF FPR={cv.false_positive_rate:.2%} ({cv.fp_per_1000_benign:.1f} FP/1,000 benign), recall={cv.recall_phishing:.2%}; validation FPR={val.false_positive_rate:.2%}, recall={val.recall_phishing:.2%}. Validation has only {int(val.n_phishing)} positives; one case changes recall by {100/val.n_phishing:.2f} percentage points.", "",
             "Strata tables include every fold, source, tier, fixed URL-length/entropy bin and domain, with supports/confusion counts. Domain strata are sparse and often single-class: no ranking as causal error mechanisms. They are diagnostics, never features or a validation tuning signal.", "",
             "### Distribution/source shift", "", _markdown(shift), "", _markdown(numerical_shift), "",
             "Numerical summaries are descriptive across eligible IDs; group dependence and source-label confounding prevent causal or iid significance claims.", "",
             source_note, "",
             "![Source composition](figures/week5/source_shift.png)", "",
             "Testable hypotheses (unverified):", "",
             "1. Prevalence/source composition explains part of the precision/AP gap. Check train OOF per-source and per-class supports; use a predeclared prevalence reweighting sensitivity analysis, then independently collected labeled data. Do not tune to official validation.",
             "2. Sparse path/query coverage in train limits stability on complex URLs. Compare train-only nested-group CV errors across fixed complexity bins and a separately labeled static challenge set; current unlabeled flips cannot verify errors.",
             "3. Domain lexical patterns interact with single-label sources. Use source-held-out diagnostics where both classes are supported and matched-length/entropy train OOF comparisons; lack of source class overlap makes some effects unidentifiable.",
             "4. IDNA/brand cues add information beyond 12 lexical features. Compare E2 with E1 on exactly the same outer folds and an independent predeclared reference list; audit reference fitting before interpreting gains.", "",
             "## H5.2 — manual error analysis", "",
             f"{len(cases)} FP/FN cases selected using seed=42, SHA256-ranked IDs, round robin across partition/fold/type/source/tier and then distinct domains within queues. No ranking by score; selection is a diversity sample, not a population estimate. Sampling pool, coverage and limitations are recorded; if a stratum has no errors it contributes no cases.", "",
             _markdown(support), "", _markdown(taxonomy), "",
             "Each case has static observations, an explicitly unverified hypothesis, offline next verification, original labels and review status. Safe URL text is fully defanged and prefixed to prevent spreadsheet formulas; no suspicious URL was visited. Source effects and label uncertainty have explicit review fields; zero direct cue counts do not assert absence of those phenomena. No model output verifies a label error or individual causal mechanism.", "",
             f"All {len(cases)} cases now have case-specific offline engineering notes, preserved read-only in [durable annotations](annotations/week5_error_reviews.json). Case signatures bind notes to ID, context, original label, URL, score and all 12 features; changed evidence fails as stale instead of silently reusing a review. Taxonomy describes observed representations, not verified root causes; all human semantic verification remains pending.", "",
             f"Exact correct-context LR arithmetic is verified for every case. Opposite-label full-vector collisions in fitting data are observed for {int(cases.taxonomy.str.contains('representation_collision', regex=False).sum())}/{len(cases)} cases (absolute feature tolerance 1e-12). The selected model is refitted only in its three existing fitting folds for explanation when those models are unavailable; no new model selection, thresholds or baseline experiments are introduced. Validation explanations use the original full-Train pipeline. Contributions are relative to each fitting mean, with correlated dot/subdomain/length terms often cancelling; they are not independent causal effects.", "",
             "Evidence: error_model_evidence.csv (reconstructed logits/scores, fitting-ID hashes and collision supports) and error_feature_attributions.csv (all 12 raw/scaled terms per case). Collision searches use fitting IDs only, not held-out labels. The coarse representation can be ambiguous under original labels, but this does not verify maliciousness, label correctness or a source shortcut.", "",
             "Case-level annotations: tables/week5/error_cases.csv; pool: error_sampling_pool.csv; taxonomy: error_taxonomy.csv. Human semantic verification remains pending; original labels are retained.", "",
             "## H5.3 — static robustness", "",
             f"{int(robust.n_cases.sum())} static cases; expected parser-validity checks passed {int((robust.expected_validity_pass_rate * robust.n_cases).sum())}/{int(robust.n_cases.sum())}. Full results/specifications and limitations: [robustness report](week5_robustness.md).", "",
             "![Score shifts](figures/week5/robustness_shift.png)", "",
             "No transformed ground truth, accuracy or F1. Prediction flips are sensitivity findings, not established model errors. Expected malformed rejection is a successful validity check.", "",
             "## H5.4 — E2 audit and KD readiness", "", e2_status, "",
             "Loaders/adapters enforce artifact hashes, exact feature order/dictionary, eligible IDs, fixed folds, finite values, lexical-contract consistency, fold-local or independent external brand references, producer training-ID lineage and matched E1/E2 comparisons. Producer declarations still need code/reference review; schema checks alone do not prove leakage absence. Synthetic fixtures validate logic only and contribute no reported experimental metrics.", "",
             "The primary E1–E2 comparison always recomputes both decisions at 0.5. Optional candidate/context thresholds require inner-Train-only OOF selection IDs within the correct fitting partition, a declared method and hashed supporting evidence. Their operating-point comparison is exported separately; changes in F1/Recall/FPR at different thresholds are not claimed as ranking improvements. AP is threshold-independent. E1 remains at 0.5.", "",
             "[KD evaluation protocol](../docs/kd_evaluation_protocol.md); [handoff and continuation prompt](../docs/week5_hung_handoff.md). Optional source-bias/pilot evidence from Khiêm remains separate from X; source bias is not claimed resolved.", ""]
    (root / "reports/week5_evaluation.md").write_text("\n".join(lines), encoding="utf-8")


def run_week5(root, config_path=None, *, rebuild_e1=False, robustness_only=False):
    root = Path(root).resolve()
    config_path = Path(config_path).resolve() if config_path else root / "configs/week5.toml"
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    paths = {k: root / value for k, value in config["paths"].items()}
    output, tables, figures = (paths[k] for k in ["artifacts", "tables", "figures"])
    previous_path = tables / "run_manifest.json"
    previous_manifest = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True).stdout.strip()
    published = subprocess.run(["git", "rev-parse", "@{upstream}"], cwd=root, text=True, capture_output=True)
    worktree = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True).stdout.strip()
    for path in [output, tables, figures]:
        path.mkdir(parents=True, exist_ok=True)
    if robustness_only:
        stress = run_robustness()
        summary = robustness_summary(stress)
        stress.to_csv(tables / "robustness_parser_only_cases.csv", index=False)
        summary.to_csv(tables / "robustness_parser_only_summary.csv", index=False)
        # Avoid replacing a completed E1 report with a parser-only report.
        return {"status": "parser/extractor-only", "cases": len(stress), "validity_pass": bool(stress.validity_check_pass.all())}
    if config["audit"]["seed"] != 42:
        raise ValueError("E1 snapshot requires seed 42")
    fingerprint = _input_fingerprint(root, config_path, paths["dataset"], paths["baseline_config"])
    source_status = subprocess.run(["git", "status", "--porcelain", "--", *fingerprint["files_sha256"]], cwd=root, text=True, capture_output=True).stdout.strip()
    features, metadata, folds, exclusions, comparisons = prepare_inputs(root, paths["dataset"], config, output)
    with paths["baseline_config"].open("rb") as handle:
        baseline_config = tomllib.load(handle)
    if baseline_config["experiment"]["seed"] != 42 or baseline_config["evaluation"]["decision_threshold"] != 0.5:
        raise ValueError("E1 config changed; explicitly review before evaluation")
    result_path, prior_path = output / "e1_result.joblib", output / "e1_provenance.json"
    cached = False
    lineage_path = output / "e1_training_lineage.json"
    if result_path.is_file() and prior_path.is_file() and lineage_path.is_file() and not rebuild_e1:
        prior = json.loads(prior_path.read_text())
        dataset_key = str(paths["dataset"].relative_to(root) if paths["dataset"].is_relative_to(root) else paths["dataset"])
        config_key = str(paths["baseline_config"].relative_to(root) if paths["baseline_config"].is_relative_to(root) else paths["baseline_config"])
        if (_baseline_cache_matches(prior, fingerprint, dataset_key, config_key) and prior["result_sha256"] == sha256(result_path)
                and prior.get("lineage_sha256") == sha256(lineage_path)):
            result = joblib.load(result_path)  # Only this runner's local artifact, never a downloaded model.
            cached = True
    if not cached:
        targets = metadata[["id", "label", "tier", "split", "registrable_domain"]]
        result = run_baseline(features, targets, folds, baseline_config)
        joblib.dump(result, result_path)
        lineage = {}
        train_ids = set(folds.id)
        for f in (0, 1, 2):
            fit_ids = sorted(train_ids - set(folds.loc[folds.fold_id.eq(f), "id"]))
            lineage[str(f)] = {"fit_ids": fit_ids, "held_out_ids": sorted(set(folds.id) - set(fit_ids)),
                               "preprocessing_fit_scope": "fitting_fold_only"}
        lineage["validation"] = {"fit_ids": sorted(train_ids), "prediction_ids": sorted(metadata.loc[metadata.split.eq("val"), "id"])}
        _json(lineage_path, lineage)
        _json(prior_path, {**fingerprint, "result_sha256": sha256(result_path), "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                           "runtime_base_revision": revision,
                           "lineage_sha256": sha256(lineage_path),
                           "method": "merged run_baseline; each held-out domain fold predicted by a fresh clone fitted only on other folds"})
    provenance = json.loads(prior_path.read_text())
    e1_revision = provenance.get("runtime_base_revision") or previous_manifest.get("e1_runtime_base_revision") or previous_manifest.get("git_revision")
    predictions = pd.concat([result["cv_predictions"], result["validation_predictions"]], ignore_index=True)
    # Concatenation gives fold_id float due to NA in official validation.
    predictions = validate_predictions(predictions, metadata, folds, threshold=result["decision_threshold"])
    raw_columns = ["id", "model", "fold_id", "evaluation_partition", "true_label", "predicted_label", "score"]
    predictions[raw_columns].to_csv(output / "e1_predictions.csv", index=False)
    metrics = metrics_table(predictions, ["model", "evaluation_partition"])
    fold_metrics = metrics_table(predictions.loc[predictions.evaluation_partition.eq("group_cv")], ["model", "fold_id"])
    archived_path = root / "reports/tables/04_cv_metrics.csv"
    archived_comparison = pd.DataFrame()
    if archived_path.is_file():
        archived = pd.read_csv(archived_path)
        compared = archived.merge(fold_metrics, on=["model", "fold_id"], suffixes=("_archived", "_recomputed"), validate="one_to_one")
        archived_comparison = compared[["model", "fold_id"]].copy()
        for metric in ["tn", "fp", "fn", "tp", "precision_phishing", "recall_phishing", "f1_phishing", "pr_auc", "false_positive_rate"]:
            archived_comparison[metric + "_delta"] = compared[metric + "_recomputed"] - compared[metric + "_archived"]
    strata = stratified_metrics(predictions)
    shift = distribution_shift(metadata)
    numerical_shift = metadata.groupby("split")[["url_len", "entropy"]].agg(["mean", "median", "min", "max"]).reset_index()
    numerical_shift.columns = ["_".join(c).rstrip("_") for c in numerical_shift.columns]
    selected = result["selected_model"]
    sample = sample_errors(predictions, model=selected, n=config["audit"]["sample_cases"], seed=config["audit"]["seed"])
    explanation_cache = output / "e1_explanation_models.joblib"
    context_models = None
    explanation_cache_valid = False
    if explanation_cache.is_file():
        prior_explanations = joblib.load(explanation_cache)
        if prior_explanations.get("result_sha256") == sha256(result_path):
            context_models = prior_explanations["models"]
            explanation_cache_valid = True
    evidence, attributions, context_models = explain_error_cases(sample, metadata, folds, result["pipeline"], context_models=context_models)
    if not explanation_cache_valid:
        joblib.dump({"result_sha256": sha256(result_path), "models": context_models}, explanation_cache)
    review_path = root / "reports/annotations/week5_error_reviews.json"
    cases = apply_case_reviews(sample, evidence, review_path)
    if len(cases) < 30:
        raise ValueError("Fewer than 30 available errors; report shortage rather than silently accepting")
    pool = predictions.loc[predictions.model.eq(selected) & predictions.outcome.isin(["FP", "FN"])].copy()
    pool["selected_for_review"] = pool.id.isin(cases.id)
    pool[["id", "evaluation_partition", "fold_id", "source", "tier", "outcome", "selected_for_review"]].to_csv(tables / "error_sampling_pool.csv", index=False)
    taxonomy = taxonomy_summary(cases)
    stress = run_robustness(lambda url: predict_url(url, result["pipeline"], result["feature_names"], result["decision_threshold"])["score"])
    robust = robustness_summary(stress)
    feature_deltas = explain_lexical_shifts(stress, result["pipeline"])
    outputs = {"metrics": metrics, "fold_metrics": fold_metrics, "stratified_metrics": strata, "distribution_shift": shift,
               "numerical_shift": numerical_shift, "error_cases": cases, "error_taxonomy": taxonomy,
               "robustness_cases": stress, "robustness_summary": robust, "exclusions": exclusions,
               "archived_e1_comparison": archived_comparison}
    outputs.update(error_model_evidence=evidence, error_feature_attributions=attributions, robustness_feature_deltas=feature_deltas)
    for name, frame in outputs.items():
        frame.to_csv(tables / f"{name}.csv", index=False)
    e2_status = "PREPARED / experimental audit BLOCKED: no E2 manifest supplied. Await Hy's features/dictionary/references and Phúc's predictions/configs/lineage/candidates; Khiêm's bias/pilot evidence is optional for core paired evaluation."
    current_csvs = [tables / f"{name}.csv" for name in outputs] + [tables / "error_sampling_pool.csv"]
    if config.get("e2", {}).get("manifest"):
        bundle = load_e2_bundle(root / config["e2"]["manifest"], metadata, folds,
                                predictions.loc[predictions.model.eq(selected)], threshold=result["decision_threshold"])
        bundle["comparison"].to_csv(tables / "e2_comparison.csv", index=False)
        bundle["operating_point_comparison"].to_csv(tables / "e2_operating_point_comparison.csv", index=False)
        metrics_table(bundle["predictions"], ["model", "evaluation_partition"]).to_csv(tables / "e2_metrics.csv", index=False)
        _json(tables / "e2_audit_checks.json", {"manifest_sha256": sha256(root / config["e2"]["manifest"]),
                                               "features": bundle["feature_check"], "source_evidence": bundle["source_evidence"],
                                               "thresholds": bundle["thresholds"],
                                               "threshold_review": "Declared inner OOF/fit IDs/domains/scores checked; optimization and preprocessing code still require producer review."})
        current_csvs += [tables / name for name in ("e2_comparison.csv", "e2_operating_point_comparison.csv", "e2_metrics.csv")]
        e2_status = bundle["status"]
        if config["e2"].get("predictor"):
            predictor_model = config["e2"].get("predictor_model") or (next(iter(bundle["thresholds"])) if len(bundle["thresholds"]) == 1 else None)
            if predictor_model not in bundle["thresholds"]:
                raise ValueError("Bind E2 predictor_model to one supplied candidate")
            module, function = config["e2"]["predictor"].split(":", 1)
            predictor = getattr(importlib.import_module(module), function)
            e2_stress = run_robustness(predictor, threshold=bundle["thresholds"][predictor_model]["-1"])
            e2_stress.to_csv(tables / "e2_robustness_cases.csv", index=False)
            robustness_summary(e2_stress).to_csv(tables / "e2_robustness_summary.csv", index=False)
            current_csvs += [tables / "e2_robustness_cases.csv", tables / "e2_robustness_summary.csv"]
            e2_status += "; supplied predictor robustness measured (verify adapter matches candidate)."
    _plots(predictions, selected, robust, shift, figures)
    manifest = {**fingerprint, "git_revision": revision, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "audit_runtime_base_revision": revision, "e1_runtime_base_revision": e1_revision,
                "published_commit": published.stdout.strip() if published.returncode == 0 else None,
                "runtime_source_state": "modified_from_head" if source_status else "matches_head",
                "git_worktree_status_at_start": worktree,
                "provenance_note": "Audit hashes identify the current runtime sources, including uncommitted review changes; published_commit identifies the existing upstream snapshot, not publication of this review. E1 generation sources and runtime base remain the original immutable training record.",
                "selected_model": selected, "threshold": result["decision_threshold"], "cached_e1": cached,
                "e1_generation": provenance, "handoff_comparisons": comparisons,
                "evaluation_scope": {"train": int(metadata.split.eq("train").sum()), "validation": int(metadata.split.eq("val").sum()), "test_evaluated": False},
                "e2_status": e2_status, "sampling": {"seed": config["audit"]["seed"], "requested": config["audit"]["sample_cases"], "actual": len(cases)},
                "supporting_evidence_sha256": {p.relative_to(root).as_posix(): sha256(p) for p in [tables / "source_audit_review.json"] if p.is_file()},
                "outputs_sha256": {p.relative_to(root).as_posix(): sha256(p) for p in sorted(current_csvs)},
                "prediction_sha256": sha256(output / "e1_predictions.csv"), "lineage_sha256": sha256(output / "e1_training_lineage.json")}
    manifest["explanation_models_sha256"] = sha256(explanation_cache)
    manifest["figures_sha256"] = {p.relative_to(root).as_posix(): sha256(p) for p in sorted(figures.glob("*.png"))}
    _json(tables / "run_manifest.json", manifest)
    _robustness_report(root, robust, selected, stress, feature_deltas)
    _report(root, metrics, fold_metrics, cases, taxonomy, robust, shift, numerical_shift, manifest, e2_status)
    return {"selected_model": selected, "cached_e1": cached, "metrics": metrics, "cases": len(cases), "robustness_cases": len(stress), "e2_status": e2_status}
