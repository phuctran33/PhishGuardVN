"""Tạo bản chạy integration QA từ mã app Hy, không sửa checkout bàn giao."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=Path("reports/tables/week7/android_python_reference.json"))
    args = parser.parse_args()
    source = args.android_root.resolve()
    qa = Path(__file__).resolve().parents[2]
    reference = args.reference.resolve()
    data = json.loads(reference.read_text(encoding="utf-8"))
    revision = subprocess.check_output(
        ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if data["source_revision"] != revision:
        raise SystemExit("Reference phải được tạo lại từ đúng revision Hy đang kiểm.")
    if data["schema"] != "k73-live-python-reference-v1" or len(data["cases"]) != 56:
        raise SystemExit("Thiếu bộ Python Teacher 47 classified/9 rejected.")
    app = source / "mobile/app"
    target = qa / "tests/week7/.teacher_android_harness"
    target.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.check_output(
        ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source), "ls-files", "mobile/app/lib", "mobile/app/android", "mobile/app/pubspec.lock"], text=True
    ).splitlines()
    hashes = {}
    for rel in tracked:
        original = source / rel
        destination = target / Path(rel).relative_to("mobile/app")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        hashes[rel] = hashlib.sha256(original.read_bytes()).hexdigest()
    assets = target / "assets"
    assets.mkdir(exist_ok=True)
    required = ["brand_reference_v1.csv", "psl_icann_tldextract_5.4.0.txt", "teacher_v2_manifest.json", "dart_svm_model.json", "dart_teacher_v2_model.json", "mobile_parity_cases.json", "mobile_parity_cases_extra.json"]
    asset_hashes = {}
    for name in required:
        original = app / "assets" / name
        raw = original.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        expected = data["assets"].get(name, {}).get("sha256")
        if name == "teacher_v2_manifest.json":
            expected = data["asset_manifest_sha256"]
        elif name == "brand_reference_v1.csv":
            expected = data["brand_reference_sha256"]
        if expected is not None and digest != expected:
            raise SystemExit(f"Asset {name} không khớp reference.")
        shutil.copy2(original, assets / name)
        asset_hashes[name] = {"sha256": digest, "size_bytes": len(raw)}
    shutil.copy2(reference, assets / "qa_python_reference.json")
    pubspec = (app / "pubspec.yaml").read_text(encoding="utf-8")
    path_line = "    path: ../packages/phishguard_features"
    if path_line not in pubspec:
        raise SystemExit("Cần kiểm lại cấu trúc pubspec mới của Hy trước khi tạo QA app.")
    pubspec = pubspec.replace(path_line, "    path: " + json.dumps((source / "mobile/packages/phishguard_features").as_posix()))
    pubspec = pubspec.replace("dev_dependencies:\n", "dev_dependencies:\n  integration_test:\n    sdk: flutter\n", 1)
    (target / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
    for name, folder in [("teacher_runtime_test.dart", "integration_test"), ("teacher_driver.dart", "test_driver")]:
        destination = target / folder / name
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes((qa / "tests/week7/teacher_runtime" / (name + ".in")).read_bytes())
    evidence = {"schema": "k73-android-source-copy-v1", "source_revision": revision,
                "source_files_sha256": hashes, "assets": asset_hashes,
                "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                "product_source_changed": False,
                "qa_changes": ["integration_test SDK dependency", "fresh Python reference asset", "QA integration entrypoint", "local extractor dependency path"]}
    (target / "qa_provenance.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"target": str(target.relative_to(qa)), "revision": revision, "copied_source_files": len(hashes)}))


if __name__ == "__main__":
    main()
