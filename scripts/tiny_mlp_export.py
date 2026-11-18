"""Export and run a trusted local Tiny MLP research artifact.

The NPZ stores plain arrays only, with no pickle or training library required
at inference. It is a Python reference, not an Android package.
"""
from collections import Counter
from pathlib import Path
from time import perf_counter_ns

import numpy as np
from scipy.sparse import csr_matrix
from scipy.special import expit

from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.student import student_text
from phishguard_vn.student_comparison import e2_matrix

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "tiny-mlp-research-v1"
ASSETS = (
    ROOT / "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt",
    ROOT / "src/phishguard_vn/resources/brand_reference_v1.csv",
)


def bundle(path, vec, text_indices, e2_scaler, weights, threshold, quantized=False):
    """Write float32 or per-hidden-unit int8 first-layer weights.

    If text_indices is supplied, it selects columns after full-vocabulary
    L2 normalization. The full vocabulary and IDF remain required.
    """
    path = Path(path)
    W, b, u, c = (np.asarray(x, dtype="<f4") for x in weights)
    if W.ndim != 2 or b.shape != (W.shape[1],) or u.size != W.shape[1] or c.size != 1:
        raise ValueError("Inconsistent Tiny MLP layer shapes")
    if not all(np.isfinite(x).all() for x in (W, b, u, c)):
        raise ValueError("Tiny MLP weights must be finite")
    if not np.isfinite(threshold) or not 0 <= threshold <= np.nextafter(1.0, np.inf):
        raise ValueError("Invalid classification threshold")
    if vec is None:
        terms = []
        idf = []
        ngrams = (3, 5)
    else:
        if (vec.analyzer != "char" or vec.lowercase or not vec.sublinear_tf
                or vec.norm != "l2" or not vec.use_idf or vec.binary
                or vec.strip_accents is not None or vec.preprocessor is not None):
            raise ValueError("Export requires the frozen character TF-IDF settings")
        terms = vec.get_feature_names_out()
        idf = vec.idf_
        ngrams = vec.ngram_range
    terms_utf8 = [str(term).encode("utf-8") for term in terms]
    offsets = np.cumsum([0, *(len(term) for term in terms_utf8)], dtype="<u4")
    selected = np.arange(len(terms), dtype="<i4") if text_indices is None else np.asarray(text_indices, dtype="<i4")
    if (selected.ndim != 1 or len(np.unique(selected)) != len(selected)
            or (selected < 0).any() or (selected >= len(terms)).any()):
        raise ValueError("Text columns must be distinct valid vocabulary indices")
    mean = [] if e2_scaler is None else e2_scaler.mean_
    scale = [] if e2_scaler is None else e2_scaler.scale_
    if len(mean) != len(scale) or len(mean) not in (0, len(E2_FEATURES)):
        raise ValueError("Invalid E2 standardization")
    if W.shape[0] != len(selected) + len(mean):
        raise ValueError("Weights must match selected text columns followed by scaled E2")
    arrays = {
        "schema": np.asarray(SCHEMA),
        "vocab_utf8": np.frombuffer(b"".join(terms_utf8), dtype=np.uint8),
        "vocab_offsets": offsets,
        "idf": np.asarray(idf, dtype="<f4"),
        "ngram_range": np.asarray(ngrams, dtype="<u1"),
        "text_indices": selected if text_indices is not None else np.empty(0, dtype="<i4"),
        "select_text": np.asarray(text_indices is not None),
        "e2_mean": np.asarray(mean, dtype="<f8"),
        "e2_scale": np.asarray(scale, dtype="<f8"),
        "hidden_bias": b,
        "out_weights": u.reshape(-1),
        "out_bias": c.reshape(()),
        "threshold": np.asarray(threshold, dtype="<f8"),
    }
    if quantized:
        scale = np.max(np.abs(W), axis=0) / 127.0
        scale[scale == 0] = 1.0
        arrays["hidden_weights"] = np.clip(np.rint(W / scale), -127, 127).astype(np.int8)
        arrays["hidden_weight_scale"] = scale.astype("<f4")
    else:
        arrays["hidden_weights"] = W
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    payload = sum(array.nbytes for array in arrays.values())
    # All models validate/parse URLs. Only E2 models use brand reference.
    assets = sum(p.stat().st_size for p in (ASSETS if len(mean) else ASSETS[:1]))
    return {
        "model_bytes": path.stat().st_size,
        "payload_bytes": payload,
        "asset_bytes": assets,
        "package_bytes": path.stat().st_size + assets,
        "uncompressed_package_bytes": payload + assets,
        "text_terms": len(terms),
        "text_columns": len(selected),
        "hidden_units": W.shape[1],
        "quantized": bool(quantized),
    }


