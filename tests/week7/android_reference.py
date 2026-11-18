"""K7.3: tạo reference từ released Teacher đang chạy, không train hoặc chấm dataset."""

import argparse
from contextlib import ExitStack
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
from unittest.mock import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.android_root.resolve()
    sys.path.insert(0, str(root / "src"))
    from phishguard_vn.brand_features import E2_FEATURES
    from phishguard_vn.teacher import load_teacher

    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    folder = root / "artifacts/teacher_v2_android"
    manifest = read(folder / "manifest.json")
    lock = read(root / "configs/teacher_lock.json")
    assert manifest["model_version"] == lock["model_version"] == "teacher-stacking-v2"
    assert manifest["threshold"] == lock["threshold"] == 0.6945740700635259
    assert manifest["decision_rule"] == lock["decision_rule"] == "score >= threshold"
    assert manifest["source_bundle_sha256"] == lock["bundle"]["sha256"]
    assert sha(root / lock["bundle"]["path"]) == manifest["source_bundle_sha256"]
    assert manifest["feature_order"] == list(E2_FEATURES)
    assert manifest["members_order"] == ["svm", "hist"]
    assert manifest["class_mapping"] == {"benign": 0, "phishing": 1}
    assert sha(root / "src/phishguard_vn/resources/brand_reference_v1.csv") == manifest["brand_reference_sha256"]
    for name, info in manifest["files"].items():
        path = folder / name
        assert path.stat().st_size == info["size_bytes"] and sha(path) == info["sha256"], name

    frozen_path = root / "mobile/packages/phishguard_features/test/fixtures/teacher_v2_pipeline_reference.json"
    frozen = read(frozen_path)
    inputs = [(case["name"], case["url"], "frozen") for case in frozen["cases"]]
    seen = {url for _, url, _ in inputs}
    for i, url in enumerate([
        "HTTPS://EXAMPLE.COM/Login?Q=%2F",
        "//example.com/path?Q=A",
        "https://user:password@example.com:8443/login#fragment",
        "https://bücher.de/Đăng-nhập?q=%2F",
        "http://[2001:db8::1]:8080/login",
        "https://example.com/a b?Q=A",
        "", "   ", " example.com", "example.com ",
        "https://example.com:99999", "http://bad host.com", "https://",
        "https://example.com/a\x00b", "https://example.com/a\tb",
    ]):
        if url not in seen:
            inputs.append((f"qa_probe_{i}", url, "qa_synthetic"))
            seen.add(url)

    def forbidden(*args, **kwargs):
        raise AssertionError("Python Teacher attempted network access")

    cases = []
    with ExitStack() as guards:
        for owner, name in [(socket, "getaddrinfo"), (socket.socket, "connect"),
                            (socket.socket, "connect_ex")]:
            guards.enter_context(patch.object(owner, name, forbidden))
        teacher = load_teacher(root)
        for name, url, scope in inputs:
            try:
                prediction = teacher.predict_one(url)
            except (ValueError, TypeError) as exc:
                assert scope != "frozen", (name, str(exc))
                cases.append(dict(name=name, url=url, scope=scope,
                                  status="rejected", exception=type(exc).__name__))
            else:
                assert prediction["model_version"] == manifest["model_version"]
                assert prediction["threshold"] == lock["threshold"]
                assert prediction["decision_rule"] == lock["decision_rule"]
                assert prediction["class_id"] == int(prediction["score"] >= lock["threshold"])
                cases.append(dict(name=name, url=url, scope=scope, status="classified",
                                  score=prediction["score"], class_id=prediction["class_id"],
                                  label=prediction["label"]))
    revision = subprocess.check_output(["git", "-c", "safe.directory=" + root.as_posix(),
        "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    report = dict(schema="k73-live-python-reference-v1", source_revision=revision,
        runtime=dict(python=platform.python_version(), packages={name: version(name)
            for name in ["numpy", "scipy", "scikit-learn", "joblib", "tldextract", "idna"]}),
        model_version=manifest["model_version"], threshold=manifest["threshold"],
        decision_rule=manifest["decision_rule"], feature_order=manifest["feature_order"],
        source_bundle_sha256=manifest["source_bundle_sha256"],
        brand_reference_sha256=manifest["brand_reference_sha256"],
        asset_manifest_sha256=sha(folder / "manifest.json"),
        assets=manifest["files"], frozen_fixture_sha256=sha(frozen_path),
        python_network_guard=True, project_training=False, cases=cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The QA repository is not the Android Flutter package. Materialize the test
    # in the target's generated directory so compiler/analyzer use its packages.
    template = Path(__file__).with_name("android_teacher_qa_test.dart.in")
    dart_test = root / "mobile/app/.dart_tool/week7_teacher_qa_test.dart"
    dart_test.parent.mkdir(parents=True, exist_ok=True)
    dart_test.write_bytes(template.read_bytes())
    print(json.dumps(dict(output=str(args.output), revision=revision,
        dart_test=str(dart_test),
        classified=sum(c["status"] == "classified" for c in cases),
        rejected=sum(c["status"] == "rejected" for c in cases)), ensure_ascii=False))


if __name__ == "__main__":
    main()
