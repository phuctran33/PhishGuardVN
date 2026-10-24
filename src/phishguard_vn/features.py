from __future__ import annotations
import math
import re
import pandas as pd
from phishguard_vn.url_parser import parse_url

CANDIDATE_FEATURES = (
    "url_len", "dom_len", "is_ip", "subdom_cnt", 
    "digit_cnt", "dot_cnt", "dash_cnt", "under_cnt", 
    "at_cnt", "entropy", "path_len", "query_len",
)

def extract_features(raw_url: str) -> dict[str, float]:
    parsed = parse_url(raw_url)
    
    url_no_scheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", "", parsed.raw_url)
    hostname = parsed.hostname
    
    # Tính Entropy trên url_no_scheme (bỏ http/https) theo chuẩn docs/schema.md
    prob = [float(url_no_scheme.count(c)) / len(url_no_scheme) for c in set(url_no_scheme)] if url_no_scheme else []
    entropy = -sum([p * math.log2(p) for p in prob]) if prob else 0.0
    
    return {
        "url_len": float(len(url_no_scheme)),
        "dom_len": float(len(hostname)),
        "is_ip": 1.0 if parsed.is_ip else 0.0,
        "subdom_cnt": float(len(parsed.subdomain.split(".")) if parsed.subdomain else 0),
        "digit_cnt": float(sum(c.isdigit() for c in url_no_scheme)),
        "dot_cnt": float(url_no_scheme.count(".")),
        "dash_cnt": float(url_no_scheme.count("-")),
        "under_cnt": float(url_no_scheme.count("_")),
        "at_cnt": float(url_no_scheme.count("@")),
        "entropy": float(entropy),
        "path_len": float(len(parsed.path)),
        "query_len": float(len(parsed.query)),
    }

def build_feature_table(frame: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in frame.iterrows():
        url_str = str(row['url'])
        feats = extract_features(url_str)
        feats['id'] = row['id']
        parsed = parse_url(url_str)
        feats['registrable_domain'] = parsed.registrable_domain
        records.append(feats)
        
    return pd.DataFrame(records)