class TinyMlpReference:
    """Character TF-IDF, optional standardized E2, ReLU, and sigmoid."""

    def __init__(self, arrays):
        if arrays["schema"].item() != SCHEMA:
            raise ValueError("Unsupported Tiny MLP artifact schema")
        vocab = arrays["vocab_utf8"].tobytes()
        offsets = arrays["vocab_offsets"]
        if (offsets.ndim != 1 or not len(offsets) or offsets[0] != 0
                or offsets[-1] != len(vocab) or (offsets[1:] <= offsets[:-1]).any()):
            raise ValueError("Malformed UTF-8 vocabulary offsets")
        words = [vocab[start:end].decode("utf-8") for start, end in zip(offsets[:-1], offsets[1:])]
        self.vocabulary = {term: idx for idx, term in enumerate(words)}
        self.idf = arrays["idf"]
        if (len(self.vocabulary) != len(words) or self.idf.shape != (len(words),)
                or not np.isfinite(self.idf).all() or (self.idf <= 0).any()):
            raise ValueError("Invalid Tiny MLP vocabulary or IDF")
        self.low, self.high = map(int, arrays["ngram_range"])
        if not 1 <= self.low <= self.high <= 5:
            raise ValueError("Invalid character n-gram range")
        self.indices = arrays["text_indices"] if arrays["select_text"].item() else None
        if self.indices is not None and ((self.indices < 0).any() or (self.indices >= len(words)).any()):
            raise ValueError("Tiny MLP text index out of range")
        self.mean = arrays["e2_mean"]
        self.scale = arrays["e2_scale"]
        if (self.mean.shape not in ((0,), (len(E2_FEATURES),)) or self.mean.shape != self.scale.shape
                or not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all()
                or (self.scale <= 0).any()):
            raise ValueError("Invalid E2 standardization")
        self.W = arrays["hidden_weights"]
        if self.W.dtype == np.int8:
            self.W = self.W.astype(np.float32) * arrays["hidden_weight_scale"]
        self.b = arrays["hidden_bias"]
        self.u = arrays["out_weights"]
        self.c = arrays["out_bias"]
        self.threshold = float(arrays["threshold"])
        n_text = len(words) if self.indices is None else len(self.indices)
        if (self.b.ndim != 1 or self.u.shape != self.b.shape or self.c.ndim != 0
                or self.W.shape != (n_text + len(self.mean), len(self.b))
                or not all(np.isfinite(x).all() for x in (self.W, self.b, self.u, self.c))
                or not np.isfinite(self.threshold) or not 0 <= self.threshold <= np.nextafter(1.0, np.inf)):
            raise ValueError("Invalid Tiny MLP layers or threshold")

    def text_matrix(self, texts):
        """Extract the full character vocabulary before optional selection."""
        data = []
        indices = []
        indptr = [0]
        for text in texts:
            counts = Counter()
            for n in range(self.low, self.high + 1):
                for i in range(len(text) - n + 1):
                    idx = self.vocabulary.get(text[i:i+n])
                    if idx is not None:
                        counts[idx] += 1
            columns = sorted(counts)
            values = (1.0 + np.log([counts[i] for i in columns])).astype(np.float32)
            values *= self.idf[columns]
            norm = np.linalg.norm(values)
            if norm:
                values /= norm
            data.extend(values)
            indices.extend(columns)
            indptr.append(len(data))
        return csr_matrix(
            (np.asarray(data, dtype=np.float32), np.asarray(indices, dtype=np.int32), indptr),
            shape=(len(texts), len(self.vocabulary)),
        )

    def predict_features(self, text_matrix, e2):
        """Scores from full unselected TF-IDF and raw unstandardized E2."""
        active_text = text_matrix if self.indices is None else text_matrix[:, self.indices]
        text_width = active_text.shape[1]
        activation = active_text.astype(np.float32) @ self.W[:text_width]
        if len(self.mean):
            standardized = ((np.asarray(e2, dtype=np.float64) - self.mean) / self.scale).astype(np.float32)
            activation += standardized @ self.W[text_width:]
        hidden = np.maximum(activation + self.b, 0.0)
        return expit(hidden @ self.u + self.c)

    def predict_proba(self, urls):
        urls = list(urls)
        text = self.text_matrix([student_text(url) for url in urls])
        e2 = e2_matrix(urls) if len(self.mean) and urls else None
        if not urls:
            return np.empty(0, dtype=np.float32)
        return self.predict_features(text, e2)


def load_bundle(path):
    with np.load(path, allow_pickle=False) as values:
        arrays = {name: values[name] for name in values.files}
    return TinyMlpReference(arrays)


def benchmark(predictor, urls, warmup=20):
    """Single-URL end-to-end CPU timing, excluding artifact load."""
    urls = list(urls)
    if not urls:
        raise ValueError("At least one benchmark URL is required")
    for i in range(warmup):
        predictor.predict_proba([urls[i % len(urls)]])
    times = []
    for url in urls:
        start = perf_counter_ns()
        predictor.predict_proba([url])
        times.append((perf_counter_ns() - start) / 1_000_000)
    return {
        "p50_ms": float(np.percentile(times, 50)),
        "p95_ms": float(np.percentile(times, 95)),
        "requests": len(urls),
        "warmup": warmup,
    }
