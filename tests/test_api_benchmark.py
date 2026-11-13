import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
from threading import Thread

import pytest


@pytest.fixture
def api_stub():
    state = {"model_ready": True, "posts": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({
                "model_ready": state["model_ready"],
                "model": "fixture-model" if state["model_ready"] else None,
                "feature_set": "lexical_12" if state["model_ready"] else None,
                "protocol": "synthetic-benchmark-test" if state["model_ready"] else None,
                "artifact_sha256": "a" * 64 if state["model_ready"] else None,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            state["posts"] += 1
            size = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(size)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

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
