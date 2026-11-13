"""Measure successful HTTP prediction latency and record model/artifact metadata."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import http.client
import json
import math
import platform
import ssl
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit


def _request(connection, method: str, path: str, body: bytes | None = None):
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    payload = response.read()
    return response.status, payload


def _mean_and_p95(samples_ms: list[float]) -> tuple[float, float]:
    ordered = sorted(samples_ms)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return statistics.fmean(samples_ms), p95


def _validate_prediction(body: bytes, health: dict) -> dict:
    try:
        prediction = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("POST /predict sai contract JSON; không ghi nhận benchmark.") from exc
    if not isinstance(prediction, dict):
        raise RuntimeError("POST /predict sai contract; không ghi nhận benchmark.")
    score = prediction.get("score")
    kind = prediction.get("score_kind")
    valid = (
        prediction.get("label") in ("benign", "phishing")
        and prediction.get("model") == health.get("model")
        and prediction.get("protocol") == health.get("protocol")
        and isinstance(prediction.get("score_definition"), str)
        and bool(prediction["score_definition"].strip())
        and kind in ("probability", "decision_function")
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(score)
    )
    rule = prediction.get("decision_rule")
    threshold = prediction.get("threshold")
    if valid and rule == "score >= threshold":
        valid = (
            kind == "probability"
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and math.isfinite(threshold)
            and 0 <= threshold <= math.nextafter(1., math.inf)
            and prediction["label"] == ("phishing" if score >= threshold else "benign")
        )
    elif rule == "estimator.predict":
        valid = valid and threshold is None
    else:
        valid = False
    if not valid or (kind == "probability" and not 0 <= score <= 1):
        raise RuntimeError("POST /predict sai contract hoặc model metadata; không ghi nhận benchmark.")
    return prediction


def benchmark(base_url: str, url: str, request_count: int, warmup_count: int, timeout: float) -> dict:
    parsed = urlsplit(base_url.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Base URL phải là HTTP(S), có host và không chứa thông tin đăng nhập.")
    if parsed.query or parsed.fragment:
        raise ValueError("Base URL không được có query hoặc fragment.")
    if not url.strip():
        raise ValueError("URL đo không được rỗng.")
    if request_count < 1 or warmup_count < 0 or timeout <= 0:
        raise ValueError("Số request đo, warm-up hoặc timeout không hợp lệ.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        connection = http.client.HTTPSConnection(
            parsed.hostname, port, timeout=timeout, context=ssl.create_default_context()
        )
    else:
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
    prefix = parsed.path.rstrip("/")
    health_path = f"{prefix}/health"
    predict_path = f"{prefix}/predict"

    try:
        health_status, health_body = _request(connection, "GET", health_path)
        if health_status != 200:
            raise RuntimeError(f"GET /health trả HTTP {health_status}; không đo latency.")
        try:
            health = json.loads(health_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("GET /health không trả JSON hợp lệ; không đo latency.") from exc
        if not isinstance(health, dict):
            raise RuntimeError("GET /health phải trả JSON object; không đo latency.")
        if health.get("model_ready") is not True:
            raise RuntimeError("Model chưa sẵn sàng theo /health; không đo latency inference.")
        digest = health.get("artifact_sha256")
        if not (isinstance(digest, str) and len(digest) == 64
                and all(char in "0123456789abcdefABCDEF" for char in digest)):
            raise RuntimeError("/health không cung cấp artifact_sha256; không ghi nhận benchmark.")
        if any(not isinstance(health.get(key), str) or not health[key].strip()
               for key in ("model", "protocol", "feature_set")):
            raise RuntimeError("/health thiếu model metadata; không ghi nhận benchmark.")

        payload = json.dumps({"url": url}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        for _ in range(warmup_count):
            status, response_body = _request(connection, "POST", predict_path, payload)
            if status != 200:
                raise RuntimeError(f"Warm-up trả HTTP {status}; không ghi nhận benchmark.")
            _validate_prediction(response_body, health)

        samples_ms = []
        for _ in range(request_count):
            started = time.perf_counter()
            status, response_body = _request(connection, "POST", predict_path, payload)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if status != 200:
                raise RuntimeError(f"Request đo trả HTTP {status}; không ghi nhận benchmark.")
            prediction = _validate_prediction(response_body, health)
            samples_ms.append(elapsed_ms)
    finally:
        connection.close()

    mean_ms, p95_ms = _mean_and_p95(samples_ms)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": f"{parsed.scheme}://{parsed.netloc}{prefix}",
        "method": "HTTP/1.1 keep-alive",
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "warmup_requests": warmup_count,
        "measured_requests": request_count,
        "url_length": len(url),
        "raw_url_recorded": False,
        "p95_method": "nearest-rank",
        "mean_ms": mean_ms,
        "p95_ms": p95_ms,
        "model": health.get("model"),
        "feature_set": health.get("feature_set"),
        "protocol": health.get("protocol"),
        "artifact_sha256": health.get("artifact_sha256"),
        "score_kind": prediction["score_kind"],
        "decision_rule": prediction["decision_rule"],
        "threshold": prediction.get("threshold"),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--url", required=True, help="Synthetic/non-sensitive input; it is not written to output.")
    parser.add_argument("--requests", type=int, default=100, dest="request_count")
    parser.add_argument("--warmup", type=int, default=10, dest="warmup_count")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    try:
        result = benchmark(args.base_url, args.url, args.request_count, args.warmup_count, args.timeout)
    except http.client.HTTPException:
        print("Benchmark không hoàn tất: phản hồi HTTP bị gián đoạn hoặc không hợp lệ.", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Benchmark không hoàn tất: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
