"""Measure local CPU model inference only for the saved week-5 lexical bundle.

This does not train/select a model or evaluate labels. It excludes URL feature
extraction, disk loading, network requests, mobile runtime and RAM measurement.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_info, threadpool_limits

from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.modeling import load_baseline_inputs
from phishguard_vn.paths import get_project_root


WARMUPS = 3
REPETITIONS = 20
SEED = 42


def _sha(path, normalize_lf=False):
    content = Path(path).read_bytes()
    if normalize_lf:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _ids_sha(ids):
    return hashlib.sha256(("\n".join(str(value) for value in ids) + "\n").encode("utf-8")).hexdigest()


def _check_predictions(estimator, values):
    scores = np.asarray(estimator.predict_proba(values), dtype=float)
    if scores.shape != (len(values), 2) or not np.isfinite(scores).all():
        raise ValueError("Unexpected/nonfinite probability output while benchmarking")
    if ((scores < 0) | (scores > 1)).any():
        raise ValueError("Probability output must stay in [0, 1]")


def benchmark(root):
    """Return measurements and metadata; no labels are inspected or scored."""
    root = Path(root).resolve()
    artifact_path = root / "models/week5_lexical_models.joblib"
    run_metadata_path = root / "reports/tables/05_run_metadata.json"
    run_metadata = json.loads(run_metadata_path.read_text(encoding="utf-8"))
    artifact_sha = _sha(artifact_path)
    if artifact_sha != run_metadata["artifact_sha256"]:
        raise ValueError("Local week-5 artifact differs from saved experiment metadata")
    for name, digest in run_metadata["source_sha256_lf"].items():
        if _sha(root / name, normalize_lf=True) != digest:
            raise ValueError(f"Runtime source changed since the experiment: {name}")
    for name, digest in run_metadata["input_sha256"].items():
        if _sha(root / name) != digest:
            raise ValueError(f"Handoff changed since the experiment: {name}")
    bundle = joblib.load(artifact_path)
    names = bundle["feature_names"]
    if bundle.get("feature_set") != "lexical_12" or list(names) != list(CANDIDATE_FEATURES):
        raise ValueError("Benchmark expects the unchanged 12-feature lexical contract")
    features, _, folds = load_baseline_inputs(root)
    training = features.merge(folds[["id"]], on="id", validate="one_to_one").sort_values("id")
    if len(training) < 128:
        raise ValueError("Need at least 128 eligible training IDs for the fixed batch benchmark")
    sample = training.sample(n=128, random_state=SEED).reset_index(drop=True)
    if not set(sample.id).issubset(set(folds.id)):
        raise ValueError("Benchmark sample must contain training IDs only")
    frames = {1: sample.iloc[:1][names], 128: sample[names]}
    rows = []
    with threadpool_limits(limits=1):
        effective_threads = threadpool_info()
        for family, estimator in sorted(bundle["estimators"].items()):
            serialized = io.BytesIO()
            joblib.dump(estimator, serialized, compress=0)
            estimator_bytes = serialized.tell()
            for batch_size, values in frames.items():
                for _ in range(WARMUPS):
                    _check_predictions(estimator, values)
                elapsed_ms = []
                for _ in range(REPETITIONS):
                    start = time.perf_counter_ns()
                    estimator.predict_proba(values)
                    elapsed_ms.append((time.perf_counter_ns() - start) / 1_000_000)
                _check_predictions(estimator, values)
                if not np.isfinite(elapsed_ms).all() or min(elapsed_ms) <= 0:
                    raise ValueError("Invalid measured inference duration")
                rows.append({
                    "model": family, "feature_set": "lexical_12", "batch_size": batch_size,
                    "repetitions": REPETITIONS, "warmups": WARMUPS,
                    "serialized_estimator_bytes": estimator_bytes,
                    "bundle_bytes": artifact_path.stat().st_size,
                    "predict_proba_median_ms": float(np.median(elapsed_ms)),
                    "predict_proba_p95_ms": float(np.percentile(elapsed_ms, 95)),
                    "threadpool_limit": 1,
                })
    measurements = pd.DataFrame(rows)
    if measurements.empty:
        raise ValueError("The bundle contains no estimators")
    metadata = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": artifact_sha,
        "artifact_path": artifact_path.relative_to(root).as_posix(),
        "experiment_source_manifest_sha256": run_metadata["source_manifest_sha256"],
        "experiment_source_sha256_lf": run_metadata["source_sha256_lf"],
        "experiment_metadata_sha256": _sha(run_metadata_path),
        "benchmark_script_sha256_lf": _sha(Path(__file__), normalize_lf=True),
        "input_sha256": run_metadata["input_sha256"],
        "python": platform.python_version(),
        "versions": {name: version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "threadpoolctl")},
        "platform": {"system": platform.system(), "release": platform.release(),
                     "machine": platform.machine(), "processor": platform.processor(),
                     "logical_cpu_count": os.cpu_count()},
        "thread_policy": {"threadpool_limit": 1, "parallel_measurements": False,
                          "effective_libraries_during_measurement": effective_threads},
        "sample": {"seed": SEED, "population": "eligible official train IDs only; labels not inspected",
                   "eligible_train_rows": len(training), "batch_sizes": [1, 128],
                   "method": "sort by ID, pandas.sample(n=128, random_state=42); batch 1 is the first sampled row",
                   "sample_ids_sha256": _ids_sha(sample.id),
                   "batch1_ids_sha256": _ids_sha(sample.iloc[:1].id),
                   "id_hash_convention": "IDs in measurement order, UTF-8, one ID per line including final LF"},
        "measurement": {"warmups_per_model_batch": WARMUPS,
                        "repetitions_per_model_batch": REPETITIONS,
                        "clock": "time.perf_counter_ns", "percentile_method": "numpy.percentile default linear",
                        "timed_call": "estimator.predict_proba(precomputed_feature_dataframe)",
                        "size_method": "joblib.dump(each estimator, BytesIO, compress=0); independent per-model serialization",
                        "bundle_size_note": "bundle_bytes includes all estimators/schema/config and is not per-model size"},
        "limitations": [
            "PC CPU inference measurement only, not Android/iOS latency or RAM.",
            "Predict-proba duration excludes URL parsing/feature extraction, artifact disk loading, network and GUI.",
            "Single shared process; cache state, OS scheduling and hardware affect timings; no latency-based model selection.",
            "Batch-128 numbers are duration of the whole batch, not latency for one URL.",
            "Model bytes exclude dependencies, Python runtime and bundled PSL/brand reference costs.",
            "Three warmups precede twenty sequential timed calls per model and batch; validation labels/test are not used.",
        ],
    }
    json.dumps(metadata, ensure_ascii=False, allow_nan=False)
    return measurements, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = get_project_root()
    measurements, metadata = benchmark(root)
    tables = root / "reports/tables"
    tables.mkdir(parents=True, exist_ok=True)
    measurements.to_csv(tables / "05_resource_benchmark.csv", index=False)
    (tables / "05_resource_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(measurements.to_string(index=False))
    print("Measured model.predict_proba only on local PC; not mobile or end-to-end URL latency.")


if __name__ == "__main__":
    main()
