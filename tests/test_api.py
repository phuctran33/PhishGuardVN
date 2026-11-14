"""Backend smoke/contract tests. Synthetic estimators are test fixtures, never demo models."""
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

pytest.importorskip("fastapi", reason="Install .[api,test] for backend smoke tests")
pytest.importorskip("httpx2", reason="Install .[api,test] for TestClient")
from fastapi.testclient import TestClient

from phishguard_vn import api
from phishguard_vn.features import CANDIDATE_FEATURES


class FixedEstimator:
    """Prebuilt synthetic fixture; no fitting or research model mutation."""
    def __init__(self, names=CANDIDATE_FEATURES):
        self.classes_ = np.array([0, 1])
        self.feature_names_in_ = np.array(names)
        self.n_features_in_ = len(names)

    def predict(self, X):
        return np.ones(len(X), dtype=int)

    def predict_proba(self, X):
        return np.tile([.3, .7], (len(X), 1))

    def decision_function(self, X):
        return np.full(len(X), 1.25)


def bundle(kind="probability"):
    return {"feature_set": "lexical_12", "feature_names": list(CANDIDATE_FEATURES),
            "selected_model": "fixture", "models": {"fixture": FixedEstimator()},
            "score_kinds": {"fixture": kind}, "protocol": "synthetic-unit-test-only"}


def artifact(tmp_path, value):
    path = tmp_path / "fixture.joblib"
    joblib.dump(value, path)
    return path


def test_unconfigured_app_starts_with_docs_but_never_fakes_prediction():
    with TestClient(api.create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "degraded", "model_ready": False, "model": None,
            "feature_set": None, "protocol": None, "artifact_sha256": None, "model_error": "not_configured"}
        assert client.get("/docs").status_code == 200
        response = client.post("/predict", json={"url": "example.com"})
        assert response.status_code == 503 and response.json()["error"]["reason"] == "not_configured"
        assert "score" not in response.json()
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/predict"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResponse")


@pytest.mark.parametrize("payload", [{}, {"url": ""}, {"url": "  "}, {"url": None},
    {"url": 12}, {"url": 1.5}, {"url": True}, {"url": []}, {"url": {}},
    {"url": "x" * 4097}, {"url": "example.com", "model": "x"}])
