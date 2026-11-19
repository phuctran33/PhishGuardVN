"""Confirm the frozen Bronze KD MLP against matched and wider hard controls."""

from dataclasses import asdict
import hashlib
from itertools import product
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from kd_bronze_cost import measure
from kd_bronze_data import DATA_CACHE, ROOT, core_train, verify_preparation
from kd_bronze_neural import PROFILES, TRAINING
from kd_bronze_runner import (
    OUT, PLAN, Recipe, checkpoint, fingerprint, fit_once, matrices, read_run,
)
from kd_bronze_stats import paired_stats
from phishguard_vn.student import sha256
from train_lightgbm_student import write_csv, write_json


ART = ROOT / "artifacts/student_bronze_kd/mlp_final"
FINAL_SEEDS = (49, 50, 51)
WIDTHS = (16, 32, 64)
RATES = (0.0015, 0.003, 0.006)


def hard_spec(width, rate):
    return {
        "candidate": f"sparse_mlp_hard_w{width}_lr{rate:g}",
        "recipe": Recipe("sparse_mlp", "large", "A"),
        "hidden_units": width,
        "learning_rate": rate,
    }


def locked_spec(recipe):
    return {
        "candidate": recipe.tag,
        "recipe": recipe,
        "hidden_units": PROFILES["sparse_mlp"][recipe.profile]["hidden_units"],
        "learning_rate": TRAINING["learning_rate"],
    }


def fit_spec(spec, seed, rows, features):
    if spec["candidate"] == spec["recipe"].tag:
        return fit_once(spec["recipe"], seed, rows, features)
    # The extension only changes the hard control's width and optimizer rate.
    # Keep the primary runner and its fingerprint unchanged.
    with patch.dict(PROFILES["sparse_mlp"], {"large": {"hidden_units": spec["hidden_units"]}}):
        with patch.dict(TRAINING, {"learning_rate": spec["learning_rate"]}):
            return fit_once(spec["recipe"], seed, rows, features)


def evaluate(stage, specs, seeds, folds, signature):
    runs, predictions = [], []
    for fold, (rows, features) in folds.items():
        held = rows["held"]
        for spec in specs:
            name = spec["candidate"]
            for seed in seeds:
                path = DATA_CACHE / "runs/mlp_extension" / stage / f"{name}_s{seed}_f{fold}.npz"
                if path.exists():
                    score, record = read_run(path, signature)
                else:
                    start = perf_counter()
                    model = fit_spec(spec, seed, rows, features)
                    seconds = perf_counter() - start
                    score = np.asarray(model.score(features[1]), dtype=float)
                    if score.shape != (len(held),) or not np.isfinite(score).all():
                        raise ValueError("Invalid held-out scores for " + name)
                    record = {
                        "candidate": name,
                        **asdict(spec["recipe"]),
                        "hidden_units": spec["hidden_units"],
                        "learning_rate": spec["learning_rate"],
                        "optimizer_steps": TRAINING["steps"],
                        "stage": stage,
                        "seed": seed,
                        "fold_id": fold,
                        "fit_seconds": seconds,
                        "ap": float(average_precision_score(held["target"], score)),
                    }
                    checkpoint(path, score, record, signature)
                    print(f"{stage} {name} seed {seed} fold {fold}: {record['ap']:.6f} ({seconds:.2f}s)", flush=True)
                runs.append(record)
                predictions.append(
                    pd.DataFrame({
                        "candidate": name, "id": held["id"], "fold_id": fold,
                        "seed": seed, "y_true": held["target"], "score": score,
                    })
                )
    return pd.DataFrame(runs), pd.concat(predictions, ignore_index=True)


def summarize(runs):
    groups = ["candidate", "mode", "hidden_units", "learning_rate", "optimizer_steps"]
    return runs.groupby(groups, as_index=False).agg(
        ap=("ap", "mean"), mean_fit_seconds=("fit_seconds", "mean")
    ).sort_values(["ap", "hidden_units", "learning_rate"], ascending=[False, True, True])


