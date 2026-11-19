"""Sensitivity analysis for CART's locked KD result against a wider hard menu.

The primary four-mode benchmark is already locked. Screen only hard models at
seed 42 across the existing folds. Freeze that menu winner for seeds 46–48.
"""
import itertools
import json
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

from kd_bronze_data import DATA_CACHE, core_train, verify_preparation
from kd_bronze_runner import OUT, PLAN, Recipe
from kd_bronze_stats import paired_stats
from train_lightgbm_student import write_csv, write_json

DEPTH = (4, 6, 8, 9, 10, 12, 16)
LEAF_WEIGHT = (0.0005, 0.001, 0.002, 0.004)


def evaluate(folds, profiles, seeds):
    fits, predictions = [], []
    for depth, leaf in profiles:
        name = f"cart_hard_depth{depth}_leaf{leaf:g}"
        for fold, data in folds.items():
            fit, held = data["fitting"], data["held"]
            for seed in seeds:
                begin = perf_counter()
                # Exactly the CART A estimator and row construction from the primary menu.
                model = DecisionTreeClassifier(criterion="entropy", max_depth=depth,
                                                min_weight_fraction_leaf=leaf, random_state=seed)
                size = len(fit)
                class_y = np.repeat([0,1],size)
                weights = np.r_[1-fit.target.to_numpy(), fit.target.to_numpy()]
                model.fit(np.concatenate((data["e2_fit"],data["e2_fit"])), class_y, sample_weight=weights)
                score = model.predict_proba(data["e2_held"])[:,1]
                fits.append(dict(candidate=name,max_depth=depth,min_weight_fraction_leaf=leaf,
                                 seed=seed,fold_id=fold,ap=average_precision_score(held.target,score),
                                 total_seconds=perf_counter()-begin))
                predictions.append(pd.DataFrame(dict(candidate=name,id=held.id,fold_id=fold,seed=seed,
                                                      y_true=held.target,score=score)))
    return pd.DataFrame(fits), pd.concat(predictions,ignore_index=True)


def main():
    verify_preparation()
    lock = json.loads((OUT/"final_lock.json").read_text(encoding="utf8"))
    kd = Recipe(**lock["chosen"][0])
    if kd.family != "cart":
        raise ValueError("Sensitivity runner requires CART as the locked finalist")
    folds = {f:joblib.load(DATA_CACHE/f"fold{f}.joblib") for f in PLAN["folds"]}
    menu = list(itertools.product(DEPTH, LEAF_WEIGHT))
    fits, raw = evaluate(folds, menu, [PLAN["screen_seed"]])
    ranking = (fits.groupby(["candidate","max_depth","min_weight_fraction_leaf"],as_index=False)
               .ap.mean().sort_values(["ap","max_depth","min_weight_fraction_leaf"],
                                     ascending=[False,True,False]))
    winner = ranking.iloc[0]
    primary = pd.read_csv(OUT/"screen_runs.csv").set_index(["candidate","fold"]).ap
    same = fits[(fits.max_depth==9)&(fits.min_weight_fraction_leaf==.0005)].sort_values("fold_id")
    np.testing.assert_allclose(same.ap, primary.loc["cart_large_A_0_0_0"].sort_index(), atol=1e-12, rtol=0)
    summary = dict(name=winner.candidate, max_depth=int(winner.max_depth),
                   min_weight_fraction_leaf=float(winner.min_weight_fraction_leaf),
                   selection_seeds=[PLAN["screen_seed"]], evaluation_seeds=lock["seeds"],
                   selection="max mean fold AP on 28 hard CART profiles; tie: lower depth, larger min leaf weight",
                   primary_cart_kd=kd.tag, candidate_ap_screen=float(winner.ap),
                   scope="post-primary sensitivity on reused development folds")
    write_json(OUT/"cart_hard_sensitivity_lock.json",summary)
    write_csv(OUT/"cart_hard_sensitivity_screen.csv",ranking)
    write_csv(OUT/"cart_hard_sensitivity_screen_runs.csv",fits)
    write_csv(OUT/"cart_hard_sensitivity_screen_oof.csv.gz",raw)
    end, scores = evaluate(folds, [(summary["max_depth"],summary["min_weight_fraction_leaf"])],lock["seeds"])
    write_csv(OUT/"cart_hard_sensitivity_final.csv",end)
    write_csv(OUT/"cart_hard_sensitivity_final_oof.csv.gz",scores)
    saved = pd.read_csv(OUT/"final_oof.csv.gz")
    known = saved[saved.candidate.eq(kd.tag)]
    stats = paired_stats(pd.concat([known,scores],ignore_index=True),
                         core_train().set_index("id").group,[(kd.tag,winner.candidate)],
                         OUT/"cart_hard_sensitivity_paired_ap.csv",
                         replicates=PLAN["bootstrap_replicates"],random_state=PLAN["bootstrap_seed"])
    print(json.dumps(summary),flush=True)
    print(stats[["mean_fold_ap","baseline_mean_fold_ap","delta_mean_fold_ap",
                 "ci_low","ci_high","fold_wins","seed_wins"]].to_string(index=False),flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
