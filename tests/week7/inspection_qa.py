"""QA độc lập /inspect; truyền file này trực tiếp cho pytest của checkout tuần 7."""

import hashlib
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phishguard_vn import api
from phishguard_vn.brand_features import E2_FEATURES, load_reference


@pytest.fixture
def inspection_client():
    with TestClient(api.create_app(cors_origins=["http://localhost:3000"])) as client:
        yield client


@pytest.mark.parametrize("payload", [{}, {"url": None}, {"url": 7}, {"url": []}, {"url": {}}, {"url": "example.com", "extra": True}])
def test_inspect_rejects_invalid_request_without_echo(inspection_client, payload):
    response = inspection_client.post("/inspect", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "reason"}
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_inspect_length_boundary_is_measured_before_outer_trim(inspection_client):
    prefix = "https://example.com/"
    value = prefix + "a" * (4096 - len(prefix))
    assert inspection_client.post("/inspect", json={"url": value}).status_code == 200
    for too_long in (value + "a", " " + value):
        response = inspection_client.post("/inspect", json={"url": too_long})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("value", ["https://example.com/a\x00b", "https://example.com/a\x7fb", "https://example.com/a\tb", "file:///secret/path", "data:text/html,secret"])
def test_inspect_rejects_controls_and_nonweb_inputs_without_echo(inspection_client, value):
    response = inspection_client.post("/inspect", json={"url": value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_URL"
    assert value not in response.text


@pytest.mark.parametrize(
    "value,host,domain,official",
    [
        ("https://vietcombank.com.vn@example.com/login", "example.com", "example.com", []),
        ("https://example.com/?next=https://vietcombank.com.vn", "example.com", "example.com", []),
        ("https://login.vietcombank.com.vn/", "login.vietcombank.com.vn", "vietcombank.com.vn", ["vietcombank"]),
        ("https://vietcombank.com.vn.example.com/", "vietcombank.com.vn.example.com", "example.com", []),
        ("http://[2001:db8::1]/vietcombank", "2001:db8::1", None, []),
    ],
)
def test_inspect_domain_identity_ignores_userinfo_and_query(inspection_client, value, host, domain, official):
    response = inspection_client.post("/inspect", json={"url": value})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["hostname"] == host
    assert result.get("registrable_domain") == domain
    assert result["official_brand_ids"] == official
    assert not {"label", "score", "threshold", "model", "decision_rule"} & result.keys()


def test_inspect_unicode_and_punycode_have_same_host_and_rule_features(inspection_client):
    results = [inspection_client.post("/inspect", json={"url": url}).json() for url in ("https://bücher.de/Path?Q=A", "https://xn--bcher-kva.de/Path?Q=A")]
    assert results[0] == results[1]


def test_inspect_offline_without_raw_url_logs_or_ml_calls(inspection_client, monkeypatch, caplog):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("QA: network or ML call during inspection")

    # TestClient's Windows event loop must exist before guarding socketpair.
    with monkeypatch.context() as guards:
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
            guards.setattr(socket, name, forbidden)
        guards.setattr(socket.socket, "connect", forbidden)
        guards.setattr(socket.socket, "connect_ex", forbidden)
        guards.setattr(api, "predict_url", forbidden)
        response = inspection_client.post("/inspect", json={"url": "https://qa-user:qa-secret@example.com/qa-private-path?token=qa-private-token"})
    assert response.status_code == 200, response.text
    assert attempts == []
    for marker in ("qa-secret", "qa-private-path", "qa-private-token"):
        assert marker not in caplog.text


@pytest.mark.parametrize("defect", ["exception", "nonfinite", "missing_field"])
def test_inspect_adapter_defects_are_sanitized_and_retryable(inspection_client, monkeypatch, caplog, defect):
    original = api.inspect_url

    def broken(url):
        if defect == "exception":
            raise RuntimeError("qa-secret /private/qa-secret-file")
        value = original(url)
        if defect == "nonfinite":
            value["features"]["brand_domain_mismatch"] = float("nan")
        else:
            value.pop("hostname")
        return value

    with monkeypatch.context() as patch:
        patch.setattr(api, "inspect_url", broken)
        response = inspection_client.post("/inspect", json={"url": "example.com"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INSPECTION_UNAVAILABLE"
    assert "qa-secret" not in response.text + caplog.text
    assert "Traceback" not in response.text
    assert inspection_client.post("/inspect", json={"url": "example.com"}).status_code == 200


def test_inspect_cors_applies_to_success_and_invalid_body(inspection_client):
    for payload, expected in (({"url": "example.com"}, 200), ({}, 422)):
        response = inspection_client.post("/inspect", json=payload, headers={"Origin": "http://localhost:3000"})
        assert response.status_code == expected
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = inspection_client.post("/inspect", json={"url": "example.com"}, headers={"Origin": "https://unapproved.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_inspect_preserves_frozen_reference_feature_order_and_extractor_sources(inspection_client):
    root = Path(api.__file__).resolve().parents[2]
    lock = json.loads((root / "configs/teacher_v2_candidate_lock.json").read_text(encoding="utf-8"))
    before = load_reference().sha256
    assert before == lock["reference_sha256"]
    assert len(load_reference().brands) == 45
    assert list(E2_FEATURES) == lock["feature_names"]
    for filename, expected in lock["source_sha256"].items():
        contents = (root / "src/phishguard_vn" / filename).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(contents).hexdigest() == expected, filename
    assert inspection_client.post("/inspect", json={"url": "example.com"}).status_code == 200
    assert load_reference().sha256 == before


def test_inspection_does_not_change_real_teacher_scores_or_operating_point(teacher_root):
    urls = ["example.com", "https://example.com/Login?Q=A", "https://vietcombank.com.vn.example.com/login"]
    with TestClient(api.create_app(bundle_format="teacher", teacher_root=teacher_root)) as client:
        assert client.get("/health").json()["model_ready"] is True
        before = [client.post("/predict", json={"url": url}).json() for url in urls]
        assert [value["label"] for value in before] == ["benign", "benign", "phishing"]
        for url in urls:
            response = client.post("/inspect", json={"url": url})
            assert response.status_code == 200
            assert not {"score", "label", "threshold"} & response.json().keys()
        after = [client.post("/predict", json={"url": url}).json() for url in urls]
        assert after == before
