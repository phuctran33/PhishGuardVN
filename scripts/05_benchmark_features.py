#!/usr/bin/env python
"""Y5.3: đo thời gian trích xuất và bộ nhớ của E2 (parse + 12 lexical + 8 brand).

Chạy từ thư mục gốc dự án, bằng tldextract THẬT (không phải bản giả), khi máy ít bận:
    python scripts/05_benchmark_features.py                 # 5000 URL train, seed 42
    python scripts/05_benchmark_features.py --n 20000

Chỉ lấy mẫu từ hàng TRAIN (không dùng Validation/Test). Ghi reports/tables/05_feature_benchmark.json.
Số liệu là của MÁY CHẠY; ghi rõ máy/CPU/phiên bản khi trích dẫn. Đây không phải đo trên thiết bị di động.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn import url_parser  # noqa: E402
from phishguard_vn.brand_features import (  # noqa: E402
    FEATURE_SCHEMA_VERSION, _osa_distance, extract_brand_features_from_parsed, extract_e2_features, load_reference,
)
from phishguard_vn.features import extract_features_from_parsed  # noqa: E402
from phishguard_vn.url_parser import parse_url  # noqa: E402


def pct(sorted_values: list[float], q: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def time_stage(fn, items) -> dict:
    _osa_distance.cache_clear()  # mỗi giai đoạn bắt đầu với cache lỗi gõ trống (tránh thiên lệch do thứ tự đo)
    lat = []
    for item in items:
        t = time.perf_counter_ns()
        fn(item)
        lat.append((time.perf_counter_ns() - t) / 1e6)  # ms
    lat.sort()
    return {"median_ms": round(statistics.median(lat), 4), "p95_ms": round(pct(lat, .95), 4),
            "p99_ms": round(pct(lat, .99), 4), "mean_ms": round(statistics.fmean(lat), 4),
            "throughput_per_s": round(1000 / statistics.fmean(lat), 1)}


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1e6 if platform.system() == "Darwin" else usage / 1e3  # macOS: bytes, Linux: KB


def cold_start_seconds() -> float:
    """Thời gian trong một tiến trình MỚI: import + nạp reference/PSL + trích xuất URL đầu tiên."""
    code = ("import time; t=time.perf_counter(); "
            "from phishguard_vn.brand_features import extract_e2_features; "
            "extract_e2_features('https://vietcombank-login.top/verify'); "
            "print(time.perf_counter()-t)")
    out = subprocess.check_output([sys.executable, "-c", code], env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]))}, text=True)
    return float(out.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "data/interim/core_gold_silver.csv")
    ap.add_argument("--train", type=Path, default=ROOT / "data/splits/url_train.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "reports/tables/05_feature_benchmark.json")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mem-sample", type=int, default=2000)
    args = ap.parse_args()

    train_ids = set(pd.read_csv(args.train, usecols=["id"])["id"])
    frame = pd.read_csv(args.input, usecols=["id", "url"])
    urls = (frame[frame["id"].isin(train_ids)]["url"].dropna()
            .sample(min(args.n, len(frame)), random_state=args.seed).tolist())
    print(f"[mẫu] {len(urls)} URL train (seed {args.seed})")

    cold = cold_start_seconds()
    ref = load_reference()
    for u in urls[:200]:      # khởi động trước (nạp PSL, import); cache lỗi gõ được xóa trước mỗi giai đoạn
        extract_e2_features(u)
    parsed_all = [parse_url(u) for u in urls]
    result = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "reference_sha256": ref.sha256,
        "n_urls": len(urls),
        "cold_start_s_new_process": round(cold, 3),
        "stages": {
            "parse_url": time_stage(parse_url, urls),
            "lexical_e1_from_parsed": time_stage(extract_features_from_parsed, parsed_all),
            "brand_from_parsed": time_stage(lambda p: extract_brand_features_from_parsed(p, ref), parsed_all),
            "e2_total_from_raw_url": time_stage(extract_e2_features, urls),
        },
    }
    rss_before = rss_mb()
    _osa_distance.cache_clear()
    tracemalloc.start()
    for u in urls[: args.mem_sample]:
        extract_e2_features(u)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result["memory"] = {"python_heap_peak_mb_during_extraction": round(peak / 1e6, 2),
                        "process_max_rss_mb_before": round(rss_before, 1), "process_max_rss_mb_after": round(rss_mb(), 1),
                        "note": "ru_maxrss là đỉnh toàn tiến trình (gồm pandas, đọc CSV), không phải riêng extractor"}
    result["environment"] = {"python": platform.python_version(), "platform": platform.platform(),
                             "machine": platform.machine(), "cpu_count": os.cpu_count(),
                             "tldextract": url_parser.TLDEXTRACT_VERSION}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"-> đã ghi {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())