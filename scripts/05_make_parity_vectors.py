#!/usr/bin/env python
"""Y5.4: sinh bộ ca parity (URL -> kết quả mong đợi) để đối chiếu Python và mobile.

Chạy từ thư mục gốc dự án, bằng tldextract THẬT (kết quả phụ thuộc PSL):
    python scripts/05_make_parity_vectors.py                # ghi docs/mobile_parity_cases.json
    python scripts/05_make_parity_vectors.py --check        # chỉ kiểm tra file hiện có còn khớp code (dùng sau khi đổi code/reference)

Mọi URL là chuỗi tĩnh tự soạn (không lấy từ dataset, không truy cập mạng).
Ngoài features, file chứa cả kết quả trung gian của parser (hostname, registrable_domain, subdomain, path, query, error_reason)
để bản mobile biết sai lệch bắt đầu từ bước nào (thường là PSL hoặc IDNA).
Các ca trong HAND_CHECKED có giá trị TÍNH TAY (không suy ra từ code): script dừng nếu Python lệch với giá trị tay.
Phải sinh lại file mỗi khi đổi FEATURE_SCHEMA_VERSION, brand reference, phiên bản tldextract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phishguard_vn import url_parser  # noqa: E402
from phishguard_vn.brand_features import (  # noqa: E402
    E2_FEATURES, FEATURE_SCHEMA_VERSION, extract_e2_features, load_reference,
)
from phishguard_vn.url_parser import parse_url  # noqa: E402

TOLERANCE = 1e-6

# (nhóm, tên, url): URL tự soạn
CASES = [
    ("official", "vcb_home", "https://www.vietcombank.com.vn/vi-VN/"),
    ("official", "bidv_login_page", "https://bidv.com.vn/ibank/login"),
    ("official", "momo_home", "https://momo.vn/"),
    ("official", "shopee_home", "https://shopee.vn/"),
    ("official", "tcb_two_domains", "https://techcombank.com/personal"),
    ("official", "gov_portal_official", "https://dichvucong.gov.vn/p/home/dvc-trang-chu.html"),
    ("brand_in_domain", "vcb_login_top", "https://vietcombank-login.top/verify"),
    ("brand_in_domain", "shopee_gift", "http://shopee-quatang.example.com/nhanqua"),
    ("brand_in_domain", "momo_short_token", "https://momo-vn.top/"),
    ("brand_in_domain", "short_alias_exact_token", "https://acb-online.com/"),
    ("brand_in_domain", "short_alias_not_token", "https://acbdoc.com/"),
    ("brand_in_domain", "concatenated_brand", "https://techcombankonline.xyz/"),
    ("brand_in_subdomain", "classic_trick", "https://vietcombank.com.vn.xacminh-id.xyz/"),
    ("brand_in_subdomain", "bank_login_subdomain", "https://login.bidv.secure-pay.top/"),
    ("brand_in_subdomain", "free_hosting_style", "https://vietcombank-ibank.weebly.com/"),
    ("brand_in_path", "path_only", "https://evil-site.top/vietcombank/login"),
    ("brand_in_path", "query_only", "https://evil-site.top/?redirect=bidv.com.vn"),
    ("typo", "transposition", "https://vietcombnak.com/"),
    ("typo", "extra_letter", "https://vietcombanks.top/"),
    ("typo", "other_brand_name_not_typo", "https://tpbank-online.top/"),
    ("typo", "short_token_ignored", "https://vcbx.top/"),
    ("homoglyph", "zero_for_o", "https://vietc0mbank.top/"),
    ("homoglyph", "one_for_i", "https://b1dv-vn.top/"),
    ("homoglyph", "rn_for_m", "https://momornomo.top/"),
    ("idn", "punycode_host", "http://xn--bcher-kva.de/Path"),
    ("idn", "unicode_host", "http://bücher.de/Path"),
    ("idn", "vietnamese_diacritics_path", "https://example.com/dang-nhap/Đăng%20Nhập"),
    ("ip", "ipv4_with_brand_path", "http://192.168.1.1/vietcombank"),
    ("ip", "ipv6_literal", "http://[2001:db8::1]/login"),
    ("normalization", "uppercase_scheme_host", "HTTPS://WWW.Example.COM/Path?Q=A"),
    ("normalization", "trailing_dot", "http://EXAMPLE.com./"),
    ("normalization", "scheme_relative", "//example.com/Path"),
    ("normalization", "missing_scheme", "vietcombank-login.top/verify"),
    ("normalization", "port_and_userinfo", "http://paypal.com@evil-site.top:8080/login"),
    ("normalization", "path_params", "https://example.com/a;b?x=1"),
    ("normalization", "percent_encoded_path", "https://example.com/%76ietcombank"),
    ("normalization", "multi_level_suffix", "https://a.b.c.example.co.uk/x"),
    ("normalization", "underscore_host", "http://my_site.example.com/a"),
    ("suspicious", "many_keywords", "https://secure-login-verify.example.com/account/update"),
    ("suspicious", "vietnamese_keywords", "https://uudai-khuyenmai.example.com/xacminh/nhanqua"),
    ("long", "very_long_url", "https://example.com/" + "a" * 180 + "/vietcombank?x=" + "1" * 40),
    ("invalid", "invalid_port", "https://example.com:99999/"),
    ("invalid", "invalid_port_text", "https://example.com:bad/p"),
    ("invalid", "unresolved_domain", "invalid_url"),
    ("invalid", "empty_string", ""),
    ("invalid", "whitespace_only", "   "),
    ("invalid", "none_input", None),
]

# Giá trị TÍNH TAY (không suy ra từ code). Entropy cố ý không nằm ở đây.
HAND_CHECKED = {
    "vcb_login_top": {"url_len": 28, "dom_len": 21, "is_ip": 0, "subdom_cnt": 0, "letter_cnt": 25, "digit_cnt": 0,
                      "dot_cnt": 1, "dash_cnt": 1, "under_cnt": 0, "slash_cnt": 1, "path_len": 7,
                      "brand_in_domain": 1, "brand_in_subdomain": 0, "brand_in_path": 0, "brand_domain_mismatch": 1,
                      "brand_typo_score": 0, "susp_token_cnt": 2, "idna_flag": 0, "homoglyph_brand_hit": 0},
    "punycode_host": {"url_len": 21, "dom_len": 16, "letter_cnt": 16, "dash_cnt": 3, "dot_cnt": 1, "slash_cnt": 1,
                      "path_len": 5, "idna_flag": 1},
    "vcb_home": {"brand_in_domain": 1, "brand_domain_mismatch": 0, "brand_typo_score": 0, "homoglyph_brand_hit": 0},
    "short_alias_not_token": {"brand_in_domain": 0, "brand_domain_mismatch": 0},
    "short_alias_exact_token": {"brand_in_domain": 1, "brand_domain_mismatch": 1},
    "classic_trick": {"brand_in_subdomain": 1, "brand_in_domain": 0, "brand_domain_mismatch": 1},
    "path_only": {"brand_in_path": 1, "brand_in_domain": 0, "brand_in_subdomain": 0, "brand_domain_mismatch": 1},
    "ipv4_with_brand_path": {"is_ip": 1, "brand_in_path": 1, "brand_domain_mismatch": 1, "dom_len": 11},
    "zero_for_o": {"homoglyph_brand_hit": 1, "brand_in_domain": 0},
    "invalid_port": {"_invalid": True}, "none_input": {"_invalid": True}, "empty_string": {"_invalid": True},
}


def build() -> dict:
    ref = load_reference()
    cases = []
    for group, name, url in CASES:
        parsed = parse_url(url)
        feats = extract_e2_features(url)
        cases.append({
            "name": name, "group": group, "url": url,
            "hand_checked": name in HAND_CHECKED,
            "parsed": {"is_valid": parsed.is_valid, "error_reason": parsed.error_reason, "hostname": parsed.hostname,
                       "registrable_domain": parsed.registrable_domain, "subdomain": parsed.subdomain,
                       "path": parsed.path, "query": parsed.query, "is_ip": parsed.is_ip},
            "expected": feats,   # None cho toàn bộ cột nếu URL không hợp lệ: bản mobile phải trả 'không phân loại được'
        })
    names = [c["name"] for c in cases]
    assert len(names) == len(set(names)), "tên ca trùng"
    for c in cases:  # đối chiếu giá trị tính tay
        for key, want in HAND_CHECKED.get(c["name"], {}).items():
            if key == "_invalid":
                assert not c["parsed"]["is_valid"] and all(v is None for v in c["expected"].values()), c["name"]
            else:
                got = c["expected"][key]
                assert got == want, f"LỆCH TÍNH TAY {c['name']}.{key}: code={got} tay={want}"
    return {"schema_version": FEATURE_SCHEMA_VERSION, "feature_order": list(E2_FEATURES), "tolerance": TOLERANCE,
            "tldextract_version": url_parser.TLDEXTRACT_VERSION, "brand_reference": ref.summary(),
            "n_cases": len(cases), "cases": cases}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "mobile_parity_cases.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.out.is_file() or json.loads(args.out.read_text(encoding="utf-8")) != json.loads(text):
            print("LỖI: file parity không khớp code hiện tại. Chạy lại không có --check.", file=sys.stderr)
            return 1
        print("OK: file parity khớp code hiện tại.")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    n_hand = sum(c["hand_checked"] for c in data["cases"])
    invalid = sum(not c["parsed"]["is_valid"] for c in data["cases"])
    print(f"-> đã ghi {args.out}: {data['n_cases']} ca ({n_hand} ca có giá trị tính tay, {invalid} ca URL không hợp lệ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())