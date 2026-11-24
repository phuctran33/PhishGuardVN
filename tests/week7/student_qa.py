"""K7.4: kiểm độc lập Student đã xuất, không train hoặc yêu cầu Teacher cache.

Chạy trực tiếp bằng Python của checkout Student; không tự collect trong suite W6.
"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from phishguard_vn import student_lightgbm as student
from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.student import student_text


MODES = ("hard_only", "kd_mixed")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def root():
    value = Path(student.__file__).resolve().parents[2]
    assert (value / "artifacts/student_lightgbm/manifest.json").is_file(), (
        "Dùng Python của checkout Student đã cài editable; không dùng venv QA tuần 6."
    )
    return value


@pytest.fixture(scope="module")
def folder(root):
    return root / "artifacts/student_lightgbm"


@pytest.fixture(scope="module")
def manifest(folder):
    return read_json(folder / "manifest.json")


@pytest.fixture(scope="module")
def references(folder):
    return read_json(folder / "python_reference.json")["cases"]


@pytest.fixture(scope="module", params=MODES)
def model(request, root):
    return student.load_lightgbm_student(root, request.param)


def test_manifest_covers_packaged_assets_and_frozen_teacher(root, folder, manifest):
    required = {"features.json", "python_reference.json", "brand_reference_v1.csv",
                "psl_icann_tldextract_5.4.0.txt"}
    required |= {f"{mode}{suffix}" for mode in MODES for suffix in (".json", ".model.txt")}
    assert required <= manifest["bundle_files_sha256"].keys()
    for name, expected in manifest["bundle_files_sha256"].items():
        assert digest(folder / name) == expected, name
    for group in ("input_sha256", "inference_source_sha256", "runtime_assets_sha256"):
        for name, expected in manifest[group].items():
            assert digest(root / name) == expected, name
    assert digest(folder / "brand_reference_v1.csv") == digest(
        root / "src/phishguard_vn/resources/brand_reference_v1.csv")
    assert digest(folder / "psl_icann_tldextract_5.4.0.txt") == digest(
        root / "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt")
    assert manifest["teacher_retrained"] is False
    assert manifest["teacher_release_unchanged"] is True
    assert manifest["official_test_evaluated"] is False
    assert manifest["external_evaluated"] is False
    assert manifest["student_default"] is False
    assert manifest["android_verified"] is False
    assert digest(root / "models/teacher_v2_candidate.joblib") == (
        "63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1")


def test_feature_layout_and_fixture_coverage(folder, references):
    features = read_json(folder / "features.json")
    assert len(features["terms"]) == len(features["idf"]) == 8192
    assert len(set(features["terms"])) == 8192
    assert features["feature_order"] == list(E2_FEATURES)
    assert len(features["feature_order"]) == 20
    assert features["ngram_range"] == [3, 5]
    assert features["lowercase"] is False
    assert features["sublinear_tf"] is True
    assert features["norm"] == "l2"
    assert sum(case["status"] == "classified" for case in references) == 52
    assert sum(case["status"] == "rejected" for case in references) == 6


def test_all_reference_fields_and_sklearn_native_json_parity(model, folder, manifest, references):
    mode = model.bundle["mode"]
    valid = [case for case in references if case["status"] == "classified"]
    urls = [case["url"] for case in valid]
    features = read_json(folder / "features.json")
    # Dựng TF-IDF từ vocabulary/IDF cố định, không fit vectorizer/model.
    vectorizer = TfidfVectorizer(
        analyzer="char", ngram_range=(3, 5), lowercase=False, sublinear_tf=True,
        vocabulary={term: i for i, term in enumerate(features["terms"])}, norm="l2")
    vectorizer.idf_ = np.asarray(features["idf"])
    texts = [student_text(url) for url in urls]
    text_matrix = vectorizer.transform(texts)
    e2 = student.e2_matrix(urls)
    matrix = hstack([text_matrix, csr_matrix(e2)], format="csr")
    native = lgb.Booster(model_file=str(folder / manifest["models"][mode]["native"]))
    assert native.num_trees() == model.bundle["tree_count"] == 400
    assert native.num_feature() == matrix.shape[1] == 8212
    native_scores = native.predict(matrix, num_threads=1)
    actual = model.predict_batch(urls)
    np.testing.assert_allclose([r["score"] for r in actual], native_scores, rtol=0, atol=1e-12)
    assert model.threshold == manifest["models"][mode]["threshold"]
    for i, (case, result) in enumerate(zip(valid, actual)):
        expected = case["expected"][mode]
        assert texts[i] == case["canonical_text"], case["name"]
        np.testing.assert_allclose(e2[i], case["e2"], rtol=0, atol=1e-12)
        row = text_matrix.getrow(i)
        ordered = sorted(zip(row.indices, row.data))
        assert [int(index) for index, _ in ordered] == case["text_indices"], case["name"]
        np.testing.assert_allclose([v for _, v in ordered], case["text_values"], rtol=0, atol=1e-12)
        assert set(result) == set(expected)
        for key in expected:
            if key == "score":
                assert result[key] == pytest.approx(expected[key], abs=1e-12), case["name"]
            else:
                assert result[key] == expected[key], (case["name"], key)
        assert result["class_id"] == int(result["score"] >= model.threshold)
        assert result["label"] == ("phishing" if result["class_id"] else "benign")
        assert np.isfinite(result["score"]) and 0 <= result["score"] <= 1
        assert model.predict_one(case["url"]) == result
    for case in references:
        if case["status"] == "rejected":
            with pytest.raises((ValueError, TypeError)):
                model.predict_one(case["url"])


@pytest.mark.parametrize("value", [False, 42, {}, [], " https://example.com", "example.com ",
                                       "https://example.com/a\x00b", "https://example.com/a\tb"])
def test_additional_invalid_inputs_do_not_return_a_prediction(model, value):
    with pytest.raises((ValueError, TypeError)):
        model.predict_one(value)


@pytest.mark.parametrize("side", ["below", "equal", "above"])
def test_decision_at_locked_threshold(model, monkeypatch, side):
    threshold = model.threshold
    score = {"below": np.nextafter(threshold, -np.inf), "equal": threshold,
             "above": np.nextafter(threshold, np.inf)}[side]
    monkeypatch.setattr(model, "score_row", lambda row: float(score))
    result = model.predict_one("example.com")
    assert result["threshold"] == threshold
    assert result["class_id"] == int(side != "below")
    assert result["label"] == ("benign" if side == "below" else "phishing")


def test_inference_without_network_teacher_or_training(root, monkeypatch):
    from phishguard_vn import teacher
    from sklearn.pipeline import Pipeline
    import requests

    def forbidden(*args, **kwargs):
        raise AssertionError("Student inference gọi network/Teacher hoặc fit model")

    for owner, name in [(socket, "getaddrinfo"), (socket.socket, "connect"),
                        (socket.socket, "connect_ex"), (requests.Session, "request"),
                        (joblib, "load"), (teacher, "load_teacher"),
                        (Pipeline, "fit"), (lgb.LGBMRegressor, "fit")]:
        monkeypatch.setattr(owner, name, forbidden)
    for mode in MODES:
        predictor = student.load_lightgbm_student(root, mode)
        assert len(predictor.predict_batch(["example.com", "https://bücher.de/", "http://[2001:db8::1]/"])) == 3


def test_default_mode_and_unknown_mode(root, manifest):
    assert student.load_lightgbm_student(root).bundle["mode"] == manifest["selected_mode"] == "kd_mixed"
    with pytest.raises(ValueError, match="Unknown"):
        student.load_lightgbm_student(root, "not-a-mode")


@pytest.fixture
def copied_bundle(root, manifest, tmp_path):
    names = {"artifacts/student_lightgbm/manifest.json"}
    names.update(manifest["inference_source_sha256"])
    names.update(manifest["runtime_assets_sha256"])
    names.update("artifacts/student_lightgbm/" + name for name in manifest["inference_files_sha256"])
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    return tmp_path


@pytest.mark.parametrize("name", ["features.json", "kd_mixed.json", "hard_only.json",
                                     "brand_reference_v1.csv", "psl_icann_tldextract_5.4.0.txt"])
def test_tampered_inference_assets_are_rejected(copied_bundle, name):
    target = copied_bundle / "artifacts/student_lightgbm" / name
    target.write_bytes(target.read_bytes() + b"\n ")
    with pytest.raises(ValueError, match="Artifact changed"):
        student.load_lightgbm_student(copied_bundle)


def test_missing_model_and_changed_runtime_source_fail_explicitly(copied_bundle):
    model_path = copied_bundle / "artifacts/student_lightgbm/kd_mixed.json"
    original = model_path.read_bytes()
    model_path.unlink()
    with pytest.raises(FileNotFoundError):
        student.load_lightgbm_student(copied_bundle)
    model_path.write_bytes(original)
    source = copied_bundle / "src/phishguard_vn/student_lightgbm.py"
    source.write_bytes(source.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="Inference source changed"):
        student.load_lightgbm_student(copied_bundle)


def test_changed_model_version_is_rejected_by_published_loader(copied_bundle):
    path = copied_bundle / "artifacts/student_lightgbm/kd_mixed.json"
    changed = read_json(path)
    changed["model_version"] = "wrong-version"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="Artifact changed"):
        student.load_lightgbm_student(copied_bundle)


@pytest.mark.parametrize("field,value", [("schema", "wrong-schema"),
                                         ("numpy_version", "0.0"),
                                         ("decision_rule", "score > threshold")])
def test_changed_model_contract_is_rejected(folder, field, value):
    features = read_json(folder / "features.json")
    bundle = read_json(folder / "kd_mixed.json")
    bundle[field] = value
    with pytest.raises(ValueError):
        student.HybridLightGBMStudent(features, bundle)


def test_changed_feature_order_is_rejected(folder):
    features = read_json(folder / "features.json")
    features["feature_order"] = list(reversed(features["feature_order"]))
    with pytest.raises(ValueError, match="feature contract"):
        student.HybridLightGBMStudent(features, read_json(folder / "kd_mixed.json"))


def test_cv_targets_lineage_from_exported_files_without_teacher_cache(root, folder, manifest):
    target_folder = folder / "cv_targets"
    target_meta = read_json(target_folder / "manifest.json")
    assert digest(target_folder / "manifest.json") == manifest["cv_targets_manifest_sha256"]
    mapping_path = root / "reports/tables/stacking/train_ids.csv.gz"
    assert digest(mapping_path) == target_meta["fold_map_sha256"]
    mapping = pd.read_csv(mapping_path)
    assert len(mapping) == mapping.id.nunique() == 13078
    assert target_meta["teacher_retrained"] is False
    for name, expected in target_meta["files_sha256"].items():
        assert digest(target_folder / name) == expected, name
    for name, expected in target_meta["input_sha256"].items():
        assert digest(root / name) == expected, name
    for fold in (0, 1, 2):
        info = target_meta["folds"][str(fold)]
        fit = pd.read_csv(target_folder / f"outer{fold}_fitting_targets.csv.gz")
        held = pd.read_csv(target_folder / f"outer{fold}_held_reference.csv.gz")
        expected_fit = mapping.loc[mapping.fold_id.ne(fold)]
        expected_held = mapping.loc[mapping.fold_id.eq(fold)]
        for table, expected, key in [(fit, expected_fit, "fitting_ids_sha256"),
                                     (held, expected_held, "held_ids_sha256")]:
            assert len(table) == table.id.nunique() == len(expected)
            assert table.id.tolist() == expected.id.tolist()
            ids_hash = hashlib.sha256("\n".join(table.id).encode()).hexdigest()
            assert ids_hash == info[key]
            assert table.target.tolist() == expected.target.tolist()
            assert np.isfinite(table.teacher_score).all()
            assert table.teacher_score.between(0, 1).all()
        assert set(expected_fit.registrable_domain).isdisjoint(expected_held.registrable_domain)
        assert set(fit.id).isdisjoint(held.id)
        assert set(fit.outer_fold) == set(held.fold_id) == {fold}
        record_path = root / f"reports/tables/stacking/stack_hist_outer{fold}.json"
        record = read_json(record_path)
        assert digest(record_path) == info["historical_record_sha256"]
        assert info["parameters"] == record["params"]
        assert info["teacher_retrained"] is False and info["domain_overlap"] == 0
        assert info["fitting_ids_sha256"] == record["fitting_ids_sha256"]
        assert info["held_ids_sha256"] == record["held_ids_sha256"]
        assert len(info["teacher_model_sha256"]) == 64
        saved = pd.read_csv(root / f"reports/tables/stacking/stack_hist_outer{fold}_oof.csv.gz")
        aligned = held.merge(saved, on="id", validate="one_to_one", suffixes=("", "_saved"))
        assert len(aligned) == len(held)
        np.testing.assert_allclose(aligned.teacher_score, aligned.score, rtol=0, atol=1e-12)
        # Model cache lịch sử không nằm trong Git; không tái tạo hoặc nhận đã hash lại cache.


@pytest.mark.parametrize("mode", MODES)
def test_cli_uses_published_mode_and_reports_invalid_input(root, mode, tmp_path):
    script = root / "scripts/predict_lightgbm_student.py"
    result = subprocess.run([sys.executable, str(script), "--mode", mode, "--examples"],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 5
    assert all(row["model_version"] == "lightgbm-student-" + mode for row in rows)
    assert all(row["android_verified"] is False for row in rows)
    invalid = subprocess.run([sys.executable, str(script), "--mode", mode, "https://example.com:bad"],
                             cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert invalid.returncode != 0 and not invalid.stdout.strip()
    assert "Traceback" not in invalid.stderr


def test_portable_json_inference_without_dataset_teacher_or_native_lightgbm(root, manifest, tmp_path):
    portable = tmp_path / "portable"
    shutil.copytree(root / "src/phishguard_vn", portable / "src/phishguard_vn",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    names = {"artifacts/student_lightgbm/manifest.json"}
    names.update(manifest["runtime_assets_sha256"])
    names.update("artifacts/student_lightgbm/" + name for name in manifest["inference_files_sha256"])
    for name in names:
        target = portable / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    code = """
import builtins, json, socket, sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root / 'src'))
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] == 'lightgbm':
        raise AssertionError('Portable inference requires native LightGBM')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
def forbidden(*args, **kwargs):
    raise AssertionError('Portable inference attempted network/Teacher')
socket.getaddrinfo = socket.socket.connect = socket.socket.connect_ex = forbidden
import joblib
joblib.load = forbidden
from phishguard_vn.student_lightgbm import load_lightgbm_student
assert not (root / 'data').exists() and not (root / 'models').exists()
assert not list(root.rglob('*.model.txt'))
rows = [load_lightgbm_student(root, mode).predict_one('example.com')
        for mode in ('hard_only', 'kd_mixed')]
print(json.dumps(rows))
"""
    env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    result = subprocess.run([sys.executable, "-c", code], cwd=portable, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)) == 2
