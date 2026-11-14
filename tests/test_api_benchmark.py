import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import runpy
import subprocess
import sys
from threading import Thread

import pytest


@pytest.fixture
def api_stub():
    state = {
        "model_ready": True,
        "posts": 0,
        "prediction": {
            "label": "phishing", "model": "fixture-model", "score": 0.7,
            "score_kind": "probability", "score_definition": "Synthetic fixture probability",
            "decision_rule": "estimator.predict", "protocol": "synthetic-benchmark-test",
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            health = {
                "model_ready": state["model_ready"],
                "model": "fixture-model" if state["model_ready"] else None,
                "feature_set": "lexical_12" if state["model_ready"] else None,
                "protocol": "synthetic-benchmark-test" if state["model_ready"] else None,
                "artifact_sha256": "a" * 64 if state["model_ready"] else None,
            }
            body = json.dumps(state.get("health_body", health)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            state["posts"] += 1
            size = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(size)
            body = json.dumps(state["prediction"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body) + (10 if state.get("disconnect") else 0)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def _run_benchmark(tmp_path, base_url, *, requests=4, warmup=1):
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "benchmark_api_latency.py"
    output = tmp_path / "latency.json"
    command = [
        sys.executable,
        str(script),
        "--base-url",
        base_url,
        "--url",
        "https://example.com/benchmark?token=raw-url-secret",
        "--requests",
        str(requests),
        "--warmup",
        str(warmup),
        "--output",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=15)
    return completed, output


def test_latency_cli_records_stats_and_artifact_without_recording_raw_url(tmp_path, api_stub):
    base_url, state = api_stub
    completed, output = _run_benchmark(tmp_path, base_url)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["measured_requests"] == 4
    assert result["warmup_requests"] == 1
    assert result["artifact_sha256"] == "a" * 64
    assert result["raw_url_recorded"] is False
    assert "raw-url-secret" not in completed.stdout
    assert result["mean_ms"] >= 0
    assert result["p95_ms"] >= 0
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert state["posts"] == 5


def test_latency_cli_refuses_to_measure_when_model_is_not_ready(tmp_path, api_stub):
    base_url, state = api_stub
    state["model_ready"] = False
    completed, output = _run_benchmark(tmp_path, base_url, requests=2, warmup=0)

    assert completed.returncode == 2
    assert "Model chưa sẵn sàng" in completed.stderr
    assert "raw-url-secret" not in completed.stderr
    assert not output.exists()
    assert state["posts"] == 0


@pytest.mark.parametrize("defect", ["empty", "model", "nonfinite", "probability-range"])
def test_latency_cli_refuses_invalid_success_response(tmp_path, api_stub, defect):
    base_url, state = api_stub
    if defect == "empty":
        state["prediction"] = {}
    elif defect == "model":
        state["prediction"]["model"] = "another-artifact"
    elif defect == "nonfinite":
        state["prediction"]["score"] = float("nan")
    else:
        state["prediction"]["score"] = 1.5
    completed, output = _run_benchmark(tmp_path, base_url, requests=2, warmup=0)
    assert completed.returncode == 2
    assert "contract" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "raw-url-secret" not in completed.stdout + completed.stderr
    assert not output.exists()


@pytest.mark.parametrize("margin", [-1.75, 1.25])
def test_latency_cli_accepts_signed_margin(tmp_path, api_stub, margin):
    base_url, state = api_stub
    state["prediction"].update(
        score=margin, score_kind="decision_function", label="benign" if margin < 0 else "phishing"
    )
    completed, output = _run_benchmark(tmp_path, base_url, requests=2, warmup=0)
    assert completed.returncode == 0, completed.stderr
    assert output.is_file()


def test_latency_cli_handles_connection_loss_without_traceback(tmp_path, api_stub):
    base_url, state = api_stub
    state["disconnect"] = True
    completed, output = _run_benchmark(tmp_path, base_url, requests=2, warmup=0)
    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert "raw-url-secret" not in completed.stdout + completed.stderr
    assert not output.exists()


def test_latency_cli_rejects_nonobject_health(tmp_path, api_stub):
    base_url, state = api_stub
    state["health_body"] = []
    completed, output = _run_benchmark(tmp_path, base_url)
    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert not output.exists()
    assert state["posts"] == 0


def test_latency_uses_nearest_rank_p95():
    script = Path(__file__).resolve().parents[1] / "scripts/benchmark_api_latency.py"
    summarize = runpy.run_path(str(script))["_mean_and_p95"]
    assert summarize(list(range(1, 21))) == (10.5, 19)


@pytest.mark.parametrize("score,label", [(0.6, "benign"), (0.7, "phishing"), (0.8, "phishing")])
def test_latency_accepts_released_teacher_threshold(tmp_path, api_stub, score, label):
    base_url, state = api_stub
    state["prediction"].update(score=score, label=label, threshold=0.7,
                               decision_rule="score >= threshold")
    completed, output = _run_benchmark(tmp_path, base_url, requests=2, warmup=0)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["threshold"] == 0.7
    assert report["decision_rule"] == "score >= threshold"


@pytest.mark.parametrize("changes", [
    {"threshold": None}, {"threshold": True}, {"threshold": float("nan")},
    {"threshold": 2.0}, {"score_kind": "decision_function"},
    {"label": "phishing"}, {"decision_rule": "unknown"},
])
def test_latency_rejects_invalid_released_teacher_contract(tmp_path, api_stub, changes):
    base_url, state = api_stub
    state["prediction"].update(score=0.6, label="benign", threshold=0.7,
                               decision_rule="score >= threshold")
    state["prediction"].update(changes)
    completed, output = _run_benchmark(tmp_path, base_url, requests=2, warmup=0)
    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert not output.exists()
