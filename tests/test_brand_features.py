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
    extract_e2_features,
    fold_text,
    load_reference,
)
from phishguard_vn.features import CANDIDATE_FEATURES


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