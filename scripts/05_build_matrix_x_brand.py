#!/usr/bin/env python
"""Xuất X E2 (id + 12 lexical E1 + 8 brand features) để bàn giao cho Phúc.

Chạy từ thư mục gốc dự án, với .venv đã bật:
    python scripts/05_build_matrix_x_brand.py                # bản nháp (chấp nhận reference status=draft)
    python scripts/05_build_matrix_x_brand.py --freeze       # bản chốt: reference phải 100% verified

Đầu ra (data/interim/, đã bị .gitignore):
    05_matrix_X_brand.csv            id + 20 features, chỉ các dòng parse hợp lệ
    05_excluded_rows.csv             id, error_reason, url của dòng bị loại (phải trùng 03_excluded_rows.csv)
    05_matrix_X_brand.manifest.json  version schema, hash nguồn/reference, thứ tự cột, số dòng
Script chỉ đọc hai cột `id`, `url`: nhãn/source/tier/split không thể lọt vào X.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn import url_parser  # noqa: E402
from phishguard_vn.brand_features import (  # noqa: E402
    BRAND_FEATURES, E2_FEATURES, FEATURE_SCHEMA_VERSION, build_e2_feature_table, load_reference,
)
from phishguard_vn.features import CANDIDATE_FEATURES  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "interim" / "core_gold_silver.csv")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "interim")
    ap.add_argument("--e1-matrix", type=Path, default=ROOT / "data" / "interim" / "03_matrix_X_features.csv")
    ap.add_argument("--freeze", action="store_true", help="từ chối chạy nếu reference còn status != verified")
    args = ap.parse_args()

    ref = load_reference()
    statuses = dict(ref.statuses)
    print(f"[reference] {len(ref.brands)} brand | status={statuses} | sha256={ref.sha256[:12]}")
    if args.freeze and set(statuses) != {"verified"}:
        print("LỖI: --freeze yêu cầu mọi brand ở status=verified.", file=sys.stderr)
        return 2

    if not args.input.is_file():
        print(f"LỖI: không thấy {args.input}. Truyền --input hoặc chạy notebook 01 để tạo file.", file=sys.stderr)
        return 2
    frame = pd.read_csv(args.input, usecols=["id", "url"])  # cố ý KHÔNG đọc cột nhãn/source/split
    assert frame["id"].notna().all(), "có id thiếu"
    assert frame["id"].is_unique, "id trùng trong đầu vào"
    print(f"[input] {len(frame)} dòng từ {args.input.name}")

    table = build_e2_feature_table(frame, ref)
    ok = table["is_valid"].astype(bool)
    matrix = table.loc[ok, ["id", *E2_FEATURES]].copy()
    excluded = (table.loc[~ok, ["id", "error_reason"]]
                .merge(frame[["id", "url"]], on="id", how="left"))

    # --- kiểm tra hợp đồng dữ liệu -------------------------------------------------------
    problems: list[str] = []
    if list(matrix.columns) != ["id", *E2_FEATURES]:
        problems.append("sai cột/thứ tự của X")
    if len(matrix) + len(excluded) != len(frame):
        problems.append("số dòng X + excluded != đầu vào")
    values = matrix[list(E2_FEATURES)].to_numpy(dtype=float)
    if np.isnan(values).any() or np.isinf(values).any():
        problems.append("X có NaN/Inf")
    if matrix["id"].duplicated().any():
        problems.append("id trùng trong X")

    if args.e1_matrix.is_file():  # E2 phải cùng tập dòng và cùng 12 cột E1 với E1
        e1 = pd.read_csv(args.e1_matrix)
        if set(e1["id"]) != set(matrix["id"]):
            problems.append(f"tập id khác E1 (E1={len(e1)}, E2={len(matrix)})")
        else:
            a = e1.set_index("id")[list(CANDIDATE_FEATURES)].sort_index()
            b = matrix.set_index("id")[list(CANDIDATE_FEATURES)].sort_index()
            if not np.allclose(a.to_numpy(float), b.to_numpy(float), rtol=0, atol=1e-9):
                problems.append("12 cột E1 trong E2 khác 03_matrix_X_features.csv (chạy lại notebook 03?)")
    else:
        print(f"[cảnh báo] không thấy {args.e1_matrix.name}: bỏ qua kiểm tra E1 parity")

    const_cols = [c for c in E2_FEATURES if matrix[c].nunique() <= 1]
    nonzero = (matrix[list(BRAND_FEATURES)] != 0).mean().mul(100).round(2)
    print(f"[X] {len(matrix)} dòng | loại {len(excluded)} | cột hằng: {const_cols or 'không có'}")
    print("[brand] % dòng khác 0 (không dùng nhãn):")
    print(nonzero.to_string())
    if problems:
        print("LỖI: " + "; ".join(problems), file=sys.stderr)
        return 1

    # --- ghi file ----------------------------------------------------------------------------
    args.out_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(args.out_dir / "05_matrix_X_brand.csv", index=False)
    excluded.to_csv(args.out_dir / "05_excluded_rows.csv", index=False)
    manifest = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "frozen": bool(args.freeze),
        "columns": ["id", *E2_FEATURES],
        "e1_columns": list(CANDIDATE_FEATURES),
        "brand_columns": list(BRAND_FEATURES),
        "rows_x": int(len(matrix)),
        "rows_excluded": int(len(excluded)),
        "input_file": args.input.name,
        "input_sha256": sha256_file(args.input),
        "brand_reference_sha256": ref.sha256,
        "brand_reference_status": statuses,
        "tldextract_version": url_parser.TLDEXTRACT_VERSION,
        "python": platform.python_version(),
        "git_commit": git_commit(),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (args.out_dir / "05_matrix_X_brand.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> đã ghi 05_matrix_X_brand.csv, 05_excluded_rows.csv, manifest ({FEATURE_SCHEMA_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())