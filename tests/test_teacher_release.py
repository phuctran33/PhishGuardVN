"""Real released bundle parity, no training or Official Test scoring."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import phishguard_vn.stacking_candidate as adapter
from phishguard_vn.teacher import load_teacher

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("runtime", [(3,10), (3,12), (3,13)])
def test_unsupported_python_rejected_before_unpickle(monkeypatch, runtime):
    monkeypatch.setattr(adapter.sys, "version_info", runtime)
    monkeypatch.setattr(adapter.joblib, "load", lambda *a: pytest.fail("Must reject before unpickle"))
    with pytest.raises(RuntimeError, match="Python 3.11"):
        adapter.load_candidate(ROOT)

def test_missing_runtime_lock_rejected():
    with pytest.raises(RuntimeError, match="Python 3.11"):
        adapter.require_python_runtime(None)

def test_real_validation_bundle_matches_saved_scores():
    teacher = load_teacher(ROOT)
    saved = pd.read_csv(ROOT / "reports/tables/stacking/candidate/validation_predictions.csv",
                        float_precision="round_trip")
    # Only select the IDs from the saved Validation table; never score Official Test.
    raw = pd.read_csv(ROOT / "data/dataset_url.csv", usecols=["id","url","split"], encoding="utf-8")
    selected = saved.merge(raw, on="id", validate="one_to_one")
    assert len(selected) == 1585 and selected.split.eq("val").all()
    actual = teacher.predict_batch(selected.url.tolist())
    np.testing.assert_allclose([r["score"] for r in actual], selected.score, rtol=0, atol=1e-12)
    np.testing.assert_array_equal([r["class_id"] for r in actual], selected.prediction)
    assert all(r["promoted"] and not r["candidate_only"] for r in actual)

def test_real_external_bundle_matches_saved_scores():
    teacher = load_teacher(ROOT)
    saved = pd.read_csv(ROOT / "reports/tables/stacking/candidate/external_predictions.csv",
                        float_precision="round_trip")
    assert len(saved) == 99
    actual = teacher.predict_batch(saved.model_input.tolist())
    np.testing.assert_allclose([r["score"] for r in actual], saved.score, rtol=0, atol=1e-12)
    assert [r["label"] for r in actual] == saved.prediction.tolist()
    assert actual[:2] == [teacher.predict_one(u) for u in saved.model_input.iloc[:2]]

def test_explicit_v1_lock_still_loads():
    lock = json.loads((ROOT / "configs/week6_teacher_lock.json").read_text(encoding="utf-8"))
    assert load_teacher(ROOT, lock).predict_one("example.com")["model_version"] == "teacher-tfidf-svm-v1"
