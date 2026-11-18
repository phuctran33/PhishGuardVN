"""Test three smaller offline LightGBM Students on the frozen domain folds.

Run with the project's Python 3.11: python scripts/experiment_android_boost.py
Compare hard/KD with identical features and settings. Select the intermediate
configuration using KD mean fold AP, before examining development Validation.
"""
import gzip
import json
import sys
from pathlib import Path
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from phishguard_vn.student import choose_threshold, metrics, sha256
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.student_lightgbm import HybridLightGBMStudent, export_booster, export_features
from train_lightgbm_student import ART as ARCHIVE, CACHE, PLAN, load_inputs, vectorizer, verify_cv_targets, write_csv, write_json
from verify_compact_lightgbm import aligned_teacher_scores, released_target_path, hybrid_inputs, fit_student
from tiny_mlp_analysis import paired_domain_bootstrap

OUT = ROOT / "reports/tables/android_kd_boost"
ART = ROOT / "artifacts/android_kd_boost"
# A 300-round fit also yields the exact predictions at 200 rounds.
ROUNDS = {0.05: (200, 300), 0.10: (200,)}
MODES = ("hard_only", "kd_mixed")
SEED = 42


def key(rate, rounds):
    return f"lr{rate:.2f}_{rounds}x15"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def parameters(plan, rate, rounds):
    return {**plan["lightgbm"], "learning_rate": rate, "n_estimators": rounds}


def cross_validate(plan, train, train_e2):
    frames = []
    fold_metrics = []
    for fold in plan["outer_folds"]:
        fitting = train.loc[train.fold_id.ne(fold)]
        held = train.loc[train.fold_id.eq(fold)]
        tfidf = vectorizer(plan).fit(fitting.text)
        x_fit = hybrid_inputs(tfidf, fitting.text, train_e2[fitting.index])
        x_held = hybrid_inputs(tfidf, held.text, train_e2[held.index])
        targets = aligned_teacher_scores(fitting, CACHE / f"outer{fold}_fitting_targets.csv.gz")
        for rate, checkpoints in ROUNDS.items():
            for mode in MODES:
                model = fit_student(x_fit, fitting.target.to_numpy(), targets, mode, plan["alpha"],
                                    parameters(plan, rate, max(checkpoints)))
                for count in checkpoints:
                    scores = model.booster_.predict(x_held, num_iteration=count, num_threads=1)
                    name = key(rate, count)
                    fold_metrics.append(dict(profile=name, mode=mode, fold_id=fold,
                                             **metrics(held.target, scores, 0.5)))
                    rows = held[["id", "fold_id", "target"]].rename(columns={"target": "y_true"})
                    frames.append(rows.assign(candidate=f"{name}_{mode}", seed=SEED, score=scores))
                    print("fold", fold, name, mode, "AP", round(fold_metrics[-1]["ap"], 6), flush=True)
    return pd.DataFrame(fold_metrics), pd.concat(frames, ignore_index=True)


def freeze(plan, train, fold_metrics, oof):
    summary = fold_metrics.groupby(["profile", "mode"], as_index=False).agg(
        cv_ap=("ap", "mean"), cv_recall_05=("recall", "mean"), cv_fpr_05=("fpr", "mean"))
    selected = summary.loc[summary["mode"].eq("kd_mixed")].sort_values(
        ["cv_ap", "profile"], ascending=[False, True]).iloc[0].profile
    thresholds, points = {}, []
    for name, rows in oof.groupby("candidate"):
        if len(rows) != len(train) or not rows.id.is_unique or set(rows.id) != set(train.id):
            raise ValueError("Unexpected OOF IDs for " + name)
        cut = choose_threshold(rows.y_true, rows.score, plan["fpr_budget"])
        thresholds[name] = cut
        points.append(dict(candidate=name, **metrics(rows.y_true, rows.score, cut)))
    write_csv(OUT / "cv_metrics.csv", fold_metrics)
    write_csv(OUT / "cv_predictions.csv.gz", oof)
    write_csv(OUT / "cv_summary.csv", summary)
    write_csv(OUT / "train_oof_at_locked_threshold.csv", pd.DataFrame(points))
    write_json(OUT / "train_lock.json", dict(selected_profile=selected,
        rule="Highest mean domain-fold AP among the 3 new KD configurations; hard at same setting is the control.",
        thresholds=thresholds, num_train=len(train), seed=SEED, fpr_budget=plan["fpr_budget"],
        fit_scope="Threshold chosen on pooled Train OOF, excluded Validation. Not independent evaluation of the threshold."))
    return selected, thresholds


