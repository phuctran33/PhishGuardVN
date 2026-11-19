"""Test whether more optimizer steps change Bronze KD gains for the same byte CNN.

Run with the existing research checkout and prepared fold-only Teacher cache:
    python scripts/kd_bronze_cnn_budget.py
The 384-step reference and 1536-step check are evaluated using paired seeds.
"""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import hashlib
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from kd_bronze_data import DATA_CACHE, ROOT, core_train, verify_preparation
from kd_bronze_neural import PROFILES, TRAINING
from kd_bronze_runner import PLAN, check_loss, checkpoint, fingerprint, fit_once, matrices, read_run, recipe
from kd_bronze_stats import paired_stats
from phishguard_vn.student import sha256
from train_lightgbm_student import write_csv, write_json

BUDGETS = (384, 1536)
SEEDS = (202, 303, 404)
SETTINGS = dict(alpha=0.9, extra_weight=0.25, extra_rows=2048)
PROFILE = "large"
OUT = ROOT / "reports/tables/student_bronze_kd_cnn_followup"


def candidate(steps, mode):
    return f"cnn_{steps}_{mode}"


def run_fold(stage, fold, tasks, signature):
    with threadpool_limits(limits=1):
        rows = joblib.load(DATA_CACHE / f"fold{fold}.joblib")
        inputs = matrices("bytes", rows, SETTINGS["extra_rows"])
        held = rows["held"]
        fits, predictions = [], []
        for steps, mode, seed in tasks:
            name = candidate(steps, mode)
            cfg = recipe("byte_cnn", PROFILE, mode, SETTINGS)
            path = DATA_CACHE / "runs/cnn_budget" / stage / f"{name}_s{seed}_f{fold}.npz"
            if path.is_file():
                score, record = read_run(path, signature)
            else:
                with patch.dict(TRAINING, {"steps": steps}):
                    start = perf_counter()
                    model = fit_once(cfg, seed, rows, inputs)
                    fit_seconds = perf_counter() - start
                    score = np.asarray(model.score(inputs[1]), dtype=float)
                if score.shape != (len(held),) or not np.isfinite(score).all():
                    raise ValueError("Invalid predictions for " + name)
                record = dict(candidate=name, steps=steps, mode=mode, seed=seed, fold_id=fold,
                              ap=float(average_precision_score(held.target, score)), seconds=fit_seconds)
                checkpoint(path, score, record, signature)
            fits.append(record)
            predictions.append(pd.DataFrame(
                dict(candidate=name, seed=seed, fold_id=fold, id=held.id, y_true=held.target, score=score)))
            print(f"{stage} fold{fold} seed{seed} {name}: AP {record['ap']:.5f}", flush=True)
        return pd.DataFrame(fits), pd.concat(predictions, ignore_index=True)


def execute(pool, stage, tasks, signature):
    futures = [pool.submit(run_fold, stage, fold, tasks, signature) for fold in PLAN["folds"]]
    runs, preds = zip(*(future.result() for future in futures))
    runs = pd.concat(runs, ignore_index=True)
    preds = pd.concat(preds, ignore_index=True)
    write_csv(OUT / f"{stage}_runs.csv", runs)
    write_csv(OUT / f"{stage}_oof.csv.gz", preds)
    return runs, preds


def main():
    verify_preparation()
    check_loss()
    base = fingerprint()
    signature = hashlib.sha256((base + sha256(Path(__file__))).encode()).hexdigest()
    with ProcessPoolExecutor(max_workers=3) as pool:
        tuning, _ = execute(pool, "tune_hard", [(n, "A", PLAN["screen_seed"]) for n in BUDGETS], signature)
        prior = pd.read_csv(ROOT / "reports/tables/student_bronze_kd/screen_runs.csv")
        known = prior.loc[prior.candidate.eq("byte_cnn_large_A_0_0_0")].sort_values("fold")
        observed = tuning.loc[tuning.steps.eq(384)].sort_values("fold_id")
        np.testing.assert_allclose(observed.ap, known.ap, atol=1e-12, rtol=0)
        ranked = tuning.groupby("steps").ap.mean().sort_values(ascending=False, kind="stable")
        hard_steps = int(ranked.index[0])
        write_json(OUT / "experiment.json", dict(
            benchmark_fingerprint=base, runner_fingerprint=signature, optimizer_steps=BUDGETS,
            cnn=PROFILES["byte_cnn"][PROFILE], training={k:v for k,v in TRAINING.items() if k!="steps"},
            bronze_settings=SETTINGS, hard_selected_steps=hard_steps, hard_tuning_seed=PLAN["screen_seed"],
            evaluation_seeds=SEEDS, domain_folds=PLAN["folds"],
            purpose="Independent optimizer-budget check, not a reproduction of an unspecified CNN recipe.",
            scope="Train-only reused development folds; never Validation, Official Test or external."))
        runs, scores = execute(pool, "evaluate", list(product(BUDGETS, "ABCD", SEEDS)), signature)
    summary = runs.groupby(["steps","mode"],as_index=False).agg(ap=("ap","mean"), fit_seconds=("seconds","mean"))
    write_csv(OUT / "summary.csv", summary)
    pairs = []
    for steps in BUDGETS:
        for a,b in (("B","A"),("C","B"),("D","C"),("D","A")):
            pairs.append((f"{steps} {a} vs {b}", candidate(steps,a), candidate(steps,b)))
        if steps != hard_steps:
            pairs.append((f"{steps} D vs tuned A", candidate(steps,"D"), candidate(hard_steps,"A")))
    paired_stats(scores, core_train().set_index("id").group, pairs,
                 OUT / "paired_ap.csv", replicates=1000, random_state=890)
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
