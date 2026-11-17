"""Week 7 development run: prepare -> Teacher targets -> paired Students -> export.

Uses only tracked Train/Validation CSVs; no notebook-generated local dependency.
Official Test and external files are never read. Read main() to follow the flow.
"""
from pathlib import Path
from importlib.metadata import version
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import platform
import subprocess
import sys
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from scipy.sparse import vstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from phishguard_vn.released_teacher import load_released_teacher
from phishguard_vn.url_parser import parse_url
from phishguard_vn.student import (Student, student_text, metrics, choose_threshold,
                                   export_model, sha256)

CONFIG = ROOT / "configs/week7_student.json"
ARTIFACTS = ROOT / "artifacts/student_week7"
TABLES = ROOT / "reports/tables/student_week7"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def write_csv(path, frame):
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def load_data(root):
    """Keep existing official splits, filter Core and log invalid/unresolved IDs."""
    frames, exclusions = {}, []
    for split in ("train", "val"):
        frame = pd.read_csv(root / f"data/splits/url_{split}.csv", dtype=str,
                            usecols=["id", "url", "label", "tier", "split", "source"])
        frame = frame.loc[frame.tier.isin(["gold", "silver"])].copy()
        if (frame.empty or frame.id.isna().any() or not frame.id.is_unique
                or not frame.split.eq(split).all()
                or not frame.label.isin(["benign", "phishing"]).all()):
            raise ValueError("Invalid core IDs/split/labels: " + split)
        parsed = frame.url.map(parse_url)
        valid = parsed.map(lambda p: p.is_valid and bool(p.registrable_domain))
        for i in frame.index[~valid]:
            exclusions.append(dict(id=frame.at[i, "id"], split=split,
                                   reason=parsed[i].error_reason or "unresolved_domain"))
        frame = frame.loc[valid].copy()
        frame["group"] = parsed[valid].map(lambda p: p.registrable_domain)
        frame["text"] = frame.url.map(student_text)
        frame["target"] = frame.label.map({"benign": 0, "phishing": 1})
        frames[split] = frame.sort_values("id").reset_index(drop=True)
    train, val = frames["train"], frames["val"]
    for key in ("id", "group", "text"):
        if set(train[key]) & set(val[key]):
            raise ValueError("Train/Validation overlap: " + key)
    if train.target.nunique() != 2 or val.target.nunique() != 2:
        raise ValueError("Need both classes in Train and Validation")
    return train, val, pd.DataFrame(exclusions, columns=["id", "split", "reason"])


