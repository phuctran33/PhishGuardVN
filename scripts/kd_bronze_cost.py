"""Research-only CPU and data-package measurements for Bronze KD Students.

measure() accepts raw URLs in the caller's fixed order. Timings include the
fitted model and all URL preprocessing, exclude loading, and use a warm Windows
Python process. The returned size_bytes includes the fitted vectorizer where
used and the shared offline data needed by preprocessing. It excludes runtimes.
"""
import hashlib
import io
import json
import platform
import sys
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter_ns
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib
import numpy as np
from scipy.special import expit
from threadpoolctl import threadpool_limits
from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.student import student_text
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.student_lightgbm import export_booster

PREFLIGHT = ("https://example.org/", "https://example.com/a/B?x=1",
             "https://sub.example.net/C?q=%2F", "https://example.org:8443/A?q=2")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def as_json(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")


def store_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        staging = Path(tmp.name)
        try:
            tmp.write(data)
        except BaseException:
            tmp.close()
            staging.unlink(missing_ok=True)
            raise
    try:
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)


@lru_cache(maxsize=3)
def shared_assets(representation):
    # The strict URL parser consults its offline PSL even for text/byte models.
    # The brand reference is used only by the E2 extractor.
    archive = ROOT / "artifacts/student_lightgbm"
    metadata = json.loads((archive / "manifest.json").read_text(encoding="utf8"))
    assets = {}
    for relative, expected in metadata["runtime_assets_sha256"].items():
        name = Path(relative).name
        if name == "brand_reference_v1.csv" and representation != "e2":
            continue
        data = (ROOT / relative).read_bytes()
        if digest(data) != expected or digest(data) != metadata["inference_files_sha256"][name]:
            raise ValueError("Offline asset differs from its frozen version: " + name)
        assets[name] = data
    return assets


def encode_bytes(canonical_texts, width=128):
    tokens = np.zeros((len(canonical_texts), width), dtype=np.uint16)
    for i, text in enumerate(canonical_texts):
        raw = text.encode("utf8")[:width]
        tokens[i, :len(raw)] = np.frombuffer(raw, dtype=np.uint8).astype(np.uint16) + 1
    return tokens


def inputs(raw_urls, representation, vectorizer):
    if representation == "e2":
        return e2_matrix(raw_urls)
    texts = [student_text(url) for url in raw_urls]
    if representation == "bytes":
        return encode_bytes(texts)
    if representation == "tfidf" and vectorizer is not None:
        return vectorizer.transform(texts)
    raise ValueError("Representation must be e2, bytes, or tfidf with its fitted vectorizer")


def paths_for(output_path):
    base = Path(output_path)
    if base.suffix == "":
        base = base / "student.joblib"
    if base.suffix != ".joblib":
        raise ValueError("output_path must be a .joblib file or a directory")
    return base, base.with_suffix(".cost.json"), base.with_suffix(".portable.zip")


def portable_tree(model, family):
    if model.family == "constant":
        return {"kind": "constant", "score": float(model.model)}
    if family == "cart":
        t = model.model.tree_
        nodes = []
        for i, left in enumerate(t.children_left):
            if left == -1:
                counts = t.value[i, 0]
                nodes.append([float(counts[1] / counts.sum())])
            else:
                nodes.append([int(t.feature[i]), float(t.threshold[i]), int(left), int(t.children_right[i])])
        return {"kind": "cart", "route_dtype": "float32", "nodes": nodes}
    # Only the tree data are copied. This score-only artifact exports no
    # classification threshold or operating point.
    trees = export_booster(model.model, threshold=0.5, mode="research")["trees"]
    return {"kind": "lightgbm", "trees": trees, "output": "sigmoid(sum(leaf_value))"}


def portable_scores(tree, x):
    if tree["kind"] == "constant":
        return np.full(len(x), tree["score"])
    values = []
    if tree["kind"] == "cart":
        for row in np.asarray(x, dtype=np.float32):
            node = tree["nodes"][0]
            while len(node) > 1:
                feature, threshold, left, right = node
                node = tree["nodes"][left if float(row[feature]) <= threshold else right]
            values.append(node[0])
        return np.asarray(values)
    for row in x:
        logit = 0.0
        for nodes in tree["trees"]:
            node = nodes[0]
            while not node["leaf"]:
                value = row[node["feature"]]
                missing = np.isnan(value) or (value == 0 and node["missing_type"] == "Zero")
                left = node["default_left"] if missing else value <= node["threshold"]
                node = nodes[node["left"] if left else node["right"]]
            logit += node["value"]
        values.append(expit(logit))
    return np.asarray(values)


