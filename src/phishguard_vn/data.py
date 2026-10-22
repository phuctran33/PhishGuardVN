"""data loading, audit and reproducible core preparation."""
from __future__ import annotations

from pathlib import Path
import pandas as pd


LABEL_MAP = {"benign": 0, "phishing": 1}

CORE_TIERS = ("gold", "silver")
REQUIRED_COLUMNS = {"id","url","label","tier","split"}

def load_dataset(path: str | Path) -> pd.DataFrame:
    """read URL table, validate required columns and preserve id/raw URL."""
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    frame = pd.read_csv(
        path,
        dtype={
            "id": "string",
            "url": "string",
            "label": "string",
            "tier": "string",
            "split": "string",
        },
    )
    missing_columns = REQUIRED_COLUMNS -  set(frame.columns)
    if missing_columns:
        raise ValueError(
            f"Dataset is missing required columns: {sorted(missing_columns)}"
        )
    if frame.empty:
        raise ValueError(f"Dataset contains no rows: {path}")
    return frame

def audit_quality(frame: pd.DataFrame) -> dict:
    """missing/constant fields, duplicates, label conflicts and counts."""
    # summarize data
    missing_by_column = {
        col: int(count)
        for col, count in frame.isna().sum().items()
    }
    constant_columns = [
        col for col in frame.columns
        if not frame.empty and frame[col].nunique(dropna=False) <=1
        ]
    # count values in a row
    def value_counts(column:str)->dict:
        if column not in frame.columns:
            return{}
        counts = frame[column].value_counts(dropna=False)
        return{
            ("Missing" if pd.isna(value) else str(value)) : int (count)
            for value, count in counts.items()
        }
    # summary the duplicated ID or URL
    def duplicate_summary(column:str)->dict:
        if column not in frame.columns:
            return {
                "repeated rows after first" :0,
                "unique duplicate values" :0,
            }
        values = frame[column].dropna()
        duplicated = values[values.duplicated(keep=False)]
        return {
            "repeated rows after first": int(values.duplicated().sum()),
            "unique duplicate values":int(duplicated.nunique()),
        }
    # Find ID or URL with many different labels
    def label_conflicts(column: str)->dict:
        if column not in frame.columns or "label" not in frame.columns:
            return {"group count": 0, "examples":[]}
        valid = frame.loc[
            frame[column].notna() & frame["label"].notna(),
            [column,"label"],
        ]
        label_per_value = valid.groupby(column)["label"].nunique()
        conflicts = label_per_value[label_per_value>1].index
        return {
            "group count": int(len(conflicts)),
            "examples":[str(value) for value in conflicts[:10]]
        }
    # Labels not in the LABELS_MAP
    unknown_labels = []
    if "label" in frame.columns:
        unknown_labels = sorted(
            str(value)
            for value in frame["label"].dropna().unique()
            if value not in LABEL_MAP
        )
    # Summary the report
    return {
        "shape": {
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
        },
        "missing_by_column": missing_by_column,
        "constant_columns": constant_columns,
        "duplicates": {
            "exact_duplicate_rows": int(frame.duplicated().sum()),
            "id": duplicate_summary("id"),
            "url": duplicate_summary("url"),
        },
        "label_counts": value_counts("label"),
        "unknown_labels": unknown_labels,
        "tier_counts": value_counts("tier"),
        "split_counts": value_counts("split"),
        "label_conflicts": {
            "by_id": label_conflicts("id"),
            "by_url": label_conflicts("url"),
        },
    }
def prepare_core(frame: pd.DataFrame) -> pd.DataFrame:
    """select gold/silver; preserve split and log further filtering by id."""
    required_columns = {"id", "url", "label", "tier", "split"}
    missing_columns = required_columns - set(frame.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    if frame["tier"].isna().any():
        raise ValueError("Missing tier values; inspect the quality report.")

    allowed_tiers = set(CORE_TIERS) | {"bronze"}
    unknown_tiers = set(frame["tier"].unique()) - allowed_tiers

    if unknown_tiers:
        raise ValueError(
            f"Unknown tier values: {sorted(unknown_tiers)}"
        )

    core = frame.loc[
        frame["tier"].isin(CORE_TIERS)
    ].copy()

    if core.empty:
        raise ValueError("Core dataset is empty.")

    return core
