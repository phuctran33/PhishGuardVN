"""Separate, unpromoted Teacher v2 candidate. Teacher v1 stays the default adapter."""
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
import hashlib
import json
import joblib
import numpy as np
from phishguard_vn.stacking import (
    FittedStack, PREPROCESSING_VERSION, raw_frame, score_model,
    source_hashes, reference_fingerprint,
)
from phishguard_vn.brand_features import E2_FEATURES

MODEL_VERSION = "teacher-stacking-v2-candidate"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_contract(value):
    expected = {
        "model_version": MODEL_VERSION, "candidate_only": True, "promoted": False,
        "preprocessing_version": PREPROCESSING_VERSION,
        "selected_by": "core_train_group_cv", "primary_metric": "mean_outer_average_precision",
        "validation_used_for_selection": False, "external_used_for_selection": False,
        "official_test_evaluated": False, "decision_rule": "score >= threshold",
        "operating_point_scope": "full_train_group_oof_fpr_target_0.01",
        "score_kind": "probability", "calibrated": False,
        "feature_names": list(E2_FEATURES), "class_mapping": {"benign": 0, "phishing": 1},
    }
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError("Candidate protocol/feature order mismatch")
    threshold = value.get("threshold")
    if type(threshold) not in (int, float) or not np.isfinite(threshold) or not 0 <= threshold <= np.nextafter(1., np.inf):
        raise ValueError("Invalid candidate threshold")
    if value.get("source_sha256") != source_hashes():
        raise ValueError("Runtime normalization/E2/parser source differs from packaged candidate")


class StackingCandidate:
    def __init__(self, bundle):
        validate_contract(bundle)
        self.bundle = bundle
        self.model = bundle["model"]
        self.reference = bundle.get("reference")
        if self.reference is None:
            raise ValueError("Candidate is missing its bundled brand reference")
        if (self.reference.sha256 != bundle.get("reference_sha256")
                or reference_fingerprint(self.reference) != bundle.get("reference_fingerprint")):
            raise ValueError("Bundled reference mismatch")
        if (not isinstance(self.model, FittedStack) or self.model.members != ["svm", "hist"]
                or list(self.model.classes_) != [0, 1]):
            raise ValueError("Expected two-branch SVM/HistGB candidate")
        hist = self.model.bases["hist"].named_steps["features"]
        if hist.transformers_[0][2] != list(E2_FEATURES):
            raise ValueError("Fitted E2 order differs from contract")
        fitted_hist = self.model.bases["hist"].named_steps["model"]
        if fitted_hist.early_stopping is not False or fitted_hist.n_iter_ != 300:
            raise ValueError("Candidate HistGB must use the fixed 300-round budget")
        if (list(self.model.meta.classes_) != [0, 1]
                or any(list(m.classes_) != [0, 1] for m in self.model.bases.values())):
            raise ValueError("Candidate base/meta class order differs")
        self.threshold = float(bundle["threshold"])

    def predict_batch(self, urls):
        frame = raw_frame(urls, self.reference)
        score = score_model(self.model, frame)
        if np.any((score < 0) | (score > 1)):
            raise ValueError("Invalid LR score")
        predicted = score >= self.threshold
        return [{"label": "phishing" if p else "benign", "class_id": int(p),
            "score": float(s), "score_kind": "probability",
            "score_definition": "Uncalibrated meta-LR score, NOT percent safety",
            "threshold": self.threshold, "decision_rule": "score >= threshold",
            "model_version": MODEL_VERSION, "preprocessing_version": PREPROCESSING_VERSION,
            "candidate_only": True, "promoted": False}
            for p, s in zip(predicted, score)]

    def predict_one(self, url):
        return self.predict_batch([url])[0]


def load_candidate(root):
    root = Path(root)
    path = root / "configs/teacher_v2_candidate_lock.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(lock)
    for package, expected in lock["runtime_versions"].items():
        try:
            actual = version(package)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"Missing runtime dependency: {package}") from exc
        if actual != expected:
            raise RuntimeError(f"Incompatible {package}: expected {expected}, got {actual}")
    model_path = root / lock["bundle"]["path"]
    if not model_path.is_file() or sha(model_path) != lock["bundle"]["sha256"]:
        raise ValueError("Candidate bundle is missing or changed")
    bundle = joblib.load(model_path)  # only trusted, hash-checked project candidate
    for key in ["threshold", "model_version", "preprocessing_version", "reference_sha256",
                "reference_fingerprint", "source_sha256"]:
        if bundle.get(key) != lock.get(key):
            raise ValueError(f"Candidate lock/bundle mismatch: {key}")
    return StackingCandidate(bundle)
