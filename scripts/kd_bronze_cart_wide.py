"""Equal-menu, post-primary CART check on the existing three Train folds.

Screen the same 7 depths x 4 minimum leaf weights for all four recipes at seed
42. Lock winners before verifying on 49-51. Seed changes are not new data.
"""
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

from kd_bronze_cart_check import DEPTH, LEAF_WEIGHT
from kd_bronze_data import DATA_CACHE, core_train, verify_preparation
from kd_bronze_runner import OUT, PLAN, fingerprint, labels, recipe
from kd_bronze_stats import paired_stats
from kd_bronze_trees import _paired_labels
from phishguard_vn.student import sha256
from train_lightgbm_student import write_csv, write_json

SETTINGS = dict(alpha=0.9, extra_weight=0.5, extra_rows=2048)
NEW_SEEDS = (49, 50, 51)


@dataclass(frozen=True)
class Profile:
    depth: int
    leaf: float
    mode: str

    @property
    def name(self):
        return f"cart_wide_{self.mode}_depth{self.depth}_leaf{self.leaf:g}"


def frozen_data(rows):
    fitting = rows["fitting"]
    prepared = {}
    for mode in "ABCD":
        cfg = recipe("cart", "wide", mode, SETTINGS)
        q, w = labels(cfg, fitting.target.to_numpy(float), rows["core_scores"], rows["extra_scores"])
        features = rows["e2_fit"]
        if cfg.extra_rows:
            features = np.vstack((features, rows["e2_extra"][:cfg.extra_rows]))
        prepared[mode] = _paired_labels(features, q, w)
    return prepared


def fold_checkpoint(stage, fold, data, configs, seeds, signature):
    file = OUT / f"cart_wide_{stage}_fold{fold}.npz"
    held = data["held"]
    ids = np.asarray(held.id, dtype=str)
    y = held.target.to_numpy()
    tasks = list(itertools.product(configs, seeds))
    description = [[cfg.name, int(seed)] for cfg,seed in tasks]
    if file.exists():
        with np.load(file, allow_pickle=False) as saved:
            if saved["signature"].item() != signature or json.loads(saved["tasks"].item()) != description:
                raise ValueError("Checkpoint uses another configuration: " + str(file))
            np.testing.assert_array_equal(saved["ids"], ids)
            np.testing.assert_array_equal(saved["labels"], y)
            scores = saved["scores"]
    else:
        matrices = frozen_data(data)
        scores = []
        for cfg, seed in tasks:
            X, target, weights = matrices[cfg.mode]
            model = DecisionTreeClassifier(criterion="entropy", max_depth=cfg.depth,
                min_weight_fraction_leaf=cfg.leaf, random_state=seed)
            model.fit(X, target, sample_weight=weights)
            scores.append(model.predict_proba(data["e2_held"])[:,1])
        scores = np.stack(scores)
        staging = file.with_suffix(".partial")
        with staging.open("wb") as stream:
            np.savez_compressed(stream, signature=signature, tasks=json.dumps(description),
                                ids=ids, labels=y, scores=scores)
        staging.replace(file)
    if scores.shape != (len(tasks),len(held)) or not np.isfinite(scores).all():
        raise ValueError("Invalid checkpoint scores")
    runs, raw = [], []
    for (cfg,seed), pred in zip(tasks,scores,strict=True):
        runs.append(dict(candidate=cfg.name, **asdict(cfg), seed=seed, fold_id=fold,
                         ap=average_precision_score(y,pred)))
        if stage == "final":
            raw.append(pd.DataFrame(dict(candidate=cfg.name, seed=seed, fold_id=fold,
                                         id=ids, y_true=y, score=pred)))
    print(stage, "fold", fold, len(tasks), "evaluated fits", flush=True)
    return runs, raw


def evaluate(stage, folds, configs, seeds, signature):
    rows, scores = [], []
    for f,data in folds.items():
        metrics,preds = fold_checkpoint(stage, f, data, configs, seeds, signature)
        rows.extend(metrics)
        scores.extend(preds)
    runs = pd.DataFrame(rows)
    write_csv(OUT / f"cart_wide_{stage}_runs.csv", runs)
    by_capacity = (runs.groupby(["candidate","mode","depth","leaf"],as_index=False)
        .agg(ap=("ap","mean"),fits=("ap","size"))
        .sort_values(["ap","depth","leaf","mode"],ascending=[False,True,False,True]))
    write_csv(OUT / f"cart_wide_{stage}_summary.csv", by_capacity)
    if scores:
        raw = pd.concat(scores,ignore_index=True)
        write_csv(OUT / f"cart_wide_{stage}_oof.csv.gz", raw)
    else:
        raw = None
    return by_capacity, raw


def from_row(row):
    return Profile(int(row.depth),float(row.leaf),row["mode"])


