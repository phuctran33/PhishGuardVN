"""Official Teacher pointer. Historical v1 and candidate artifacts stay unchanged."""
from pathlib import Path
import json
from phishguard_vn.stacking_candidate import load_candidate, sha, require_python_runtime

class ReleasedTeacher:
    def __init__(self, candidate):
        self.candidate = candidate

    def predict_batch(self, urls):
        rows = self.candidate.predict_batch(urls)
        return [{**r, "artifact_model_version": r["model_version"],
                 "model_version": "teacher-stacking-v2", "candidate_only": False,
                 "promoted": True} for r in rows]

    def predict_one(self, url):
        return self.predict_batch([url])[0]

def load_released_teacher(root):
    root = Path(root)
    lock = json.loads((root / "configs/teacher_lock.json").read_text(encoding="utf-8"))
    require_python_runtime(lock.get("python_runtime"))
    expected = dict(teacher_finalized=True, promoted=True, model_version="teacher-stacking-v2",
        selected_by="core_train_group_cv", external_used_for_selection=False,
        official_test_evaluated=False, decision_rule="score >= threshold",
        operating_point_scope="full_train_group_oof_fpr_target_0.01")
    if any(lock.get(k) != v for k,v in expected.items()):
        raise ValueError("Official Teacher release protocol mismatch")
    path = root / lock["candidate_lock"]["path"]
    if sha(path) != lock["candidate_lock"]["sha256"]:
        raise ValueError("Candidate runtime lock changed since promotion")
    candidate = load_candidate(root)
    if (lock["bundle"] != json.loads(path.read_text(encoding="utf-8"))["bundle"]
            or lock["threshold"] != candidate.threshold):
        raise ValueError("Official Teacher artifact/threshold mismatch")
    return ReleasedTeacher(candidate)
