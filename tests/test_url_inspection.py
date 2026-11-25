"""Offline rule adapter tests; no synthetic ML verdicts for heuristic signals."""

import socket

import pytest
from fastapi.testclient import TestClient

from phishguard_vn import api
from phishguard_vn.brand_features import explain_brand_matches, load_reference
from phishguard_vn.url_inspection import inspect_url


@pytest.mark.parametrize(
    "url,domain,signal",
    [
        ("https://www.vietcombank.com.vn/", "vietcombank.com.vn", "brand_in_domain"),
        (
            "https://vietcombank.com.vn.example.com/login",
            "example.com",
            "brand_in_subdomain",
        ),
        ("https://example.com/vietcombank?login=1", "example.com", "brand_in_path"),
        ("https://vietcombnak.com/", "vietcombnak.com", "brand_typo_score"),
        ("https://vietc0mbank.top/", "vietc0mbank.top", "homoglyph_brand_hit"),
        ("https://bücher.de/Path", "xn--bcher-kva.de", "idna_flag"),
        ("http://127.0.0.1/login", None, None),
    ],
)
def test_inspection_preserves_reference_engine_and_exposes_evidence(
    url, domain, signal
):
    result = inspect_url(url)
    assert result["registrable_domain"] == domain
    assert result["features"] == explain_brand_matches(url)[0]
    assert result["reference_sha256"] == load_reference().sha256
    assert result["reference_brands"] == 45
    if signal:
        assert result["features"][signal] > 0
    if domain == "vietcombank.com.vn":
        assert result["official_brand_ids"] == ["vietcombank"]
        assert result["features"]["brand_domain_mismatch"] == 0
    assert not {"label", "score", "threshold", "model"} & result.keys()
    assert all(e["brand_name"] or e["rule"] == "susp_token" for e in result["matches"])


def test_inspect_works_without_teacher_and_never_uses_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Target network access forbidden")

    # Bootstrap the TestClient event loop before guarding sockets (Windows socketpair).
    with TestClient(api.create_app()) as client:
        with monkeypatch.context() as guards:
            for name in (
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
                "create_connection",
            ):
                guards.setattr(socket, name, forbidden)
            guards.setattr(socket.socket, "connect", forbidden)
            guards.setattr(socket.socket, "connect_ex", forbidden)
            for url in [
                "EXAMPLE.com/Login?Q=A",
                "https://vietcombank.com.vn.example.com/",
                "https://bücher.de/",
                "http://[::1]/",
            ]:
                r = client.post("/inspect", json={"url": f"  {url}  "})
                assert r.status_code == 200, r.text
                assert r.json()["scope"] == "rule_based_url_inspection"
        assert client.post("/predict", json={"url": "example.com"}).status_code == 503
        assert (
            "InspectionResponse"
            in client.get("/openapi.json").json()["components"]["schemas"]
        )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "http://example.com:99999",
        "ftp://example.com",
        "http://bad host.com",
        "https://",
    ],
)
def test_inspect_and_predict_share_validation(value):
    with TestClient(api.create_app()) as client:
        left = client.post("/inspect", json={"url": value})
        right = client.post("/predict", json={"url": value})
        assert left.status_code == right.status_code == 422
        assert left.json() == right.json()


def test_reference_failure_sanitized_and_retryable(monkeypatch):
    with TestClient(api.create_app()) as client:
        original = api.inspect_with_catalog

        def broken(_):
            raise RuntimeError("/secret/path token")

        monkeypatch.setattr(api, "inspect_with_catalog", broken)
        r = client.post("/inspect", json={"url": "example.com"})
        assert (
            r.status_code == 503
            and r.json()["error"]["code"] == "INSPECTION_UNAVAILABLE"
        )
        assert "secret" not in r.text
        monkeypatch.setattr(api, "inspect_with_catalog", original)
        assert client.post("/inspect", json={"url": "example.com"}).status_code == 200
