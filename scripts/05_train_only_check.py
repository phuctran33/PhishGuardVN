#!/usr/bin/env python
"""Kiểm tra riêng trên TRAIN cho X E2 (theo yêu cầu review của Phúc).

Chạy từ thư mục gốc dự án:
    python scripts/05_train_only_check.py                       # chỉ in kết quả
    python scripts/05_train_only_check.py --write-dictionary    # ghi thêm train_check vào dictionary

Chỉ đọc cột `id` của url_train.csv (không đọc nhãn). Phần "bằng chứng v0.1" chỉ dùng hàng train.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn.brand_features import BRAND_FEATURES, E2_FEATURES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", type=Path, default=ROOT / "data/interim/05_matrix_X_brand.csv")
    ap.add_argument("--train", type=Path, default=ROOT / "data/splits/url_train.csv")
    ap.add_argument("--domains", type=Path, default=ROOT / "data/interim/03_registrable_domains.csv")
    ap.add_argument("--dictionary", type=Path, default=ROOT / "reports/templates/brand_feature_dictionary.csv")
    ap.add_argument("--write-dictionary", action="store_true")
    args = ap.parse_args()

    x = pd.read_csv(args.matrix)
    train_ids = set(pd.read_csv(args.train, usecols=["id"])["id"])
    in_train = x["id"].isin(train_ids)
    xt, rest = x[in_train], x[~in_train]
    print(f"[split] X={len(x)} | train={len(xt)} | ngoài train (val/test)={len(rest)}")

    cols = list(E2_FEATURES)
    const_train = [c for c in cols if xt[c].nunique() <= 1]
    const_all = [c for c in cols if x[c].nunique() <= 1]
    print(f"[const] hằng trên train: {const_train or 'không có'}")
    print(f"[const] hằng trên toàn X: {const_all or 'không có'}")
    for col in const_train:
        if col not in const_all:
            nonzero = int((rest[col] != 0).sum())
            print(f"        {col}: hằng trên train nhưng có {nonzero}/{len(rest)} dòng khác 0 ngoài train")

    rates = (xt[list(BRAND_FEATURES)] != 0).mean().mul(100).round(2)
    print("[brand] % dòng khác 0 trên train:")
    print(rates.to_string())

    if args.write_dictionary:
        d = pd.read_csv(args.dictionary)
        d["train_check"] = d["train_check"].astype(object)
        for i, name in enumerate(d["feature"]):
            if name not in xt.columns:
                continue
            nz = int((xt[name] != 0).sum())
            note = f"train n={len(xt)}: {nz} dòng khác 0 ({nz / len(xt):.2%})"
            if xt[name].nunique() <= 1:
                note += "; HẰNG trên train"
            d.loc[i, "train_check"] = note
        d.to_csv(args.dictionary, index=False, lineterminator="\n")
        print(f"[dictionary] đã ghi train_check vào {args.dictionary.name}")

    if args.domains.is_file():
        mt = xt.merge(pd.read_csv(args.domains)[["id", "registrable_domain"]], on="id")
        trusted = mt["registrable_domain"].fillna("").str.endswith((".gov.vn", ".edu.vn"))
        flagged = mt[trusted & ((mt["brand_domain_mismatch"] == 1) | (mt["brand_typo_score"] > 0))]
        print(f"\n[bằng chứng v0.1, chỉ train] domain .gov.vn/.edu.vn bị gán mismatch hoặc typo: {len(flagged)} dòng")
        if len(flagged):
            print(flagged["registrable_domain"].value_counts().head(15).to_string())
        typo = (mt.loc[mt["brand_typo_score"] > 0, ["registrable_domain", "brand_typo_score"]]
                .drop_duplicates().sort_values("brand_typo_score", ascending=False))
        print(f"[bằng chứng v0.1, chỉ train] {len(typo)} domain có brand_typo_score > 0 (xem có ngân hàng/đơn vị thật không):")
        print(typo.head(40).to_string(index=False))
    else:
        print(f"\n[cảnh báo] không thấy {args.domains.name}: bỏ qua phần bằng chứng v0.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())