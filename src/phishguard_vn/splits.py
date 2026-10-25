"""Diagnostics for supplied domains and reproducible CV on official core train.

No URL parsing or Public Suffix List inference is performed here. Domain keys
must be supplied and approved by the parser owner before use on real data.
"""
from __future__ import annotations

from ipaddress import ip_address
from itertools import combinations
from numbers import Integral
import re

import numpy as np
import pandas as pd


OFFICIAL_SPLITS = ("train", "val", "test")
LABELS = ("benign", "phishing")
_DOMAIN_PATTERN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


def _validate_frame(frame: pd.DataFrame, required: set[str]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Expected a pandas DataFrame.")
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Input frame must not be empty.")
    ids = frame["id"]
    if ids.isna().any() or not ids.map(
        lambda value: isinstance(value, str) and bool(value.strip())
    ).all():
        raise ValueError("id must contain non-missing, non-blank strings.")
    if not ids.is_unique:
        raise ValueError("Duplicate id values are not allowed.")
    if not frame["split"].isin(OFFICIAL_SPLITS).all():
        raise ValueError("Unknown or missing split; expected train, val or test.")
    return frame.copy().reset_index(drop=True)


def _domain_issue(value) -> str | None:
    """Syntactic key policy only: not proof of registrability or PSL validity.

    Require lowercase ASCII/IDNA keys without whitespace, scheme, path or port.
    IP literals are unresolved until the team agrees an explicit grouping policy.
    Do not repair invalid keys, which could silently change grouping semantics.
    """
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return "missing"
    if not isinstance(value, str):
        return "not_string"
    if not value.strip():
        return "blank"
    if value != value.strip() or value != value.lower() or value.endswith("."):
        return "noncanonical"
    try:
        ip_address(value.removeprefix("[").removesuffix("]"))
    except ValueError:
        pass
    else:
        return "ip_literal"
    if len(value) > 253 or not _DOMAIN_PATTERN.fullmatch(value):
        return "invalid_syntax"
    return None


def _domain_issues(frame: pd.DataFrame) -> pd.Series:
    return frame["registrable_domain"].map(_domain_issue)


def audit_domain_overlap(frame: pd.DataFrame) -> dict:
    """Report supplied-domain overlaps, keeping unresolved keys separate.

    Require unique string id, official split and registrable_domain columns.
    Invalid/missing domains are counted, not treated as a shared domain and not
    dropped from the input. Status describes only the supplied, resolved keys;
    syntactic validity does not establish that Hy's mapping has been approved.
    """
    work = _validate_frame(frame, {"id", "split", "registrable_domain"})
    issues = _domain_issues(work)
    valid = issues.isna()
    groups = {
        split: set(work.loc[work["split"].eq(split) & valid, "registrable_domain"])
        for split in OFFICIAL_SPLITS
    }
    pairwise = []
    for left, right in combinations(OFFICIAL_SPLITS, 2):
        shared = sorted(groups[left] & groups[right])
        pairwise.append({
            "split_a": left, "split_b": right,
            "groups_a": len(groups[left]), "groups_b": len(groups[right]),
            "overlap_count": len(shared), "overlap_groups": shared,
        })
    unknown = int((~valid).sum())
    if any(row["overlap_count"] for row in pairwise):
        status = "overlap_detected"
    elif not valid.any():
        status = "unresolved"
    elif unknown:
        status = "no_overlap_among_resolved"
    else:
        status = "no_overlap_detected"
    return {
        "n_rows": len(work), "unique_ids": int(work["id"].nunique()),
        "rows_by_split": {s: int(work["split"].eq(s).sum()) for s in OFFICIAL_SPLITS},
        "valid_domain_rows": int(valid.sum()), "unknown_domain_rows": unknown,
        "invalid_domain_reasons": {str(k): int(v) for k, v in issues.value_counts().items()},
        "unknown_by_split": {
            s: int((work["split"].eq(s) & ~valid).sum()) for s in OFFICIAL_SPLITS
        },
        "unique_groups_by_split": {s: len(groups[s]) for s in OFFICIAL_SPLITS},
        "pairwise": pairwise, "coverage_complete": unknown == 0, "status": status,
        "limitation": "Supplied keys only; syntax checks do not validate PSL, parser provenance or approval.",
    }


def make_group_folds(train_frame: pd.DataFrame, n_splits: int = 3, seed: int = 42) -> pd.DataFrame:
    """Return exactly id/fold_id for official Gold/Silver TRAIN rows only.

    Require id, split, tier, label and approved registrable_domain keys. Only
    benign/phishing string labels are supported. Each class must occupy at least
    n_splits groups; that necessary check does not guarantee stratification.
    Fail if the single seeded StratifiedGroupKFold attempt yields a one-class
    train or validation fold. Do not retry or silently change the algorithm.

    IDs are sorted before splitting, making the mapping independent of input
    row order. Fold numbers are 0..n_splits-1. attrs['fold_summary'] contains
    validation/train class supports and group counts; phishing_ratio is a
    fraction in [0, 1]. Group CV does not imply temporal holdout.
    """
    if isinstance(n_splits, bool) or not isinstance(n_splits, Integral) or n_splits < 2:
        raise ValueError("n_splits must be an integer >= 2.")
    if isinstance(seed, bool) or not isinstance(seed, Integral) or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer in [0, 2**32).")
    work = _validate_frame(
        train_frame, {"id", "split", "tier", "label", "registrable_domain"}
    )
    if not work["split"].eq("train").all():
        raise ValueError("Group CV accepts official train only; val/test rows are forbidden.")
    if not work["tier"].isin(("gold", "silver")).all():
        raise ValueError("Group CV accepts core gold/silver tiers only.")
    if not work["label"].isin(LABELS).all() or set(work["label"]) != set(LABELS):
        raise ValueError("Both string labels benign/phishing are required; unknown labels are rejected.")
    issues = _domain_issues(work)
    if issues.notna().any():
        counts = {str(k): int(v) for k, v in issues.value_counts().items()}
        raise ValueError(
            f"Unresolved registrable_domain keys: {counts}. "
            "Agree missing/invalid/IP policy with Hy before Group CV."
        )
    n_groups = work["registrable_domain"].nunique()
    if n_groups < n_splits:
        raise ValueError(f"Insufficient distinct groups: {n_groups} for {n_splits} folds.")
    support = work.groupby("label")["registrable_domain"].nunique().reindex(LABELS)
    if support.lt(n_splits).any():
        raise ValueError(
            f"Insufficient class group support for {n_splits} folds: {support.to_dict()}. "
            "Each label must occur in at least n_splits distinct groups."
        )

    from sklearn.model_selection import StratifiedGroupKFold

    work = work.sort_values("id", kind="stable").reset_index(drop=True)
    splitter = StratifiedGroupKFold(
        n_splits=int(n_splits), shuffle=True, random_state=int(seed)
    )
    fold_ids = np.full(len(work), -1, dtype=int)
    summary = []
    for fold, (train_index, val_index) in enumerate(splitter.split(
        np.zeros((len(work), 1)), work["label"], groups=work["registrable_domain"]
    )):
        train = work.iloc[train_index]
        val = work.iloc[val_index]
        train_groups = set(train["registrable_domain"])
        val_groups = set(val["registrable_domain"])
        assert train_groups.isdisjoint(val_groups), "Group leakage inside CV fold."
        if set(train["label"]) != set(LABELS) or set(val["label"]) != set(LABELS):
            raise ValueError(
                f"StratifiedGroupKFold produced one-class fold {fold}: "
                f"train={train['label'].value_counts().to_dict()}, "
                f"validation={val['label'].value_counts().to_dict()}. "
                "No folds returned; review n_splits/group support without using official test."
            )
        assert (fold_ids[val_index] == -1).all(), "ID assigned to multiple folds."
        fold_ids[val_index] = fold
        summary.append({
            "fold_id": fold, "n_validation": len(val), "n_train": len(train),
            "validation_groups": len(val_groups), "train_groups": len(train_groups),
            "benign": int(val["label"].eq("benign").sum()),
            "phishing": int(val["label"].eq("phishing").sum()),
            "phishing_ratio": float(val["label"].eq("phishing").mean()),
            "train_benign": int(train["label"].eq("benign").sum()),
            "train_phishing": int(train["label"].eq("phishing").sum()),
        })
    assert (fold_ids >= 0).all(), "Some IDs have no validation fold."
    result = work[["id"]].copy()
    result["fold_id"] = fold_ids
    assert result["id"].is_unique and set(result["id"]) == set(train_frame["id"])
    result.attrs.update({
        "strategy": "StratifiedGroupKFold", "n_splits": int(n_splits),
        "seed": int(seed), "fold_summary": summary,
        "domain_policy": "Approved canonical ASCII/IDNA domain keys; unresolved/IP keys rejected.",
    })
    return result
