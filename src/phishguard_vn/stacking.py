"""Small building blocks for the registered stacking experiment and offline candidate.

Flow: raw URL -> canonical text / frozen E2 -> base scores -> fitted meta LR.
Training loops and group splits are explicit in scripts/run_stacking.py.
"""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import hashlib
import json
import idna
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, ExtraTreesClassifier

from phishguard_vn.brand_features import E2_FEATURES, load_reference, extract_brand_features_from_parsed
from phishguard_vn.features import extract_features_from_parsed
from phishguard_vn.url_parser import parse_url, SCHEME_RE

PREPROCESSING_VERSION = "canonical-reference-v1"


def canonical_url(value):
    """Lossy research contract: omit scheme/userinfo/fragment, preserve path/query.

    Matches the previous canonical research representation for eligible Train.
    Handles scheme-relative input explicitly. Does not claim resource equivalence.
    """
    working = value if SCHEME_RE.match(value) else ("http:" + value if value.startswith("//") else "//" + value)
    parts = urlsplit(working)
    host = parts.hostname or ""
    try:
        host = idna.encode(host, uts46=True).decode("ascii").lower()
    except idna.IDNAError:
        host = host.lower()
    if not host:
        raise ValueError("URL has no hostname")
    if ":" in host:
        host = "[" + host + "]"
    port = parts.port
    default = (parts.scheme.lower(), port) in {("http", 80), ("https", 443)}
    netloc = host + (f":{port}" if port is not None and not default else "")
    return netloc + urlunsplit(("", "", parts.path, parts.query, ""))


class CanonicalText(TransformerMixin, BaseEstimator):
    def __init__(self, enabled=True):
        self.enabled = enabled

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return [canonical_url(u) for u in X] if self.enabled else list(X)


def text_features(canonical=True, ngram=(2, 5), cap=100000):
    return Pipeline([
        ("canonical", CanonicalText(canonical)),
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=tuple(ngram),
            min_df=2, max_features=cap, lowercase=False, sublinear_tf=True,
            use_idf=True, norm="l2")),
    ])


def make_base(name, params=None, spec=None):
    """Construct unfitted estimators. No group/ID/source/label becomes a feature."""
    params = params or {}
    if name in {"hist", "extra", "lgbm"}:
        if name == "hist":
            model = HistGradientBoostingClassifier(max_iter=300, learning_rate=.05,
                max_leaf_nodes=15, random_state=42)
        elif name == "extra":
            model = ExtraTreesClassifier(n_estimators=400, min_samples_leaf=2,
                max_features=1.0, random_state=42, n_jobs=2)
        else:
            from lightgbm import LGBMClassifier
            model = LGBMClassifier(n_estimators=600, learning_rate=.035, num_leaves=15,
                min_child_samples=20, max_bin=127, deterministic=True,
                force_col_wise=True, random_state=42, n_jobs=2, verbosity=-1)
        return Pipeline([("features", ColumnTransformer([
            ("e2", "passthrough", list(E2_FEATURES))])), ("model", model)])
    spec = spec or {}
    hybrid = name in {"hybrid_svm", "hybrid_lr"}
    branches = [("text", text_features(spec.get("canonical", True),
        spec.get("ngram", (2, 5)), spec.get("cap", 100000)), "url")]
    if hybrid:
        branches.append(("e2", StandardScaler(), list(E2_FEATURES)))
    features = ColumnTransformer(branches, sparse_threshold=1.0,
        transformer_weights={"text": 1.0, "e2": params.get("numeric_weight", .25)} if hybrid else None)
    model = (LogisticRegression(C=params.get("C", 1), max_iter=3000, random_state=42)
             if name == "hybrid_lr" else
             LinearSVC(C=params.get("C", 1), max_iter=30000, random_state=42))
    return Pipeline([("features", features), ("model", model)])


def make_meta(C, scale):
    return Pipeline([("scale", StandardScaler() if scale else "passthrough"),
                     ("lr", LogisticRegression(C=C, max_iter=3000, random_state=42))])


