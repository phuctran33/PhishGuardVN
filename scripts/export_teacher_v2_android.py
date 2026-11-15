from pathlib import Path
import hashlib
import json

import numpy as np
from phishguard_vn.stacking_candidate import load_candidate

ROOT = Path.cwd()
OUT = ROOT / "artifacts" / "teacher_v2_android"
OUT.mkdir(parents=True, exist_ok=True)

c = load_candidate(ROOT)
model = c.model

# SVM parameters
svm = model.bases["svm"]
text = svm.named_steps["features"].named_transformers_["text"]
canonical = text.named_steps["canonical"]
tfidf = text.named_steps["tfidf"]
linear = svm.named_steps["model"]

assert len(tfidf.vocabulary_) == len(tfidf.idf_)
assert linear.coef_.shape[1] == len(tfidf.vocabulary_)

with (OUT / "svm_vocabulary.json").open("w", encoding="utf-8") as f:
    json.dump(
    {k: int(v) for k, v in tfidf.vocabulary_.items()},
    f,
    ensure_ascii=False
)

# HistGB parameters
hist_pipe = model.bases["hist"]
hist = hist_pipe.named_steps["model"]
hist_features = hist_pipe.named_steps["features"]

feature_order = None
for name, transformer, columns in hist_features.transformers_:
    if name == "e2":
        feature_order = list(columns)
        break

assert feature_order is not None
assert len(feature_order) == hist.n_features_in_ == 20
assert len(hist._predictors) == 300

tree_arrays = {
    f"tree_{i:03d}": iteration[0].nodes
    for i, iteration in enumerate(hist._predictors)
}

# Meta Logistic Regression
meta = model.meta
scaler = meta.named_steps["scale"]
lr = meta.named_steps["lr"]

# Save numeric model parameters without pickle.
np.savez_compressed(
    OUT / "teacher_numeric.npz",
    svm_idf=tfidf.idf_,
    svm_coef=linear.coef_[0],
    svm_intercept=linear.intercept_,
    hist_baseline=hist._baseline_prediction,
    hist_learning_rate=np.asarray(hist.learning_rate),
    meta_mean=scaler.mean_,
    meta_scale=scaler.scale_,
    meta_coef=lr.coef_[0],
    meta_intercept=lr.intercept_,
    **tree_arrays,
)

manifest = {
    "model_version": "teacher-stacking-v2",
    "runtime_reference": "CPython 3.11",
    "threshold": float(c.threshold),
    "decision_rule": "score >= threshold",
    "score_definition": "Uncalibrated meta-LR score, NOT percent safety",
    "members_order": list(model.members),
    "class_mapping": {"benign": 0, "phishing": 1},
    "feature_order": feature_order,
    "feature_count": len(feature_order),
    "svm": {
        "analyzer": tfidf.analyzer,
        "ngram_range": list(tfidf.ngram_range),
        "vocabulary_size": len(tfidf.vocabulary_),
        "sublinear_tf": tfidf.sublinear_tf,
        "use_idf": tfidf.use_idf,
        "norm": tfidf.norm,
        "lowercase": tfidf.lowercase,
        "canonical_enabled": canonical.enabled,
        "canonical_implementation": "Must match source CanonicalText",
    },
    "hist": {
        "iterations": len(hist._predictors),
        "nodes_per_iteration": [
            len(iteration[0].nodes) for iteration in hist._predictors
        ],
        "learning_rate": float(hist.learning_rate),
        "baseline": hist._baseline_prediction.tolist(),
        "missing_value_routing": "Use each node's missing_go_to_left",
    },
    "meta": {
        "input_order": list(model.members),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
    },
    "source_bundle_sha256":
        "63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1",
    "brand_reference_sha256":
        "6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6",
}

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

for filename in ("svm_vocabulary.json", "teacher_numeric.npz"):
    path = OUT / filename
    manifest.setdefault("files", {})[filename] = {
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }

with (OUT / "manifest.json").open("w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print("EXPORT SUCCESS")
print("Output:", OUT)
for path in sorted(OUT.iterdir()):
    print(path.name, path.stat().st_size, "bytes")
print("Trees exported:", len(tree_arrays))
print("Total nodes:", sum(len(x) for x in tree_arrays.values()))
print("Vocabulary:", len(tfidf.vocabulary_))
print("Feature order:", feature_order)
print("Threshold:", c.threshold)
