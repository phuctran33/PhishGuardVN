#!/usr/bin/env python
"""Rà soát TỪNG CA: URL .gov.vn/.edu.vn bị gán brand_domain_mismatch hoặc brand_typo_score > 0.

Chỉ dùng hàng TRAIN. Chạy từ thư mục gốc dự án:
    python scripts/05_audit_brand_matches.py
    python scripts/05_audit_brand_matches.py --suffixes .gov.vn .edu.vn --out reports/tables/05_gov_edu_brand_audit.csv

Đầu ra: một dòng cho mỗi lý do (rule, brand_id, key, text). Hai cột `verdict` và `note` để trống cho người rà soát:
    correct_flag             cờ đúng thiết kế (vd. brand ở subdomain của domain không liên quan)
    false_match              khớp sai (vd. địa danh/tên chung bị khớp với key brand)
    missing_official_domain  domain/subdomain hợp lệ nhưng chưa có trong official_domains của reference
Sau khi có verdict mới sửa reference (theo từng brand, có nguồn) hoặc quy tắc khớp, kèm regression test.
KHÔNG loại trừ cả .gov.vn/.edu.vn: mọi miễn trừ phải gắn với một brand và một nguồn xác minh.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn.brand_features import explain_brand_matches  # noqa: E402
from phishguard_vn.url_parser import parse_url  # noqa: E402

FLAG_RULES = {"brand_domain_mismatch", "brand_typo_score"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "data/interim/core_gold_silver.csv")
    ap.add_argument("--train", type=Path, default=ROOT / "data/splits/url_train.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "reports/tables/05_gov_edu_brand_audit.csv")
    ap.add_argument("--suffixes", nargs="+", default=[".gov.vn", ".edu.vn"])
    args = ap.parse_args()

    train_ids = set(pd.read_csv(args.train, usecols=["id"])["id"])
    frame = pd.read_csv(args.input, usecols=["id", "url"])  # không đọc nhãn
    frame = frame[frame["id"].isin(train_ids)]
    print(f"[audit] {len(frame)} URL thuộc train (chỉ train); suffix theo dõi: {args.suffixes}")

    rows, flagged_urls = [], 0
    for rid, url in zip(frame["id"], frame["url"]):
        parsed = parse_url(url if isinstance(url, str) else None)
        reg = parsed.registrable_domain
        if not (parsed.is_valid and reg and reg.endswith(tuple(args.suffixes))):
            continue
        _, events = explain_brand_matches(url)
        flags = [e for e in events if e["rule"] in FLAG_RULES]
        if not flags:
            continue
        flagged_urls += 1
        for e in events:
            if e["rule"] in FLAG_RULES or e["rule"].startswith(("brand_in_", "homoglyph")):
                rows.append({"id": rid, "url": url, "registrable_domain": reg, "subdomain": parsed.subdomain,
                             "rule": e["rule"], "brand_id": e["brand_id"], "key": e["key"], "text": e["text"],
                             "value": round(float(e["value"]), 4), "distance": e.get("distance", ""),
                             "verdict": "", "note": ""})
    out = pd.DataFrame(rows)
    print(f"[audit] {flagged_urls} URL bị cờ; {len(out)} dòng lý do")
    if out.empty:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"-> đã ghi {args.out}  (điền cột verdict/note)")
    flagged = out[out["rule"].isin(FLAG_RULES)]
    summary = (flagged.groupby(["rule", "brand_id", "key"]).agg(urls=("id", "nunique"), domains=("registrable_domain", "nunique"),
                                                                  ví_dụ=("registrable_domain", "first"))
               .reset_index().sort_values("urls", ascending=False))
    print("\n[tóm tắt theo (rule, brand, key)]")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())