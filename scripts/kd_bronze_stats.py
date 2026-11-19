"""Paired domain-bootstrap AP differences on already-held-out predictions.

One comparison is (candidate, baseline) or (tag, candidate, baseline).
Pass one stage at a time, with domain_by_id indexed by every expected OOF ID.
All statistics give equal weight to the held-out folds and training seeds.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from tiny_mlp_analysis import paired_domain_bootstrap


def _wins(values, prefix):
    # Count floating-point ties as ties, including duplicated deterministic seeds.
    values = np.asarray(values)
    return {prefix + "_wins": int(np.sum(values > 1e-12)),
            prefix + "_ties": int(np.sum(np.abs(values) <= 1e-12)),
            prefix + "_losses": int(np.sum(values < -1e-12))}


def _records(pairs):
    output = []
    for pair in pairs:
        if len(pair) == 2:
            candidate, baseline = pair
            tag = f"{candidate} minus {baseline}"
        elif len(pair) == 3:
            tag, candidate, baseline = pair
        else:
            raise ValueError("Use (candidate, baseline) or (tag, candidate, baseline)")
        output.append((tag, candidate, baseline))
    if not output:
        raise ValueError("Expected at least one comparison")
    return output


def paired_stats(oof, domain_by_id, pairs, output_path=None, *, replicates=1000, random_state=42):
    """Return CIs, paired fold/seed win counts, and fold/seed mean-AP deltas.

    Intervals are conditional on the fitted models, folds and available domains.
    Hyperparameter search and repeated inspections are not reflected in the CI.
    """
    pairs = _records(pairs)
    candidates = list(dict.fromkeys(name for _, a, b in pairs for name in (a, b)))
    if not isinstance(domain_by_id, pd.Series) or not domain_by_id.index.is_unique or domain_by_id.isna().any():
        raise ValueError("Supply one registrable domain for every expected OOF ID")
    rows = oof.loc[oof.candidate.isin(candidates), ["candidate","seed","fold_id","id","y_true","score"]]
    if rows.empty or rows.isna().any().any() or rows.duplicated(["candidate","seed","id"]).any():
        raise ValueError("Missing or duplicate OOF values; pass one stage at a time")
    # Enforce the complete cohort, even if all candidates omit the same ID.
    if not rows.id.isin(domain_by_id.index).all():
        raise ValueError("Some OOF IDs are absent from the domain map")
    counts = rows.groupby(["candidate","seed"], observed=True).size()
    if not counts.eq(len(domain_by_id)).all():
        raise ValueError("Each candidate/seed must cover the full supplied ID cohort")
    seed_sets = {a: tuple(sorted(sub.seed.unique())) for a, sub in rows.groupby("candidate", observed=True)}
    groups = {}
    for tagged in pairs:
        _, candidate, baseline = tagged
        if candidate not in seed_sets or baseline not in seed_sets or seed_sets[candidate] != seed_sets[baseline]:
            raise ValueError(f"Missing candidate or unmatched seed set: {candidate}, {baseline}")
        groups.setdefault(seed_sets[candidate], []).append(tagged)

    output = []
    for seeds, comparisons in groups.items():
        distinct = list(dict.fromkeys((a, b) for _, a, b in comparisons))
        names = {name for pair in distinct for name in pair}
        cohort = rows[rows.candidate.isin(names)]
        intervals = paired_domain_bootstrap(cohort, domain_by_id, distinct,
            replicates=replicates, random_state=random_state).set_index(["candidate","baseline"])
        per_run = {(a,s,f): average_precision_score(frame.y_true, frame.score)
                   for (a,s,f), frame in cohort.groupby(["candidate","seed","fold_id"], observed=True)}
        scores = pd.Series(per_run).rename_axis(["candidate","seed","fold_id"])
        for tag, candidate, baseline in comparisons:
            a = scores.loc[candidate].sort_index()
            b = scores.loc[baseline].sort_index()
            delta = a - b
            result = intervals.loc[(candidate,baseline)].to_dict()
            # Independent sklearn scoring verifies the bootstrapped point estimate.
            np.testing.assert_allclose([a.mean(), b.mean(), delta.mean()],
                [result["mean_fold_ap"], result["baseline_mean_fold_ap"], result["delta_mean_fold_ap"]],
                rtol=0, atol=1e-12)
            folds = delta.groupby("fold_id").mean()
            training_seeds = delta.groupby("seed").mean()
            output.append(dict(comparison=tag, candidate=candidate, baseline=baseline, **result,
                ids=len(domain_by_id), domains=domain_by_id.nunique(), folds=len(folds), seeds=len(seeds),
                **_wins(folds, "fold"), **_wins(training_seeds, "seed"),
                **_wins(delta, "fold_seed"), fold_delta=json.dumps({str(k):v for k,v in folds.items()}),
                seed_delta=json.dumps({str(k):v for k,v in training_seeds.items()})))
    result = pd.DataFrame(output)
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return result