def score_model(model, X):
    score = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else model.decision_function(X)
    score = np.asarray(score, dtype=float)
    if score.shape != (len(X),) or not np.isfinite(score).all():
        raise ValueError("Invalid model scores")
    return score


class FittedStack:
    """Inference only: base models were fitted on fitting rows; meta used group OOF."""
    def __init__(self, members, bases, meta):
        self.members = list(members)
        self.bases = {k: bases[k] for k in members}
        self.meta = meta
        self.classes_ = np.array([0, 1])

    def base_scores(self, X):
        return np.column_stack([score_model(self.bases[k], X) for k in self.members])

    def predict_proba(self, X):
        return self.meta.predict_proba(self.base_scores(X))

    def predict(self, X):
        return self.meta.predict(self.base_scores(X))


def validate_urls(urls):
    if not isinstance(urls, (list, tuple)) or not urls:
        raise TypeError("Expected a nonempty list/tuple of URLs")
    if any(not isinstance(u, str) for u in urls):
        raise TypeError("Every URL must be a string")
    for u in urls:
        if not u.strip() or "\x00" in u or any(ord(c) < 32 for c in u):
            raise ValueError("Blank/NUL/control characters are invalid")
        # Do not silently strip meaningful input or turn malformed input into benign.
        if u != u.strip():
            raise ValueError("Surrounding whitespace is invalid")
        parsed = parse_url(u)
        if not parsed.is_valid:
            raise ValueError(f"Invalid URL: {parsed.error_reason}")


def raw_frame(urls, reference=None, numeric=True):
    """Offline extraction. Frozen E2 is always computed from RAW input."""
    validate_urls(urls)
    result = pd.DataFrame({"url": list(urls)})
    if numeric:
        reference = reference or load_reference()
        values = []
        for u in urls:
            parsed = parse_url(u)
            values.append({**extract_features_from_parsed(parsed),
                           **extract_brand_features_from_parsed(parsed, reference)})
        matrix = pd.DataFrame(values, columns=E2_FEATURES)
        if not np.isfinite(matrix.to_numpy(float)).all():
            raise ValueError("Nonfinite E2 features")
        result = pd.concat([result, matrix], axis=1)
    return result


def choose_threshold(y, score, target_fpr):
    """score >= threshold. Group tied scores; maximize recall, then higher threshold."""
    y, score = np.asarray(y), np.asarray(score, dtype=float)
    if not (0 <= target_fpr < 1) or set(np.unique(y)) != {0, 1}:
        raise ValueError("Need both classes and a valid FPR target")
    if score.shape != y.shape or not np.isfinite(score).all():
        raise ValueError("Invalid threshold scores")
    order = np.argsort(-score, kind="stable")
    s, labels = score[order], y[order]
    ends = np.r_[np.flatnonzero(s[:-1] != s[1:]), len(s) - 1]
    tp, fp = np.cumsum(labels == 1)[ends], np.cumsum(labels == 0)[ends]
    valid = fp / np.sum(y == 0) <= target_fpr
    threshold = float(np.nextafter(s[0], np.inf))
    if valid.any():
        best_tp = tp[valid].max()
        candidates = np.flatnonzero(valid & (tp == best_tp))
        # Include predict-none in a zero-recall tie, the most conservative rule.
        if best_tp:
            threshold = float(s[ends[candidates[0]]])
    return threshold


def source_hashes():
    """LF-normalized runtime source fingerprints; checkout EOL is not model logic."""
    folder = Path(__file__).parent
    return {name: hashlib.sha256((folder / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in ["stacking.py", "features.py", "brand_features.py", "url_parser.py"]}


def reference_fingerprint(reference):
    from dataclasses import asdict
    def canonical(v):
        if isinstance(v, dict):
            return {k: canonical(x) for k, x in v.items()}
        if isinstance(v, (set, frozenset)):
            return sorted(v)
        if isinstance(v, (tuple, list)):
            return [canonical(x) for x in v]
        return v
    return hashlib.sha256(json.dumps(canonical(asdict(reference)), sort_keys=True).encode()).hexdigest()
