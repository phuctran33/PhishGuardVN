"""Small Student inference: URL -> character TF-IDF -> linear score.

Training stays explicit in scripts/train_student.py. JSON stores every number
needed for inference; Teacher and dataset are not loaded here.
"""
from collections import Counter
from pathlib import Path
from importlib.metadata import version
import hashlib
import json
import platform
import re
import sys

import numpy as np
from scipy.special import expit
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score, f1_score

from phishguard_vn.stacking import canonical_url, validate_urls

SCHEMA = "student-char-tfidf-lr-v1"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def student_text(url):
    """Use Teacher's canonical text, preserving path/query case and escapes."""
    validate_urls([url])
    # Match sklearn's character analyzer whitespace treatment, before n-grams.
    return re.sub(r"\s\s+", " ", canonical_url(url))


def choose_threshold(y, scores, fpr_budget):
    """Choose the lowest score interval within the benign false-positive budget."""
    y, scores = np.asarray(y), np.asarray(scores, dtype=float)
    if (set(np.unique(y)) != {0, 1} or scores.shape != y.shape
            or not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any()
            or not 0 <= fpr_budget < 1):
        raise ValueError("Need two classes, finite scores and a valid FPR budget")
    benign = np.sort(scores[y == 0])[::-1]
    allowed = int(np.floor(fpr_budget * len(benign)))
    # Stay above the excluded tied benign group. A midpoint avoids putting a
    # portable JSON decision boundary only one floating-point ULP from a sample.
    excluded = benign[allowed]
    higher = scores[scores > excluded]
    upper = float(higher.min()) if len(higher) else 1.0
    threshold = (excluded + upper) / 2
    return float(threshold if threshold > excluded else np.nextafter(excluded, np.inf))


def metrics(y, scores, threshold):
    y, scores = np.asarray(y), np.asarray(scores)
    pred = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return dict(ap=float(average_precision_score(y, scores)),
                precision=float(precision_score(y, pred, zero_division=0)),
                recall=float(recall_score(y, pred, zero_division=0)),
                f1=float(f1_score(y, pred, zero_division=0)),
                fpr=float(fp / (fp + tn)), tp=int(tp), fp=int(fp),
                tn=int(tn), fn=int(fn), threshold=float(threshold))


def export_model(vectorizer, model, threshold, name, config):
    terms = vectorizer.get_feature_names_out().tolist()
    return dict(schema=SCHEMA, model_version="student-week7-" + name,
                release_status="experimental", score_kind="uncalibrated_sigmoid",
                calibrated=False, decision_rule="score >= threshold",
                normalization="canonical-reference-v1; whitespace-collapse-v1",
                ngram_range=config["ngram_range"], sublinear_tf=True, norm="l2",
                terms=terms, idf=vectorizer.idf_.tolist(),
                coef=model.coef_[0].tolist(), intercept=float(model.intercept_[0]),
                threshold=threshold, class_mapping={"benign": 0, "phishing": 1},
                python_runtime="CPython 3.11", idna_version=version("idna"))


class Student:
    """Readable JSON predictor. Vocabulary order aligns terms, idf and coef."""

    def __init__(self, bundle):
        expected = dict(schema=SCHEMA, release_status="experimental",
                        score_kind="uncalibrated_sigmoid", calibrated=False,
                        decision_rule="score >= threshold",
                        normalization="canonical-reference-v1; whitespace-collapse-v1",
                        sublinear_tf=True, norm="l2",
                        class_mapping={"benign": 0, "phishing": 1},
                        python_runtime="CPython 3.11", idna_version=version("idna"))
        if any(bundle.get(k) != v for k, v in expected.items()):
            raise ValueError("Unsupported Student contract")
        if sys.version_info[:2] != (3, 11) or platform.python_implementation() != "CPython":
            raise RuntimeError("Student reference runtime requires CPython 3.11")
        terms = bundle["terms"]
        if (not terms or any(not isinstance(t, str) or not t for t in terms)
                or len(terms) != len(set(terms))):
            raise ValueError("Invalid Student vocabulary")
        self.idf = np.asarray(bundle["idf"], dtype=float)
        self.coef = np.asarray(bundle["coef"], dtype=float)
        if (self.idf.shape != (len(terms),) or self.coef.shape != self.idf.shape
                or not np.isfinite(self.idf).all() or not np.isfinite(self.coef).all()
                or (self.idf <= 0).any()):
            raise ValueError("Invalid Student weights")
        self.low, self.high = bundle["ngram_range"]
        if not (type(self.low) is int and type(self.high) is int and 1 <= self.low <= self.high <= 5):
            raise ValueError("Invalid n-gram range")
        self.intercept, self.threshold = bundle["intercept"], bundle["threshold"]
        if (not np.isfinite(self.intercept) or not np.isfinite(self.threshold)
                or not 0 <= self.threshold <= np.nextafter(1., np.inf)):
            raise ValueError("Invalid Student intercept/threshold")
        self.index = {term: i for i, term in enumerate(terms)}
        self.bundle = bundle

    def score_one(self, url):
        text = student_text(url)
        counts = Counter(text[i:i+n] for n in range(self.low, self.high+1)
                         for i in range(len(text)-n+1))
        selected = sorted((self.index[t], count) for t, count in counts.items() if t in self.index)
        if not selected:
            return float(expit(self.intercept))
        indices = np.array([i for i, _ in selected])
        weights = (1 + np.log([count for _, count in selected])) * self.idf[indices]
        weights /= np.linalg.norm(weights)
        return float(expit(weights @ self.coef[indices] + self.intercept))

    def predict_one(self, url):
        score = self.score_one(url)
        positive = score >= self.threshold
        return dict(label="phishing" if positive else "benign", class_id=int(positive),
                    score=score, score_kind="uncalibrated_sigmoid", calibrated=False,
                    threshold=self.threshold, model_version=self.bundle["model_version"],
                    release_status="experimental", android_verified=False)

    def predict_batch(self, urls):
        validate_urls(urls)
        return [self.predict_one(url) for url in urls]


def load_student(root, candidate=None):
    """Check the local manifest and source hashes before accepting model JSON."""
    root = Path(root)
    manifest = json.loads((root / "artifacts/student_week7/manifest.json").read_text(encoding="utf-8"))
    candidate = candidate or manifest["selected_candidate"]
    if candidate not in manifest["models"]:
        raise ValueError("Unknown Student candidate")
    for relative, digest in manifest["inference_source_sha256"].items():
        if sha256(root / relative) != digest:
            raise ValueError("Student inference source changed: " + relative)
    record = manifest["models"][candidate]
    path = root / record["path"]
    if sha256(path) != record["sha256"]:
        raise ValueError("Student artifact hash mismatch")
    return Student(json.loads(path.read_text(encoding="utf-8")))
