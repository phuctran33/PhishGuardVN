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