def tree_archive(path, model, family, assets, x, expected):
    tree = portable_tree(model, family)
    files = {"tree.json": as_json(tree), **assets}
    files["manifest.json"] = as_json({
        "schema": "bronze-kd-e2-tree-score-only-v1", "family": family,
        "feature_order": list(E2_FEATURES), "model_input": "frozen raw E2 v1",
        "sha256": {k: digest(v) for k, v in files.items()}, "android_verified": False,
    })
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as package:
        for name, data in files.items():
            package.writestr(ZipInfo(name, (1980,1,1,0,0,0)), data, compress_type=ZIP_DEFLATED, compresslevel=6)
    with ZipFile(buffer, "r") as package:
        manifest = json.loads(package.read("manifest.json"))
        for name, checksum in manifest["sha256"].items():
            if digest(package.read(name)) != checksum:
                raise ValueError("Portable asset round-trip mismatch: " + name)
        portable = portable_scores(json.loads(package.read("tree.json")), x)
    diff = float(np.max(np.abs(expected-portable)))
    np.testing.assert_allclose(portable, expected, rtol=0, atol=1e-12)
    store_bytes(path, buffer.getvalue())
    return {"portable_zip_bytes": path.stat().st_size, "portable_max_score_error": diff,
            "portable_reference_rows": len(expected), "portable_zip": str(path)}


def measure(model, family, representation, vectorizer, urls, output_path):
    """Return size and latency for one fitted Student on the ordered URL sample.

    output_path is a directory or .joblib name. If urls is a dataframe with
    columns id/url, persist a digest of its ordered IDs as well as the URL digest.
    """
    if representation not in {"e2", "tfidf", "bytes"}:
        raise ValueError("Unknown representation: " + representation)
    if (vectorizer is None) == (representation == "tfidf"):
        raise ValueError("Pass a fitted vectorizer only for tfidf")
    id_hash = None
    if hasattr(urls, "columns"):
        if "id" in urls.columns:
            id_hash = digest(as_json(urls["id"].astype(str).tolist()))
        urls = urls["url"]
    urls = list(urls)
    if not urls:
        raise ValueError("Timing requires a non-empty URL sample")
    artifact, sidecar, portable_path = paths_for(output_path)
    assets = shared_assets(representation)
    resources = {name:digest(data) for name, data in assets.items()}
    fitted = dict(model=model, family=family, representation=representation, vectorizer=vectorizer,
                  assets_sha256=resources, score_only=True)
    serialized = io.BytesIO()
    joblib.dump(fitted, serialized, compress=("zlib", 3), protocol=5)
    data = serialized.getvalue()
    loaded = joblib.load(io.BytesIO(data))
    student = loaded["model"]
    tfidf = loaded["vectorizer"]
    x = inputs(urls, representation, tfidf)
    with threadpool_limits(limits=1):
        expected = np.asarray(model.score(x), dtype=float)
        restored = np.asarray(student.score(x), dtype=float)
        if restored.shape != (len(urls),) or not np.all(np.isfinite(restored)):
            raise ValueError("Expected one finite score per URL")
        np.testing.assert_allclose(restored, expected, rtol=0, atol=1e-12)
        for _ in range(3):
            for u in PREFLIGHT:
                student.score(inputs([u], representation, tfidf))
        elapsed, preprocess, forward, singleton_scores = [], [], [], []
        for u in urls:
            start = perf_counter_ns()
            matrix = inputs([u], representation, tfidf)
            split = perf_counter_ns()
            result = student.score(matrix)[0]
            stop = perf_counter_ns()
            elapsed.append((stop-start)/1e6)
            preprocess.append((split-start)/1e6)
            forward.append((stop-split)/1e6)
            singleton_scores.append(result)
    # Sparse float32 and neural matrix kernels can round differently for N=1.
    single_diff = float(np.max(np.abs(np.asarray(singleton_scores)-expected)))
    np.testing.assert_allclose(singleton_scores, expected, rtol=1e-5, atol=2e-6)
    store_bytes(artifact, data)
    shared = sum(map(len, assets.values()))
    row = dict(family=family, representation=representation, joblib_path=str(artifact),
               model_vectorizer_bytes=len(data), shared_assets_bytes=shared, size_bytes=len(data)+shared,
               p50_ms=float(np.median(elapsed)), p95_ms=float(np.percentile(elapsed,95)),
               preprocess_p50_ms=float(np.median(preprocess)), forward_p50_ms=float(np.median(forward)),
               sample_size=len(urls), warmup_requests=3*len(PREFLIGHT), threads=1,
               sample_sha256=digest(as_json(urls)), sample_ids_sha256=id_hash, joblib_sha256=digest(data),
               batch_vs_single_max_error=single_diff, reload_max_error=float(np.max(abs(restored-expected))),
               python=platform.python_version(), os=platform.platform(), cpu=platform.processor(),
               timing_scope="raw URL to score; native Python warm single requests; excludes load",
               size_scope="zlib-3 joblib including fitted transform plus raw offline data assets; excludes runtime",
               android_verified=False, numpy=version("numpy"), sklearn=version("scikit-learn"))
    if representation == "e2" and family in {"cart", "lightgbm"}:
        row.update(tree_archive(portable_path, student, family, assets, x, expected))
    store_bytes(sidecar, as_json({**row, "shared_assets_sha256":resources}))
    return row
