"""K7.4: kiểm bundle MLP int8 đã bàn giao, không train hoặc thay adapter Hy."""
from __future__ import annotations

import base64
from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

QA_ROOT = Path(__file__).resolve().parents[2]
HANDOFF = Path(os.environ.get("QA_STUDENT_MLP_ROOT", QA_ROOT.parent / "PhishGuardVN-w7-student-mlp-review")).resolve()
REVISION = "bc3a3a7054e2f6e6e733595f40f38439784536a1"
FOLDER = HANDOFF / "artifacts/student_mlp_android"
HASHES = {
    "manifest.json": "96044c0e024dabba64071c134d053fb1ff3fbceeb043bbb485be2bd347009277",
    "student_mlp.json.gz": "8d118ac5346543bdfa29b7970b48ae206305d5fe8992e0c4754aa070cc032341",
    "python_reference.json": "7ace7a342969ec0dcbef1334c27e84917962ec034181c76ad162f6c2a181c8f1",
    "verification.json": "a8c4e543bbf001c5e3c8db42fa6c8f37a57fd240765038888046ddd50bf80d37",
}
REFERENCE = json.loads((FOLDER / "python_reference.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def delivery():
    spec = importlib.util.spec_from_file_location("qa_student_mlp_delivery", HANDOFF / "scripts/prepare_android_mlp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def payload():
    return json.loads(gzip.decompress((FOLDER / "student_mlp.json.gz").read_bytes()))


@pytest.fixture(scope="module")
def model(delivery):
    return delivery.load_student()


@pytest.fixture(scope="module")
def evidence(request):
    data = {"schema": "k74-student-mlp-python-qa-v1", "checked_on": "2026-11-19",
            "source_revision": REVISION, "model_version": "student-mlp-kd-int8-v1",
            "threshold": 0.72961075, "decision_rule": "score >= threshold",
            "absolute_tolerance": 2e-6, "runtime": "CPython; not Dart/Android",
            "python": sys.version.split()[0], "assets_sha256": HASHES,
            "project_training": False, "teacher_inference": False,
            "cases": [], "independent_int8_max_delta": 0.0}
    yield data
    data["status"] = "passed" if request.session.testsfailed == 0 else "failed"
    data["classified_matched"] = sum(c["status"] == "classified" for c in data["cases"])
    data["rejected_matched"] = sum(c["status"] == "rejected" for c in data["cases"])
    data["max_fixture_score_delta"] = max((c.get("absolute_delta", 0) for c in data["cases"]), default=0)
    destination = os.environ.get("QA_STUDENT_MLP_OUTPUT")
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def copied(tmp_path):
    for name in ["manifest.json", "student_mlp.json.gz"]:
        shutil.copy2(FOLDER / name, tmp_path / name)
    return tmp_path


def test_exact_revision_and_declared_contract(delivery):
    revision = subprocess.check_output(["git", "-c", f"safe.directory={HANDOFF.as_posix()}", "-C", str(HANDOFF), "rev-parse", "HEAD"], text=True).strip()
    assert revision == REVISION
    manifest = delivery.read_json(FOLDER / "manifest.json")
    assert manifest["schema"] == "android-student-char-tfidf-mlp-int8-v1"
    assert manifest["model_version"] == "student-mlp-kd-int8-v1"
    assert manifest["threshold"] == 0.72961075
    assert manifest["classes"] == {"benign": 0, "phishing": 1}
    assert manifest["decision_rule"] == "score >= threshold"
    assert manifest["score_kind"] == "uncalibrated_sigmoid"
    assert manifest["android_verified"] is False
    assert manifest["model"]["bytes"] == 283334
    assert manifest["psl"]["bytes"] == 75007
    assert delivery.file_record(delivery.PSL_PATH) == manifest["psl"]
    lock = delivery.read_json(HANDOFF / "configs/teacher_lock.json")
    assert manifest["teacher"]["bundle_sha256"] == lock["bundle"]["sha256"]
    assert manifest["teacher"]["lock_sha256"] == delivery.sha256(HANDOFF / "configs/teacher_lock.json")


@pytest.mark.parametrize("name", list(HASHES))
def test_all_four_pinned_files(name):
    assert hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() == HASHES[name]


@pytest.mark.parametrize("row", REFERENCE["cases"], ids=lambda row: row["status"] + "-" + row["url"][:50])
def test_each_shared_reference_input(model, row, evidence):
    if row["status"] == "rejected":
        with pytest.raises((TypeError, ValueError)):
            model.predict(row["url"])
        evidence["cases"].append({"url": row["url"], "status": "rejected"})
    else:
        result = model.predict(row["url"])
        delta = abs(result["score"] - row["score"])
        assert delta <= 2e-6
        for name in ["class_id", "model_version", "threshold", "decision_rule", "score_kind"]:
            assert result[name] == row[name]
        assert math.isfinite(result["score"]) and 0 <= result["score"] <= 1
        evidence["cases"].append({"url": row["url"], "status": "classified", "python_score": result["score"], "reference_score": row["score"], "absolute_delta": delta, "class_id": result["class_id"]})


def test_int8_layout_per_hidden_scales_and_scalar_path(model, payload, delivery, evidence):
    """Independent scalar accumulation catches signedness/transpose/scale mistakes."""
    codes = [v if v < 128 else v - 256 for v in base64.b64decode(payload["weights_int8_base64"], validate=True)]
    assert len(codes) == 4096 * 64 and min(codes) < 0 < max(codes)
    assert payload["weight_layout"] == "row_major_term_then_hidden"
    indices = {term: i for i, term in enumerate(payload["terms"])}
    for row in REFERENCE["cases"]:
        if row["status"] != "classified":
            continue
        text = delivery.student_text(row["url"])
        counts = Counter(text[i:i+n] for n in range(3, 6) for i in range(len(text)-n+1))
        hits = [(indices[t], (1 + math.log(count)) * payload["idf"][indices[t]]) for t, count in counts.items() if t in indices]
        norm = math.sqrt(math.fsum(v*v for _, v in hits))
        hidden = [max(0.0, math.fsum(v/norm * codes[i*64+j] * payload["hidden_scales"][j] for i, v in hits) + payload["hidden_bias"][j]) for j in range(64)]
        margin = math.fsum(h*w for h, w in zip(hidden, payload["output_weight"])) + payload["output_bias"]
        score = 1/(1+math.exp(-margin)) if margin >= 0 else math.exp(margin)/(1+math.exp(margin))
        delta = abs(score - model.score(row["url"]))
        evidence["independent_int8_max_delta"] = max(evidence["independent_int8_max_delta"], delta)
        assert delta <= 1e-12


def test_zero_vocabulary_match_still_evaluates_biases(delivery, payload):
    modified = copy.deepcopy(payload)
    modified["terms"] = [chr(0xE000+i)*3 for i in range(4096)]
    predictor = delivery.StudentMlp(modified)
    margin = math.fsum(max(0, b)*w for b, w in zip(payload["hidden_bias"], payload["output_weight"])) + payload["output_bias"]
    expected = 1/(1+math.exp(-margin)) if margin >= 0 else math.exp(margin)/(1+math.exp(margin))
    assert predictor.score("https://example.com/") == pytest.approx(expected, abs=1e-15, rel=0)


@pytest.mark.parametrize("side,expected", [("below", 0), ("equal", 1), ("above", 1)])
def test_locked_decision_boundary(model, monkeypatch, side, expected):
    score = {"below": math.nextafter(model.threshold, 0), "equal": model.threshold, "above": math.nextafter(model.threshold, 1)}[side]
    monkeypatch.setattr(model, "score", lambda _: score)
    assert model.predict("example.com")["class_id"] == expected


@pytest.mark.parametrize("url,expected", [
    ("https://user:pass@EXAMPLE.com:443/A%2FB?Ref=Q#ignore", "example.com/A%2FB?Ref=Q"),
    ("http://EXAMPLE.com:80/A", "example.com/A"),
    ("https://BÜCHER.de/Đăng?q=🙂", "xn--bcher-kva.de/Đăng?q=🙂"),
    ("//example.org/path", "example.org/path"),
    ("https://example.com/abc  xyz?a=x%20y", "example.com/abc xyz?a=x%20y"),
])
def test_preprocessing_preserves_unicode_case_and_percent_escape(delivery, url, expected):
    assert delivery.student_text(url) == expected


@pytest.mark.parametrize("change", ["missing_model", "missing_manifest", "corrupt_model", "wrong_psl", "wrong_version", "wrong_threshold", "wrong_score_kind"])
def test_asset_or_contract_failure_never_returns_prediction(delivery, copied, tmp_path, monkeypatch, change):
    manifest = delivery.read_json(copied / "manifest.json")
    if change.startswith("missing_"):
        (copied / ("student_mlp.json.gz" if change == "missing_model" else "manifest.json")).unlink()
    elif change == "corrupt_model":
        raw = bytearray((copied / "student_mlp.json.gz").read_bytes()); raw[-1] ^= 1
        (copied / "student_mlp.json.gz").write_bytes(raw)
    elif change == "wrong_psl":
        path = tmp_path / "wrong_psl.txt"; path.write_text("com\n", encoding="utf-8")
        monkeypatch.setattr(delivery, "PSL_PATH", path)
    else:
        key, value = {"wrong_version": ("model_version", "student-other"), "wrong_threshold": ("threshold", 0.5), "wrong_score_kind": ("score_kind", "probability")}[change]
        manifest[key] = value
        (copied / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((OSError, ValueError, KeyError)):
        delivery.load_student(copied)


def test_portable_inference_without_teacher_dataset_network_or_training(tmp_path):
    runtime = tmp_path / "runtime"
    shutil.copytree(HANDOFF / "src/phishguard_vn", runtime / "src/phishguard_vn", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ["scripts/prepare_android_mlp.py", "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt", "artifacts/student_mlp_android/manifest.json", "artifacts/student_mlp_android/student_mlp.json.gz"]:
        destination = runtime / name; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(HANDOFF / name, destination)
    assert not (runtime / "models").exists() and not (runtime / "data").exists()
    probe = r'''
import importlib.util,json,socket,sys
def forbidden(*args,**kwargs): raise AssertionError("Network/training/Teacher forbidden by Student QA")
socket.getaddrinfo=forbidden
socket.socket.connect=forbidden
socket.socket.connect_ex=forbidden
spec=importlib.util.spec_from_file_location("portable_mlp","scripts/prepare_android_mlp.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.build=m.build_assets=m.verified_research=forbidden
m.TfidfVectorizer.fit=forbidden
import phishguard_vn.teacher as teacher
teacher.load_teacher=forbidden
print(json.dumps(m.load_student().predict("https://example.com/")))
'''
    env = {k:v for k,v in os.environ.items() if k not in ["PYTHONPATH", "PYTHONHOME"]}
    env["OMP_NUM_THREADS"] = "1"
    result = subprocess.run([sys.executable, "-c", probe], cwd=runtime, env=env, text=True, encoding="utf-8", capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr
    prediction = json.loads(result.stdout)
    assert prediction["model_version"] == "student-mlp-kd-int8-v1"
    assert prediction["class_id"] == REFERENCE["cases"][0]["class_id"]
    assert prediction["score"] == pytest.approx(REFERENCE["cases"][0]["score"], abs=2e-6, rel=0)
