"""TODO(Hy): reference candidates, not a validated selection result."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Reference names from docs/schema.md. Verify formulas and useful columns.
# is_https is intentionally excluded.
CANDIDATE_FEATURES = (
    "url_len", "dom_len", "is_ip", "tld_len", "subdom_cnt",
    "letter_cnt", "digit_cnt", "special_cnt", "eq_cnt", "qm_cnt",
    "amp_cnt", "dot_cnt", "dash_cnt", "under_cnt", "letter_ratio",
    "digit_ratio", "spec_ratio", "slash_cnt", "entropy", "path_len", "query_len",
)


def extract_features(raw_url: str) -> dict[str, float]:
    """TODO: use shared parser; define count scope and stable feature names."""
    raise NotImplementedError("TODO(Hy): implement extract_features.")


def build_feature_table(frame: pd.DataFrame) -> pd.DataFrame:
    """TODO: numeric features plus id for joins; keep metadata out of X."""
    raise NotImplementedError("TODO(Hy): implement build_feature_table.")
