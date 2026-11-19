"""Replay locked Students, export research bundles and compare offline CPU cost."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import json
import subprocess

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from kd_bronze_cost import measure
from kd_bronze_data import DATA_CACHE, ROOT, verify_preparation
from kd_bronze_runner import (OUT, PLAN, Recipe, destination, fingerprint, fit_once, matrices,
                              read_run, representation)
from phishguard_vn.student import sha256
from train_lightgbm_student import write_csv, write_json

ART = ROOT / "artifacts/student_bronze_kd"
FIG = ROOT / "reports/figures/student_bronze_kd"
SIZE_BUDGET = 1024**2
LATENCY_BUDGET_MS = 1.0


def records(stage):
    return pd.read_csv(OUT / f"{stage}_summary.csv")


def profile(row):
    return Recipe(row.family, row.profile, row.mode, row.alpha, row.extra_weight, row.extra_rows)


def bench_menu():
    screen = records("screen")
    hard = (screen[screen["mode"].eq("A")].sort_values(["ap","candidate"], ascending=[False,True])
            .drop_duplicates("family"))
    kd = (screen[screen["mode"].ne("A")].sort_values(["ap","candidate"], ascending=[False,True])
          .drop_duplicates("family"))
    yield "screen", PLAN["screen_seed"], pd.concat([hard,kd], ignore_index=True)
    for stage in ("confirm","final"):
        locked = json.loads((OUT / f"{stage}_lock.json").read_text(encoding="utf8"))
        chosen = [Recipe(**d) for d in locked["chosen"]]
        all_rows = records(stage)
        if stage == "confirm":
            ids = {r.tag for r in chosen}
        else:
            ids = set(all_rows.candidate)
        yield stage, locked["seeds"][0], all_rows[all_rows.candidate.isin(ids)]


def costs():
    signature = fingerprint()
    verify_preparation()
    rows = joblib.load(DATA_CACHE / "fold0.joblib")
    drawn = rows["held"][["id","url"]].sort_values("id").sample(n=250,random_state=2357)
    observations = []
    for stage, seed, candidates in bench_menu():
        for kind in ("e2","tfidf","bytes"):
            group = candidates[candidates.representation.eq(kind)]
            if group.empty:
                continue
            inputs = matrices(kind, rows, int(group.extra_rows.max()))
            for spec in group.itertuples(index=False):
                cfg = profile(spec)
                model = fit_once(cfg, seed, rows, inputs)
                archived, _ = read_run(destination(stage, cfg, seed, 0), signature)
                np.testing.assert_allclose(model.score(inputs[1]), archived, atol=1e-12, rtol=0)
                filename = ART / stage / (cfg.tag+".joblib")
                row = measure(model, cfg.family, kind, inputs[3], drawn, filename)
                for key in ("joblib_path","portable_zip"):
                    if key in row:
                        row[key] = Path(row[key]).relative_to(ROOT).as_posix()
                observations.append(dict(candidate=cfg.tag, stage=stage, fold=0, seed=seed,
                    cv_ap=spec.ap, delta_vs_matched=spec.delta_vs_matched, delta_vs_tuned=spec.delta_vs_tuned,
                    mode=cfg.mode, **row))
                print(stage, cfg.tag, "AP", round(spec.ap,6), "bytes", row["size_bytes"],
                      "desktop p95 ms", round(row["p95_ms"],4), flush=True)
    return pd.DataFrame(observations)


def compare_costs(table):
    # Screen is the common phase, covering all 13 families under the same seed.
    kd = table[table.stage.eq("screen") & table["mode"].ne("A")].copy()
    kd["within_proxy_budget"] = (kd.size_bytes <= SIZE_BUDGET) & (kd.p95_ms <= LATENCY_BUDGET_MS)
    kd["pareto_size_ap"] = [
        not ((kd.size_bytes <= row.size_bytes) & (kd.cv_ap >= row.cv_ap)
             & ((kd.size_bytes < row.size_bytes) | (kd.cv_ap > row.cv_ap))).any()
        for row in kd.itertuples(index=False)]
    ranked = kd.sort_values(["within_proxy_budget","cv_ap","p95_ms"], ascending=[False,False,True])
    write_csv(OUT / "android_tradeoff.csv", ranked)
    FIG.mkdir(parents=True, exist_ok=True)
    fig, (left,right) = plt.subplots(1,2,figsize=(13,5.5),layout="constrained")
    for axis,xcol,xlabel,marker_limit in (
        (left,"size_bytes","Model and inference data (KiB)", SIZE_BUDGET/1024),
        (right,"p95_ms","Windows Python p95 (ms)", LATENCY_BUDGET_MS),
    ):
        vals = kd[xcol] / 1024 if xcol == "size_bytes" else kd[xcol]
        axis.scatter(vals,kd.cv_ap,c=kd.within_proxy_budget.map({True:"#006d77",False:"#ab5353"}),s=40)
        axis.axvline(marker_limit,linestyle="--",color="#7a8697",linewidth=1)
        for key,label,dy in (("byte_cnn","Byte CNN",5),("tfidf_lr","TF-IDF LR",11),
                             ("sparse_mlp","MLP",-14),("multinomial_nb","Naive Bayes",-11),
                             ("cart","CART",-11),("rbf_random_features","Random features",7)):
            match = kd.family.eq(key)
            val = vals[match].item()
            ap = kd[match].cv_ap.item()
            offset = (-7,dy) if xcol=="size_bytes" and key=="rbf_random_features" else (5,dy)
            axis.annotate(label,(val,ap),xytext=offset,textcoords="offset points",
                          ha="right" if offset[0]<0 else "left",fontsize=8)
        axis.set_xscale("log")
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Mean Group CV AP")
        axis.grid(alpha=.20)
    fig.suptitle("Bronze KD Students on the same three development folds")
    fig.savefig(FIG / "offline_tradeoff.png",dpi=155)
    plt.close(fig)


def provenance():
    settings = {p.name:sha256(p) for p in sorted(OUT.iterdir()) if p.is_file()
                and p.name!="research_manifest.json"}
    base = verify_preparation()
    write_json(OUT / "research_manifest.json", dict(
        git_branch=subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
        base_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        model_runtime_versions={lib:version(lib) for lib in
            ("numpy","pandas","scipy","scikit-learn","joblib","lightgbm","xgboost","catboost")},
        ran_utc=datetime.now(timezone.utc).isoformat(), benchmark_fingerprint=fingerprint(),
        registered_settings=PLAN, fold_preparation=base, output_sha256=settings,
        source_sha256={p.name:sha256(p) for p in sorted((ROOT/"scripts").glob("kd_bronze_*.py"))},
        measurements={"databytes_limit":SIZE_BUDGET,"desktop_p95_ms_limit":LATENCY_BUDGET_MS,
                      "scope":"proxy to compare measured Student settings, not an approved device limit"},
        validation_test_external_read=False, teacher_product_changed=False, android_verified=False))


def export_cohort():
    manifest = verify_preparation()
    parts = []
    for fold in PLAN["folds"]:
        cache = joblib.load(DATA_CACHE / f"fold{fold}.joblib")
        extra = cache["extra"]
        parts.append(pd.DataFrame(dict(fold_id=fold, sample_rank=np.arange(1, len(extra)+1),
                                       id=extra.id, teacher_score=cache["extra_scores"])))
    write_csv(OUT / "teacher_bronze_scores.csv.gz", pd.concat(parts, ignore_index=True))
    write_json(OUT / "data_preparation.json", manifest)


def plot_gain():
    mlp = pd.read_csv(OUT / "mlp_final_paired_ap.csv").set_index("comparison")
    cart = pd.read_csv(OUT / "cart_wide_final_paired.csv").set_index("comparison")
    rows = pd.DataFrame([
        mlp.loc["D vs expanded tuned A"], mlp.loc["D vs Bronze hard C"],
        cart.loc["primary_D_vs_tuned_A"], cart.loc["D_vs_matched_C"]
    ])
    labels = ["MLP  D vs tuned hard", "MLP  D vs hard bronze",
              "CART  D vs tuned hard", "CART  D vs hard bronze"]
    center = rows.delta_mean_fold_ap.to_numpy()
    left = center - rows.ci_low.to_numpy()
    right = rows.ci_high.to_numpy() - center
    fig, ax = plt.subplots(figsize=(9.4, 3.8), layout="constrained")
    ax.axvline(0, color="#7a8697", linewidth=1)
    ax.errorbar(center, np.arange(len(rows)), xerr=np.vstack((left,right)), fmt="o", capsize=4,
                color="#006d77", linewidth=1.7, markersize=6)
    ax.set_yticks(np.arange(len(rows)), labels)
    ax.invert_yaxis()
    ax.set_title("KD on three final training seeds", loc="left")
    ax.set_xlabel("Change in mean-fold AP with paired 95% domain bootstrap interval")
    ax.grid(axis="x", alpha=.20)
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "paired_gain.png", dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true", help="Update cohort audit, gain figure, and provenance")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        if args.finalize:
            export_cohort()
            plot_gain()
        else:
            table = costs()
            write_csv(OUT / "offline_cpu_cost.csv",table)
            compare_costs(table)
        provenance()
