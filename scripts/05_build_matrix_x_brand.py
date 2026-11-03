#!/usr/bin/env python
"""Xuất X E2 (id + 12 lexical E1 + 8 brand features) kèm manifest để bàn giao.

Chạy từ thư mục gốc dự án, với .venv đã bật:
    python scripts/05_build_matrix_x_brand.py                        # toàn core (draft, chấp nhận reference còn draft)
    python scripts/05_build_matrix_x_brand.py --partition trainval   # CHỈ Train + Validation; không đọc, không xử lý Test
    python scripts/05_build_matrix_x_brand.py --freeze               # bản chốt: reference 100% verified, git sạch

Đầu ra (data/interim/, đã bị .gitignore), hậu tố _trainval khi dùng --partition trainval:
    05_matrix_X_brand[_trainval].csv            id + 20 features, chỉ các dòng parse hợp lệ
    05_excluded_rows[_trainval].csv             id, error_reason, url của dòng bị loại
    05_matrix_X_brand[_trainval].manifest.json  version, thứ tự cột, hash nguồn/reference/dictionary, số dòng theo split
Script chỉ đọc cột `id`, `url`: nhãn/source/tier/split không thể lọt vào X.
Chế độ trainval lọc theo id TRƯỚC khi tính feature, và không mở url_test.csv.
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


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git_output(*cmd: str) -> str | None:
    try:
        return subprocess.check_output(["git", *cmd], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def ids_sha256(ids: pd.Series) -> str:
    return hashlib.sha256("\n".join(sorted(map(str, ids))).encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "interim" / "core_gold_silver.csv")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "interim")
    ap.add_argument("--e1-matrix", type=Path, default=ROOT / "data" / "interim" / "03_matrix_X_features.csv")
    ap.add_argument("--splits-dir", type=Path, default=ROOT / "data" / "splits")
    ap.add_argument("--partition", choices=["all", "trainval"], default="all")
    ap.add_argument("--brand-dictionary", type=Path, default=ROOT / "reports/templates/brand_feature_dictionary.csv")
    ap.add_argument("--e1-dictionary", type=Path, default=ROOT / "reports/templates/feature_dictionary.csv")
    ap.add_argument("--freeze", action="store_true",
                    help="từ chối chạy nếu reference chưa verified/thiếu provenance hoặc git còn thay đổi")
    args = ap.parse_args()

    ref = load_reference()
    print(f"[reference] {ref.summary()}")
    dirty = bool(git_output("status", "--porcelain"))
    if args.freeze:
        problems = []
        if not ref.is_fully_verified:
            problems.append("reference chưa 100% verified hoặc thiếu source_accessed/source_url")
        if dirty:
            problems.append("git còn thay đổi chưa commit")
        if problems:
            print("LỖI: --freeze yêu cầu: " + "; ".join(problems), file=sys.stderr)
            return 2

    if not args.input.is_file():
        print(f"LỖI: không thấy {args.input}. Truyền --input hoặc chạy notebook 01 để tạo file.", file=sys.stderr)
        return 2
    frame = pd.read_csv(args.input, usecols=["id", "url"])  # cố ý KHÔNG đọc cột nhãn/source/split
    assert frame["id"].notna().all(), "có id thiếu"
    assert frame["id"].is_unique, "id trùng trong đầu vào"
    print(f"[input] {len(frame)} dòng từ {args.input.name}")

    split_of: dict[str, str] = {}
    splits_sha: dict[str, str | None] = {}
    suffix = ""
    if args.partition == "trainval":
        suffix = "_trainval"
        for name in ("train", "val"):  # CỐ Ý không mở url_test.csv
            path = args.splits_dir / f"url_{name}.csv"
            if not path.is_file():
                print(f"LỖI: không thấy {path}. Truyền --splits-dir.", file=sys.stderr)
                return 2
            splits_sha[f"url_{name}.csv"] = sha256_file(path)
            for rid in pd.read_csv(path, usecols=["id"])["id"]:
                if split_of.setdefault(rid, name) != name:
                    print(f"LỖI: id {rid} nằm ở cả train và val", file=sys.stderr)
                    return 1
        frame = frame[frame["id"].isin(split_of)].reset_index(drop=True)
        print(f"[partition] trainval: giữ {len(frame)} dòng (Test bị loại trước khi tính feature)")

    table = build_e2_feature_table(frame, ref)
    ok = table["is_valid"].astype(bool)
    matrix = table.loc[ok, ["id", *E2_FEATURES]].copy()
    excluded = (table.loc[~ok, ["id", "error_reason"]].merge(frame[["id", "url"]], on="id", how="left"))

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
    if not set(matrix["id"]).isdisjoint(excluded["id"]):
        problems.append("id vừa nằm trong X vừa bị loại")

    e1_checked = False
    if args.e1_matrix.is_file():  # E2 phải cùng tập dòng và cùng 12 cột E1 với E1 (trên các id đang xét)
        e1 = pd.read_csv(args.e1_matrix)
        e1 = e1[e1["id"].isin(set(frame["id"]))]
        if set(e1["id"]) != set(matrix["id"]):
            problems.append(f"tập id khác E1 (E1={len(e1)}, E2={len(matrix)})")
        else:
            a = e1.set_index("id")[list(CANDIDATE_FEATURES)].sort_index()
            b = matrix.set_index("id")[list(CANDIDATE_FEATURES)].sort_index()
            if not np.allclose(a.to_numpy(float), b.to_numpy(float), rtol=0, atol=1e-9):
                problems.append("12 cột E1 trong E2 khác 03_matrix_X_features.csv (chạy lại notebook 03?)")
            else:
                e1_checked = True
    else:
        print(f"[cảnh báo] không thấy {args.e1_matrix.name}: bỏ qua kiểm tra E1 parity")

    rows_by_split = None
    if split_of:
        rows_by_split = {
            name: {"x": int(matrix["id"].map(split_of).eq(name).sum()),
                   "excluded": int(excluded["id"].map(split_of).eq(name).sum())}
            for name in ("train", "val")
        }
    const_cols = [c for c in E2_FEATURES if matrix[c].nunique() <= 1]
    nonzero = (matrix[list(BRAND_FEATURES)] != 0).mean().mul(100).round(2)
    print(f"[X] {len(matrix)} dòng | loại {len(excluded)} | cột hằng: {const_cols or 'không có'}")
    if rows_by_split:
        print(f"[X] theo split: {rows_by_split}")
    print("[brand] % dòng khác 0 (không dùng nhãn):")
    print(nonzero.to_string())
    if problems:
        print("LỖI: " + "; ".join(problems), file=sys.stderr)
        return 1

    # --- ghi file ----------------------------------------------------------------------------
    args.out_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(args.out_dir / f"05_matrix_X_brand{suffix}.csv", index=False)
    excluded.to_csv(args.out_dir / f"05_excluded_rows{suffix}.csv", index=False)
    manifest = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "frozen": bool(args.freeze),
        "partition": args.partition,
        "test_excluded_from_this_artifact": args.partition == "trainval",
        "columns": ["id", *E2_FEATURES],
        "e1_columns": list(CANDIDATE_FEATURES),
        "brand_columns": list(BRAND_FEATURES),
        "e1_columns_verified_identical_to_e1_matrix": e1_checked,
        "rows_x": int(len(matrix)),
        "rows_excluded": int(len(excluded)),
        "rows_by_split": rows_by_split,
        "ids_sha256_x": ids_sha256(matrix["id"]),
        "ids_sha256_excluded": ids_sha256(excluded["id"]),
        "input_file": args.input.name,
        "input_sha256": sha256_file(args.input),
        "splits_sha256": splits_sha or None,
        "brand_reference": ref.summary(),
        "brand_feature_dictionary_sha256": sha256_file(args.brand_dictionary),
        "e1_feature_dictionary_sha256": sha256_file(args.e1_dictionary),
        "tldextract_version": url_parser.TLDEXTRACT_VERSION,
        "python": platform.python_version(),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_dirty": dirty,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (args.out_dir / f"05_matrix_X_brand{suffix}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> đã ghi 05_matrix_X_brand{suffix}.csv, 05_excluded_rows{suffix}.csv, manifest ({FEATURE_SCHEMA_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())