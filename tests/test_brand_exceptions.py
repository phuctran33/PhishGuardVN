"""Kiểm soát các ngoại lệ của brand reference và provenance (theo review PR #10).

- Ngoại lệ official_suffixes phải HẸP: đúng một brand, chỉ khi brand khớp duy nhất ở subdomain.
- Các ca dưới đây dùng chuỗi tĩnh tự soạn (không lấy từ dataset). Không truy cập mạng.
- Provenance: reference đóng gói phải đạt fully_verified, và bộ kiểm tra phải bắt được các thiếu sót.
"""
from __future__ import annotations

import pytest

from phishguard_vn.brand_features import (
    extract_brand_features,
    extract_brand_features_from_parsed,
    load_reference,
)
from phishguard_vn.url_parser import parse_url

_HEADER = ("brand_id,canonical_name,aliases,official_domains,sector,source_url,source_accessed,status,notes,"
           "official_suffixes,typo_ignore_tokens,source_url_2,verified_by\n")
_GOOD = "{bid},{name},,{dom},bank,https://a.example/,2026-11-04,verified,Đối chiếu hai nguồn,{suf},,https://b.example/,Hy"


def _ref(tmp_path, rows):
    path = tmp_path / f"ref_{len(list(tmp_path.iterdir()))}.csv"  # load_reference cache theo đường dẫn
    path.write_text(_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return load_reference(path)


def _mismatch(url, ref=None):
    return extract_brand_features_from_parsed(parse_url(url), ref)["brand_domain_mismatch"] if ref else \
        extract_brand_features(url)["brand_domain_mismatch"]


# --- official_suffixes hẹp (reference tạm, không phụ thuộc reference đóng gói) ----------------
@pytest.fixture
def dvc_ref(tmp_path):
    return _ref(tmp_path, [
        _GOOD.format(bid="dvc", name="Dichvucong", dom="dichvucong.gov.vn", suf=".gov.vn"),
        _GOOD.format(bid="vcb", name="Vietcombank", dom="vietcombank.com.vn", suf=""),
    ])


@pytest.mark.parametrize("url,expected", [
    ("https://dichvucong.caobang.gov.vn/", 0.0),              # ngoại lệ đúng thiết kế: subdomain trên .gov.vn
    ("https://dichvucong.hokhauso.com/", 1.0),                # cùng key trên domain tự do
    ("https://dichvucong.gov.vn.evil-site.top/", 1.0),        # giả suffix: registrable domain là evil-site.top
    ("https://dichvucong-gov.vn/", 1.0),                      # '-gov.vn' không phải suffix '.gov.vn'
    ("https://dichvucong-hanoi.gov.vn/", 1.0),                # brand ở nhãn domain đăng ký: không được miễn
    ("https://evil-site.gov.vn/dichvucong/login", 1.0),       # brand chỉ ở path: không được miễn
    ("https://dichvucong.truong.edu.vn/", 1.0),               # suffix chỉ là .gov.vn, không lan sang .edu.vn
    ("https://vietcombank.caobang.gov.vn/", 1.0),             # brand KHÁC trên .gov.vn vẫn bị cờ
])
def test_official_suffix_exception_stays_narrow(dvc_ref, url, expected):
    assert _mismatch(url, dvc_ref) == expected


# --- Cùng các ca đối chứng trên reference đóng gói (chỉ khi reference có ngoại lệ gov) -----------
def _packaged_has_gov_exception():
    brand = next((b for b in load_reference().brands if b.brand_id == "dvcquocgia"), None)
    return bool(brand and brand.official_suffixes)


@pytest.mark.skipif(not _packaged_has_gov_exception(), reason="reference đóng gói không dùng official_suffixes cho dvcquocgia")
@pytest.mark.parametrize("url,expected", [
    ("https://dichvucong.caobang.gov.vn/", 0.0),
    ("https://dichvucong.hokhauso.com/", 1.0),
    ("https://dichvucong.gov.vn.evil-site.top/", 1.0),
    ("https://dichvucong-hanoi.gov.vn/", 1.0),
    ("https://evil-site.gov.vn/dichvucong/login", 1.0),
    ("https://dichvucong.truong.edu.vn/", 1.0),
    ("https://vietcombank.caobang.gov.vn/", 1.0),
])
def test_packaged_reference_keeps_required_warnings(url, expected):
    assert _mismatch(url) == expected


# --- Provenance ---------------------------------------------------------------------------------
def test_packaged_reference_is_fully_verified():
    ref = load_reference()
    assert ref.is_fully_verified, ref.provenance_issues


def test_provenance_complete_rows_pass(tmp_path):
    ref = _ref(tmp_path, [_GOOD.format(bid="a", name="Alpha Corp", dom="alpha.vn", suf="")])
    assert ref.provenance_issues == () and ref.is_fully_verified


@pytest.mark.parametrize("mutate,expected", [
    (lambda r: r.replace(",https://b.example/,Hy", ",,Hy"), "thiếu source_url_2"),
    (lambda r: r.replace(",Hy", ","), "thiếu verified_by"),
    (lambda r: r.replace("2026-11-04", ""), "thiếu source_accessed"),
    (lambda r: r.replace("2026-11-04", "2999-01-01"), "ở tương lai"),
    (lambda r: r.replace("2026-11-04", "04/11/2026"), "YYYY-MM-DD"),
    (lambda r: r.replace("https://b.example/", "https://a.example/"), "trùng nhau"),
    (lambda r: r.replace("https://b.example/", "http://b.example/"), "https://"),
    (lambda r: r.replace("Đối chiếu hai nguồn", "ỨNG VIÊN (AI tra): bạn cần mở nguồn"), "chờ xác minh"),
    (lambda r: r.replace("Đối chiếu hai nguồn", "CHƯA TRA"), "chờ xác minh"),
])
def test_provenance_checker_catches_defects(tmp_path, mutate, expected):
    row = mutate(_GOOD.format(bid="a", name="Alpha Corp", dom="alpha.vn", suf=""))
    ref = _ref(tmp_path, [row])
    assert not ref.is_fully_verified
    assert any(expected in issue for issue in ref.provenance_issues), ref.provenance_issues


def test_normal_verification_wording_is_not_flagged(tmp_path):
    row = _GOOD.format(bid="a", name="Alpha Corp", dom="alpha.vn", suf="").replace(
        "Đối chiếu hai nguồn", "VNBA và trang chủ khớp bản nháp")
    assert _ref(tmp_path, [row]).is_fully_verified


def test_draft_status_is_never_fully_verified(tmp_path):
    ref = _ref(tmp_path, [_GOOD.format(bid="a", name="Alpha Corp", dom="alpha.vn", suf="").replace("verified", "draft")])
    assert not ref.is_fully_verified
