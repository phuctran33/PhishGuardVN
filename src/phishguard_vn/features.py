"""Trích xuất 12 lexical features (xem reports/.../feature_dictionary.csv).

Mọi số đếm/độ dài/entropy tính trên URL đã bỏ scheme, đúng quy ước của schema.md.
"""
from __future__ import annotations

import math
from collections import Counter

import pandas as pd

from phishguard_vn.url_parser import SCHEME_STRIP_RE, ParsedURL, parse_url

CANDIDATE_FEATURES = (
    "url_len", "dom_len", "is_ip", "subdom_cnt",
    "letter_cnt", "digit_cnt", "dot_cnt", "dash_cnt",
    "under_cnt", "slash_cnt", "entropy", "path_len",
)


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in Counter(text).values())


def extract_features_from_parsed(parsed: ParsedURL) -> dict[str, float | None]:
    """Chỉ URL parse hợp lệ (kể cả IP) mới có feature; URL lỗi trả toàn None."""
    if not parsed.is_valid:
        return {name: None for name in CANDIDATE_FEATURES}

    text = SCHEME_STRIP_RE.sub("", parsed.raw_url, count=1)
    # dom_len = độ dài registrable domain (dvc.bcavn.cc -> bcavn.cc = 8), khớp vn_compphish.csv.
    # URL là IP thì không có registrable domain: dùng độ dài chính địa chỉ IP.
    domain_text = parsed.registrable_domain or parsed.hostname

    return {
        "url_len": float(len(text)),
        "dom_len": float(len(domain_text)),
        "is_ip": 1.0 if parsed.is_ip else 0.0,
        "subdom_cnt": float(len(parsed.subdomain.split(".")) if parsed.subdomain else 0),
        "letter_cnt": float(sum(ch.isalpha() for ch in text)),
        "digit_cnt": float(sum(ch.isdigit() for ch in text)),
        "dot_cnt": float(text.count(".")),
        "dash_cnt": float(text.count("-")),
        "under_cnt": float(text.count("_")),
        "slash_cnt": float(text.count("/")),
        "entropy": _entropy(text),
        "path_len": float(len(parsed.path)),
    }


def extract_features(raw_url: str | None) -> dict[str, float | None]:
    return extract_features_from_parsed(parse_url(raw_url))


def build_feature_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Một dòng/URL: id + 12 features + metadata (registrable_domain, error_reason, is_valid).

    Giá trị url thiếu (NaN/None) KHÔNG được ép thành chuỗi 'nan': đi vào parse_url dưới dạng
    None và nhận error_reason='missing_url'. Cột is_valid cho biết dòng nào được vào X.
    """
    records = []
    for row_id, url in zip(frame["id"], frame["url"]):
        parsed = parse_url(url if isinstance(url, str) else None)
        record = dict(extract_features_from_parsed(parsed))
        record["id"] = row_id
        record["registrable_domain"] = parsed.registrable_domain or pd.NA
        record["error_reason"] = parsed.error_reason
        record["is_valid"] = parsed.is_valid
        records.append(record)
    return pd.DataFrame(records)