"""TODO(Phúc): Dummy/LR baselines; no model has been trained."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def build_dummy_baseline():
    """TODO: construct DummyClassifier(strategy='most_frequent')."""
    raise NotImplementedError("TODO(Phúc): implement build_dummy_baseline.")


def build_logistic_baseline(seed: int = 42, class_weight: str | None = None):
    """TODO: scaler + LR pipeline; learned selectors belong inside each CV fold."""
    raise NotImplementedError("TODO(Phúc): implement build_logistic_baseline.")


def run_baseline(features: pd.DataFrame, targets: pd.DataFrame, folds: pd.DataFrame, config: dict) -> dict:
    """TODO: align by id, evaluate matched folds and log settings/artifacts.

    Fit preprocessing in each training fold. Keep test separate; return actual
    measured results only. Save feature schema alongside the trained pipeline.
    """
    raise NotImplementedError("TODO(Phúc): implement run_baseline.")


def predict_url(raw_url: str, pipeline, feature_names: list[str]) -> dict:
    """TODO: same extractor and column order as training, for local prediction."""
    raise NotImplementedError("TODO(Phúc): implement predict_url.")
