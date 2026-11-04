"""Tests cho brand_features. Giá trị kỳ vọng được tính tay (xem chú thích từng ca)."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from phishguard_vn.brand_features import (
    BRAND_FEATURES,
    E2_FEATURES,
    REFERENCE_PATH,
    build_e2_feature_table,
    extract_brand_features,
    extract_brand_features_from_parsed,
    explain_brand_matches,
    extract_e2_features,
    fold_text,
    load_reference,
)
from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.url_parser import parse_url


def test_e2_schema_keeps_e1_columns_untouched():
    assert E2_FEATURES[: len(CANDIDATE_FEATURES)] == CANDIDATE_FEATURES
    assert E2_FEATURES[len(CANDIDATE_FEATURES):] == BRAND_FEATURES
    assert len(E2_FEATURES) == len(set(E2_FEATURES)) == 20


def test_fold_text_vietnamese():
    assert fold_text("Đăng Nhập Ngân Hàng") == "dang nhap ngan hang"


def test_official_domain_has_no_mismatch_typo_or_homoglyph():
    f = extract_brand_features("https://www.vietcombank.com.vn/vi-VN/")
    assert f["brand_in_domain"] == 1.0
    assert f["brand_domain_mismatch"] == 0.0
    assert f["brand_typo_score"] == 0.0 and f["homoglyph_brand_hit"] == 0.0


def test_brand_in_registered_domain_of_other_site():
    f = extract_brand_features("https://vietcombank-login.top/verify")
    assert (f["brand_in_domain"], f["brand_domain_mismatch"]) == (1.0, 1.0)
    assert f["susp_token_cnt"] == 2.0  # login, verify


def test_brand_in_subdomain_only():
    f = extract_brand_features("https://vietcombank.com.vn.xacminh-id.xyz/")
    assert f["brand_in_subdomain"] == 1.0 and f["brand_in_domain"] == 0.0
    assert f["brand_domain_mismatch"] == 1.0


def test_brand_in_path_only():
    f = extract_brand_features("https://evil.top/vietcombank/login")
    assert (f["brand_in_path"], f["brand_in_domain"], f["brand_in_subdomain"]) == (1.0, 0.0, 0.0)
    assert f["brand_domain_mismatch"] == 1.0


def test_short_alias_requires_whole_token():
    assert extract_brand_features("https://acbdoc.com/")["brand_in_domain"] == 0.0
    assert extract_brand_features("https://acb-online.com/")["brand_in_domain"] == 1.0


def test_typosquat_transposition_score():
    # vietcombnak vs vietcombank: hoán vị 'na' -> d=1, key dài 11 => 1 - 1/11
    f = extract_brand_features("https://vietcombnak.com/")
    assert math.isclose(f["brand_typo_score"], 1 - 1 / 11)


def test_other_brand_name_is_not_typo_of_similar_brand():
    # tpbank và vpbank cách nhau 1 ký tự, nhưng tpbank là tên brand khác nên không tính lỗi gõ
    assert extract_brand_features("https://tpbank-online.top/")["brand_typo_score"] == 0.0


def test_homoglyph_hit_requires_confusable_fold():
    f = extract_brand_features("https://vietc0mbank.top/")  # 0 thay o
    assert f["homoglyph_brand_hit"] == 1.0 and f["brand_in_domain"] == 0.0








def test_idna_flag():
    assert extract_brand_features("http://xn--bcher-kva.de/")["idna_flag"] == 1.0
    assert extract_brand_features("http://example.com/")["idna_flag"] == 0.0


def test_no_brand_gives_all_zero():
    f = extract_brand_features("https://thanhhoa.gov.vn/")
    assert all(f[name] == 0.0 for name in BRAND_FEATURES)


def test_ip_url_is_valid_and_path_hit_counts_as_mismatch():
    f = extract_brand_features("http://192.168.1.1/vietcombank")
    assert (f["brand_in_path"], f["brand_domain_mismatch"]) == (1.0, 1.0)


@pytest.mark.parametrize("bad", [None, "", "https://example.com:bad/p", "invalid_url"])
def test_invalid_rows_return_none_for_all_20(bad):
    feats = extract_e2_features(bad)
    assert list(feats) == list(E2_FEATURES)
    assert all(v is None for v in feats.values())


def test_table_order_ids_and_finite_values():
    frame = pd.DataFrame({
        "id": ["a", "b", "c", "d"],
        "url": ["https://vietcombank.com.vn/", "https://vietcombank-login.top/", None, "invalid_url"],
    })
    table = build_e2_feature_table(frame)
    ok = table["is_valid"].astype(bool)
    assert ok.tolist() == [True, True, False, False]
    x = table.loc[ok, ["id", *E2_FEATURES]]
    assert list(x.columns) == ["id", *E2_FEATURES]
    assert x[list(E2_FEATURES)].notna().all().all()
    assert (x[list(E2_FEATURES)].abs() != float("inf")).all().all()


def test_e1_columns_identical_between_e1_and_e2_extractors():
    from phishguard_vn.features import extract_features
    url = "https://login.vietcombank-secure.top/Path?x=1"
    e1, e2 = extract_features(url), extract_e2_features(url)
    assert all(e1[name] == e2[name] for name in CANDIDATE_FEATURES)


# --- Brand reference --------------------------------------------------------------------------
def _write_ref(tmp_path, rows):
    header = "brand_id,canonical_name,aliases,official_domains,sector,source_url,source_accessed,status,notes\n"
    path = tmp_path / "ref.csv"
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_reference_rejects_alias_collision(tmp_path):
    path = _write_ref(tmp_path, [
        "a,Alpha Corp,sharedname,alpha.vn,bank,,,draft,",
        "b,Beta Corp,sharedname,beta.vn,bank,,,draft,",
    ])
    with pytest.raises(ValueError, match="va chạm"):
        load_reference(path)


def test_reference_rejects_short_and_stoplist_aliases(tmp_path):
    with pytest.raises(ValueError, match="ngắn hơn"):
        load_reference(_write_ref(tmp_path, ["a,Alpha Corp,mb,alpha.vn,bank,,,draft,"]))
    with pytest.raises(ValueError, match="STOPLIST"):
        load_reference(_write_ref(tmp_path, ["c,Gamma Corp,bank,gamma.vn,bank,,,draft,"]))


def test_packaged_reference_loads_and_has_no_label_columns():
    ref = load_reference()
    assert len(ref.brands) >= 30
    with open(REFERENCE_PATH, encoding="utf-8") as handle:
        header = handle.readline().strip().split(",")
    assert not {"label", "source", "tier", "split"} & set(header)


def test_packaged_reference_reports_provenance():
    summary = load_reference().summary()
    assert {"sha256", "status_counts", "n_missing_source_accessed", "fully_verified"} <= set(summary)
    assert 0 <= summary["n_missing_source_accessed"] <= summary["n_brands"]


# --- explain_brand_matches: cùng một lõi với features --------------------------------------
@pytest.mark.parametrize("url", [
    "https://vietcombank-login.top/verify",
    "https://vietcombank.com.vn.xacminh-id.xyz/",
    "https://vietcombnak.com/",
    "https://vietc0mbank.top/",
    "https://evil.top/vietcombank/login",
    "https://thanhhoa.gov.vn/",
])
def test_explain_is_consistent_with_features(url):
    feats, events = explain_brand_matches(url)
    assert feats == extract_brand_features(url)
    rules = {e["rule"] for e in events}
    for name, rule in [("brand_in_domain", "brand_in_domain"), ("brand_in_subdomain", "brand_in_subdomain"),
                       ("brand_in_path", "brand_in_path"), ("brand_domain_mismatch", "brand_domain_mismatch"),
                       ("homoglyph_brand_hit", "homoglyph_brand_hit"), ("brand_typo_score", "brand_typo_score")]:
        assert (feats[name] > 0) == (rule in rules), (url, name)
    assert feats["susp_token_cnt"] == sum(e["rule"] == "susp_token" for e in events)


# --- Vector tính tay (không dùng chính hàm để suy ra kỳ vọng) -----------------------------
def test_hand_checked_vectors():
    # "vietcombank-login.top/verify": 11+1+5+4=21 ký tự domain, +7 path = 28
    f = extract_e2_features("https://vietcombank-login.top/verify")
    expected = {"url_len": 28, "dom_len": 21, "is_ip": 0, "subdom_cnt": 0, "letter_cnt": 25, "digit_cnt": 0,
                "dot_cnt": 1, "dash_cnt": 1, "under_cnt": 0, "slash_cnt": 1, "path_len": 7,
                "brand_in_domain": 1, "brand_in_subdomain": 0, "brand_in_path": 0, "brand_domain_mismatch": 1,
                "brand_typo_score": 0, "susp_token_cnt": 2, "idna_flag": 0, "homoglyph_brand_hit": 0}
    assert all(f[k] == v for k, v in expected.items())
    # "xn--bcher-kva.de/Path": 16 + 5 = 21; chữ cái 12 + 4 = 16; gạch ngang 3
    g = extract_e2_features("http://xn--bcher-kva.de/Path")
    expected = {"url_len": 21, "dom_len": 16, "letter_cnt": 16, "dash_cnt": 3, "dot_cnt": 1, "slash_cnt": 1,
                "path_len": 5, "idna_flag": 1}
    assert all(g[k] == v for k, v in expected.items())


# --- Cột tùy chọn của reference: chỉ điền sau khi rà soát từng ca -----------------------------
_HEADER = ("brand_id,canonical_name,aliases,official_domains,sector,source_url,source_accessed,status,notes,"
           "official_suffixes,typo_ignore_tokens\n")


def _ref(tmp_path, rows):
    path = tmp_path / f"ref_{len(list(tmp_path.iterdir()))}.csv"  # load_reference cache theo đường dẫn
    path.write_text(_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return load_reference(path)


def test_official_suffix_is_scoped_to_one_brand(tmp_path):
    ref = _ref(tmp_path, [
        "dvc,Dich vu cong,dichvucong,dichvucong.gov.vn,gov,u,d,verified,,.gov.vn,",
        "vcb,Vietcombank,,vietcombank.com.vn,bank,u,d,verified,,,",
    ])
    mm = lambda url: extract_brand_features_from_parsed(parse_url(url), ref)["brand_domain_mismatch"]  # noqa: E731
    assert mm("https://dichvucong.caobang.gov.vn/") == 0.0   # miễn trừ gắn riêng brand dvc
    assert mm("https://dichvucong.hokhauso.com/") == 1.0     # domain tự do vẫn là mismatch
    assert mm("https://vietcombank.caobang.gov.vn/") == 1.0  # brand khác trên .gov.vn KHÔNG được miễn trừ


def test_typo_ignore_token_removes_confirmed_false_match(tmp_path):
    base = "vina,VinaPhone,,vinaphone.com.vn,telecom,u,d,verified,,,%s"
    url = "https://vinhphong.haiphong.edu.vn/"
    score = lambda ref: extract_brand_features_from_parsed(parse_url(url), ref)["brand_typo_score"]  # noqa: E731
    assert score(_ref(tmp_path, [base % ""])) > 0.0          # không có danh sách bỏ qua: bị coi là lỗi gõ
    assert score(_ref(tmp_path, [base % "vinhphong"])) == 0.0  # đã xác nhận là địa danh


def test_official_suffix_must_start_with_dot(tmp_path):
    with pytest.raises(ValueError, match="bắt đầu bằng"):
        _ref(tmp_path, ["a,Alpha Corp,,alpha.vn,bank,u,d,draft,,gov.vn,"])