def compare_archive(train, oof):
    original = pd.read_csv(ROOT / "reports/tables/student_lightgbm/cv_predictions.csv.gz", float_precision="round_trip")
    original = original.loc[original.family.eq("hybrid_lightgbm") & original.seed.eq(SEED)]
    original = original.assign(candidate="archive400_" + original["mode"])
    pairs = []
    for rate, counts in ROUNDS.items():
        for count in counts:
            name = key(rate, count)
            pairs += [(name + "_kd_mixed", name + "_hard_only"), (name + "_kd_mixed", "archive400_kd_mixed")]
    paired_domain_bootstrap(pd.concat([oof, original[oof.columns]], ignore_index=True),
                            train.set_index("id").group, pairs, output_path=OUT / "paired_bootstrap.csv")


def time_url_predictions(model, urls):
    for url in urls[:30]:
        model.predict_one(url)
    elapsed = []
    for url in urls:
        start = perf_counter_ns()
        model.predict_one(url)
        elapsed.append((perf_counter_ns() - start) / 1_000_000)
    return dict(p50_ms=np.percentile(elapsed, 50), p95_ms=np.percentile(elapsed, 95),
                timing_n=len(elapsed), timing_warmup=30)


def final_models(plan, name, thresholds, train, validation, train_e2, release_path):
    rate, count = next((r, n) for r, counts in ROUNDS.items() for n in counts if key(r, n) == name)
    tfidf = vectorizer(plan).fit(train.text)
    x_train = hybrid_inputs(tfidf, train.text, train_e2)
    val_e2 = e2_matrix(validation.url)
    x_val = hybrid_inputs(tfidf, validation.text, val_e2)
    targets = aligned_teacher_scores(train, release_path)
    features = export_features(tfidf)
    if features != read_json(ARCHIVE / "features.json"):
        raise ValueError("Full-Train features differ from original LightGBM Student")
    common = [ARCHIVE / x for x in ("features.json", "psl_icann_tldextract_5.4.0.txt", "brand_reference_v1.csv")]
    sample = validation.sort_values("id").sample(250, random_state=SEED).url.tolist()
    rows, predictions = [], []
    paths = list(common)
    for mode in MODES:
        model = fit_student(x_train, train.target.to_numpy(), targets, mode, plan["alpha"],
                            parameters(plan, rate, count))
        threshold = thresholds[name + "_" + mode]
        bundle = export_booster(model, threshold, mode)
        bundle["model_version"] = name + "_" + mode
        model_path = ART / (mode + ".json")
        write_json(model_path, bundle, compact=True)
        paths.append(model_path)
        portable = HybridLightGBMStudent(features, read_json(model_path))
        native = model.booster_.predict(x_val, num_threads=1)
        scores = np.array([portable.score_row(portable.vector(u, e)) for u, e in zip(validation.url, val_e2)])
        np.testing.assert_allclose(scores, native, atol=1e-12, rtol=0)
        np.testing.assert_array_equal(scores >= threshold, native >= threshold)
        package = [model_path, *common]
        gzip_total = 0
        for path in package:
            raw = path.read_bytes()
            compressed = gzip.compress(raw, compresslevel=6, mtime=0)
            if gzip.decompress(compressed) != raw:
                raise ValueError("Compression roundtrip failed")
            gzip_total += len(compressed)
        rows.append(dict(profile=name, mode=mode, **metrics(validation.target, scores, threshold),
                         parity_max_abs=float(np.max(abs(scores-native))),
                         total_bytes=sum(p.stat().st_size for p in package), gzip_bytes=gzip_total,
                         **time_url_predictions(portable, sample)))
        predictions.append(validation[["id", "target"]].rename(columns={"target": "y_true"}).assign(
            mode=mode, score=scores, prediction=(scores>=threshold).astype(int)))
    write_csv(OUT / "validation_metrics.csv", pd.DataFrame(rows))
    write_csv(OUT / "validation_predictions.csv.gz", pd.concat(predictions, ignore_index=True))
    files = [*paths, PLAN, CACHE / "manifest.json", release_path, OUT / "train_lock.json", Path(__file__)]
    write_json(ART / "manifest.json", dict(profile=name, parameters=parameters(plan, rate, count),
        sample_seed=SEED, kd_alpha=plan["alpha"], models={m:m+".json" for m in MODES},
        shared_assets=[p.relative_to(ROOT).as_posix() for p in common], thresholds=thresholds,
        sha256={p.relative_to(ROOT).as_posix():sha256(p) for p in files},
        seed=SEED, num_train=len(train), num_validation=len(validation),
        benchmark="Windows Python 3.11, one thread, portable JSON raw URL -> score, warm single URL requests, excludes load",
        android_verified=False, teacher_retrained=False, external_evaluated=False, official_test_evaluated=False))
    print(pd.DataFrame(rows).to_string(index=False), flush=True)


