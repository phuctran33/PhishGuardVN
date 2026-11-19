"""Check the real Android handoff with Python and no project training."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_android_mlp", ROOT / "scripts/prepare_android_mlp.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def test_reference_scores_and_input_rejections():
    model = delivery.load_student()
    fixture = delivery.read_json(delivery.ARTIFACT / "python_reference.json")
    assert len(fixture["cases"]) == 63
    outcomes = set()
    for row in fixture["cases"]:
        if row["status"] == "rejected":
            with pytest.raises((TypeError, ValueError)):
                model.predict(row["url"])
            outcomes.add("rejected")
            continue
        actual = model.predict(row["url"])
        assert actual["score"] == pytest.approx(row["score"], abs=fixture["score_absolute_tolerance"], rel=0)
        assert actual["model_version"] == row["model_version"]
        assert actual["threshold"] == row["threshold"]
        assert actual["class_id"] == row["class_id"]
        outcomes.add(row["class_id"])
    assert outcomes == {0, 1, "rejected"}


def test_corrupt_model_or_threshold_is_rejected(tmp_path):
    model = delivery.ARTIFACT / delivery.MODEL_FILE
    manifest = delivery.read_json(delivery.ARTIFACT / delivery.MANIFEST_FILE)
    target_model = tmp_path / delivery.MODEL_FILE
    target_manifest = tmp_path / delivery.MANIFEST_FILE
    target_manifest.write_text(json.dumps(manifest), encoding="utf8")
    damaged = bytearray(model.read_bytes())
    damaged[-1] ^= 1
    target_model.write_bytes(damaged)
    with pytest.raises(ValueError, match="asset or parser hash"):
        delivery.load_student(tmp_path)
    target_model.write_bytes(model.read_bytes())
    manifest["threshold"] = 0.5
    target_manifest.write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError, match="threshold mismatch"):
        delivery.load_student(tmp_path)
