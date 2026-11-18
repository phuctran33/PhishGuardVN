"""Paired domain-bootstrap intervals for mean outer-fold average precision.

Resample registrable domains separately within each held-out fold. Every
candidate and training seed uses the same sampled IDs in a replicate. The
intervals describe uncertainty conditional on the fitted models and folds.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd


def _prepare_ranking(labels, scores):
    """Sort once per model and retain score-tie boundaries for weighted AP."""
    order = np.argsort(-scores, kind="stable")
    ranked_scores = scores[order]
    tie_ends = np.flatnonzero(np.r_[ranked_scores[1:] != ranked_scores[:-1], True])
    return order, tie_ends, labels[order]


def _weighted_ap(ranking, weights):
    """Average precision with per-row multiplicities, including tied scores."""
    order, tie_ends, ranked_labels = ranking
    ranked_weights = weights[:, order]
    cumulative_positives = np.cumsum(ranked_weights * ranked_labels, axis=1)[:, tie_ends]
    cumulative_total = np.cumsum(ranked_weights, axis=1)[:, tie_ends]
    precision = np.divide(
        cumulative_positives,
        cumulative_total,
        out=np.zeros(cumulative_positives.shape, dtype=float),
        where=cumulative_total != 0,
    )
    positive_gains = np.diff(cumulative_positives, axis=1, prepend=0)
    total_positives = cumulative_positives[:, -1]
    return np.divide(
        np.sum(precision * positive_gains, axis=1),
        total_positives,
        out=np.full(len(weights), np.nan),
        where=(total_positives > 0) & (total_positives < cumulative_total[:, -1]),
    )


def paired_domain_bootstrap(
    oof: pd.DataFrame,
    domain_by_id: pd.Series,
    comparisons: Sequence[tuple[str, str]],
    *,
    replicates: int = 1000,
    random_state: int = 42,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Return candidate-minus-baseline AP differences and percentile intervals.

    The OOF frame has one row per candidate, seed and ID, with columns
    candidate, seed, fold_id, id, y_true and score. The Series maps each ID to
    its domain. AP is averaged with equal weights over seeds and outer folds.
    """
    if replicates < 1 or not comparisons:
        raise ValueError("Provide at least one comparison and bootstrap replicate.")
    if not domain_by_id.index.is_unique:
        raise ValueError("Domain mapping must have one row per ID.")

    candidates = list(dict.fromkeys(name for pair in comparisons for name in pair))
    rows = oof.loc[oof["candidate"].isin(candidates)].copy()
    if rows.empty or rows[["candidate", "seed", "fold_id", "id", "y_true"]].isna().any().any():
        raise ValueError("Out-of-fold prediction identifiers and labels must be present.")
    if rows.duplicated(["candidate", "seed", "id"]).any():
        raise ValueError("Each candidate and seed must have one prediction per ID.")
    if (rows.groupby("id")[["fold_id", "y_true"]].nunique() != 1).any().any():
        raise ValueError("Candidates must agree on the fold and label of each ID.")
    if not rows["y_true"].isin([0, 1]).all() or not np.isfinite(rows["score"]).all():
        raise ValueError("Expected binary labels and finite scores.")

    ids = rows.drop_duplicates("id").set_index("id")[["fold_id", "y_true"]].join(
        domain_by_id.rename("domain"), how="left"
    )
    if ids["domain"].isna().any():
        raise ValueError("Every out-of-fold ID needs a domain.")
    if ids.groupby("domain")["fold_id"].nunique().gt(1).any():
        raise ValueError("A domain occurs in more than one held-out fold.")

    seeds = sorted(rows["seed"].unique())
    columns = pd.MultiIndex.from_product([candidates, seeds], names=["candidate", "seed"])
    rng = np.random.default_rng(random_state)
    point_ap = np.zeros(len(candidates))
    sampled_ap = np.zeros((len(candidates), replicates))
    n_folds = ids["fold_id"].nunique()

    for fold, part in rows.groupby("fold_id", sort=True):
        scores = part.pivot(index="id", columns=["candidate", "seed"], values="score")
        scores = scores.reindex(index=ids.index[ids["fold_id"].eq(fold)], columns=columns)
        if scores.isna().any().any():
            raise ValueError(f"Fold {fold} lacks paired predictions for some IDs or seeds.")
        labels = ids.loc[scores.index, "y_true"].to_numpy(dtype=np.int64)
        if np.unique(labels).size != 2:
            raise ValueError(f"Fold {fold} lacks both classes.")
        domains, distinct_domains = pd.factorize(ids.loc[scores.index, "domain"], sort=True)
        n_domains = len(distinct_domains)
        rankings = [
            [_prepare_ranking(labels, scores[(candidate, seed)].to_numpy()) for seed in seeds]
            for candidate in candidates
        ]

        original_weights = np.ones((1, len(labels)), dtype=np.int64)
        for index, candidate_rankings in enumerate(rankings):
            point_ap[index] += np.mean(
                [_weighted_ap(ranking, original_weights)[0] for ranking in candidate_rankings]
            ) / n_folds

        # Keep the largest working arrays bounded by this number of replicates.
        batch_size = 64
        for start in range(0, replicates, batch_size):
            stop = min(start + batch_size, replicates)
            draws = rng.integers(n_domains, size=(stop - start, n_domains))
            domain_weights = np.stack(
                [np.bincount(draw, minlength=n_domains) for draw in draws]
            )
            weights = domain_weights[:, domains]
            for index, candidate_rankings in enumerate(rankings):
                sampled_ap[index, start:stop] += np.mean(
                    [_weighted_ap(ranking, weights) for ranking in candidate_rankings],
                    axis=0,
                ) / n_folds

    records = []
    for candidate, baseline in comparisons:
        a, b = candidates.index(candidate), candidates.index(baseline)
        sampled_delta = sampled_ap[a] - sampled_ap[b]
        valid = sampled_delta[np.isfinite(sampled_delta)]
        low, high = np.quantile(valid, [0.025, 0.975]) if valid.size else (np.nan, np.nan)
        records.append(
            {
                "candidate": candidate,
                "baseline": baseline,
                "mean_fold_ap": point_ap[a],
                "baseline_mean_fold_ap": point_ap[b],
                "delta_mean_fold_ap": point_ap[a] - point_ap[b],
                "ci_low": low,
                "ci_high": high,
                "valid_replicates": valid.size,
                "replicates": replicates,
                "bootstrap_seed": random_state,
            }
        )
    result = pd.DataFrame(records)
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return result
