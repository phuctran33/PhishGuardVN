#!/usr/bin/env python
"""Kiểm tra các artifact E2 đã commit có NHẤT QUÁN với mã, reference và tài liệu hiện tại không.

    python scripts/05_verify_e2_artifacts.py
    python scripts/05_verify_e2_artifacts.py --manifest reports/tables/05_matrix_X_brand_v1.manifest.json

Kiểm tra: reference fully_verified (đủ provenance); từng manifest (version, frozen, git sạch, thứ tự cột, hash reference và
hai dictionary, phiên bản tldextract, E1 giữ nguyên, Test không nằm trong bản trainval); file parity khớp mã (và sinh lại
được từ mã); version trong dictionary/contract; mã nguồn không đổi kể từ commit ghi trong manifest (ngoài artifact).
Thoát mã 1 nếu có mục FAIL. Chạy sau khi đã commit manifest; chạy lại mỗi khi đổi mã, reference, dictionary hoặc version.

Thứ tự freeze đúng: (1) sửa mã/reference/dictionary/test, (2) cập nhật train_check của dictionary, (3) commit,
(4) chạy build --freeze (cả all và trainval) + parity, (5) commit manifest/parity, (6) chạy script này.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn import url_parser  # noqa: E402
from phishguard_vn.brand_features import (  # noqa: E402
    BRAND_FEATURES, E2_FEATURES, FEATURE_SCHEMA_VERSION, REFERENCE_PATH, load_reference,
)
from phishguard_vn.features import CANDIDATE_FEATURES  # noqa: E402

ALLOWED_CHANGED_AFTER_FREEZE = ("reports/tables/", "docs/mobile_parity_cases.json")
results: list[tuple[bool, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git(*cmd: str) -> str | None:
    try:
        return subprocess.check_output(["git", *cmd], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def verify_manifest(path: Path, ref, dict_sha: str | None, e1_dict_sha: str | None) -> None:
    label = path.name
    m = json.loads(path.read_text(encoding="utf-8"))
    check(m.get("feature_schema_version") == FEATURE_SCHEMA_VERSION, f"{label}: schema_version = {FEATURE_SCHEMA_VERSION}",
          str(m.get("feature_schema_version")))
    check(m.get("frozen") is True, f"{label}: frozen")
    check(m.get("git_dirty") is False, f"{label}: tạo khi git sạch")
    check(m.get("columns") == ["id", *E2_FEATURES], f"{label}: thứ tự cột")
    check(m.get("e1_columns") == list(CANDIDATE_FEATURES) and m.get("brand_columns") == list(BRAND_FEATURES),
          f"{label}: nhóm cột E1/brand")
    check(m.get("e1_columns_verified_identical_to_e1_matrix") is True, f"{label}: 12 cột E1 khớp ma trận E1")
    br = m.get("brand_reference", {})
    check(br.get("sha256") == ref.sha256, f"{label}: hash reference khớp reference hiện tại")
    check(br.get("fully_verified") is True, f"{label}: reference lúc sinh đã fully_verified")
    check(m.get("brand_feature_dictionary_sha256") == dict_sha, f"{label}: hash brand dictionary khớp")
    check(m.get("e1_feature_dictionary_sha256") == e1_dict_sha, f"{label}: hash E1 dictionary khớp")
    check(m.get("tldextract_version") == url_parser.TLDEXTRACT_VERSION, f"{label}: phiên bản tldextract",
          f"{m.get('tldextract_version')} vs {url_parser.TLDEXTRACT_VERSION}")
    if m.get("partition") == "trainval":
        check(m.get("test_excluded_from_this_artifact") is True, f"{label}: Test bị loại")
        check(set((m.get("rows_by_split") or {})) == {"train", "val"}, f"{label}: chỉ có split train và val")
        check(set(m.get("splits_sha256") or {}) == {"url_train.csv", "url_val.csv"}, f"{label}: không ghi hash url_test.csv")
    commit = m.get("git_commit")
    if commit and git("cat-file", "-e", f"{commit}^{{commit}}") is not None:
        changed = (git("diff", "--name-only", commit, "HEAD") or "").splitlines()
        stale = [p for p in changed if not p.startswith(ALLOWED_CHANGED_AFTER_FREEZE)]
        check(not stale, f"{label}: mã/tài liệu không đổi kể từ commit freeze {commit[:8]}", ", ".join(stale[:5]))
    else:
        check(False, f"{label}: tìm thấy commit freeze trong git", str(commit))
    local = ROOT / "data/interim" / ("05_matrix_X_brand_trainval.csv" if m.get("partition") == "trainval" else "05_matrix_X_brand.csv")
    if local.is_file():
        ids = pd.read_csv(local, usecols=["id"])["id"]
        same = len(ids) == m.get("rows_x") and hashlib.sha256("\n".join(sorted(map(str, ids))).encode()).hexdigest() == m.get("ids_sha256_x")
        check(same, f"{label}: ma trận cục bộ khớp manifest (số dòng và hash id)")
    else:
        print(f"SKIP  {label}: không có ma trận cục bộ để đối chiếu ({local.name})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, action="append",
                    help="mặc định: các file reports/tables/05_matrix_X_brand*_v1.manifest.json")
    ap.add_argument("--parity", type=Path, default=ROOT / "docs/mobile_parity_cases.json")
    ap.add_argument("--brand-dictionary", type=Path, default=ROOT / "reports/templates/brand_feature_dictionary.csv")
    ap.add_argument("--e1-dictionary", type=Path, default=ROOT / "reports/templates/feature_dictionary.csv")
    ap.add_argument("--contract", type=Path, default=ROOT / "docs/mobile_feature_contract.md")
    args = ap.parse_args()

    ref = load_reference(REFERENCE_PATH)
    print(f"[reference] {ref.summary()}")
    check(ref.is_fully_verified, "reference fully_verified (đủ provenance, notes sạch)",
          "; ".join(getattr(ref, "provenance_issues", ())[:3]))
    check(not (git("status", "--porcelain") or ""), "git sạch")

    dict_sha, e1_dict_sha = sha256(args.brand_dictionary), sha256(args.e1_dictionary)
    if args.brand_dictionary.is_file():
        versions = set(pd.read_csv(args.brand_dictionary, dtype=str)["schema_version"])
        check(versions == {FEATURE_SCHEMA_VERSION}, "brand dictionary: cột schema_version = version hiện tại", str(versions))
    check(args.contract.is_file() and FEATURE_SCHEMA_VERSION in args.contract.read_text(encoding="utf-8"),
          "mobile contract: có ghi version hiện tại")

    manifests = args.manifest or sorted((ROOT / "reports/tables").glob("05_matrix_X_brand*_v1.manifest.json"))
    check(bool(manifests), "có manifest E2 đã commit")
    for path in manifests:
        verify_manifest(path, ref, dict_sha, e1_dict_sha)

    if args.parity.is_file():
        parity = json.loads(args.parity.read_text(encoding="utf-8"))
        check(parity.get("schema_version") == FEATURE_SCHEMA_VERSION, "parity: schema_version khớp")
        check((parity.get("brand_reference") or {}).get("sha256") == ref.sha256, "parity: hash reference khớp")
        check(parity.get("tldextract_version") == url_parser.TLDEXTRACT_VERSION, "parity: phiên bản tldextract khớp")
        spec = importlib.util.spec_from_file_location("parity_builder", ROOT / "scripts/05_make_parity_vectors.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fresh = json.loads(json.dumps(module.build(), ensure_ascii=False))
        check(fresh == parity, "parity: sinh lại từ mã cho kết quả y hệt (đồng thời qua kiểm tra giá trị tính tay)")
    else:
        check(False, "có file parity", str(args.parity))

    failed = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} mục đạt" + (f"; KHÔNG ĐẠT: {len(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
