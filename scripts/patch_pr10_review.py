#!/usr/bin/env python
"""Vá MỘT LẦN các thay đổi theo review PR #10 (KHÔNG commit file này).

    python scripts/patch_pr10_review.py --dry-run     # chỉ kiểm tra các điểm neo
    python scripts/patch_pr10_review.py               # áp dụng

Sửa src/phishguard_vn/brand_features.py bằng thay thế chuỗi chính xác (giữ nguyên các chỉnh sửa khác của bạn, vd. dòng version):
  1. fully_verified kiểm TOÀN BỘ provenance: source_url, source_url_2, source_accessed (YYYY-MM-DD, không ở tương lai),
     verified_by, https, hai nguồn khác nhau, và notes không còn nội dung chờ xác minh;
  2. official_suffixes chỉ miễn trừ mismatch khi brand khớp DUY NHẤT ở subdomain (khớp ở nhãn domain hoặc path vẫn bị cờ).
Cũng cập nhật câu mô tả trong docs/mobile_feature_contract.md và reports/templates/brand_feature_dictionary.csv nếu tìm thấy.
Sau khi vá: nhớ sinh lại parity, manifest, và chạy toàn bộ test.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src/phishguard_vn/brand_features.py"

EDITS = [
    ("import",
     "from dataclasses import dataclass\n",
     "from dataclasses import dataclass\nfrom datetime import date\n"),
    ("constants",
     "@dataclass(frozen=True)\nclass BrandReference:",
     '''# Provenance bắt buộc cho mọi brand status=verified (kiểm khi nạp reference và khi --freeze).
REQUIRED_PROVENANCE = ("source_url", "source_url_2", "source_accessed", "verified_by")
# Cụm cố định của các mẫu ghi chú chờ xác minh; so khớp PHÂN BIỆT hoa/thường để không bắt nhầm lời văn bình thường
# (vd. "khớp bản nháp" trong ghi chú xác minh là hợp lệ).
PENDING_MARKERS = ("ỨNG VIÊN", "CHƯA TRA", "BẢN NHÁP:", "(AI tra", "Bạn cần", "cần người kiểm tra", "TODO",
                   "needs_fix:", "unverifiable:")


@dataclass(frozen=True)
class BrandReference:'''),
    ("fields+property",
     '''    n_missing_source_accessed: int
    n_missing_source_url: int

    @property
    def is_fully_verified(self) -> bool:
        """Điều kiện để freeze E2 v1: mọi brand verified và đủ provenance."""
        counts = dict(self.statuses)
        return (set(counts) == {"verified"} and self.n_missing_source_accessed == 0
                and self.n_missing_source_url == 0)''',
     '''    n_missing_source_accessed: int
    n_missing_source_url: int
    provenance_issues: tuple[str, ...] = ()

    @property
    def is_fully_verified(self) -> bool:
        """Điều kiện để freeze E2 v1: mọi brand verified, đủ provenance và không còn ghi chú chờ xác minh."""
        counts = dict(self.statuses)
        return (set(counts) == {"verified"} and self.n_missing_source_accessed == 0
                and self.n_missing_source_url == 0 and not self.provenance_issues)'''),
    ("summary",
     '            "fully_verified": self.is_fully_verified,\n',
     '            "fully_verified": self.is_fully_verified,\n'
     '            "n_provenance_issues": len(self.provenance_issues),\n'
     '            "provenance_issues": list(self.provenance_issues[:20]),\n'),
    ("issues function",
     "@lru_cache(maxsize=4)\ndef load_reference",
     '''def _provenance_issues(rows: list[dict]) -> list[str]:
    """Liệt kê mọi chỗ provenance của brand chưa đạt chuẩn verified."""
    issues: list[str] = []
    for row in rows:
        bid = (row.get("brand_id") or "").strip()
        status = (row.get("status") or "").strip()
        if status != "verified":
            issues.append(f"{bid}: status={status!r} (chưa verified)")
            continue
        for col in REQUIRED_PROVENANCE:
            if not (row.get(col) or "").strip():
                issues.append(f"{bid}: thiếu {col}")
        urls = [(row.get(c) or "").strip() for c in ("source_url", "source_url_2")]
        for col, url in zip(("source_url", "source_url_2"), urls):
            if url and not url.startswith("https://"):
                issues.append(f"{bid}: {col} phải bắt đầu bằng https://")
        if urls[0] and urls[0] == urls[1]:
            issues.append(f"{bid}: source_url và source_url_2 trùng nhau")
        accessed = (row.get("source_accessed") or "").strip()
        if accessed:
            try:
                if date.fromisoformat(accessed) > date.today():
                    issues.append(f"{bid}: source_accessed ở tương lai")
            except ValueError:
                issues.append(f"{bid}: source_accessed phải dạng YYYY-MM-DD")
        notes = row.get("notes") or ""
        for marker in PENDING_MARKERS:
            if marker in notes:
                issues.append(f"{bid}: notes còn nội dung chờ xác minh ({marker})")
                break
    return issues


@lru_cache(maxsize=4)
def load_reference'''),
    ("pass issues",
     '        n_missing_source_url=sum(1 for r in rows if not r["source_url"].strip()),\n    )',
     '        n_missing_source_url=sum(1 for r in rows if not r["source_url"].strip()),\n'
     '        provenance_issues=tuple(_provenance_issues(rows)),\n    )'),
    ("suffix narrowing",
     "        brand_suffix_ok = bool(reg and brand.official_suffixes and reg.endswith(brand.official_suffixes))\n",
     '''        # official_suffixes chỉ miễn trừ khi brand khớp DUY NHẤT ở subdomain (vd. dichvucong.<đơn vị>.gov.vn);
        # khớp ở nhãn domain đăng ký hoặc ở path vẫn bị gán mismatch.
        brand_suffix_ok = bool(reg and brand.official_suffixes and reg.endswith(brand.official_suffixes)
                               and hit_s and not hit_d and not hit_p)
'''),
]

DOC_OLD = "và không thuộc `official_suffixes` của chính brand đó (cột tùy chọn, mặc định rỗng)"
DOC_NEW = ("và không thuộc ngoại lệ `official_suffixes` của chính brand đó (cột tùy chọn, mặc định rỗng; chỉ miễn trừ khi "
           "brand khớp DUY NHẤT ở subdomain và registrable domain kết thúc bằng suffix đó)")
DICT_NOTE = (" Ngoại lệ theo từng brand: nếu brand có official_suffixes và registrable_domain kết thúc bằng suffix đó thì KHÔNG tính "
             "mismatch CHỈ KHI brand khớp duy nhất ở subdomain (khớp ở nhãn domain đăng ký hoặc path vẫn là mismatch).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    text = TARGET.read_text(encoding="utf-8")
    if "_provenance_issues" in text:
        print("Đã vá trước đó (thấy _provenance_issues). Không làm gì.")
        return 0
    bad = [name for name, old, _ in EDITS if text.count(old) != 1]
    if bad:
        print(f"LỖI: không tìm thấy điểm neo duy nhất cho: {bad}. File của bạn đã bị sửa khác bản mình dựa vào; "
              "không ghi gì. Gửi mình đoạn code tương ứng.", file=sys.stderr)
        return 1
    for _, old, new in EDITS:
        text = text.replace(old, new)
    print(f"[ok] {len(EDITS)} điểm neo khớp trong {TARGET.relative_to(ROOT)}")
    if args.dry_run:
        print("(dry-run: chưa ghi)")
        return 0
    TARGET.write_text(text, encoding="utf-8")

    doc = ROOT / "docs/mobile_feature_contract.md"
    if doc.is_file() and DOC_OLD in doc.read_text(encoding="utf-8"):
        doc.write_text(doc.read_text(encoding="utf-8").replace(DOC_OLD, DOC_NEW), encoding="utf-8")
        print(f"[ok] cập nhật {doc.relative_to(ROOT)}")
    else:
        print(f"[bỏ qua] không thấy câu cần sửa trong docs/mobile_feature_contract.md: tự sửa mục brand_domain_mismatch")
    dictionary = ROOT / "reports/templates/brand_feature_dictionary.csv"
    if dictionary.is_file():
        import pandas as pd
        d = pd.read_csv(dictionary, dtype=str, keep_default_na=False)
        mask = d["feature"] == "brand_domain_mismatch"
        if mask.any() and "official_suffixes" not in d.loc[mask, "formula"].iloc[0]:
            d.loc[mask, "formula"] = d.loc[mask, "formula"] + DICT_NOTE
            d.to_csv(dictionary, index=False, lineterminator="\n")
            print(f"[ok] cập nhật {dictionary.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
