"""TODO(Khiêm): data loading, audit and reproducible core preparation."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

LABEL_MAP = {"benign": 0, "phishing": 1}
CORE_TIERS = ("gold", "silver")


def load_dataset(path: str | Path) -> pd.DataFrame:
    """TODO: read URL table, validate required columns and preserve id/raw URL."""
    raise NotImplementedError("TODO(Khiêm): implement load_dataset.")


def audit_quality(frame: pd.DataFrame) -> dict:
    """TODO: missing/constant fields, duplicates, label conflicts and counts."""
    raise NotImplementedError("TODO(Khiêm): implement audit_quality.")


def prepare_core(frame: pd.DataFrame) -> pd.DataFrame:
    """TODO: select gold/silver; preserve split and log further filtering by id."""
    raise NotImplementedError("TODO(Khiêm): implement prepare_core.")
