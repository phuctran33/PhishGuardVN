from __future__ import annotations
import math
import re
import pandas as pd

from phishguard_vn.url_parser import parse_url

# Tập hợp 12 features thỏa mãn đúng yêu cầu của phân công Vai 3
CANDIDATE_FEATURES = (
    "url_len", "dom_len", "is_ip", "subdom_cnt", 
    "digit_cnt", "dot_cnt", "dash_cnt", "under_cnt", 
    "at_cnt", "entropy", "path_len", "query_len",
)

# ... (Các hàm extract_features và build_feature_table bên dưới giữ nguyên)

def extract_features(raw_url: str) -> dict[str, float]:
    """Sử dụng shared parser để tính toán các đặc trưng số từ URL."""
    parsed = parse_url(raw_url)
    
    # Bỏ scheme để tính url_len
    url_no_scheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+-.]*://", "", parsed.raw_url)
    hostname = parsed.hostname
    
    # Tính Entropy của hostname
    prob = [float(hostname.count(c)) / len(hostname) for c in set(hostname)] if hostname else []
    entropy = -sum([p * math.log2(p) for p in prob]) if prob else 0.0
    
    # Cờ IP
    is_ip = 1.0 if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", hostname) else 0.0
    
    return {
        "url_len": float(len(url_no_scheme)),
        "dom_len": float(len(hostname)),
        "is_ip": is_ip,
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
    """Tạo bảng features số kèm theo ID và domain để xuất file bàn giao."""
    records = []
    for _, row in frame.iterrows():
        url_str = str(row['url'])
        
        # 1. Trích xuất features
        feats = extract_features(url_str)
        feats['id'] = row['id']
        
        # 2. Lấy thêm registrable_domain để bàn giao riêng cho Hưng
        parsed = parse_url(url_str)
        feats['registrable_domain'] = parsed.registrable_domain
        
        records.append(feats)
        
    return pd.DataFrame(records)