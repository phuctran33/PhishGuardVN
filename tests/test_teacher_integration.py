"""QA độc lập cho Teacher phát hành và API; không train hoặc sửa artifact."""
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from phishguard_vn import api

pytestmark = pytest.mark.teacher


@pytest.fixture(scope="module")
def teacher_module(teacher_root):
    return importlib.import_module("phishguard_vn.teacher")


@pytest.fixture(scope="module")
def teacher_lock(teacher_root):
    return json.loads((teacher_root / "configs/teacher_lock.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_teacher(teacher_module, teacher_root):
    return teacher_module.load_teacher(teacher_root)


@pytest.fixture(scope="module")
def teacher_urls():
    prefix = "https://example.com/"
    return [
        "https://example.com/login", "example.com", "https://EXAMPLE.com/Case?Q=A",
        "https://example.com/a%2Fb?q=hello%20world", "https://example.com:8443/path",
        "https://bücher.de/đăng-nhập", "https://xn--bcher-kva.de/a",
        "http://192.0.2.1/login", "http://[2001:db8::1]/login",
        "https://www.hcmus.edu.vn", "https://example.com/a?next=https%3A%2F%2Fexample.net",
        "https://user@example.com/Case#fragment", prefix + "a" * (4096 - len(prefix)),
    ]


def test_release_lock_hashes_and_promotion(teacher_root, teacher_lock, real_teacher):
    assert teacher_lock["teacher_finalized"] is True and teacher_lock["promoted"] is True
    for name in ("bundle", "candidate_lock"):
        record = teacher_lock[name]
        assert hashlib.sha256((teacher_root / record["path"]).read_bytes()).hexdigest() == record["sha256"]
    row = real_teacher.predict_one("example.com")
    assert row["model_version"] == teacher_lock["model_version"]
    assert row["promoted"] is True and row["candidate_only"] is False
    assert row["threshold"] == teacher_lock["threshold"]


def test_real_teacher_single_batch_and_official_cli_parity(real_teacher, teacher_root, teacher_urls, tmp_path):
    batch = real_teacher.predict_batch(teacher_urls)
    single = [real_teacher.predict_one(url) for url in teacher_urls]
    completed = subprocess.run(
        [sys.executable, str(teacher_root / "scripts/predict_teacher.py"), *teacher_urls],
        cwd=tmp_path, env=dict(os.environ, PYTHONIOENCODING="utf-8", OMP_NUM_THREADS="1"),
        capture_output=True, text=True, encoding="utf-8", timeout=60, check=True,
    )
    cli = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert len(cli) == len(batch) == len(single) == 13
    for expected, one, command in zip(batch, single, cli):
        for actual in (one, command):
            assert actual["label"] == expected["label"]
            assert actual["score"] == pytest.approx(expected["score"], abs=1e-12, rel=0)
            assert actual["threshold"] == expected["threshold"]
            assert actual["decision_rule"] == expected["decision_rule"]


def test_real_teacher_labels_follow_locked_operating_point(real_teacher, teacher_urls, teacher_lock):
    for row in real_teacher.predict_batch(teacher_urls):
        assert row["score_kind"] == "probability"
        assert row["decision_rule"] == "score >= threshold"
        assert 0 <= row["score"] <= 1
        assert row["threshold"] == teacher_lock["threshold"]
        assert row["label"] == ("phishing" if row["score"] >= row["threshold"] else "benign")


@pytest.mark.parametrize("values", [None, 42, {}, [None], [""], [" "], ["https://example.com:99999"]])
def test_real_teacher_rejects_invalid_inputs(real_teacher, values):
    with pytest.raises((TypeError, ValueError)):
        real_teacher.predict_batch(values)


def _forbid_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Offline inference attempted DNS/socket access")
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)


def test_real_teacher_load_predict_offline_and_no_raw_logging(teacher_module, teacher_root, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    _forbid_network(monkeypatch)
    raw = "https://example.com/private?token=qa-secret-not-for-logs"
    teacher_module.load_teacher(teacher_root).predict_one(raw)
    assert raw not in caplog.text and "qa-secret-not-for-logs" not in caplog.text


def _copy_release(root, destination):
    lock = json.loads((root / "configs/teacher_lock.json").read_text(encoding="utf-8"))
    for name in ("configs/teacher_lock.json", lock["candidate_lock"]["path"], lock["bundle"]["path"]):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    return lock


@pytest.mark.parametrize("field,value", [("promoted", False), ("teacher_finalized", False),
                                         ("model_version", "unknown"), ("threshold", 0.5)])
def test_release_rejects_changed_protocol(teacher_root, teacher_module, tmp_path, field, value):
    lock = _copy_release(teacher_root, tmp_path)
    lock[field] = value
    (tmp_path / "configs/teacher_lock.json").write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        teacher_module.load_teacher(tmp_path)


def test_release_rejects_changed_bundle(teacher_root, teacher_module, tmp_path):
    lock = _copy_release(teacher_root, tmp_path)
    (tmp_path / lock["bundle"]["path"]).write_bytes(b"corrupt QA fixture copy")
    with pytest.raises(ValueError):
        teacher_module.load_teacher(tmp_path)


def test_release_rejects_wrong_python_runtime(teacher_root, teacher_module, tmp_path):
    lock = _copy_release(teacher_root, tmp_path)
    lock["python_runtime"]["minor"] = 12
    (tmp_path / "configs/teacher_lock.json").write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CPython"):
        teacher_module.load_teacher(tmp_path)


@pytest.fixture(scope="module")
def teacher_api(teacher_root, teacher_lock):
    source_root = Path(api.__file__).resolve().parents[2]
    assert source_root == teacher_root, "Cài backend từ checkout release được chọn trước khi chạy QA."
    with TestClient(api.create_app(bundle_format="teacher", teacher_root=teacher_root,
                                  expected_sha256=teacher_lock["bundle"]["sha256"])) as client:
        health = client.get("/health").json()
        assert health["model_ready"] is True, health
        assert health["artifact_sha256"] == teacher_lock["bundle"]["sha256"]
        assert health["model"] == teacher_lock["model_version"]
        yield client


@pytest.mark.teacher_api
@pytest.mark.parametrize("index", range(13))
def test_api_matches_released_python_and_cli(teacher_api, real_teacher, teacher_urls, teacher_lock, index):
    url = teacher_urls[index]
    expected = real_teacher.predict_one(url)
    response = teacher_api.post("/predict", json={"url": url})
    assert response.status_code == 200, response.text
    actual = response.json()
    assert set(actual) == {"label", "model", "score", "score_kind", "score_definition",
                           "decision_rule", "protocol", "threshold"}
    for key in ("label", "score_kind", "score_definition", "decision_rule", "threshold"):
        assert actual[key] == expected[key]
    assert actual["score"] == pytest.approx(expected["score"], abs=1e-12, rel=0)
    assert actual["model"] == teacher_lock["model_version"]
    assert actual["protocol"] == teacher_lock["operating_point_scope"]


@pytest.mark.teacher_api
def test_api_trims_outer_whitespace_and_keeps_teacher_rule(teacher_api, real_teacher):
    url = "https://EXAMPLE.com/Case?Q=A"
    response = teacher_api.post("/predict", json={"url": " \t" + url + "\r\n"})
    assert response.status_code == 200
    expected = real_teacher.predict_one(url)
    assert response.json()["score"] == pytest.approx(expected["score"], abs=1e-12, rel=0)
    assert response.json()["label"] == expected["label"]


@pytest.mark.teacher_api
def test_real_api_prediction_offline_without_raw_url_logs(teacher_api, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    _forbid_network(monkeypatch)
    raw = "https://example.com/private?token=api-secret-not-for-logs"
    response = teacher_api.post("/predict", json={"url": raw})
    assert response.status_code == 200
    assert raw not in caplog.text and "api-secret-not-for-logs" not in caplog.text
