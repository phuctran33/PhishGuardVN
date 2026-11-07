#!/usr/bin/env python
"""Bảng xác minh brand reference (Y5.1): xuất bảng điền tay, rồi áp dụng lại vào reference có kiểm tra.

    python scripts/05_reference_worksheet.py export              # tạo reports/tables/05_brand_reference_worksheet.csv
    python scripts/05_reference_worksheet.py status              # tóm tắt trạng thái reference hiện tại
    python scripts/05_reference_worksheet.py apply --dry-run     # xem sẽ đổi gì, chưa ghi
    python scripts/05_reference_worksheet.py apply               # ghi vào reference sau khi kiểm tra hợp lệ

Cách điền (mỗi dòng một brand), cột verdict:
    verified      đã xác minh: BẮT BUỘC điền confirmed_domains, source_url, source_url_2, source_accessed (YYYY-MM-DD), verified_by
    needs_fix     sai/thiếu so với bản nháp: ghi lý do ở note, reference giữ status draft
    unverifiable  không tìm được nguồn đáng tin: ghi note, giữ draft
    (để trống)    chưa xét: không đổi gì
Brand MỚI: thêm một dòng với brand_id chưa có, điền canonical_name, aliases, sector và verdict=verified như trên.
source_url = trang CHÍNH THỨC xác nhận domain; source_url_2 = nguồn độc lập thứ hai (cơ quan quản lý/danh bạ chính thức).
Không dùng nguồn từ dataset (tinnhiemmang, impersonated_org, nhãn) để xác minh. Không mở URL trong dataset.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn.brand_features import REFERENCE_PATH, load_reference  # noqa: E402

BASE_COLS = ["brand_id", "canonical_name", "aliases", "official_domains", "sector", "source_url",
             "source_accessed", "status", "notes"]
EXTRA_COLS = ["official_suffixes", "typo_ignore_tokens", "source_url_2", "verified_by"]
SHEET_FILL = ["confirmed_domains", "source_url", "source_url_2", "source_accessed", "verified_by",
              "official_suffixes", "typo_ignore_tokens", "verdict", "note"]
SHEET_COLS = ["brand_id", "canonical_name", "aliases", "current_official_domains", "sector", *SHEET_FILL]
REQUIRED_FOR_VERIFIED = ["confirmed_domains", "source_url", "source_url_2", "source_accessed", "verified_by"]


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_verified(row: dict) -> list[str]:
    errors = [f"thiếu {c}" for c in REQUIRED_FOR_VERIFIED if not (row.get(c) or "").strip()]
    for c in ("source_url", "source_url_2"):
        if (row.get(c) or "").strip() and not row[c].strip().startswith("https://"):
            errors.append(f"{c} phải bắt đầu bằng https://")
    if (row.get("source_accessed") or "").strip():
        try:
            if date.fromisoformat(row["source_accessed"].strip()) > date.today():
                errors.append("source_accessed ở tương lai")
        except ValueError:
            errors.append("source_accessed phải dạng YYYY-MM-DD")
    if (row.get("source_url") or "").strip() == (row.get("source_url_2") or "").strip() != "":
        errors.append("source_url và source_url_2 phải là hai nguồn khác nhau")
    return errors


def cmd_export(args) -> int:
    rows = read_csv(args.reference)
    sheet = [{"brand_id": r["brand_id"], "canonical_name": r["canonical_name"], "aliases": r["aliases"],
              "current_official_domains": r["official_domains"], "sector": r["sector"]} for r in rows]
    write_csv(args.sheet, SHEET_COLS, sheet)
    print(f"-> đã ghi {args.sheet} ({len(sheet)} brand). Điền các cột {SHEET_FILL}")
    return 0


def cmd_status(args) -> int:
    ref = load_reference(args.reference)
    print(ref.summary())
    return 0


def cmd_apply(args) -> int:
    ref_rows = read_csv(args.reference)
    cols = BASE_COLS + [c for c in EXTRA_COLS if c not in BASE_COLS]
    by_id = {r["brand_id"]: {**{c: "" for c in cols}, **r} for r in ref_rows}
    errors, changed, added, kept = [], [], [], []
    for sheet_row in read_csv(args.sheet):
        bid, verdict = sheet_row["brand_id"].strip(), (sheet_row.get("verdict") or "").strip().lower()
        if not verdict:
            continue
        if verdict not in {"verified", "needs_fix", "unverifiable"}:
            errors.append(f"{bid}: verdict không hợp lệ {verdict!r}")
            continue
        is_new = bid not in by_id
        row = by_id.setdefault(bid, {c: "" for c in cols})
        note = (sheet_row.get("note") or "").strip()
        if verdict == "verified":
            problems = validate_verified(sheet_row)
            if is_new:
                problems += [f"thiếu {c}" for c in ("canonical_name", "sector") if not (sheet_row.get(c) or "").strip()]
            if problems:
                errors.append(f"{bid}: " + "; ".join(problems))
                if is_new:
                    del by_id[bid]
                continue
            if is_new:
                row.update(brand_id=bid, canonical_name=sheet_row["canonical_name"].strip(),
                           aliases=(sheet_row.get("aliases") or "").strip(), sector=sheet_row["sector"].strip())
            row.update(official_domains=sheet_row["confirmed_domains"].strip(), source_url=sheet_row["source_url"].strip(),
                       source_url_2=sheet_row["source_url_2"].strip(), source_accessed=sheet_row["source_accessed"].strip(),
                       verified_by=sheet_row["verified_by"].strip(), status="verified", notes=note or "verified")
            for c in ("official_suffixes", "typo_ignore_tokens"):
                if (sheet_row.get(c) or "").strip():
                    row[c] = sheet_row[c].strip()
            (added if is_new else changed).append(bid)
        else:
            if is_new:
                errors.append(f"{bid}: brand mới chỉ được thêm khi verdict=verified")
                del by_id[bid]
                continue
            row["notes"] = f"{verdict}: {note}" if note else verdict
            kept.append(bid)
    if errors:
        print("LỖI (không ghi gì):\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    out_rows = list(by_id.values())
    tmp = args.reference.with_suffix(".tmp.csv")
    write_csv(tmp, cols, out_rows)
    try:
        ref = load_reference(tmp)  # kiểm tra va chạm alias, STOPLIST, alias ngắn, official_suffixes
    except ValueError as exc:
        tmp.unlink()
        print(f"LỖI: reference sau khi sửa không hợp lệ: {exc}", file=sys.stderr)
        return 1
    print(f"[apply] verified/cập nhật: {len(changed)} | thêm mới: {len(added)} | giữ draft kèm ghi chú: {len(kept)}")
    print(f"[reference sau khi áp] {ref.summary()}")
    if args.dry_run:
        tmp.unlink()
        print("(dry-run: chưa ghi)")
        return 0
    tmp.replace(args.reference)
    print(f"-> đã ghi {args.reference}. Đổi hash reference: nhớ cập nhật version, sinh lại X E2 và parity.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "status", "apply"])
    ap.add_argument("--reference", type=Path, default=REFERENCE_PATH)
    ap.add_argument("--sheet", type=Path, default=ROOT / "reports/tables/05_brand_reference_worksheet.csv")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return {"export": cmd_export, "status": cmd_status, "apply": cmd_apply}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())