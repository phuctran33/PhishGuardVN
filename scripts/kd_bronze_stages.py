"""Summarize checkpoints and lock each successive development stage."""
import argparse
from dataclasses import asdict
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from kd_bronze_data import DATA_CACHE, core_train, verify_preparation
from kd_bronze_runner import (FAMILIES, OUT, PLAN, Recipe, destination, fingerprint,
                              read_run, recipe, suite)
from train_lightgbm_student import write_csv, write_json


def checkpoint_results(stage):
    configs, seeds = suite(stage)
    signature = fingerprint()
    payloads, predictions = [], []
    for fold in PLAN["folds"]:
        held = joblib.load(DATA_CACHE / f"fold{fold}.joblib")["held"]
        y, ids = held.target.to_numpy(), held.id.to_numpy()
        for cfg in configs:
            for seed in seeds:
                path = destination(stage, cfg, seed, fold)
                if not path.is_file():
                    raise FileNotFoundError(path)
                scores, payload = read_run(path, signature)
                check = {**asdict(cfg), "stage":stage, "seed":seed, "fold":fold}
                if len(scores) != len(held) or any(payload[k] != v for k,v in check.items()):
                    raise ValueError("Checkpoint rows/recipe mismatch: " + str(path))
                np.testing.assert_allclose(payload["ap"], average_precision_score(y, scores),
                                           rtol=0, atol=1e-14)
                payloads.append(dict(candidate=cfg.tag, **payload))
                predictions.append(pd.DataFrame(dict(candidate=cfg.tag, seed=seed, fold_id=fold,
                                                      id=ids, y_true=y, score=scores)))
    return pd.DataFrame(payloads), pd.concat(predictions, ignore_index=True)


def save_lock(stage, recipes, seeds, context):
    lock = dict(benchmark_fingerprint=fingerprint(), seeds=seeds,
                recipes=[asdict(r) for r in sorted(set(recipes), key=lambda r:r.tag)], **context)
    path = OUT / f"{stage}_lock.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf8")) != lock:
            raise ValueError("Stage already locked using other settings: " + stage)
        return
    write_json(path, lock)


def best_hard(screen):
    a = screen[screen["mode"].eq("A")].sort_values(["ap", "profile"], ascending=[False, True])
    return a.drop_duplicates("family").set_index("family")["profile"].to_dict()


def summarize(rows):
    keys = ["candidate", "family", "profile", "mode", "alpha", "extra_weight", "extra_rows", "representation"]
    return rows.groupby(keys, as_index=False).agg(ap=("ap", "mean"), fits=("ap", "size"),
                                                   mean_fit_seconds=("fit_seconds", "mean"))


def compare_to_hard(summary, hard_profiles):
    a = summary[summary["mode"].eq("A")].set_index(["family", "profile"]).ap
    summary = summary.copy()
    summary["hard_matched_ap"] = [a[f,p] for f,p in zip(summary.family, summary.profile)]
    summary["hard_tuned_ap"] = [a[f,hard_profiles[f]] for f in summary.family]
    summary["delta_vs_matched"] = summary.ap - summary.hard_matched_ap
    summary["delta_vs_tuned"] = summary.ap - summary.hard_tuned_ap
    return summary


def from_row(row):
    return Recipe(row.family, row.profile, row.mode, row.alpha, row.extra_weight, row.extra_rows)


def rank_kd(summary):
    return summary[summary["mode"].ne("A")].sort_values(
        ["delta_vs_tuned","ap","candidate"], ascending=[False,False,True])


def lock_sweep(screen, hard_profiles):
    fresh = rank_kd(screen).drop_duplicates("family").head(PLAN["shortlist_size"])
    menu = [recipe(row.family,row.profile,"D",point) for row in fresh.itertuples(index=False)
            for point in PLAN["sweep"]]
    context = dict(selection="Top four families by best screening KD delta vs tuned A; sweep same winning capacity",
                   nominees=[row.candidate for row in fresh.itertuples(index=False)],
                   hard_profiles=hard_profiles)
    save_lock("sweep", menu, [PLAN["screen_seed"]], context)
    print("Sweep families:", ", ".join(fresh.family), flush=True)


def matching_suite(winners):
    menu = []
    for choice in winners:
        settings = dict(alpha=choice.alpha, extra_weight=choice.extra_weight, extra_rows=choice.extra_rows)
        if not choice.extra_rows:
            settings.update(extra_weight=PLAN["screen"]["extra_weight"], extra_rows=PLAN["screen"]["extra_rows"])
        for profile in FAMILIES[choice.family]:
            menu.append(Recipe(choice.family, profile,"A"))
        menu.extend(recipe(choice.family, choice.profile, mode, settings) for mode in "BCD")
    return menu


def lock_confirm(screen, sweep, hard_profiles):
    sweep_lock = json.loads((OUT / "sweep_lock.json").read_text(encoding="utf8"))
    nominees = {Recipe(**d).family for d in sweep_lock["recipes"]}
    combined = pd.concat([screen.drop(columns=["hard_matched_ap","hard_tuned_ap","delta_vs_matched","delta_vs_tuned"]),
                           sweep], ignore_index=True)
    combined = compare_to_hard(combined, hard_profiles)
    winners = rank_kd(combined[combined.family.isin(nominees)]).drop_duplicates("family")
    write_csv(OUT / "sweep_comparison.csv", combined.sort_values(["family","delta_vs_tuned"], ascending=[True,False]))
    chosen = [from_row(row) for row in winners.itertuples(index=False)]
    save_lock("confirm", matching_suite(chosen), PLAN["confirm_seeds"], dict(
              selection="Best Train KD recipe within each swept family, including screening anchors",
              chosen=[asdict(cfg) for cfg in chosen], hard_profiles=hard_profiles))
    print(winners[["family","candidate","ap","delta_vs_tuned"]].to_string(index=False), flush=True)


