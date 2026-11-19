"""Compare stored Tiny MLP, LightGBM and Teacher results on one desktop."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tiny_mlp_export import benchmark, load_bundle
from phishguard_vn.released_teacher import load_released_teacher
from phishguard_vn.student_lightgbm import HybridLightGBMStudent, load_lightgbm_student
from phishguard_vn.student import sha256

OUT = ROOT / "reports/tables/student_tiny_mlp"
ART = ROOT / "artifacts/student_tiny_mlp"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pack_size(folder, mode):
    return sum((folder / name).stat().st_size for name in
               (f"{mode}.json", "features.json", "psl_icann_tldextract_5.4.0.txt", "brand_reference_v1.csv"))


class ScoreAdapter:
    """Time the same raw-URL-to-score interface for existing model adapters."""
    def __init__(self, model):
        self.model = model

    def predict_proba(self, urls):
        return [row["score"] for row in self.model.predict_batch(urls)]


def main():
    tiny = read_json(ART / "manifest.json")
    for name, digest in tiny["artifact_sha256"].items():
        if sha256(ART / name) != digest:
            raise ValueError("Tiny MLP artifact changed: " + name)
    for name, digest in tiny["output_sha256"].items():
        if sha256(OUT / name) != digest:
            raise ValueError("Tiny MLP result changed: " + name)
    values = pd.read_csv(OUT / "validation_metrics.csv")
    cv = pd.read_csv(OUT / "cv_summary.csv").set_index("candidate")
    val = pd.read_csv(ROOT / "data/splits/url_val.csv", usecols=["id", "url"], dtype=str)
    predictions = pd.read_csv(OUT / "validation_predictions.csv.gz", usecols=["id"])
    selected_ids = predictions.drop_duplicates().sort_values("id")
    sample = selected_ids.sample(n=250, random_state=42).merge(val, on="id", validate="one_to_one")
    if len(sample) != 250:
        raise ValueError("Missing benchmark URLs")
    urls = sample.url.tolist()
    variants = []
    names = {
        ("full__hard", "float32"): "Tiny MLP hard-label",
        ("full__score_kd", "int8"): "Tiny MLP score KD int8",
        ("full__mixed_logit", "float32"): "Tiny MLP mixed logit float32",
        ("full__mixed_logit", "int8"): "Tiny MLP mixed logit int8",
        ("full__logit_only", "int8"): "Tiny MLP logit only int8",
        ("compact__hard", "int8"): "Tiny MLP 1024 hard int8",
        ("compact__mixed_logit", "int8"): "Tiny MLP 1024 mixed int8",
    }
    for row in values.itertuples(index=False):
        if (row.candidate, row.encoding) in names:
            variants.append((
                names[(row.candidate, row.encoding)], load_bundle(ART / row.file),
                row._asdict(), cv.loc[row.candidate, "mean_ap"], row.package_bytes, "compressed NPZ + data assets"
            ))
    legacy = ROOT / "artifacts/student_lightgbm"
    original_cv = pd.read_csv(ROOT / "reports/tables/student_lightgbm/cv_summary.csv")
    original_val = pd.read_csv(ROOT / "reports/tables/student_lightgbm/validation_metrics.csv")
    for mode in ("hard_only", "kd_mixed"):
        val_record = original_val.loc[original_val["mode"].eq(mode) & original_val.seed.eq(42)].iloc[0]
        ap = original_cv.loc[original_cv.family.eq("hybrid_lightgbm") & original_cv["mode"].eq(mode), "ap_mean"].item()
        variants.append((f"LightGBM 400x15 {mode}", ScoreAdapter(load_lightgbm_student(ROOT, mode)),
                        val_record, ap, pack_size(legacy, mode), "JSON + data assets"))
    compact = ART / "compact_lightgbm"
    compact_table = OUT / "compact_lightgbm"
    compact_cv = pd.read_csv(compact_table / "cv_summary.csv")
    compact_val = pd.read_csv(compact_table / "validation_metrics.csv")
    for mode in ("hard_only", "kd_mixed"):
        model = HybridLightGBMStudent(read_json(compact/"features.json"), read_json(compact/f"{mode}.json"))
        val_record = compact_val.loc[compact_val["mode"].eq(mode)].iloc[0]
        ap = compact_cv.loc[compact_cv["mode"].eq(mode), "ap_mean"].item()
        variants.append((f"LightGBM 100x7 {mode}", ScoreAdapter(model), val_record,
                         ap, val_record.inference_data_bytes, "JSON + data assets"))
    teacher_val = read_json(ROOT / "reports/tables/student_week7/teacher_validation.json")
    teacher_ap = pd.read_csv(ROOT / "reports/tables/student_kd_analysis/fold_teacher_metrics.csv").ap.mean()
    teacher_dir = ROOT / "artifacts/teacher_v2_android"
    assets = pack_size(legacy, "kd_mixed") - (legacy/"kd_mixed.json").stat().st_size - (legacy/"features.json").stat().st_size
    teacher_bytes = sum((teacher_dir/p).stat().st_size for p in
                        ("dart_teacher_v2_model.json", "dart_svm_model.json")) + assets
    variants.append(("Teacher stacking v2", ScoreAdapter(load_released_teacher(ROOT)), teacher_val,
                     teacher_ap, teacher_bytes, "Dart JSON + data assets"))
    all_runs = []
    with threadpool_limits(limits=1):
        for name, predictor, val_row, mean_ap, size, format_note in variants:
            print("Timing", name, flush=True)
            timing = benchmark(predictor, urls, warmup=30)
            quality = {key:val_row[key] for key in ("ap","recall","precision","fpr","f1","tp","fp","tn","fn","threshold")}
            all_runs.append(dict(model=name, mean_cv_ap=mean_ap, package_bytes=size, package_format=format_note,
                                 **quality, **timing))
    table = pd.DataFrame(all_runs)
    # Lossless, format-neutral size diagnostic for the existing bundles. No training.
    # These GZIP bytes are an estimate of asset transfer/storage, not a built APK.
    from gzip import compress, decompress

    def gzip_bytes(paths):
        total = 0
        for path in paths:
            raw = path.read_bytes()
            data = compress(raw, compresslevel=6, mtime=0)
            if decompress(data) != raw:
                raise ValueError("Lossless compression check failed: " + str(path))
            total += len(data)
        return total

    common = [legacy / p for p in ("brand_reference_v1.csv", "psl_icann_tldextract_5.4.0.txt")]
    model_paths = {name: [ART / values.loc[values.candidate.eq(k[0]) & values.encoding.eq(k[1]), "file"].item()]
                   for k, name in names.items()}
    for mode in ("hard_only", "kd_mixed"):
        model_paths[f"LightGBM 400x15 {mode}"] = [legacy / f"{mode}.json", legacy / "features.json"]
        model_paths[f"LightGBM 100x7 {mode}"] = [compact / f"{mode}.json", compact / "features.json"]
    model_paths["Teacher stacking v2"] = [teacher_dir / "dart_teacher_v2_model.json",
                                         teacher_dir / "dart_svm_model.json"]
    table["gzip_package_bytes"] = table.model.map(lambda name: gzip_bytes(model_paths[name] + common))

    # Post-hoc Validation ranking diagnostic at the released Teacher's FP count.
    # Never pass these thresholds into a model or report them as CV/locked policy.
    from phishguard_vn.student import choose_threshold, metrics
    tiny_val = pd.read_csv(OUT / "validation_predictions.csv.gz")
    original_predictions = pd.read_csv(ROOT / "reports/tables/student_lightgbm/validation_predictions.csv.gz")
    compact_predictions = pd.read_csv(compact_table / "validation_predictions.csv.gz")
    teacher_predictions = pd.read_csv(ROOT / "reports/tables/student_week7/hard_only_validation.csv")
    score_rows = {name: tiny_val.loc[tiny_val.candidate.eq(k[0]) & tiny_val.encoding.eq(k[1])]
                  for k, name in names.items()}
    for mode in ("hard_only", "kd_mixed"):
        score_rows[f"LightGBM 400x15 {mode}"] = original_predictions.loc[
            original_predictions["mode"].eq(mode) & original_predictions.seed.eq(42)]
        score_rows[f"LightGBM 100x7 {mode}"] = compact_predictions.loc[compact_predictions["mode"].eq(mode)]
    score_rows["Teacher stacking v2"] = teacher_predictions.assign(score=teacher_predictions.teacher_score)
    counts = []
    for name, rows in score_rows.items():
        merged = teacher_predictions[["id","y_true"]].merge(rows[["id","y_true","score"]],
            on="id", validate="one_to_one", suffixes=("", "_model"))
        if len(merged) != len(teacher_predictions) or not merged.y_true.eq(merged.y_true_model).all():
            raise ValueError("Validation ID or label mismatch: " + name)
        num_negatives = merged.y_true.eq(0).sum()
        budget = (teacher_val["fp"] + .5) / num_negatives
        cut = choose_threshold(merged.y_true, merged.score, budget)
        counts.append(dict(model=name, max_fp=teacher_val["fp"],
            scope="post-hoc Validation diagnostic, not deployment threshold",
            **metrics(merged.y_true, merged.score, cut)))
    pd.DataFrame(counts).to_csv(OUT / "validation_matched_fp.csv", index=False,
                               encoding="utf-8", lineterminator="\n")
    table.to_csv(OUT / "tradeoff.csv", index=False, encoding="utf-8", lineterminator="\n")
    print(table[["model","mean_cv_ap","ap","tp","fp","package_bytes","gzip_package_bytes","p95_ms"]].to_string(index=False))

    # Keep labels in a shared legend to avoid overlapping points.
    shown = table.loc[table.model.isin([
        "Tiny MLP mixed logit float32", "Tiny MLP mixed logit int8", "Tiny MLP 1024 hard int8",
        "LightGBM 400x15 kd_mixed", "LightGBM 100x7 hard_only", "LightGBM 100x7 kd_mixed",
        "Teacher stacking v2",
    ])].reset_index(drop=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.6))
    colors = plt.get_cmap("tab10")
    for i, row in shown.iterrows():
        label = row.model
        x = row.gzip_package_bytes / 1024
        color = colors(i)
        ax1.scatter(x, row.mean_cv_ap, c=[color], label=label, s=48)
        ax2.scatter(x, row.ap, c=[color], s=48)
    ax1.set(xscale="log", xlabel="Lossless GZIP data (KiB, logarithmic)", ylabel="Mean Train Group CV AP")
    ax2.set(xscale="log", xlabel="Lossless GZIP data (KiB, logarithmic)", ylabel="Validation AP (24 phishing URLs)")
    for ax in (ax1, ax2):
        ax.grid(True, alpha=.25)
    fig.legend(loc="lower center", ncol=3, fontsize=9, bbox_to_anchor=(.5, .012))
    fig.suptitle("Student quality versus package size")
    fig.subplots_adjust(left=.08, right=.98, bottom=.25, top=.90, wspace=.24)
    plot = ROOT / "reports/figures/student_tiny_mlp/tradeoff.png"
    plot.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
