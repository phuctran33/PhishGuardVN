"""Tests of the public inspection boundary and the packaged catalog."""
import csv
import hashlib
from io import StringIO
import json

import pytest
from fastapi.testclient import TestClient

from phishguard_vn.api import create_app
from phishguard_vn.brand_features import load_reference
from phishguard_vn import inspection_catalog as data
from phishguard_vn.url_inspection import inspect_url


def test_packaged_catalog_keeps_frozen_domains_and_counts_additions():
    catalog = data.load_catalog()
    frozen = load_reference()
    assert frozen.is_fully_verified and len(frozen.brands) == 45
    assert catalog.n_brands == len(catalog.by_id) + 45
    assert not set(catalog.by_domain) & frozen.all_official_domains
    assert "ergobank.com" not in catalog.by_domain
    assert catalog.by_domain["facebook.com"] == "facebook"
    assert catalog.stats["combined"]["vietnam_scope"]["international_operating_in_vietnam"] > 0
    assert catalog.by_domain["napas.com.vn"] == catalog.by_domain["vietqr.net"] == "napas"
    assert catalog.stats["combined"]["domains"] == len(catalog.by_domain) + len(frozen.all_official_domains)
    assert catalog.sha256 == hashlib.sha256(data.CATALOG_PATH.read_bytes()).hexdigest()


@pytest.mark.parametrize("website", [
    "https://tenant.github.io/",
    "https://brand.example.com/",
    "https://facebook.com/company",
    "https://user@example.com/",
    "https://192.0.2.1/",
    "*.example.com",
    "https://example.com:1234/",
])
def test_invalid_or_shared_website_cannot_be_admitted(website):
    with pytest.raises(ValueError):
        data.listed_domain(website)


def test_idna_and_trailing_dot_are_normalized_locally():
    assert data.listed_domain("https://WWW.BÜCHER.DE./") == "xn--bcher-kva.de"


@pytest.mark.parametrize(("column", "replacement"), [
    ("verification_status", "pending"),
    ("source_url", ""),
    ("vietnam_scope", "international_only"),
    ("vietnam_scope_source_url", ""),
    ("vietnam_scope_evidence", "  "),
    ("verified_at", "tomorrow"),
    ("brand_id", "vietcombank"),
    ("official_domain", "unrelated.example.com"),
    ("aliases", "pay"),
    ("aliases", "vietcombank"),
    ("aliases", "co|hello"),
    ("aliases", "hello|Hello"),
])
def test_validation_rejects_unverified_or_ambiguous_rows(column, replacement):
    csv_content = data.CATALOG_PATH.read_text(encoding="utf-8")
    reader = csv.DictReader(StringIO(csv_content))
    row = next(reader)
    row[column] = replacement
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=data.FIELDS)
    writer.writeheader()
    writer.writerow(row)
    with pytest.raises(ValueError):
        data.read_catalog(buffer.getvalue().encode())


def test_manifest_must_match_counts_bytes_and_frozen_reference(tmp_path):
    catalog = tmp_path / "catalog.csv"
    manifest = tmp_path / "manifest.json"
    original = data.CATALOG_PATH.read_bytes()
    original_manifest = data.MANIFEST_PATH.read_bytes()
    catalog.write_bytes(original + b"\n")
    manifest.write_bytes(original_manifest)
    with pytest.raises(ValueError, match="checksum"):
        data.load_catalog(catalog, manifest)
    catalog.write_bytes(original)
    wrong = json.loads(original_manifest)
    wrong["counts"]["combined"]["brands"] += 1
    manifest.write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(ValueError, match="counts"):
        data.load_catalog(catalog, manifest)


@pytest.mark.parametrize("failure", [FileNotFoundError, ValueError])
def test_inspection_fallback_is_visible_and_independent_of_teacher(monkeypatch, failure):
    def invalid():
        raise failure("private on-disk path")

    data.active_catalog.cache_clear()
    try:
        with monkeypatch.context() as m:
            m.setattr(data, "load_catalog", invalid)
            with TestClient(create_app()) as client:
                inspect = client.post("/inspect", json={"url": "https://napas.com.vn"})
                response = inspect.json()
                assert inspect.status_code == 200
                assert response["catalog_status"] == "fallback_v1"
                assert response["catalog_version"] == "e2-brand-v1"
                assert response["reference_brands"] == 45
                assert response["reference_sha256"] == load_reference().sha256
                assert response["official_brand_ids"] == []
                assert "private" not in inspect.text
                assert client.post("/predict", json={"url": "example.com"}).status_code == 503
    finally:
        data.active_catalog.cache_clear()


@pytest.mark.parametrize(("url", "official", "other"), [
    ("https://napas.com.vn/vietcombank", "napas", "vietcombank"),
    ("https://vietcombank.com.vn/napas", "vietcombank", "napas"),
])
def test_official_domain_cannot_exempt_alias_of_another_brand(url, official, other):
    result = inspect_url(url, catalog=data.load_catalog())
    assert result["official_brand_ids"] == [official]
    assert [m["brand_id"] for m in result["matches"] if m["rule"] == "brand_domain_mismatch"] == [other]


def test_api_exposes_catalog_and_redacts_query_evidence():
    catalog = data.load_catalog()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        matched = client.post("/inspect", json={"url": "https://VietQR.NET/"})
        assert matched.status_code == 200
        result = matched.json()
        assert result["catalog_status"] == "expanded"
        assert result["catalog_version"] == "brand-catalog-v2"
        assert result["reference_sha256"] == catalog.sha256
        assert result["reference_brands"] == catalog.n_brands
        assert result["official_brands"] == [{
            "brand_id": "napas", "brand_name": "NAPAS", "official_domains": ["napas.com.vn", "vietqr.net"],
        }]
        query = client.post("/inspect", json={
            "url": "https://example.org/?vendor=napas&brand=vietcombank&token=privateDummy123",
        })
        assert query.status_code == 200
        assert "privateDummy123" not in query.text
        assert all("privatedummy123" not in m["text"] for m in query.json()["matches"])
        assert any(m.get("zone") == "query" and m["brand_id"] == "napas" for m in query.json()["matches"])


@pytest.mark.parametrize(("url", "expected"), [
    ("https://example.com/apple-pie?tag=zoom", set()),
    ("https://example.com/fpt/shop?other=fpt&category=shop", set()),
    ("https://example.com/?q=B%C3%A1o+Thanh+Ni%C3%AAn", {"thanhnien"}),
    ("https://example.com/fpt-shop", {"fptshop"}),
    ("https://example.com/fptshopper", set()),
    ("https://sub.napas.com.vn/", {"napas"}),
])
def test_only_context_bounded_approved_aliases_active(url, expected):
    catalog = data.load_catalog()
    result = inspect_url(url, catalog=catalog)
    defined = {m["brand_id"] for m in result["matches"] if m["brand_id"] in catalog.by_id}
    assert defined == expected