def compare_seeds(rows, chosen, hard_profiles):
    hard = rows[rows["mode"].eq("A")].set_index(["family","profile","seed","fold"]).ap
    paired = []
    for cfg in chosen:
        obs = rows[rows.candidate.eq(cfg.tag)]
        for row in obs.itertuples(index=False):
            other = hard[cfg.family, cfg.profile, row.seed, row.fold]
            tuned = hard[cfg.family, hard_profiles[cfg.family], row.seed, row.fold]
            paired.append(dict(candidate=cfg.tag, family=cfg.family, seed=row.seed, fold=row.fold,
                               ap=row.ap, hard_matched_ap=other, hard_tuned_ap=tuned,
                               delta_vs_matched=row.ap-other, delta_vs_tuned=row.ap-tuned))
    return pd.DataFrame(paired)


def lock_final(rows, chosen, hard_profiles):
    paired = compare_seeds(rows, chosen, hard_profiles)
    write_csv(OUT / "confirm_nominee_fold_deltas.csv", paired)
    seed = paired.groupby(["candidate","family","seed"],as_index=False).agg(ap=("ap","mean"),
                                                              delta=("delta_vs_tuned","mean"))
    ranking = seed.groupby(["candidate","family"],as_index=False).agg(
        mean_ap=("ap","mean"), mean_delta=("delta","mean"), worst_seed_delta=("delta","min"),
        seeds_won=("delta",lambda a:int((a>1e-12).sum())))
    ranking = ranking.sort_values(["seeds_won","worst_seed_delta","mean_delta","mean_ap","candidate"],
                                  ascending=[False,False,False,False,True])
    write_csv(OUT / "confirm_nominee_rank.csv", ranking)
    winner = next(cfg for cfg in chosen if cfg.tag == ranking.iloc[0].candidate)
    all_confirm = suite("confirm")[0]
    menus = [cfg for cfg in all_confirm if cfg.family == winner.family]
    save_lock("final", menus, PLAN["final_seeds"], dict(
        selection="Most positive confirmation seeds vs preselected tuned hard, then minimum seed delta, mean delta and AP",
        chosen=[asdict(winner)], hard_profiles={winner.family:hard_profiles[winner.family]}))
    print(ranking.to_string(index=False), flush=True)
    print("Finalist:",winner.tag,flush=True)


def interval_pairs(rows, recipes, hard_profiles):
    choices = []
    for cfg in recipes:
        if cfg.mode != "A":
            hard_matched = Recipe(cfg.family,cfg.profile,"A").tag
            hard_tuned = Recipe(cfg.family,hard_profiles[cfg.family],"A").tag
            choices.extend([(cfg.tag, hard_matched), (cfg.tag, hard_tuned)])
        if cfg.mode == "D":
            c = Recipe(cfg.family,cfg.profile,"C",cfg.alpha,cfg.extra_weight,cfg.extra_rows).tag
            if c in set(rows.candidate):
                choices.append((cfg.tag,c))
    return list(dict.fromkeys(choices))


def main(stage, bootstrap):
    verify_preparation()
    rows, raw = checkpoint_results(stage)
    write_csv(OUT / f"{stage}_runs.csv", rows)
    write_csv(OUT / f"{stage}_oof.csv.gz", raw)
    summary = summarize(rows)
    if stage == "screen":
        hard_profiles = best_hard(summary)
        summary = compare_to_hard(summary, hard_profiles)
        write_csv(OUT / "screen_summary.csv", summary)
        lock_sweep(summary, hard_profiles)
    elif stage == "sweep":
        screen = pd.read_csv(OUT / "screen_summary.csv")
        lock_confirm(screen, summary, best_hard(screen))
        write_csv(OUT / "sweep_summary.csv", summary)
    else:
        locked = json.loads((OUT / f"{stage}_lock.json").read_text(encoding="utf8"))
        chosen = [Recipe(**d) for d in locked["chosen"]]
        hard_profiles = locked["hard_profiles"]
        summary = compare_to_hard(summary, hard_profiles)
        write_csv(OUT / f"{stage}_summary.csv", summary)
        write_csv(OUT / f"{stage}_chosen_deltas.csv", compare_seeds(rows, chosen, hard_profiles))
        if stage == "confirm":
            lock_final(rows, chosen, hard_profiles)
        if bootstrap:
            from kd_bronze_stats import paired_stats
            pairs = interval_pairs(rows, suite(stage)[0], hard_profiles)
            paired_stats(raw, core_train().set_index("id").group, pairs, OUT / f"{stage}_paired_ap.csv", replicates=PLAN["bootstrap_replicates"], random_state=PLAN["bootstrap_seed"])
    print(f"{stage}: {len(rows)} fits, {len(raw):,} OOF scores", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["screen","sweep","confirm","final"])
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        main(args.stage, args.bootstrap)
