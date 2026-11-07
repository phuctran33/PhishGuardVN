"""Regression tests cho các false match đã xác nhận ở Y5.2.

SINH TỰ ĐỘNG bởi scripts/05_audit_decisions.py từ 05_gov_edu_brand_audit.csv; đừng sửa tay, hãy đổi verdict rồi sinh lại.
Mỗi ca khẳng định ĐÚNG MỘT lý do (rule, brand_id, key) không còn xuất hiện, nên không phụ thuộc các cờ khác của cùng URL.
Chuỗi URL là chuỗi tĩnh (không truy cập mạng).
"""
import pytest

from phishguard_vn.brand_features import explain_brand_matches

CONFIRMED_FIXED = [
    ('bhxh.gov.vn', 'brand_domain_mismatch', 'bhxh', 'bhxh'),
    ('dichvucong.angiang.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.backan.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.bacninh.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.bocongan.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.cantho.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.caobang.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.daklak.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.dongnai.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.haiphong.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.hanoi.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.hungyen.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.lamdong.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.langson.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.laocai.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.mard.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.mof.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.mofa.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.moh.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.moit.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.moj.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.quangninh.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.ssc.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.thainguyen.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.thuathienhue.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('dichvucong.tuyenquang.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.baria-vungtau.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.binhdinh.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.binhthuan.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.daknong.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.hoabinh.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.kiengiang.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://dichvucong.tiengiang.gov.vn', 'brand_domain_mismatch', 'dvcquocgia', 'dichvucong'),
    ('https://vinhphong-vt.kiengiang.gov.vn', 'brand_typo_score', 'vinaphone', 'vinaphone'),
    ('vinhphong.baolam.caobang.gov.vn', 'brand_typo_score', 'vinaphone', 'vinaphone'),
]  # (url, rule, brand_id, key)
CONFIRMED_STILL_FLAGGED = [
]  # đối chứng: miễn trừ KHÔNG được lan sang các ca này


@pytest.mark.parametrize("url,rule,brand_id,key", CONFIRMED_FIXED)
def test_confirmed_false_match_is_not_flagged(url, rule, brand_id, key):
    _, events = explain_brand_matches(url)
    assert (rule, brand_id, key) not in {(e["rule"], e["brand_id"], e["key"]) for e in events}


@pytest.mark.parametrize("url,rule,brand_id,key", CONFIRMED_STILL_FLAGGED)
def test_correct_flags_are_still_flagged(url, rule, brand_id, key):
    _, events = explain_brand_matches(url)
    assert (rule, brand_id, key) in {(e["rule"], e["brand_id"], e["key"]) for e in events}