def main():
    plan = read_json(PLAN)
    train, validation, _ = load_inputs()
    if verify_cv_targets(train) is None:
        raise ValueError("Missing archived fold Teachers")
    release_path = released_target_path()
    train_e2 = e2_matrix(train.url)
    fold_metrics, oof = cross_validate(plan, train, train_e2)
    name, thresholds = freeze(plan, train, fold_metrics, oof)
    print("Frozen on Train:", name, flush=True)
    compare_archive(train, oof)
    final_models(plan, name, thresholds, train, validation, train_e2, release_path)


def verify_export():
    """Replay existing parity cases and time both KD models on the same URLs."""
    archive_cases = ARCHIVE / "python_reference.json"
    features = read_json(ARCHIVE / "features.json")
    local = {mode: HybridLightGBMStudent(features, read_json(ART / (mode + ".json")))
             for mode in MODES}
    original = read_json(archive_cases)["cases"]
    cases = []
    for case in original:
        result = {k: case[k] for k in ("name", "url", "status")}
        if case["status"] == "classified":
            result["expected"] = {mode: model.predict_one(case["url"]) for mode, model in local.items()}
        else:
            for model in local.values():
                try:
                    model.predict_one(case["url"])
                except (ValueError, TypeError) as error:
                    if type(error).__name__ != case["error_type"]:
                        raise
                else:
                    raise AssertionError("Expected rejection: " + case["name"])
            result["error_type"] = case["error_type"]
        cases.append(result)
    reference = ART / "python_reference.json"
    write_json(reference, {"scope": "Static offline parity cases, without accuracy labels", "cases": cases})

    manifest_path = ART / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["sha256"].update({p.relative_to(ROOT).as_posix(): sha256(p)
                               for p in [archive_cases, reference, Path(__file__)]})
    write_json(manifest_path, manifest)
    for name, digest in manifest["sha256"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Changed artifact " + name)

    _, validation, _ = load_inputs()
    urls = validation.sort_values("id").sample(250, random_state=SEED).url.tolist()
    models = [("selected_200_kd", local["kd_mixed"]),
              ("archived_400_kd", HybridLightGBMStudent(features, read_json(ARCHIVE / "kd_mixed.json")))]
    for _, model in models:
        for url in urls[:30]:
            model.predict_one(url)
    elapsed = {name: [] for name, _ in models}
    for repeat in range(3):
        for index, url in enumerate(urls):
            order = models if (index + repeat) % 2 == 0 else reversed(models)
            for name, model in order:
                start = perf_counter_ns()
                model.predict_one(url)
                elapsed[name].append((perf_counter_ns() - start) / 1_000_000)
    rows = [dict(model=name, p50_ms=np.percentile(values,50), p95_ms=np.percentile(values,95),
                 requests=len(values), unique_urls=len(urls), warmup=30)
            for name, values in elapsed.items()]
    write_csv(OUT / "paired_desktop_latency.csv", pd.DataFrame(rows))
    print(pd.DataFrame(rows).to_string(index=False), flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-export", action="store_true", help="Replay export fixtures and benchmark existing KD bundles")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        if not args.verify_export:
            main()
        verify_export()