def fit_student(X, target, config):
    """Fractional-label BCE using weighted positive/negative copies.

    For q=0/1 this is ordinary hard-label training. For 0<q<1:
    loss_i = -q_i*log(p_i) - (1-q_i)*log(1-p_i).
    Total sample weight remains N for both hard-only and KD.
    """
    target = np.asarray(target, dtype=float)
    if target.shape != (X.shape[0],) or not np.isfinite(target).all() or ((target < 0) | (target > 1)).any():
        raise ValueError("Student targets must be finite scores in [0,1]")
    model = LogisticRegression(C=config["C"], solver="liblinear",
                               max_iter=config["max_iter"], random_state=config["seed"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(vstack([X, X]), np.r_[np.ones(len(target)), np.zeros(len(target))],
                  sample_weight=np.r_[target, 1-target])
    return model


def teacher_scores(teacher, frame):
    """Never silently drop inference failures or synthesize benign targets."""
    rows = teacher.predict_batch(frame.url.tolist())
    scores = np.array([r["score"] for r in rows])
    if (len(rows) != len(frame) or not np.isfinite(scores).all()
            or ((scores < 0) | (scores > 1)).any()):
        raise ValueError("Teacher output count/range is invalid")
    if any(r["model_version"] != "teacher-stacking-v2" for r in rows):
        raise ValueError("Wrong Teacher")
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT,
                        help="Optional separate output folder for reproducibility checks")
    args = parser.parse_args()
    output = args.output_root.resolve()
    artifacts, tables = output / ARTIFACTS.relative_to(ROOT), output / TABLES.relative_to(ROOT)
    for folder in (artifacts, tables):
        folder.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())

    # 1. Inputs and split checks BEFORE Teacher inference or Student fitting.
    train, val, excluded = load_data(ROOT)
    if len(train) != 13078 or len(val) != 1585:
        raise ValueError("Eligibility snapshot changed; review protocol before fitting")
    source_paths = ["configs/week7_student.json", "scripts/train_student.py",
                    "src/phishguard_vn/student.py", "src/phishguard_vn/stacking.py",
                    "src/phishguard_vn/url_parser.py", "src/phishguard_vn/released_teacher.py",
                    "src/phishguard_vn/stacking_candidate.py", "src/phishguard_vn/features.py",
                    "src/phishguard_vn/brand_features.py", "requirements-teacher.txt"]
    input_paths = ["data/splits/url_train.csv", "data/splits/url_val.csv",
                   "configs/teacher_lock.json", "configs/teacher_v2_candidate_lock.json",
                   "models/teacher_v2_candidate.joblib"]
    source_hashes = {p: sha256(ROOT / p) for p in source_paths}
    input_hashes = {p: sha256(ROOT / p) for p in input_paths}
    source_dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *source_paths], cwd=ROOT).returncode != 0
    write_csv(tables / "exclusions.csv", excluded)
    ids = pd.concat([f[["id", "split", "target"]].assign(
        group_sha256=f.group.map(lambda s: hashlib.sha256(s.encode()).hexdigest()))
        for f in (train, val)], ignore_index=True)
    write_csv(tables / "split_ids.csv", ids)
    supports = pd.concat([train, val]).groupby(["split", "source", "label"]).size().reset_index(name="count")
    write_csv(tables / "source_label_counts.csv", supports)
    print(f"Data: Train={len(train)}, Validation={len(val)}, excluded={len(excluded)}", flush=True)

    # 2. Targets ONLY on Train. Validation Teacher outputs are agreement references.
    teacher = load_released_teacher(ROOT)
    train_scores = teacher_scores(teacher, train)
    val_teacher = teacher_scores(teacher, val)
    teacher_threshold = teacher.candidate.threshold
    targets = train[["id", "target"]].copy()
    targets["teacher_score"] = train_scores
    targets["teacher_label"] = (train_scores >= teacher_threshold).astype(int)
    targets["kd_target"] = (1-config["kd_alpha"])*train.target.to_numpy() + config["kd_alpha"]*train_scores
    target_path = artifacts / "teacher_targets.csv.gz"
    target_path.write_bytes(gzip.compress(targets.to_csv(index=False, lineterminator="\n").encode("utf-8"), mtime=0))
    target_sha = sha256(target_path)
    print("Teacher targets: verified, Train only; no Teacher retraining.", flush=True)

    # 3. Fit vocabulary/IDF on Train only; both Students see exactly the same X.
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=tuple(config["ngram_range"]),
                                min_df=config["min_df"], max_features=config["max_features"],
                                lowercase=False, sublinear_tf=True, norm="l2")
    X_train = vectorizer.fit_transform(train.text)
    X_val = vectorizer.transform(val.text)
    rows, model_records, prediction_tables, portable_checks = [], {}, {}, {}
    with threadpool_limits(limits=1):
        for name in config["candidates"]:
            q = train.target.to_numpy() if name == "hard_only" else targets.kd_target.to_numpy()
            started = time.perf_counter()
            model = fit_student(X_train, q, config)
            fit_seconds = time.perf_counter()-started
            score = model.predict_proba(X_val)[:, 1]
            threshold = choose_threshold(val.target, score, config["fpr_budget"])

            # 4. Export and verify JSON inference against fitted sklearn on ALL Val.
            bundle = export_model(vectorizer, model, threshold, name, config)
            path = artifacts / (name + ".json")
            write_json(path, bundle)
            portable = Student(json.loads(path.read_text(encoding="utf-8")))
            actual = np.array([portable.score_one(url) for url in val.url])
            np.testing.assert_allclose(actual, score, rtol=0, atol=1e-12)
            np.testing.assert_array_equal(actual >= threshold, score >= threshold)
            portable_checks[name] = dict(inputs=len(val), max_abs_score_diff=float(np.max(np.abs(actual-score))),
                                         labels_equal=True)
            prediction = val[["id", "target"]].rename(columns={"target": "y_true"}).copy()
            prediction["score"], prediction["prediction"] = score, (score >= threshold).astype(int)
            prediction["teacher_score"] = val_teacher
            prediction["teacher_prediction"] = (val_teacher >= teacher_threshold).astype(int)
            prediction_tables[name] = prediction
            write_csv(tables / (name + "_validation.csv"), prediction)
            record = dict(candidate=name, **metrics(val.target, score, threshold),
                          agreement=float(np.mean(prediction.prediction == prediction.teacher_prediction)),
                          teacher_score_mae=float(np.mean(np.abs(score-val_teacher))),
                          fit_seconds=fit_seconds, model_bytes=path.stat().st_size,
                          features=len(vectorizer.vocabulary_))
            fixed = metrics(val.target, score, .5)
            rows.append({**record, "operating_point": "validation_fpr_budget"})
            fixed_agreement = float(np.mean((score >= .5) == prediction.teacher_prediction.to_numpy()))
            rows.append({**record, **fixed, "agreement": fixed_agreement, "operating_point": "fixed_0.5"})
            model_records[name] = dict(path=str(path.relative_to(output)).replace("\\", "/"),
                                      sha256=sha256(path), threshold=threshold)
            print(name, "AP", record["ap"], "bytes", record["model_bytes"], flush=True)

    # 5. Validation selection, explicitly NOT unbiased final test performance.
    dev = pd.DataFrame(rows)
    ranking = dev.loc[dev.operating_point.eq("validation_fpr_budget")].sort_values(
        ["ap", "candidate"], ascending=[False, True])
    selected = str(ranking.iloc[0].candidate)
    write_csv(tables / "benchmark.csv", dev)
    teacher_row = dict(candidate="released_teacher_v2", **metrics(val.target, val_teacher, teacher_threshold))
    write_json(tables / "teacher_validation.json", teacher_row)

    # Measured desktop URL-to-score latency, no network and no Teacher at inference.
    timings = []
    for name, record in model_records.items():
        started = time.perf_counter()
        model = Student(json.loads((output / record["path"]).read_text(encoding="utf-8")))
        load_ms = (time.perf_counter()-started)*1000
        for url in val.url.iloc[:50]:
            model.score_one(url)
        times = []
        for i in range(300):
            started = time.perf_counter()
            model.score_one(val.url.iloc[i % len(val)])
            times.append((time.perf_counter()-started)*1000)
        timings.append(dict(candidate=name, json_load_ms=load_ms, warmup=50, requests=300,
                            p50_ms=float(np.median(times)), p95_ms=float(np.quantile(times, .95)),
                            scope="desktop sequential raw URL to score", android_measured=False))
    write_csv(tables / "latency.csv", pd.DataFrame(timings))

    # Static inputs are synthetic fixtures, not evidence of detection accuracy.
    examples = ["example.com", "https://EXAMPLE.com/Login?Q=%2F",
                "https://www.hcmus.edu.vn", "https://example.com:8443/path", "https://bücher.de/"]
    model = Student(json.loads((output / model_records[selected]["path"]).read_text(encoding="utf-8")))
    write_json(artifacts / "examples.json", [
        {"url": u, **model.predict_one(u)} for u in examples])
    manifest = dict(protocol=config, selected_candidate=selected, release_status="experimental",
                    official_test_evaluated=False, external_evaluated=False, android_verified=False,
                    go_no_go="NO-GO for default replacement: Android and independent evaluation pending",
                    created_utc=datetime.now(timezone.utc).isoformat(), producer_revision=revision,
                    working_tree_dirty=dirty, producer_source_dirty=source_dirty,
                    source_sha256=source_hashes, input_sha256=input_hashes,
                    teacher_targets=dict(path="artifacts/student_week7/teacher_targets.csv.gz", sha256=target_sha,
                                         rows=len(train), in_sample=True, cross_fitted=False),
                    train_rows=len(train), validation_rows=len(val),
                    validation_positive=int(val.target.sum()), group_overlap=0, canonical_overlap=0,
                    portable_checks=portable_checks, models=model_records,
                    environment=dict(python=platform.python_version(), platform=platform.platform(),
                        libraries={p: version(p) for p in ["numpy","scipy","scikit-learn","pandas","idna"]}))
    # Fail if a protected input/source changed during the run.
    for relative, digest in {**source_hashes, **input_hashes}.items():
        if sha256(ROOT / relative) != digest:
            raise ValueError("Input/source changed during training: " + relative)
    manifest["inference_source_sha256"] = {p: source_hashes[p] for p in
        ["src/phishguard_vn/student.py", "src/phishguard_vn/stacking.py", "src/phishguard_vn/url_parser.py"]}
    manifest["split_ids_sha256"] = sha256(tables / "split_ids.csv")
    manifest["canonical_duplicates_within_train"] = int(train.text.duplicated().sum())
    manifest["output_sha256"] = {str(p.relative_to(output)).replace("\\", "/"): sha256(p)
                                  for p in sorted(tables.glob("*")) if p.is_file()}
    write_json(artifacts / "manifest.json", manifest)
    print("Selected for Android feasibility only:", selected)
    print("Official Test untouched; not a production release.")


if __name__ == "__main__":
    main()