def test_invalid_body_precedes_readiness_and_does_not_echo_input(payload):
    with TestClient(api.create_app()) as client:
        response = client.post("/predict", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.json()["error"]["reason"] == "schema_validation"
    assert set(response.json()) == {"error"} and "input" not in response.json()["error"]


def test_url_at_maximum_contract_length_is_accepted(tmp_path):
    prefix = "https://example.com/"
    url = prefix + "a" * (4096 - len(prefix))
    assert len(url) == 4096

    path = artifact(tmp_path, bundle())
    with TestClient(api.create_app(bundle_path=path)) as client:
        response = client.post("/predict", json={"url": url})

    assert response.status_code == 200


def test_outer_whitespace_is_trimmed_before_inference(tmp_path, monkeypatch):
    path = artifact(tmp_path, bundle())
    received_urls = []
    original_predict_url = api.predict_url

    def record_trimmed_url(url, model_bundle, model_name):
        received_urls.append(url)
        return original_predict_url(url, model_bundle, model_name)

    monkeypatch.setattr(api, "predict_url", record_trimmed_url)
    with TestClient(api.create_app(bundle_path=path)) as client:
        response = client.post("/predict", json={"url": " \texample.com \r\n"})

    assert response.status_code == 200
    assert received_urls[-1] == "example.com"


def test_malformed_json_and_unknown_http_routes_use_error_envelope():
    with TestClient(api.create_app()) as client:
        r = client.post("/predict", content='{"url":', headers={"Content-Type": "application/json"})
        assert r.status_code == 422 and r.json()["error"]["reason"] == "invalid_json"
        assert client.get("/missing").json()["error"]["code"] == "NOT_FOUND"
        r = client.get("/predict")
        assert r.status_code == 405 and r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert "POST" in r.headers["allow"]


@pytest.mark.parametrize("url,reason", [
    ("http://example.com:99999", "invalid_port"), ("http://example.com:no", "invalid_port"),
    ("http://[broken/", "parse_error"), ("not_a_domain", "unresolved_domain"),
    ("http://☃.example.com/", "invalid_hostname"),
    ("ftp://example.com", "unsupported_scheme"), ("https://example.com/a b", "invalid_characters")])
def test_parser_boundary_errors_are_422_even_without_model(url, reason):
    with TestClient(api.create_app()) as client:
        r = client.post("/predict", json={"url": url})
    assert r.status_code == 422 and r.json()["error"]["reason"] == reason
    assert url not in r.text


@pytest.mark.parametrize("url", ["example.com", "https://BÜCHER.de/Path", "http://127.0.0.1/",
                                  "http://[2001:db8::1]/", "//example.com/path"])
def test_valid_parser_inputs_use_existing_inference_offline(tmp_path, monkeypatch, url):
    import socket

    def deny_network(*args, **kwargs):
        pytest.fail("Prediction attempted outbound network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    path = artifact(tmp_path, bundle())
    with TestClient(api.create_app(bundle_path=path)) as client:
        monkeypatch.setattr(socket.socket, "connect", deny_network)
        monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
        assert client.get("/health").json()["model_ready"] is True
        r = client.post("/predict", json={"url": url})
    assert r.status_code == 200
    assert r.json() == {"label": "phishing", "model": "fixture", "score": .7,
        "score_kind": "probability", "score_definition": "predict_proba cho phishing; chưa hiệu chuẩn nguy cơ thực tế",
        "decision_rule": "estimator.predict", "protocol": "synthetic-unit-test-only"}


def test_api_response_matches_python_inference_on_same_artifact(tmp_path):
    url = "https://example.com/path?source=contract-test"
    path = artifact(tmp_path, bundle())
    with TestClient(api.create_app(bundle_path=path)) as client:
        response = client.post("/predict", json={"url": url})

    direct_bundle = joblib.load(path)
    direct_result = api.predict_url(url, direct_bundle, "fixture")
    assert response.status_code == 200
    assert response.json() == direct_result


def test_api_prediction_matches_python_cli_on_same_synthetic_artifact(tmp_path):
    feature_names = list(CANDIDATE_FEATURES)
    train = pd.DataFrame(np.zeros((2, len(feature_names))), columns=feature_names)
    model = DummyClassifier(strategy="constant", constant=1).fit(train, [0, 1])
    bundle_value = {
        "feature_set": "lexical_12",
        "feature_names": feature_names,
        "selected_model": "dummy",
        "models": {"dummy": model},
        "score_kinds": {"dummy": "probability"},
        "protocol": "synthetic-cli-parity-test-only",
    }

    cli_root = tmp_path / "cli"
    scripts_dir = cli_root / "scripts"
    models_dir = cli_root / "models"
    scripts_dir.mkdir(parents=True)
    models_dir.mkdir()
    repository_root = Path(api.__file__).resolve().parents[2]
    shutil.copyfile(repository_root / "scripts" / "predict_week5.py", scripts_dir / "predict_week5.py")
    artifact_path = models_dir / "week5_readable_models.joblib"
    joblib.dump(bundle_value, artifact_path)

    url = "https://example.com/path?source=qa-cli-parity"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in [str(repository_root / "src"), env.get("PYTHONPATH", "")] if part
    )
    cli = subprocess.run(
        [sys.executable, str(scripts_dir / "predict_week5.py"), url],
        cwd=cli_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )

    with TestClient(api.create_app(bundle_path=artifact_path)) as client:
        response = client.post("/predict", json={"url": url})

    assert response.status_code == 200
    assert response.json() == json.loads(cli.stdout)


def test_margin_is_not_converted_to_probability(tmp_path):
    with TestClient(api.create_app(bundle_path=artifact(tmp_path, bundle("decision_function")))) as client:
        r = client.post("/predict", json={"url": "example.com"})
    assert r.json()["score"] == 1.25 and r.json()["score_kind"] == "decision_function"


def test_bundle_loaded_once_and_hash_exposed_without_local_path(tmp_path, monkeypatch):
    path = artifact(tmp_path, bundle()); calls = []
    original = api.joblib.load
    def tracked(stream):
        calls.append(1)
        return original(stream)
    monkeypatch.setattr(api.joblib, "load", tracked)
    with TestClient(api.create_app(bundle_path=path)) as client:
        health = client.get("/health")
        assert health.json()["artifact_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert str(path) not in health.text
        for _ in range(2): assert client.post("/predict", json={"url": "example.com"}).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize("defect", ["missing", "corrupt", "feature_order", "class_order", "v0", "sha256"])
def test_unusable_artifacts_degrade_safely(tmp_path, defect):
    b = bundle(); expected = None
    if defect == "feature_order": b["feature_names"] = list(reversed(CANDIDATE_FEATURES))
    if defect == "class_order": b["models"]["fixture"].classes_ = np.array([1, 0])
    if defect == "v0": b["feature_set"] = "e2-brand-v0"
    path = artifact(tmp_path, b)
    reason = "artifact_incompatible"
    if defect == "missing": path.unlink(); reason = "artifact_missing"
    if defect == "corrupt": path.write_bytes(b"not a pickle"); reason = "artifact_load_failed"
    if defect == "sha256": expected = "0" * 64
    with TestClient(api.create_app(bundle_path=path, expected_sha256=expected)) as client:
        h = client.get("/health").json()
        assert h["model_error"] == reason and h["model_ready"] is False
        r = client.post("/predict", json={"url": "example.com"})
        assert r.status_code == 503 and r.json()["error"]["reason"] == reason


def test_existing_e1_cache_adapter_is_not_a_training_or_teacher_export(tmp_path):
    value = {"pipeline": FixedEstimator(), "selected_model": "cached_fixture", "feature_names": list(CANDIDATE_FEATURES),
             "decision_threshold": .5, "scope": {"test_evaluated": False}}
    path = artifact(tmp_path, value)
    with TestClient(api.create_app(bundle_path=path, bundle_format="week5_e1_audit")) as client:
        assert client.get("/health").json()["protocol"] == "week5_e1_audit"
        assert client.post("/predict", json={"url": "example.com"}).json()["model"] == "cached_fixture"


def test_e2_reference_and_extractor_guard(tmp_path):
    from phishguard_vn.brand_features import E2_FEATURES, load_reference
    b = bundle(); b.update(feature_set="e2-brand-v1", feature_names=list(E2_FEATURES), brand_reference=load_reference(),
        models={"fixture": FixedEstimator(E2_FEATURES)}, extractor_source_sha256={
            n: hashlib.sha256((Path(api.__file__).parent / n).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for n in ["features.py", "url_parser.py", "brand_features.py"]})
    with TestClient(api.create_app(bundle_path=artifact(tmp_path, b))) as client:
        assert client.post("/predict", json={"url": "example.com"}).status_code == 200
    b["extractor_source_sha256"]["features.py"] = "changed"
    with TestClient(api.create_app(bundle_path=artifact(tmp_path, b))) as client:
        assert client.get("/health").json()["model_error"] == "artifact_incompatible"


def test_inference_exception_does_not_leak_input_exception_or_traceback(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    with TestClient(api.create_app(bundle_path=artifact(tmp_path, bundle()))) as client:
        def broken(*args): raise RuntimeError("secret raw-url must not escape")
        monkeypatch.setattr(api, "predict_url", broken)
        r = client.post("/predict", json={"url": "example.com/private?token=secret"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "INFERENCE_FAILED"
    assert "secret" not in r.text + caplog.text and "Traceback" not in r.text


def test_successful_prediction_does_not_log_raw_url(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    url = "https://example.com/private?token=qa-log-secret-marker"
    with TestClient(api.create_app(bundle_path=artifact(tmp_path, bundle()))) as client:
        response = client.post("/predict", json={"url": url})

    assert response.status_code == 200
    assert url not in caplog.text
    assert "qa-log-secret-marker" not in caplog.text


def test_unexpected_route_exception_uses_sanitized_internal_error(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    with TestClient(api.create_app(bundle_path=artifact(tmp_path, bundle()))) as client:
        def broken_parser(*args, **kwargs):
            raise RuntimeError("sensitive parser detail")

        monkeypatch.setattr(api, "parse_url", broken_parser)
        response = client.post("/predict", json={"url": "https://example.com/private?token=secret"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["reason"] == "internal_error"
    assert "secret" not in response.text + caplog.text
    assert "sensitive parser detail" not in response.text + caplog.text
    assert "Traceback" not in response.text


def test_cors_is_explicit_and_applies_to_errors():
    with TestClient(api.create_app(cors_origins=["http://localhost:3000"])) as client:
        r = client.post("/predict", json={"url": "example.com"}, headers={"Origin": "http://localhost:3000"})
        assert r.status_code == 503 and r.headers["access-control-allow-origin"] == "http://localhost:3000"
        r = client.options("/predict", headers={"Origin": "https://unlisted.example", "Access-Control-Request-Method": "POST"})
        assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    with pytest.raises(ValueError): api.create_app(cors_origins=["*"])
