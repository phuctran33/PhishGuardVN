"""Tạo bản QA từ implementation Hy và reference Phúc, không sửa mã bàn giao."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HY_REVISION = "f817ec96eee8f5301c06bae6c59b0059b9fe3d78"
STUDENT_REVISION = "bc3a3a7054e2f6e6e733595f40f38439784536a1"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args], text=True
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--student-root", type=Path, required=True)
    parser.add_argument("--prepare-release-assets", action="store_true", help="Chép đúng assets vào thư mục build đã được Git ignore của Hy")
    args = parser.parse_args()
    android, student = args.android_root.resolve(), args.student_root.resolve()
    if git(android, "rev-parse", "HEAD") != HY_REVISION or git(student, "rev-parse", "HEAD") != STUDENT_REVISION:
        raise SystemExit("Cần checkout đúng revision Hy/Phúc đã được QA pin.")
    qa = Path(__file__).resolve().parents[2]
    target = qa / "tests/week7/.student_mlp_android_harness"
    target.mkdir(parents=True, exist_ok=True)
    source_hashes = {}
    for rel in git(android, "ls-files", "mobile/app/lib", "mobile/app/android", "mobile/app/pubspec.lock").splitlines():
        original = android / rel
        destination = target / Path(rel).relative_to("mobile/app")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        source_hashes[rel] = hashlib.sha256(original.read_bytes()).hexdigest()
    asset_sources = {
        "brand_reference_v1.csv": android / "src/phishguard_vn/resources/brand_reference_v1.csv",
        "psl_icann_tldextract_5.4.0.txt": android / "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt",
        "mobile_parity_cases.json": android / "docs/mobile_parity_cases.json",
        "mobile_parity_cases_extra.json": android / "docs/mobile_parity_cases_extra.json",
        "teacher_v2_manifest.json": android / "artifacts/teacher_v2_android/manifest.json",
        "dart_svm_model.json": android / "artifacts/teacher_v2_android/dart_svm_model.json",
        "dart_teacher_v2_model.json": android / "artifacts/teacher_v2_android/dart_teacher_v2_model.json",
    }
    folder = student / "artifacts/student_mlp_android"
    asset_sources.update({"student_mlp.json.gz": folder / "student_mlp.json.gz", "student_mlp_manifest.json": folder / "manifest.json"})
    assets = target / "assets"
    assets.mkdir(exist_ok=True)
    records = {}
    for name, original in asset_sources.items():
        raw = original.read_bytes()
        (assets / name).write_bytes(raw)
        records[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if args.prepare_release_assets:
            relative = f"mobile/app/assets/{name}"
            if not git(android, "check-ignore", relative):
                raise SystemExit(f"Không ghi vào asset chưa được Git ignore: {relative}")
            destination = android / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert records["student_mlp.json.gz"] == manifest["model"]
    assert records["psl_icann_tldextract_5.4.0.txt"] == manifest["psl"]
    sys.path.insert(0, str(student / "src"))
    spec = importlib.util.spec_from_file_location("qa_phuc_mlp", student / "scripts/prepare_android_mlp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.load_student(folder)
    reference = json.loads((folder / "python_reference.json").read_text(encoding="utf-8"))
    for case in reference["cases"]:
        if case["status"] == "classified":
            actual = model.predict(case["url"])
            assert actual["class_id"] == case["class_id"]
            assert abs(actual["score"] - case["score"]) <= 2e-6
            case["canonical_text"] = module.student_text(case["url"])
    payload = json.loads(gzip.decompress((folder / "student_mlp.json.gz").read_bytes()))
    import math
    logit = math.fsum(max(0, b) * w for b, w in zip(payload["hidden_bias"], payload["output_weight"])) + payload["output_bias"]
    reference.update({"android_source_revision": HY_REVISION, "student_source_revision": STUDENT_REVISION,
                      "zero_vector_score": 1 / (1 + math.exp(-logit)), "assets": records})
    (assets / "qa_mlp_reference.json").write_text(json.dumps(reference, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pubspec = (android / "mobile/app/pubspec.yaml").read_text(encoding="utf-8")
    dependency = "    path: ../packages/phishguard_features"
    assert dependency in pubspec
    pubspec = pubspec.replace(dependency, "    path: " + json.dumps((android / "mobile/packages/phishguard_features").as_posix()))
    pubspec = pubspec.replace("dev_dependencies:\n", "dev_dependencies:\n  integration_test:\n    sdk: flutter\n", 1)
    (target / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
    for source, destination in [("student_mlp_tests.dart.in", "test/student_mlp_tests.dart"),
                                ("host_test.dart.in", "test/mlp_host_test.dart"),
                                ("runtime_test.dart.in", "integration_test/mlp_runtime_test.dart"),
                                ("driver.dart.in", "test_driver/mlp_driver.dart")]:
        dest = target / destination
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((qa / "tests/week7/student_mlp_runtime" / source).read_bytes())
    evidence = {"android_source_revision": HY_REVISION, "student_source_revision": STUDENT_REVISION,
                "product_source_changed": False, "source_files_sha256": source_hashes, "assets": records,
                "qa_changes": ["QA entrypoints/reference asset", "integration_test SDK dependency", "local extractor dependency path"],
                "reference_file_sha256": hashlib.sha256((folder / "python_reference.json").read_bytes()).hexdigest()}
    (target / "qa_provenance.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"harness": str(target.relative_to(qa)), "copied_source_files": len(source_hashes), "classified": 54, "rejected": 9}))


if __name__ == "__main__":
    main()