def main():
    verify_preparation()
    fingerprint_before = fingerprint()
    confirm_path = OUT / "confirm_lock.json"
    confirm = json.loads(confirm_path.read_text(encoding="utf8"))
    if confirm["benchmark_fingerprint"] != fingerprint_before:
        raise ValueError("The earlier MLP lock refers to a different benchmark.")
    recipes = [
        Recipe(**row) for row in confirm["recipes"] if row["family"] == "sparse_mlp"
    ]
    chosen = next(Recipe(**row) for row in confirm["chosen"] if row["family"] == "sparse_mlp")
    if chosen != Recipe("sparse_mlp", "large", "D", .9, .25, 8192):
        raise ValueError("The previously selected MLP D recipe changed.")
    # Extra rows are included in the fit matrices only for C/D. The TF-IDF
    # vocabulary and IDF always come from the core fitting fold.
    folds = {}
    for fold in PLAN["folds"]:
        rows = joblib.load(DATA_CACHE / f"fold{fold}.joblib")
        folds[fold] = (rows, matrices("tfidf", rows, chosen.extra_rows))
    signature = hashlib.sha256(
        (fingerprint_before + sha256(Path(__file__)) + sha256(confirm_path)).encode()
    ).hexdigest()
    menu = [hard_spec(width, rate) for width, rate in product(WIDTHS, RATES)]
    tuning, tuning_oof = evaluate("screen", menu, (PLAN["screen_seed"],), folds, signature)
    tuning_rank = summarize(tuning)
    winner_name = tuning_rank.iloc[0]["candidate"]
    winner = next(spec for spec in menu if spec["candidate"] == winner_name)
    write_csv(OUT / "mlp_final_hard_tuning_runs.csv", tuning)
    write_csv(OUT / "mlp_final_hard_tuning_oof.csv.gz", tuning_oof)
    write_csv(OUT / "mlp_final_hard_tuning_rank.csv", tuning_rank)

    locked = {
        "benchmark_fingerprint": fingerprint_before,
        "extension_source_sha256": sha256(Path(__file__)),
        "parent_lock_sha256": sha256(confirm_path),
        "hard_grid_widths": WIDTHS,
        "hard_grid_learning_rates": RATES,
        "optimizer_steps": TRAINING["steps"],
        "batch_size": TRAINING["batch_size"],
        "tuning_seed": PLAN["screen_seed"],
        "verification_seeds": FINAL_SEEDS,
        "expanded_hard_winner": winner_name,
        "expanded_hard_width": winner["hidden_units"],
        "expanded_hard_rate": winner["learning_rate"],
        "expanded_hard_selection_ap": float(tuning_rank.iloc[0]["ap"]),
        "expanded_hard_selection": "Mean fold AP descending, then width and rate ascending",
        "kd_recipe": asdict(chosen),
        "matched_recipes": [asdict(cfg) for cfg in recipes],
        "scope": "New seed replay on already reused development folds",
    }
    write_json(OUT / "mlp_final_lock.json", locked)
    print(f"Locked MLP hard-grid winner: {winner_name}", flush=True)

    specs = [locked_spec(cfg) for cfg in recipes] + [winner]
    final, final_oof = evaluate("final", specs, FINAL_SEEDS, folds, signature)
    final_summary = summarize(final)
    write_csv(OUT / "mlp_final_runs.csv", final)
    write_csv(OUT / "mlp_final_oof.csv.gz", final_oof)
    write_csv(OUT / "mlp_final_summary.csv", final_summary)

    by_mode = {cfg.mode: cfg.tag for cfg in recipes if cfg.profile == chosen.profile}
    original_tuned = next(cfg.tag for cfg in recipes if cfg.mode == "A"
                          and cfg.profile == confirm["hard_profiles"]["sparse_mlp"])
    domains = core_train().set_index("id")["group"]
    comparisons = [
        ("D vs matched hard A", chosen.tag, by_mode["A"]),
        ("D vs two-width tuned A", chosen.tag, original_tuned),
        ("D vs expanded tuned A", chosen.tag, winner_name),
        ("D vs core-only KD B", chosen.tag, by_mode["B"]),
        ("D vs Bronze hard C", chosen.tag, by_mode["C"]),
    ]
    result = paired_stats(
        final_oof, domains, comparisons,
        OUT / "mlp_final_paired_ap.csv",
        replicates=PLAN["bootstrap_replicates"], random_state=PLAN["bootstrap_seed"],
    )
    print(result[["comparison", "delta_mean_fold_ap", "ci_low", "ci_high",
                  "fold_wins", "seed_wins", "fold_seed_wins"]].to_string(index=False), flush=True)

    rows, features = folds[0]
    drawn = rows["held"][["id", "url"]].sort_values("id").sample(n=250, random_state=2357)
    cost = []
    measured_names = {chosen.tag, winner_name, by_mode["A"], original_tuned}
    for spec in specs:
        if spec["candidate"] not in measured_names:
            continue
        name = spec["candidate"]
        model = fit_spec(spec, FINAL_SEEDS[0], rows, features)
        archived = final_oof.loc[
            final_oof.candidate.eq(name) & final_oof.seed.eq(FINAL_SEEDS[0])
            & final_oof.fold_id.eq(0)
        ].set_index("id").loc[rows["held"]["id"]]["score"]
        np.testing.assert_allclose(model.score(features[1]), archived, rtol=0, atol=1e-12)
        timing = measure(model, "sparse_mlp", "tfidf", features[3], drawn, ART / f"{name}.joblib")
        timing["joblib_path"] = Path(timing["joblib_path"]).relative_to(ROOT).as_posix()
        ap = final_summary.loc[final_summary.candidate.eq(name), "ap"].item()
        cost.append({"candidate": name, "cv_ap": ap, "fold": 0, "seed": FINAL_SEEDS[0], **timing})
    write_csv(OUT / "mlp_final_cost.csv", pd.DataFrame(cost))
    if fingerprint() != fingerprint_before:
        raise RuntimeError("Primary research inputs changed during the MLP extension.")


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
