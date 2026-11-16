#!/usr/bin/env python
"""Sinh bộ ca parity BỔ SUNG (soi sâu các chỗ port Dart/Kotlin dễ lệch).

Ghi docs/mobile_parity_cases_extra.json cùng định dạng với mobile_parity_cases.json nhưng KHÔNG
thay file đã freeze và KHÔNG có giá trị tính tay: kỳ vọng chính là hành vi của code Python hiện tại.
Mục đích: tìm chỗ bản mobile lệch Python. Ca nào lệch vì giới hạn đã biết thì ghi vào báo cáo parity,
không sửa công thức Python.

    python scripts/05_make_parity_extra.py            # ghi file
    python scripts/05_make_parity_extra.py --check    # kiểm file còn khớp code
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

CASES = [
    # --- IDN / Unicode ---
    ("idn_unicode", "vn_diacritics_host", "https://vietcombank-đăngnhập.top/"),
    ("idn_unicode", "vn_tld_diacritics", "http://tiếtkiệm.vn/"),
    ("idn_unicode", "fullwidth_host", "http://ｅｘａｍｐｌｅ.com/"),
    ("idn_unicode", "ideographic_dot", "http://example。com/"),
    ("idn_unicode", "sharp_s", "http://straße.de/"),
    ("idn_unicode", "upper_unicode", "HTTP://BÜCHER.DE/ÜBER"),
    ("idn_unicode", "emoji_host", "http://😀.com/"),
    ("idn_unicode", "emoji_path_nonbmp", "https://example.com/😀/a"),
    ("idn_unicode", "superscript_digits_path", "https://example.com/a²b①"),
    ("idn_unicode", "idn_tld", "http://example.中国/"),
    ("idn_unicode", "punycode_tld", "http://xn--fiqs8s/"),
    ("idn_unicode", "punycode_brand_label", "http://xn--vietcombank-xyz.top/"),
    ("idn_unicode", "mixed_script_confusable", "http://vietcοmbank.top/"),  # chữ ο Hy Lạp
    # --- IP ---
    ("ip_forms", "ipv6_loopback", "http://[::1]/"),
    ("ip_forms", "ipv6_long_form", "http://[2001:db8:0:0:1:0:0:1]/x"),
    ("ip_forms", "ipv6_zone", "http://[fe80::1%25eth0]/"),
    ("ip_forms", "ipv6_v4_mapped", "http://[::ffff:1.2.3.4]/"),
    ("ip_forms", "ipv6_double_colon_twice", "http://[1::2::3]/"),
    ("ip_forms", "ipv6_unclosed", "http://[::1/"),
    ("ip_forms", "ipv6_unopened", "http://::1]/"),
    ("ip_forms", "ipv4_leading_zero", "http://01.2.3.4/"),
    ("ip_forms", "ipv4_out_of_range", "http://256.1.1.1/"),
    ("ip_forms", "ipv4_three_parts", "http://1.2.3/"),
    ("ip_forms", "ipv4_hex_part", "http://0x7f.1/"),
    ("ip_forms", "ipv4_trailing_dot", "http://1.2.3.4./"),
    # --- userinfo / port ---
    ("authority", "userinfo_pass", "http://user:pass@vietcombank.com.vn/"),
    ("authority", "empty_userinfo", "http://@example.com/"),
    ("authority", "double_at", "http://a@b@evil.top/"),
    ("authority", "userinfo_no_host", "http://user@/x"),
    ("authority", "empty_port", "http://example.com:/"),
    ("authority", "port_zero", "http://example.com:0/"),
    ("authority", "port_max", "http://example.com:65535/"),
    ("authority", "port_over", "http://example.com:65536/"),
    ("authority", "port_plus_sign", "http://example.com:+80/"),
    ("authority", "port_fullwidth_digits", "http://example.com:８０/"),
    ("authority", "port_huge", "http://example.com:99999999999999999999/"),
    # --- khoảng trắng / ký tự điều khiển ---
    ("whitespace", "space_in_host", "http://exa mple.com/"),
    ("whitespace", "outer_spaces", "  http://example.com/  "),
    ("whitespace", "tab_in_path", "http://example.com/a\tb"),
    ("whitespace", "newline_in_host", "http://exam\nple.com/"),
    ("whitespace", "nbsp_outer", "\u00a0http://example.com/\u00a0"),
    ("whitespace", "nul_in_path", "http://example.com/\u0000x"),
    # --- fragment / query / scheme ---
    ("structure", "fragment_with_brand", "http://example.com#frag/vietcombank"),
    ("structure", "query_then_fragment", "http://example.com?x#y?z"),
    ("structure", "fragment_no_scheme", "example.com#a"),
    ("structure", "ftp_scheme", "ftp://example.com/"),
    ("structure", "javascript_scheme", "javascript:alert(1)"),
    ("structure", "mailto_scheme", "mailto:a@b.com"),
    ("structure", "single_slash", "http:/example.com"),
    ("structure", "scheme_no_slashes", "http:example.com"),
    ("structure", "empty_scheme", "://example.com"),
    ("structure", "scheme_only", "http://"),
    ("structure", "only_path", "/just/a/path"),
    # --- PSL ---
    ("psl", "suffix_only", "http://co.uk/"),
    ("psl", "wildcard_tld", "http://a.b.ck/"),
    ("psl", "wildcard_exception", "http://www.ck/"),
    ("psl", "unknown_tld", "http://foo.unknowntld/"),
    ("psl", "private_suffix_not_used", "http://example.github.io/"),
    ("psl", "weebly_private", "http://x.y.weebly.com/"),
    ("psl", "deep_vn", "http://a.b.com.vn/"),
    ("psl", "gov_vn_brand", "https://dichvucong.gov.vn.verify.top/"),
    ("psl", "trailing_dots", "http://example.com../"),
    ("psl", "leading_dot", "http://.example.com/"),
    ("psl", "single_label", "http://localhost/"),
    # --- brand ---
    ("brand_edge", "typo_dist1", "https://vietcombnk.com/"),
    ("brand_edge", "typo_insert", "https://vietcombaank.top/"),
    ("brand_edge", "typo_dist3_ignored", "https://vietcmbnk.top/"),
    ("brand_edge", "official_upper", "HTTPS://VIETCOMBANK.COM.VN/LOGIN"),
    ("brand_edge", "brand_dash_vn", "https://shopee-vn.xyz/"),
    ("brand_edge", "official_as_subdomain_of_other", "https://shopee.com.vn.evil.top/"),
    ("brand_edge", "brand_prefix_login", "https://login-momo.vn.com/"),
    ("brand_edge", "homoglyph_five", "https://sh0pee.top/"),
    ("brand_edge", "homoglyph_vv", "https://vvwv.example.com/momo"),
    ("brand_edge", "brand_in_both_zones", "https://bidv.evil.top/bidv"),
    # --- percent-encoding ---
    ("percent", "utf8_multibyte", "https://example.com/%E1%BA%A1%76ietcombank"),
    ("percent", "bad_escape", "https://example.com/%ZZ"),
    ("percent", "overlong_utf8", "https://example.com/%C0%AF"),
    ("percent", "encoded_brand_query", "https://evil.top/?u=%62idv.com.vn"),
    ("percent", "encoded_in_host", "http://vietcombank%2Ecom.vn/"),
    # --- kích thước ---
    ("size", "long_5000", "https://example.com/" + "ab-" * 1700),
    ("size", "many_subdomains", "https://" + ".".join(["a"] * 40) + ".example.com/"),
]


def build() -> dict:
    ref = load_reference()
    cases = []
    for group, name, url in CASES:
        parsed = parse_url(url)
        cases.append({
            "name": name, "group": group, "url": url, "hand_checked": False,
            "parsed": {"is_valid": parsed.is_valid, "error_reason": parsed.error_reason,
                       "hostname": parsed.hostname, "registrable_domain": parsed.registrable_domain,
                       "subdomain": parsed.subdomain, "path": parsed.path, "query": parsed.query,
                       "is_ip": parsed.is_ip},
            "expected": extract_e2_features(url),
        })
    names = [c["name"] for c in cases]
    assert len(names) == len(set(names)), "tên ca trùng"
    return {"schema_version": FEATURE_SCHEMA_VERSION, "feature_order": list(E2_FEATURES),
            "tolerance": TOLERANCE, "tldextract_version": url_parser.TLDEXTRACT_VERSION,
            "brand_reference": ref.summary(), "n_cases": len(cases), "cases": cases}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "mobile_parity_cases_extra.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        ok = args.out.is_file() and json.loads(args.out.read_text(encoding="utf-8")) == json.loads(text)
        print("OK: khớp code hiện tại." if ok else "LỖI: file extra không khớp code.", file=None if ok else sys.stderr)
        return 0 if ok else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"-> đã ghi {args.out}: {len(CASES)} ca bổ sung")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
