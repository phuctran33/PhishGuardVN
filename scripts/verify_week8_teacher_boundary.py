"""Capture frozen Teacher HTTP/feature outputs or compare them to a clean base."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

from fastapi.testclient import TestClient

URLS = (
    "example.com",
    "https://www.vietcombank.com.vn/",
    "https://vietcombank-verify.example.net/login/secure?mode=demo",
    "https://www.google.com/",
    "https://bücher.de/Über?src=demo",
    "http://192.0.2.1/account",
    "https://[2001:db8::1]/",
    "https://EXAMPLE.COM:443/Aa?k=v",
    "https://a.example.org:8080/",
    "https://example.com:bad/path",
    "ftp://example.com/x",
    "https://napas-verify.example.net/account",
)


def snapshot(root: Path) -> dict:
    # One checkout per process so the chosen source is used, even with an
    # editable installation pointing to the feature worktree.
    sys.path.insert(0, str(root / "src"))
    from phishguard_vn.api import create_app
    from phishguard_vn.brand_features import E2_FEATURES
    from phishguard_vn.stacking import raw_frame

    release = json.loads((root / "configs/teacher_lock.json").read_text(encoding="utf-8"))
    candidate_path = release["candidate_lock"]["path"]
    candidate = json.loads((root / candidate_path).read_text(encoding="utf-8"))
    files = {
        candidate_path: release["candidate_lock"]["sha256"],
        release["bundle"]["path"]: release["bundle"]["sha256"],
        "src/phishguard_vn/resources/brand_reference_v1.csv": candidate["reference_sha256"],
        **{f"src/phishguard_vn/{name}": digest for name, digest in candidate["source_sha256"].items()},
    }
    actual = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in files}
    assert actual == files
    assert candidate["feature_names"] == list(E2_FEATURES)
    for path in (
        "configs/teacher_lock.json",
        "artifacts/student_mlp_android/student_mlp.json.gz",
        "artifacts/student_mlp_android/manifest.json",
    ):
        actual[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
    with TestClient(create_app(bundle_format="teacher", teacher_root=root)) as client:
        health = client.get("/health").json()
        assert health["model_ready"] and health["model"] == release["model_version"]
        records = []
        for url in URLS:
            response = client.post("/predict", json={"url": url})
            assert response.status_code in {200, 422}
            if response.status_code == 200:
                assert response.json()["threshold"] == release["threshold"]
                assert response.json()["decision_rule"] == release["decision_rule"]
            records.append({"url": url, "status": response.status_code, "json": response.json()})
    valid = [row["url"] for row in records if row["status"] == 200]
    matrix = raw_frame(valid)[list(E2_FEATURES)]
    return {
        "base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "python": platform.python_version(), "health": health, "sha256": actual,
        "e2_order": list(E2_FEATURES), "e2_values": matrix.to_numpy().tolist(), "rows": records,
    }


def verify(reference, current):
    for key in ("health", "sha256", "e2_order", "e2_values"):
        assert current[key] == reference[key], key
    before, after = reference["rows"], current["rows"]
    assert len(before) == len(after) == len(URLS)
    score_differences = []
    for left, right in zip(before, after):
        assert left["url"] == right["url"] and left["status"] == right["status"]
        a, b = left["json"].copy(), right["json"].copy()
        if left["status"] == 200:
            score_differences.append(abs(a.pop("score") - b.pop("score")))
        assert a == b, left["url"]
    assert score_differences and max(score_differences) <= 1e-12
    return {
        "baseline_revision": reference["base_revision"], "execution_revision": current["base_revision"],
        "python": current["python"], "health": current["health"],
        "sha256": current["sha256"], "feature_order": current["e2_order"],
        "e2_rows_identical": len(current["e2_values"]),
        "http_cases_equal": len(after), "valid": len(score_differences),
        "invalid": len(after) - len(score_differences),
        "max_abs_score_difference": max(score_differences), "score_atol": 1e-12,
        "predictions": [
            {k: v for k, v in row.items() if k != "url"} | {"fixture_id": i}
            for i, row in enumerate(after, start=1)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    result = snapshot(args.root.resolve())
    if args.compare:
        result = verify(json.loads(args.compare.read_text(encoding="utf-8")), result)
    with args.out.open("w", newline="\n", encoding="utf-8") as out:
        out.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(args.out)


if __name__ == "__main__":
    main()
