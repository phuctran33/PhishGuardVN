"""Synthetic split/domain contracts; no network or real PhishVN domains needed."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from phishguard_vn.splits import audit_domain_overlap, make_group_folds


@pytest.fixture
def official_splits():
    return pd.DataFrame({
        "id": ["train-id", "val-id", "test-id"],
        "split": ["train", "val", "test"],
        "registrable_domain": ["alpha.example", "beta.example", "gamma.example"],
    })


@pytest.fixture
def synthetic_train():
    # Domains identify independent synthetic sites, not labels or sources.
    return pd.DataFrame([
        {
            "id": f"site-{group:02d}-row-{row}",
            "url": f"https://site-{group}.example/page-{row}",
            "split": "train", "tier": "gold",
            "registrable_domain": f"site-{group}.example",
            "label": label,
        }
        for group in range(12)
        for row, label in enumerate(["benign", "benign", "phishing"])
    ])


def test_clean_splits_have_no_domain_overlap(official_splits):
    before = official_splits.copy(deep=True)
    report = audit_domain_overlap(official_splits)
    assert report["status"] == "no_overlap_detected"
    assert report["coverage_complete"]
    assert report["unique_groups_by_split"] == {"train": 1, "val": 1, "test": 1}
    assert all(pair["overlap_count"] == 0 for pair in report["pairwise"])
    pd.testing.assert_frame_equal(official_splits, before)


def test_shared_domain_is_detected(official_splits):
    official_splits.loc[1, "registrable_domain"] = "alpha.example"
    report = audit_domain_overlap(official_splits)
    pair = report["pairwise"][0]
    assert (pair["split_a"], pair["split_b"]) == ("train", "val")
    assert pair["overlap_count"] == 1
    assert pair["overlap_groups"] == ["alpha.example"]
    assert report["status"] == "overlap_detected"


@pytest.mark.parametrize("key", [None, pd.NA, np.nan, "", "  "])
def test_missing_domains_never_form_a_shared_group(official_splits, key):
    frame = official_splits.assign(registrable_domain=[key, key, "gamma.example"])
    report = audit_domain_overlap(frame)
    assert report["unknown_domain_rows"] == 2
    assert report["unknown_by_split"] == {"train": 1, "val": 1, "test": 0}
    assert report["unique_groups_by_split"] == {"train": 0, "val": 0, "test": 1}
    assert report["status"] == "no_overlap_among_resolved"
    assert not report["coverage_complete"]
    assert all(pair["overlap_count"] == 0 for pair in report["pairwise"])


def test_all_unknown_domains_are_not_reported_as_clean(official_splits):
    report = audit_domain_overlap(official_splits.assign(registrable_domain=None))
    assert report["status"] == "unresolved"
    assert report["valid_domain_rows"] == 0
    assert report["unknown_domain_rows"] == len(official_splits)


@pytest.mark.parametrize("key,reason", [
    ("Alpha.example", "noncanonical"), ("alpha.example.", "noncanonical"),
    (" alpha.example", "noncanonical"), ("https://alpha.example", "invalid_syntax"),
    ("alpha.example/path", "invalid_syntax"), ("alpha.example:443", "invalid_syntax"),
    ("localhost", "invalid_syntax"), ("a_b.example", "invalid_syntax"),
    ("127.0.0.1", "ip_literal"), ("[2001:db8::1]", "ip_literal"),
    ("ngân-hàng.example", "invalid_syntax"), (123, "not_string"),
])
def test_invalid_keys_are_diagnostics_not_silently_repaired(official_splits, key, reason):
    frame = official_splits.assign(registrable_domain=[key, "beta.example", "gamma.example"])
    report = audit_domain_overlap(frame)
    assert report["invalid_domain_reasons"] == {reason: 1}
    assert report["unknown_domain_rows"] == 1


def test_punycode_is_accepted_syntactically_without_claiming_psl_approval(official_splits):
    frame = official_splits.assign(registrable_domain=["xn--bcher-kva.example", "beta.example", "gamma.example"])
    assert audit_domain_overlap(frame)["valid_domain_rows"] == 3


@pytest.mark.parametrize("operation,match", [
    (lambda f: f.assign(id=["same", "same", "other"]), "Duplicate id"),
    (lambda f: f.assign(id=[None, "val-id", "test-id"]), "id must"),
    (lambda f: f.assign(split=["training", "val", "test"]), "Unknown or missing split"),
    (lambda f: f.drop(columns="registrable_domain"), "Missing required columns"),
    (lambda f: f.iloc[:0], "must not be empty"),
])
def test_audit_schema_failures_are_explicit(official_splits, operation, match):
    with pytest.raises(ValueError, match=match):
        audit_domain_overlap(operation(official_splits))


def test_fold_assignment_covers_ids_and_preserves_groups(synthetic_train):
    before = synthetic_train.copy(deep=True)
    folds = make_group_folds(synthetic_train)
    assert list(folds.columns) == ["id", "fold_id"]
    assert folds["id"].is_unique and set(folds["id"]) == set(synthetic_train["id"])
    assert set(folds["fold_id"]) == {0, 1, 2}
    joined = synthetic_train.merge(folds, on="id", validate="one_to_one")
    assert joined.groupby("registrable_domain")["fold_id"].nunique().eq(1).all()
    for fold in range(3):
        validation = joined.loc[joined["fold_id"].eq(fold)]
        training = joined.loc[joined["fold_id"].ne(fold)]
        assert set(validation["label"]) == set(training["label"]) == {"benign", "phishing"}
        assert set(validation["registrable_domain"]).isdisjoint(training["registrable_domain"])
    summary = pd.DataFrame(folds.attrs["fold_summary"])
    assert summary["n_validation"].sum() == len(synthetic_train)
    assert summary["benign"].add(summary["phishing"]).equals(summary["n_validation"])
    assert np.allclose(summary["phishing_ratio"], summary["phishing"] / summary["n_validation"])
    pd.testing.assert_frame_equal(synthetic_train, before)


def test_seed_and_input_order_reproduce_the_same_id_mapping(synthetic_train):
    expected = make_group_folds(synthetic_train, seed=42)
    pd.testing.assert_frame_equal(expected, make_group_folds(synthetic_train, seed=42))
    shuffled = synthetic_train.sample(frac=1, random_state=15)
    pd.testing.assert_frame_equal(expected, make_group_folds(shuffled, seed=42))


@pytest.mark.parametrize("key", [None, "", "bad/domain", "127.0.0.1", "SITE.example"])
def test_unresolved_group_keys_fail_before_cv(synthetic_train, key):
    frame = synthetic_train.copy()
    frame.loc[0, "registrable_domain"] = key
    with pytest.raises(ValueError, match="Unresolved registrable_domain"):
        make_group_folds(frame)


@pytest.mark.parametrize("split", ["val", "test"])
def test_official_validation_and_test_are_rejected(synthetic_train, split):
    frame = synthetic_train.copy()
    frame.loc[0, "split"] = split
    with pytest.raises(ValueError, match="official train only"):
        make_group_folds(frame)


@pytest.mark.parametrize("n_splits", [0, 1, -1, True, 2.5])
def test_invalid_fold_counts(synthetic_train, n_splits):
    with pytest.raises(ValueError, match="n_splits"):
        make_group_folds(synthetic_train, n_splits=n_splits)


def test_insufficient_groups_and_class_support(synthetic_train):
    with pytest.raises(ValueError, match="Insufficient distinct groups"):
        make_group_folds(synthetic_train[synthetic_train["registrable_domain"].eq("site-0.example")])
    frame = synthetic_train.loc[
        synthetic_train["label"].eq("benign") |
        synthetic_train["registrable_domain"].eq("site-0.example")
    ]
    with pytest.raises(ValueError, match="Insufficient class group support"):
        make_group_folds(frame)


@pytest.mark.parametrize("operation,match", [
    (lambda f: f.assign(label="benign"), "Both string labels"),
    (lambda f: f.assign(label=0), "Both string labels"),
    (lambda f: f.assign(label="unknown"), "Both string labels"),
    (lambda f: f.assign(tier="bronze"), "core gold/silver"),
    (lambda f: pd.concat([f, f.iloc[[0]]]), "Duplicate id"),
    (lambda f: f.drop(columns="tier"), "Missing required columns"),
])
def test_noncore_or_invalid_labels_and_ids_fail(synthetic_train, operation, match):
    with pytest.raises(ValueError, match=match):
        make_group_folds(operation(synthetic_train))


def test_one_class_fold_from_splitter_is_not_returned(monkeypatch):
    # A heuristic splitter can fail despite necessary class/group support.
    frame = pd.DataFrame([
        {"id": f"g-{g}-r-{r}", "split": "train", "tier": "silver",
         "registrable_domain": f"group-{g}.example",
         "label": "benign" if g < 3 else "phishing"}
        for g in range(6) for r in range(2)
    ])

    class OneClassSplitter:
        def __init__(self, **kwargs):
            pass

        def split(self, X, y, groups):
            validation = np.flatnonzero(groups.eq("group-3.example").to_numpy())
            training = np.flatnonzero(groups.ne("group-3.example").to_numpy())
            yield training, validation

    monkeypatch.setattr("sklearn.model_selection.StratifiedGroupKFold", OneClassSplitter)
    with pytest.raises(ValueError, match="produced one-class fold"):
        make_group_folds(frame)


def test_local_real_handoff_matches_reproducible_train_only_fold_export():
    """Integration test when ignored local handoff CSVs have been generated."""
    interim = Path(__file__).resolve().parents[1] / "data" / "interim"
    names = ["core_gold_silver.csv", "03_registrable_domains.csv", "02_group_folds_train.csv"]
    if not all((interim / name).is_file() for name in names):
        pytest.skip("Run notebook 03 and notebook 02 to generate local real-data handoffs.")
    core, domains, saved = [pd.read_csv(interim / name, dtype={"id": "string"}) for name in names]
    assert domains["id"].is_unique and set(domains["id"]) == set(core["id"])
    joined = core.merge(domains, on="id", validate="one_to_one", how="left")
    report = audit_domain_overlap(joined)
    unresolved = joined["registrable_domain"].isna()
    assert report["unknown_domain_rows"] == int(unresolved.sum())
    eligible = joined.loc[joined["split"].eq("train") & ~unresolved]
    expected = make_group_folds(eligible, n_splits=3, seed=42)
    pd.testing.assert_frame_equal(saved, expected, check_dtype=False)
    pd.testing.assert_frame_equal(
        expected, make_group_folds(eligible.sample(frac=1, random_state=99), n_splits=3, seed=42)
    )
    assert list(saved.columns) == ["id", "fold_id"] and saved["id"].is_unique
    assert set(saved["id"]) == set(eligible["id"])
    assert set(saved["id"]).isdisjoint(joined.loc[joined["split"].ne("train"), "id"])
    assigned = eligible.merge(saved, on="id", validate="one_to_one")
    assert assigned.groupby("registrable_domain")["fold_id"].nunique().eq(1).all()
    for fold in range(3):
        assert set(assigned.loc[assigned["fold_id"].eq(fold), "label"]) == {"benign", "phishing"}
