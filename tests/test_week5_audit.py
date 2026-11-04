"""Synthetic fixtures test validation logic only; never experimental evidence."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from phishguard_vn.evaluation_audit import distribution_shift, metrics_table, validate_predictions
from phishguard_vn.error_analysis import case_manifest, defang_url, sample_errors, taxonomy_summary
from phishguard_vn.e2_audit import adapt_predictions, load_e2_bundle, paired_comparison, sha256, validate_feature_matrix, validate_lineage
from phishguard_vn.features import CANDIDATE_FEATURES


@pytest.fixture
def inputs():
    metadata = pd.DataFrame([{"id": f"id_{i:02d}", "url": f"https://example.com/{i}", "split": "train" if i < 18 else "val",
                             "label": "phishing" if i % 2 else "benign", "source": f"source_{i % 2}", "tier": "silver",
                             "registrable_domain": f"group{i}.com", **{name: float(i + 1) for name in CANDIDATE_FEATURES}}
                            for i in range(24)])
    folds = pd.DataFrame({"id": metadata.id[:18], "fold_id": [i // 6 for i in range(18)]})
    predictions = pd.DataFrame([{"id": row.id, "model": "E1", "evaluation_partition": "group_cv" if i < 18 else "official_validation",
                                 "fold_id": i // 6 if i < 18 else np.nan, "true_label": i % 2, "predicted_label": 1 - i % 2,
                                 "score": 0.9 if i % 2 == 0 else 0.1} for i, row in metadata.iterrows()])
    return metadata, folds, predictions


def test_confusion_support_fp_rate_and_zero_positive(inputs):
    metadata, folds, pred = inputs
    joined = validate_predictions(pred, metadata, folds)
    metrics = metrics_table(joined, ["model", "evaluation_partition"])
    cv = metrics.loc[metrics.evaluation_partition.eq("group_cv")].iloc[0]
    assert (cv.tn, cv.fp, cv.fn, cv.tp, cv.n_rows) == (0, 9, 9, 0, 18)
    assert cv.fp_per_1000_benign == 1000
    only_benign = metrics_table(joined.loc[joined.true_label.eq(0)], ["model"])
    assert pd.isna(only_benign.iloc[0].pr_auc)
    assert pd.isna(only_benign.iloc[0].recall_phishing)


@pytest.mark.parametrize("defect", ["duplicate", "missing", "label", "fold", "test", "score_nan", "score_range", "threshold", "missing_validation"])
def test_predictions_fail_closed(inputs, defect):
    metadata, folds, pred = inputs
    if defect == "duplicate": pred = pd.concat([pred, pred.iloc[[0]]])
    if defect == "missing": pred = pred.iloc[1:]
    if defect == "label": pred.loc[0, "true_label"] = 1
    if defect == "fold": pred.loc[0, "fold_id"] = 1
    if defect == "test": pred.loc[0, "evaluation_partition"] = "official_test"
    if defect == "score_nan": pred.loc[0, "score"] = np.nan
    if defect == "score_range": pred.loc[0, "score"] = 2.0
    if defect == "threshold": pred.loc[0, "predicted_label"] = 0
    if defect == "missing_validation": pred = pred.iloc[:18]
    with pytest.raises(ValueError): validate_predictions(pred, metadata, folds)


def test_domain_leakage(inputs):
    metadata, folds, pred = inputs
    metadata.loc[6, "registrable_domain"] = metadata.loc[0, "registrable_domain"]
    with pytest.raises(ValueError, match="Domain crosses folds"): validate_predictions(pred, metadata, folds)


def test_sampling_reproducible_diverse_and_safe(inputs):
    metadata, folds, pred = inputs
    joined = validate_predictions(pred, metadata, folds)
    a = sample_errors(joined, model="E1", n=16)
    b = sample_errors(joined.sample(frac=1, random_state=15), model="E1", n=16)
    assert list(a.id) == list(b.id)
    assert set(a.sampling_fold) == {-1, 0, 1, 2}
    assert set(a.outcome) == {"FP", "FN"}
    assert a.id.is_unique
    cases = case_manifest(a)
    assert cases.review_status.str.contains("human_verification_pending").all()
    assert not cases.url_safe.str.contains("://", regex=False).any()
    assert set(taxonomy_summary(cases).category) >= {"unknown", "label_uncertainty", "source_effects"}
    assert defang_url('=HYPERLINK("https://evil.com")\n<script>') .startswith("URL_TEXT: ")
    assert "<script>" not in defang_url("<script>")


def test_shift_denominators(inputs):
    metadata, _, _ = inputs
    shift = distribution_shift(metadata)
    for _, group in shift.groupby("dimension"):
        assert group.train_share.sum() == pytest.approx(1)
        assert group.val_share.sum() == pytest.approx(1)


def feature_fixture(inputs):
    metadata, folds, _ = inputs
    names = [*CANDIDATE_FEATURES, "brand_similarity"]
    matrix = metadata[["id", *CANDIDATE_FEATURES]].copy()
    matrix["brand_similarity"] = 0.1
    dictionary = pd.DataFrame([{"feature": n, "definition": "synthetic unit test feature", "inputs": "url", "version": "test_v1"} for n in names])
    references = {"scope": "frozen_external", "selection_scope": "external_fixed", "independent_of_dataset": True,
                  "version": "test_v1", "records": [{"reference_id": "r1", "source": "synthetic fixture", "sha256": "a" * 64, "obtained_at": "2026-10-01"}]}
    return matrix, names, dictionary, references


@pytest.mark.parametrize("defect", [None, "order", "nan", "metadata", "missing_id", "reference", "dictionary", "global_fit"])
def test_feature_contract(inputs, defect):
    metadata, folds, _ = inputs
    matrix, names, dictionary, refs = feature_fixture(inputs)
    if defect == "order": matrix = matrix[list(reversed(matrix.columns))]
    if defect == "nan": matrix.loc[0, "brand_similarity"] = np.nan
    if defect == "metadata": matrix = matrix.rename(columns={"brand_similarity": "label_hint"}); names[-1] = "label_hint"; dictionary.loc[len(dictionary)-1, "feature"] = "label_hint"
    if defect == "missing_id": matrix = matrix.iloc[1:]
    if defect == "reference": refs["records"] = []
    if defect == "dictionary": dictionary.loc[0, "definition"] = ""
    if defect == "global_fit": refs["selection_scope"] = "all_data"
    if defect is None:
        assert validate_feature_matrix(matrix, names, dictionary, refs, metadata, folds)["features"] == 13
    else:
        with pytest.raises(ValueError): validate_feature_matrix(matrix, names, dictionary, refs, metadata, folds)


def make_lineage(metadata, folds, config_hash="abc"):
    train = set(folds.id)
    return {"hyperparameter_selection": "inner_train_only", "threshold_selection": "train_only", "contexts": {
        str(f): {"fit_ids": sorted(train if f == -1 else train - set(folds.loc[folds.fold_id.eq(f), "id"])),
                 "config_sha256": config_hash, "producer_revision": "fixture_revision"} for f in (-1, 0, 1, 2)}}


def test_fold_local_references(inputs):
    metadata, folds, _ = inputs
    matrix, names, dictionary, refs = feature_fixture(inputs)
    refs.update(scope="fold_local", selection_scope="train_only")
    lineage = make_lineage(metadata, folds)
    refs["contexts"] = {k: {"fit_ids": v["fit_ids"], "reference_ids": ["r1"]} for k, v in lineage["contexts"].items()}
    matrices = []
    for f in (-1, 0, 1, 2):
        part = matrix if f == -1 else matrix.loc[matrix.id.isin(folds.id)]
        part = part.copy(); part.insert(1, "fold_id", f); matrices.append(part)
    matrix = pd.concat(matrices)
    assert validate_feature_matrix(matrix, names, dictionary, refs, metadata, folds)["feature_scope"] == "fold_local"
    refs["contexts"]["0"]["fit_ids"].append(folds.id.iloc[0])
    with pytest.raises(ValueError, match="held-out"): validate_feature_matrix(matrix, names, dictionary, refs, metadata, folds)


def test_lineage_rejects_held_out_training(inputs):
    metadata, folds, _ = inputs
    lineage = make_lineage(metadata, folds)
    validate_lineage(lineage, metadata, folds)
    lineage["contexts"]["0"]["fit_ids"].append(folds.id.iloc[0])
    with pytest.raises(ValueError, match="leakage"): validate_lineage(lineage, metadata, folds)


def test_adapter_and_paired_comparison(inputs):
    metadata, folds, pred = inputs
    renamed = pred.rename(columns={"score": "p_positive"})
    adapted = adapt_predictions(renamed, {"p_positive": "score"})
    a = validate_predictions(adapted, metadata, folds)
    b = a.copy(); b["model"] = "E2"
    comparison = paired_comparison(a, b)
    assert comparison.pr_auc_delta.eq(0).all()
    with pytest.raises(ValueError): paired_comparison(a, b.iloc[1:])
    with pytest.raises(ValueError): adapt_predictions(pred, {"score": "true_label"})


def test_hashed_bundle_and_tamper(inputs, tmp_path):
    metadata, folds, pred = inputs
    matrix, names, dictionary, refs = feature_fixture(inputs)
    pred = pred.copy(); pred["model"] = "E2"
    configs = {"E2": {"model": "synthetic_only", "feature_names": names, "feature_version": "test_v1", "reference_version": "test_v1"}}
    config_hash = hashlib.sha256(json.dumps(configs["E2"], sort_keys=True).encode()).hexdigest()
    lineage = {"E2": make_lineage(metadata, folds, config_hash)}
    frames = {"features": matrix, "dictionary": dictionary, "predictions": pred, "folds": folds}
    artifacts = {}
    for key, value in {**frames, "references": refs, "configs": configs, "lineage": lineage}.items():
        path = tmp_path / (key + (".csv" if isinstance(value, pd.DataFrame) else ".json"))
        if isinstance(value, pd.DataFrame): value.to_csv(path, index=False)
        else: path.write_text(json.dumps(value))
        artifacts[key] = {"path": path.name, "sha256": sha256(path)}
    manifest = {"schema_version": 1, "feature_version": "test_v1", "feature_names": names, "producer_revision": "fixture",
                "threshold": 0.5, "score_definition": "phishing_probability", "artifacts": artifacts, "teacher_candidates": ["E2"]}
    manifest_path = tmp_path / "manifest.json"; manifest_path.write_text(json.dumps(manifest))
    e1 = validate_predictions(inputs[2], metadata, folds)
    bundle = load_e2_bundle(manifest_path, metadata, folds, e1)
    assert bundle["comparison"].pr_auc_delta.eq(0).all()
    # A valid Train-selected operating point never replaces the primary 0.5 comparison.
    threshold_manifest, threshold_files = threshold_fixture(inputs, tmp_path)
    manifest.update(threshold_manifest)
    threshold_path = threshold_files["threshold_evidence"]
    manifest["artifacts"]["threshold_evidence"] = {"path": threshold_path.name, "sha256": sha256(threshold_path)}
    pred["predicted_label"] = 0  # all synthetic scores are below the fixture threshold 0.95
    pred.to_csv(tmp_path / "predictions.csv", index=False)
    manifest["artifacts"]["predictions"]["sha256"] = sha256(tmp_path / "predictions.csv")
    manifest_path.write_text(json.dumps(manifest))
    bundle = load_e2_bundle(manifest_path, metadata, folds, e1)
    assert bundle["comparison"].false_positive_rate_delta.eq(0).all()
    assert bundle["comparison"].operating_point.eq("fixed_0.5").all()
    assert bundle["operating_point_comparison"].false_positive_rate_delta.eq(-1).all()
    assert bundle["predictions"].decision_threshold.eq(0.95).all()
    (tmp_path / "features.csv").write_text("tampered")
    with pytest.raises(ValueError, match="SHA256"): load_e2_bundle(manifest_path, metadata, folds, e1)


def test_dictionary_rejects_declared_metadata_input(inputs):
    metadata, folds, _ = inputs
    matrix, names, dictionary, refs = feature_fixture(inputs)
    dictionary.loc[len(dictionary)-1, "inputs"] = "url, label, source"
    with pytest.raises(ValueError, match="forbidden metadata inputs"):
        validate_feature_matrix(matrix, names, dictionary, refs, metadata, folds)


def test_optional_source_pilot_provenance(inputs):
    from phishguard_vn.e2_audit import validate_source_evidence
    metadata, _, _ = inputs
    evidence = {"producer_revision": "fixture", "population": "official_train_val", "collection_protocol": "synthetic test",
                "label_policy": "original labels", "official_test_used": False,
                "records": [{"source": "source_0", "observation": "test observation", "review_status": "unverified"}]}
    assert validate_source_evidence(evidence, metadata)["records"] == 1
    evidence["official_test_used"] = True
    with pytest.raises(ValueError, match="Test"): validate_source_evidence(evidence, metadata)
    evidence["official_test_used"] = False
    evidence["population"] = "external_pilot"
    evidence["records"][0].update(id=metadata.id.iloc[0], label="benign", collected_at="2026-10-01", label_provenance="synthetic")
    with pytest.raises(ValueError, match="reuses"): validate_source_evidence(evidence, metadata)


def test_brand_only_adapter_aligns_by_id(inputs):
    from phishguard_vn.e2_audit import assemble_brand_features
    metadata, _, _ = inputs
    matrix, names, _, _ = feature_fixture(inputs)
    brands = matrix[["id", "brand_similarity"]].sample(frac=1, random_state=3)
    combined = assemble_brand_features(brands, names, metadata)
    assert list(combined) == ["id", *names]
    assert list(combined.id) == list(brands.id)
    assert combined.url_len.tolist() == metadata.set_index("id").loc[brands.id, "url_len"].tolist()
    brands.loc[brands.index[0], "id"] = "unexpected_id"
    with pytest.raises(ValueError, match="ineligible"): assemble_brand_features(brands, names, metadata)


def test_review_overlay_is_durable_bound_and_never_semantically_verified(inputs, tmp_path):
    from phishguard_vn.error_analysis import apply_case_reviews, case_signature
    metadata, folds, pred = inputs
    sample = sample_errors(validate_predictions(pred, metadata, folds), model="E1", n=3)
    reviews = {"schema_version": 1, "cases": [
        {"id": r.id, "case_signature": case_signature(r), "taxonomy": ["unknown"],
         "observation": "Specific offline observation for " + r.id, "hypothesis": "Unverified hypothesis for " + r.id,
         "next_verification": "Inspect original evidence for " + r.id, "review_status": "human_verified"}
        for _, r in sample.iterrows()]}
    evidence = pd.DataFrame([{"id": r.id, "case_signature": case_signature(r), "context": int(r.sampling_fold),
                             "intercept": 0.1, "positive_contributions": "toy=0.2", "negative_contributions": "toy=-0.1",
                             "opposite_label_fitting_rows": 0} for _, r in sample.iterrows()])
    path = tmp_path / "reviews.json"; path.write_text(json.dumps(reviews)); original = path.read_bytes()
    cases = apply_case_reviews(sample, evidence, path)
    assert cases.observation.nunique() == len(cases)
    assert cases.review_status.str.contains("human_semantic_verification_pending").all()
    assert not cases.review_status.eq("human_verified").any()
    assert path.read_bytes() == original
    pd.testing.assert_frame_equal(cases, apply_case_reviews(sample, evidence, path))
    sample.loc[0, "score"] += 0.001
    with pytest.raises(ValueError, match="Stale"): apply_case_reviews(sample, evidence, path)


def test_selected_fold_explanations_reconstruct_scores_without_leakage(inputs):
    from sklearn.base import clone
    from phishguard_vn.modeling import build_logistic_baseline
    from phishguard_vn.error_analysis import explain_error_cases
    metadata, folds, _ = inputs
    names = list(CANDIDATE_FEATURES)
    train = metadata.loc[metadata.split.eq("train")].merge(folds, on="id")
    pipeline = build_logistic_baseline(class_weight="balanced")
    pipeline.fit(train[names], train.label.map({"benign": 0, "phishing": 1}))
    selected = []
    for fold in range(3):
        fit = train.loc[train.fold_id.ne(fold)]
        held = train.loc[train.fold_id.eq(fold)].iloc[[0]].copy()
        fitted = clone(pipeline).fit(fit[names], fit.label.map({"benign": 0, "phishing": 1}))
        held["score"] = fitted.predict_proba(held[names])[:, 1]
        selected.append(held)
    sample = pd.concat(selected, ignore_index=True)
    sample["model"] = "E1"; sample["evaluation_partition"] = "group_cv"; sample["outcome"] = "FP"
    evidence, terms, models = explain_error_cases(sample, metadata, folds, pipeline)
    assert evidence.score_abs_error.max() < 1e-10
    assert evidence.fit_rows.eq(12).all()
    assert len(terms) == 3 * len(names)
    np.testing.assert_allclose(terms.groupby("id").logit_contribution.sum().reindex(evidence.id).to_numpy() + evidence.intercept.to_numpy(), evidence.logit)
    sample.loc[0, "score"] += 0.1
    with pytest.raises(ValueError, match="reproduce"): explain_error_cases(sample, metadata, folds, pipeline, context_models=models)


def test_analysis_edit_reuses_e1_but_training_edit_does_not():
    from phishguard_vn.week5 import _baseline_cache_matches
    modules = ["__init__", "data", "features", "url_parser", "splits", "modeling", "evaluation"]
    files = {f"src/phishguard_vn/{m}.py": "training" for m in modules}
    files.update({"raw.csv": "raw", "baseline.toml": "config", "src/phishguard_vn/error_analysis.py": "old"})
    prior = {"files_sha256": files, "versions": {"numpy": "test"}, "python": "test"}
    current = json.loads(json.dumps(prior)); current["files_sha256"]["src/phishguard_vn/error_analysis.py"] = "new"
    assert _baseline_cache_matches(prior, current, "raw.csv", "baseline.toml")
    current["files_sha256"]["src/phishguard_vn/modeling.py"] = "changed"
    assert not _baseline_cache_matches(prior, current, "raw.csv", "baseline.toml")


def threshold_fixture(inputs, tmp_path):
    metadata, folds, _ = inputs
    allowed = {str(f): set(folds.id if f == -1 else folds.loc[folds.fold_id.ne(f), "id"]) for f in (-1, 0, 1, 2)}
    records, rows = {}, []
    for context, ids in allowed.items():
        ordered = sorted(ids)
        inner = {row_id: (i // 2) % 2 for i, row_id in enumerate(ordered)}
        for row_id in ordered:
            label = int(metadata.set_index("id").label[row_id] == "phishing")
            rows.append({"model": "E2", "context": context, "id": row_id, "true_label": label, "score": 0.1 + 0.8*label, "inner_fold_id": inner[row_id]})
        records[context] = {"value": 0.95, "selection_scope": "inner_train_only", "prediction_kind": "inner_oof", "selection_ids": ordered,
                            "method": "synthetic protocol fixture only", "evidence_artifact": "threshold_evidence",
                            "inner_fit_ids": {str(f): [i for i in ordered if inner[i] != f] for f in (0, 1)}}
    path = tmp_path / "threshold.csv"; pd.DataFrame(rows).to_csv(path, index=False)
    return {"decision_thresholds": {"E2": records}}, {"threshold_evidence": path}


@pytest.mark.parametrize("defect", [None, "outer_held_out", "validation", "scope", "inner_leak", "evidence_label", "missing_evidence"])
def test_candidate_threshold_provenance(inputs, tmp_path, defect):
    from phishguard_vn.e2_audit import validate_candidate_thresholds
    metadata, folds, pred = inputs
    manifest, files = threshold_fixture(inputs, tmp_path)
    record = manifest["decision_thresholds"]["E2"]["0"]
    if defect == "outer_held_out": record["selection_ids"].append(folds.id.iloc[0])
    if defect == "validation": record["selection_ids"].append(metadata.id.iloc[-1])
    if defect == "scope": record["selection_scope"] = "official_validation"
    if defect == "inner_leak": record["inner_fit_ids"]["0"].append(record["selection_ids"][0])
    if defect == "evidence_label":
        table = pd.read_csv(files["threshold_evidence"]); table.loc[0, "true_label"] = 1-table.loc[0, "true_label"]; table.to_csv(files["threshold_evidence"], index=False)
    if defect == "missing_evidence": files = {}
    if defect:
        with pytest.raises(ValueError): validate_candidate_thresholds(manifest, ["E2"], metadata, folds, files)
    else:
        thresholds = validate_candidate_thresholds(manifest, ["E2"], metadata, folds, files)
        assert set(thresholds["E2"].values()) == {0.95}
        pred["model"] = "E2"; pred["predicted_label"] = 0
        joined = validate_predictions(pred, metadata, folds, thresholds=thresholds)
        assert joined.decision_threshold.eq(0.95).all()
        # E1 fixture was edited by reference above: rebuild its original fixed decisions.
        raw_e1 = pred.copy(); raw_e1["model"] = "E1"; raw_e1["predicted_label"] = raw_e1.score.ge(0.5).astype(int)
        e1 = validate_predictions(raw_e1, metadata, folds)
        comparison = paired_comparison(e1, joined)
        assert comparison.e1_threshold.eq(0.5).all()
        assert comparison.operating_point.eq("candidate_train_selected").all()


def test_resource_feature_name_is_not_source_metadata(inputs):
    metadata, folds, _ = inputs
    matrix, names, dictionary, refs = feature_fixture(inputs)
    matrix = matrix.rename(columns={"brand_similarity": "resource_similarity"})
    names[-1] = "resource_similarity"; dictionary.loc[len(dictionary)-1, "feature"] = "resource_similarity"
    validate_feature_matrix(matrix, names, dictionary, refs, metadata, folds)


def test_pr5_parser_alias_cache_compatibility_is_narrow():
    from phishguard_vn.week5 import _baseline_cache_matches
    modules = ["__init__", "data", "features", "url_parser", "splits", "modeling", "evaluation"]
    files = {f"src/phishguard_vn/{m}.py": "original" for m in modules}
    files.update({"raw.csv": "raw", "baseline.toml": "config"})
    prior = {"files_sha256": files, "versions": {"tldextract": "5.4.0"}, "python": "test"}
    current = json.loads(json.dumps(prior))
    current["files_sha256"]["src/phishguard_vn/url_parser.py"] = "alias-renamed"
    assert not _baseline_cache_matches(prior, current, "raw.csv", "baseline.toml")
    current["parser_legacy_alias_sha256"] = "original"
    assert _baseline_cache_matches(prior, current, "raw.csv", "baseline.toml")
    current["parser_legacy_alias_sha256"] = "additional-behavior-change"
    assert not _baseline_cache_matches(prior, current, "raw.csv", "baseline.toml")


@pytest.mark.parametrize("defect", [None, "duplicate", "test_id", "order", "nan", "lexical_drift", "reference", "false_freeze"])
def test_native_hy_feature_audit_without_models(inputs, tmp_path, defect):
    from pathlib import Path
    from phishguard_vn.brand_features import BRAND_FEATURES, E2_FEATURES, FEATURE_SCHEMA_VERSION, load_reference
    from phishguard_vn.e2_audit import audit_native_brand_features
    metadata, folds, _ = inputs
    interim = tmp_path / "data/interim"; interim.mkdir(parents=True)
    splits = tmp_path / "data/splits"; splits.mkdir()
    templates = tmp_path / "reports/templates"; templates.mkdir(parents=True)
    original_root = Path(__file__).resolve().parents[1]
    for filename in ["brand_feature_dictionary.csv", "feature_dictionary.csv"]:
        (templates / filename).write_bytes((original_root / "reports/templates" / filename).read_bytes())
    excluded = pd.DataFrame({"id": ["excluded_1", "excluded_2"], "error_reason": ["unresolved_domain"]*2, "split": ["train"]*2})
    excluded[["id", "error_reason"]].to_csv(interim / "05_excluded_rows_trainval.csv", index=False)
    matrix = metadata[["id", *CANDIDATE_FEATURES]].copy()
    for name in BRAND_FEATURES: matrix[name] = 0.0
    for split in ["train", "val"]:
        metadata.loc[metadata.split.eq(split), ["id"]].to_csv(splits / f"url_{split}.csv", index=False)
    # No Test file or model/prediction/config/lineage files exist in this fixture.
    metadata[["id", "url"]].to_csv(interim / "core_gold_silver.csv", index=False)
    ids_hash = lambda ids: hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
    native = {"feature_schema_version": FEATURE_SCHEMA_VERSION, "partition": "trainval", "test_excluded_from_this_artifact": True,
              "frozen": False, "columns": ["id", *E2_FEATURES], "e1_columns": list(CANDIDATE_FEATURES), "brand_columns": list(BRAND_FEATURES),
              "rows_x": len(matrix), "rows_excluded": 2, "rows_by_split": {"train": {"x": 18, "excluded": 2}, "val": {"x": 6, "excluded": 0}},
              "ids_sha256_x": ids_hash(matrix.id), "ids_sha256_excluded": ids_hash(excluded.id), "brand_reference": load_reference().summary(),
              "input_file": "core_gold_silver.csv", "input_sha256": sha256(interim / "core_gold_silver.csv"),
              "splits_sha256": {f"url_{s}.csv": sha256(splits / f"url_{s}.csv") for s in ["train", "val"]},
              "brand_feature_dictionary_sha256": sha256(templates / "brand_feature_dictionary.csv"),
              "e1_feature_dictionary_sha256": sha256(templates / "feature_dictionary.csv")}
    if defect == "duplicate": matrix = pd.concat([matrix, matrix.iloc[[0]]])
    if defect == "test_id": matrix.loc[0, "id"] = "official_test_id"
    if defect == "order": matrix = matrix[list(reversed(matrix.columns))]
    if defect == "nan": matrix.loc[0, "brand_in_domain"] = np.nan
    if defect == "lexical_drift": matrix.loc[0, "url_len"] += 1
    if defect == "reference": native["brand_reference"]["sha256"] = "wrong"
    if defect == "false_freeze": native["frozen"] = True
    matrix.to_csv(interim / "05_matrix_X_brand_trainval.csv", index=False)
    manifest = interim / "05_matrix_X_brand_trainval.manifest.json"; manifest.write_text(json.dumps(native))
    report = tmp_path / "audit.json"
    if defect:
        with pytest.raises(ValueError): audit_native_brand_features(manifest, metadata, folds, excluded, tmp_path, report)
        assert json.loads(report.read_text())["status"] == "FAIL"
    else:
        result = audit_native_brand_features(manifest, metadata, folds, excluded, tmp_path, report)
        assert result["status"] == "PASS" and result["feature_status"] == "PRELIMINARY"
        assert result["n_features"] == 20 and result["model_comparison_status"] == "PENDING_PRODUCER_E2_PREDICTIONS"