def main():
    verify_preparation()
    primary_file = OUT / "final_lock.json"
    chosen = json.loads(primary_file.read_text(encoding="utf8"))["chosen"][0]
    if chosen["family"] != "cart" or chosen["mode"] != "D" or any(chosen[k]!=v for k,v in SETTINGS.items()):
        raise ValueError("Previously locked CART recipe differs")
    settings_hash = hashlib.sha256((fingerprint()+sha256(Path(__file__))+sha256(primary_file)
        +sha256(Path(__file__).with_name("kd_bronze_cart_check.py"))).encode()).hexdigest()
    folds = {f:joblib.load(DATA_CACHE / f"fold{f}.joblib") for f in PLAN["folds"]}
    grid = [Profile(d,w,m) for d,w,m in itertools.product(DEPTH,LEAF_WEIGHT,"ABCD")]
    ranking,_ = evaluate("screen",folds,grid,(PLAN["screen_seed"],),settings_hash)
    # Reproduce all 28 previous hard APs as a boundary check, including ties.
    known = pd.read_csv(OUT / "cart_hard_sensitivity_screen.csv").rename(columns={
        "max_depth":"depth", "min_weight_fraction_leaf":"leaf"})
    pair = known.merge(ranking[ranking["mode"].eq("A")],on=["depth","leaf"],validate="one_to_one")
    if len(pair) != len(DEPTH)*len(LEAF_WEIGHT):
        raise ValueError("Missing previous hard comparison")
    np.testing.assert_allclose(pair.ap_x,pair.ap_y,rtol=0,atol=1e-12)
    winners = {m:from_row(ranking[ranking["mode"].eq(m)].iloc[0]) for m in "ABCD"}
    global_kd = from_row(ranking[ranking["mode"].ne("A")].iloc[0])
    hard, soft = winners["A"], winners["D"]
    # Primary D and secondary best-of-B/C/D get their own capacity-matched A/B/C/D.
    locked = list(dict.fromkeys([hard, *[Profile(p.depth,p.leaf,mode)
                            for p in (soft,global_kd) for mode in "ABCD"]]))
    selection = dict(screen_seed=PLAN["screen_seed"], confirmation_seeds=NEW_SEEDS,
        recipe_settings=SETTINGS, menu_by_mode=len(DEPTH)*len(LEAF_WEIGHT), criteria=
        "Highest mean fold AP; tie lower depth, larger minimum weight, then mode alphabetical",
        primary="Best D from 28 vs best A from 28", secondary="Best among B/C/D vs tuned A",
        winners={m:asdict(p) for m,p in winners.items()}, best_kd=asdict(global_kd),
        confirm_configs=[asdict(p) for p in locked], signature=settings_hash,
        folds=PLAN["folds"], registered_minimum_delta=PLAN["minimum_reportable_delta"],
        scope="Reused Train domain folds, post-primary capacity search. No other splits used.")
    lock_path = OUT / "cart_wide_lock.json"
    if lock_path.exists() and json.loads(lock_path.read_text(encoding="utf8"))!=json.loads(json.dumps(selection)):
        raise ValueError("Existing confirmation lock differs")
    write_json(lock_path,selection)
    print("Frozen", {m:p.name for m,p in winners.items()},"global",global_kd.name,flush=True)
    summary,raw = evaluate("final",folds,locked,NEW_SEEDS,settings_hash)
    comparisons = []
    def compare(tag,x,y):
        if x.name != y.name:
            comparisons.append((tag,x.name,y.name))
    compare("primary_D_vs_tuned_A",soft,hard)
    for mode in "ABC":
        compare("D_vs_matched_"+mode,soft,Profile(soft.depth,soft.leaf,mode))
    compare("secondary_best_BCD_vs_tuned_A",global_kd,hard)
    compare("secondary_best_BCD_vs_matched_A",global_kd,Profile(global_kd.depth,global_kd.leaf,"A"))
    domains = core_train().set_index("id").group
    stats = paired_stats(raw,domains,comparisons,OUT/"cart_wide_final_paired.csv",
                         replicates=PLAN["bootstrap_replicates"],random_state=PLAN["bootstrap_seed"])
    base = stats[stats.comparison.eq("primary_D_vs_tuned_A")].iloc[0]
    counts = dict(screen_fits=112*3,screen_scores=112*len(domains),final_fits=len(locked)*len(NEW_SEEDS)*3,
                  final_scores=len(raw),held_unique_ids=len(domains),threshold=PLAN["minimum_reportable_delta"],
                  primary_point_clears_delta=bool(base.delta_mean_fold_ap>=PLAN["minimum_reportable_delta"]),
                  primary_interval_excludes_zero=bool(base.ci_low>0),all_final_seed_means_positive=bool(base.seed_wins==3),
                  validation_external_test_evaluated=False,checkpoint_layout="one compressed matrix of scores per stage/fold, indexed by tasks/ids")
    write_json(OUT/"cart_wide_counts.json",counts)
    print(summary.to_string(index=False), flush=True)
    print(stats[["comparison","delta_mean_fold_ap","ci_low","ci_high","seed_wins","fold_wins"]].to_string(index=False),flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
