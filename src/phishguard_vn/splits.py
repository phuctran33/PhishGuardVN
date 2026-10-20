"""TODO(Hưng): inspect official splits and create group CV on train only."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def audit_domain_overlap(frame: pd.DataFrame) -> dict:
    """TODO: compare registrable_domain groups across official train/val/test."""
    raise NotImplementedError("TODO(Hưng): implement audit_domain_overlap.")


def make_group_folds(train_frame: pd.DataFrame, n_splits: int = 3, seed: int = 42) -> pd.DataFrame:
    """TODO: return id/fold_id; verify disjoint domains and both labels per fold.

    Input must be agreed train partition. Group CV is not itself temporal holdout.
    Resolve invalid fold conditions explicitly.
    """
    raise NotImplementedError("TODO(Hưng): implement make_group_folds.")
