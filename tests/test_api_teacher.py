"""API integration with the official release loader; fixtures never count as demo."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from phishguard_vn.api import PredictionResponse, create_app
from phishguard_vn import teacher as teacher_module

ROOT = Path(__file__).resolve().parents[1]


def release_copy(tmp_path):
    for name in ["configs/teacher_lock.json", "configs/teacher_v2_candidate_lock.json"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    lock = json.loads((tmp_path / "configs/teacher_lock.json").read_text())
    target = tmp_path / lock["bundle"]["path"]
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / lock["bundle"]["path"], target)
    return lock


@pytest.mark.parametrize("score,label", [(.6, "benign"), (.7, "phishing")])
def test_nondefault_threshold_and_inclusive_boundary_are_owned_by_adapter(tmp_path, monkeypatch, score, label):
    lock = release_copy(tmp_path)
    lock["threshold"] = .7  # Explicit synthetic operating point for this test only.
    (tmp_path / "configs/teacher_lock.json").write_text(json.dumps(lock))
    calls, urls = [], []

    class Fixture:
        def predict_one(self, url):
            urls.append(url)
            return dict(label=label, score=score, threshold=.7, score_kind="probability",
                        score_definition="Synthetic uncalibrated LR fixture",
                        decision_rule="score >= threshold", model_version=lock["model_version"],
                        preprocessing_version="fixture-only", promoted=True, candidate_only=False)

    def load(root):
        calls.append(root)
        return Fixture()

    monkeypatch.setattr(teacher_module, "load_teacher", load)
    with TestClient(create_app(bundle_format="teacher", teacher_root=tmp_path)) as client:
        assert client.get("/health").json()["model_ready"]
        for _ in range(2):
            r = client.post("/predict", json={"url": "  EXAMPLE.com/Case?Q=A  "})
            assert r.status_code == 200
            assert r.json()["label"] == label
            assert r.json()["score"] == score and r.json()["threshold"] == .7
            assert r.json()["decision_rule"] == "score >= threshold"
        schema = client.get("/openapi.json").json()["components"]["schemas"]["PredictionResponse"]
        assert "threshold" in schema["properties"]
    assert len(calls) == 1 and urls == ["https://example.com", "EXAMPLE.com/Case?Q=A", "EXAMPLE.com/Case?Q=A"]


@pytest.mark.parametrize("defect", ["missing_lock", "missing_artifact", "hash", "runtime", "metadata", "reference", "pin"])
def test_official_loader_guards_remain_active_in_api(tmp_path, defect):
    lock = release_copy(tmp_path)
    lock_path = tmp_path / "configs/teacher_lock.json"
    candidate_path = tmp_path / lock["candidate_lock"]["path"]
    expected = None
    if defect == "missing_lock":
        lock_path.unlink()
    elif defect == "missing_artifact":
        (tmp_path / lock["bundle"]["path"]).unlink()
    elif defect == "hash":
        (tmp_path / lock["bundle"]["path"]).write_bytes(b"changed synthetic test copy")
    elif defect == "runtime":
        lock["python_runtime"]["minor"] = 12
    elif defect == "metadata":
        lock["teacher_finalized"] = False
    elif defect == "reference":
        candidate = json.loads(candidate_path.read_text())
        candidate["reference_fingerprint"] = "changed"
        candidate_path.write_text(json.dumps(candidate))
        lock["candidate_lock"]["sha256"] = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    elif defect == "pin":
        expected = "0" * 64
    if defect != "missing_lock":
        lock_path.write_text(json.dumps(lock))
    with TestClient(create_app(bundle_format="teacher", teacher_root=tmp_path, expected_sha256=expected)) as client:
        health = client.get("/health").json()
        assert not health["model_ready"] and health["model"] is None
        r = client.post("/predict", json={"url": "example.com"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_UNAVAILABLE"
        assert str(tmp_path) not in r.text and "score" not in r.json()


def test_real_released_teacher_warmup_and_prediction_are_offline(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        pytest.fail("Teacher inference must not access target DNS/network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with TestClient(create_app(bundle_format="teacher", teacher_root=ROOT)) as client:
        health = client.get("/health").json()
        lock = json.loads((ROOT / "configs/teacher_lock.json").read_text())
        assert health["model_ready"] and health["model"] == lock["model_version"]
        assert health["artifact_sha256"] == lock["bundle"]["sha256"]
        r = client.post("/predict", json={"url": "https://EXAMPLE.com/Case?Q=A"})
        assert r.status_code == 200
        assert r.json()["threshold"] == lock["threshold"]
        assert r.json()["protocol"] == lock["operating_point_scope"]
        assert r.json()["decision_rule"] == lock["decision_rule"]


def test_failed_teacher_warmup_never_marks_ready(tmp_path, monkeypatch):
    release_copy(tmp_path)
    class Broken:
        def predict_one(self, url):
            raise RuntimeError("sensitive local path/raw URL")
    monkeypatch.setattr(teacher_module, "load_teacher", lambda root: Broken())
    with TestClient(create_app(bundle_format="teacher", teacher_root=tmp_path)) as client:
        assert client.get("/health").json()["model_ready"] is False
        r = client.post("/predict", json={"url": "example.com"})
        assert r.status_code == 503 and "sensitive" not in r.text


@pytest.mark.parametrize("changes", [{"threshold": None}, {"threshold": float("nan")},
    {"decision_rule": "arbitrary"}, {"score_kind": "decision_function"}])
def test_invalid_threshold_response_contract_is_rejected(changes):
    value = dict(label="benign", model="fixture", score=.6, score_kind="probability",
                 score_definition="fixture", protocol="fixture", threshold=.7,
                 decision_rule="score >= threshold")
    with pytest.raises(ValueError):
        PredictionResponse.model_validate(value | changes)
