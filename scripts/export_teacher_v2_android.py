from pathlib import Path
import hashlib
import json
import sys

import numpy as np
from phishguard_vn.stacking_candidate import load_candidate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "teacher_v2_android"
OUT.mkdir(parents=True, exist_ok=True)

c = load_candidate(ROOT)
model = c.model

# SVM export: retain the frozen fitted pipeline and write its parameters as
# interoperable JSON; Dart does not read joblib or NPZ.
svm = model.bases["svm"]
text = svm.named_steps["features"].named_transformers_["text"]
canonical = text.named_steps["canonical"]
tfidf = text.named_steps["tfidf"]
linear = svm.named_steps["model"]

assert len(tfidf.vocabulary_) == len(tfidf.idf_)
assert linear.coef_.shape == (1, len(tfidf.vocabulary_))
assert tfidf.analyzer == "char"
assert tuple(tfidf.ngram_range) == (2, 5)
assert tfidf.min_df == 2
assert tfidf.sublinear_tf and tfidf.use_idf and tfidf.norm == "l2"
assert tfidf.lowercase is False

vocabulary = {key: int(value) for key, value in tfidf.vocabulary_.items()}
with (OUT / "svm_vocabulary.json").open("w", encoding="utf-8") as f:
    json.dump(vocabulary, f, ensure_ascii=False, separators=(",", ":"))

dart_model = {
    "schema_version": "dart-svm-v1",
    "model_version": "teacher-stacking-v2",
    "config": {
        "analyzer": "char",
        "ngram_range": [2, 5],
        "min_df": 2,
        "sublinear_tf": True,
        "use_idf": True,
        "norm": "l2",
        "lowercase": False,
        "canonical_enabled": bool(canonical.enabled),
        "idf_dtype": str(tfidf.idf_.dtype),
    },
    "vocabulary": vocabulary,
    "idf": tfidf.idf_.astype(np.float64).tolist(),
    "coefficients": linear.coef_[0].astype(np.float64).tolist(),
    "intercept": float(linear.intercept_[0]),
}
model_path = OUT / "dart_svm_model.json"
with model_path.open("w", encoding="utf-8") as f:
    json.dump(dart_model, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

# Preserve/export the existing numeric stack parameters without changing them.
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
meta = model.meta
scaler = meta.named_steps["scale"]
lr = meta.named_steps["lr"]
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

# Generate Python reference decision margins from the frozen fitted SVM for
# every valid URL in docs/mobile_parity_cases.json.
cases_path = ROOT / "docs" / "mobile_parity_cases.json"
parity = json.loads(cases_path.read_text(encoding="utf-8"))
valid_cases = [case for case in parity["cases"] if case["parsed"]["is_valid"]]
urls = [case["url"] for case in valid_cases]
from phishguard_vn.stacking import raw_frame
frame = raw_frame(urls, c.reference, numeric=False)
margins = np.asarray(svm.decision_function(frame), dtype=np.float64)
fixture = {
    "schema_version": "teacher-v2-svm-reference-v1",
    "model_version": "teacher-stacking-v2",
    "source": "fitted sklearn SVM decision_function",
    "absolute_tolerance": 1e-6,
    "cases": [
        {"name": case["name"], "url": case["url"], "margin": float(margin)}
        for case, margin in zip(valid_cases, margins, strict=True)
    ],
}
fixture_path = ROOT / "mobile" / "packages" / "phishguard_features" / "test" / "fixtures" / "svm_reference_margins.json"
fixture_path.parent.mkdir(parents=True, exist_ok=True)
fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

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
        "min_df": int(tfidf.min_df),
        "vocabulary_size": len(tfidf.vocabulary_),
        "sublinear_tf": tfidf.sublinear_tf,
        "use_idf": tfidf.use_idf,
        "norm": tfidf.norm,
        "lowercase": tfidf.lowercase,
        "idf_dtype": str(tfidf.idf_.dtype),
        "canonical_enabled": canonical.enabled,
        "canonical_implementation": "src/phishguard_vn/stacking.py:canonical_url",
        "coefficient_shape": list(linear.coef_.shape),
        "intercept": float(linear.intercept_[0]),
    },
    "hist": {
        "iterations": len(hist._predictors),
        "nodes_per_iteration": [len(iteration[0].nodes) for iteration in hist._predictors],
        "learning_rate": float(hist.learning_rate),
        "baseline": hist._baseline_prediction.tolist(),
        "missing_value_routing": "Use each node's missing_go_to_left",
    },
    "meta": {
        "input_order": list(model.members),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
    },
    "source_bundle_sha256": "63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1",
    "brand_reference_sha256": "6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


files = ("svm_vocabulary.json", "teacher_numeric.npz", "dart_svm_model.json")
for filename in files:
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
print("Total nodes:", sum(len(nodes) for nodes in tree_arrays.values()))
print("Vocabulary:", len(tfidf.vocabulary_))
print("Python SVM reference cases:", len(fixture["cases"]))
print("Feature order:", feature_order)
print("Threshold:", c.threshold)



# Full Teacher v2 export and official per-stage golden fixture.
# This block intentionally uses the frozen fitted candidate only; it does not fit
# or modify any model, feature, threshold, or reference data.
hist_pipeline = model.bases["hist"]
hist_estimator = hist_pipeline.named_steps["model"]
hist_transformer = hist_pipeline.named_steps["features"]
meta_pipeline = model.meta
meta_scaler = meta_pipeline.named_steps["scale"]
meta_lr = meta_pipeline.named_steps["lr"]

from phishguard_vn.stacking import raw_frame

valid_cases = [case for case in parity["cases"] if case["parsed"]["is_valid"]]
full_urls = [case["url"] for case in valid_cases]
full_frame = raw_frame(full_urls, c.reference, numeric=True)

svm_margins = np.asarray(svm.decision_function(full_frame), dtype=np.float64)
hist_raw_scores = np.asarray(
    hist_pipeline.decision_function(full_frame), dtype=np.float64
).reshape(-1)
hist_probabilities = np.asarray(
    hist_pipeline.predict_proba(full_frame)[:, 1], dtype=np.float64
)
meta_inputs = np.column_stack([svm_margins, hist_probabilities])
meta_raw_scores = np.asarray(
    meta_pipeline.decision_function(meta_inputs), dtype=np.float64
).reshape(-1)
meta_probabilities = np.asarray(
    meta_pipeline.predict_proba(meta_inputs)[:, 1], dtype=np.float64
)

full_trees = []
for iteration in hist_estimator._predictors:
    nodes = iteration[0].nodes
    exported_nodes = []
    for node in nodes:
        is_leaf = bool(node["is_leaf"])
        item = {
            "is_leaf": is_leaf,
            "value": float(node["value"]),
        }
        if not is_leaf:
            item.update({
                "feature_idx": int(node["feature_idx"]),
                "num_threshold": float(node["num_threshold"]),
                "left": int(node["left"]),
                "right": int(node["right"]),
                "missing_go_to_left": bool(node["missing_go_to_left"]),
            })
        exported_nodes.append(item)
    full_trees.append(exported_nodes)

full_teacher = {
    "schema_version": "teacher-v2-dart-full-v1",
    "model_version": "teacher-stacking-v2",
    "decision_rule": "score >= threshold",
    "threshold": float(c.threshold),
    "members_order": ["svm", "hist"],
    "meta_input_order": ["svm", "hist"],
    "class_order": [0, 1],
    "feature_order": feature_order,
    "source_bundle_sha256": manifest["source_bundle_sha256"],
    "brand_reference_sha256": manifest["brand_reference_sha256"],
    "leaf_values_include_shrinkage": True,
    "hist": {
        "iterations": len(hist_estimator._predictors),
        "learning_rate": float(hist_estimator.learning_rate),
        "baseline": float(np.asarray(hist_estimator._baseline_prediction).reshape(-1)[0]),
        "trees": full_trees,
    },
    "meta": {
        "input_order": ["svm", "hist"],
        "scaler_mean": meta_scaler.mean_.astype(np.float64).tolist(),
        "scaler_scale": meta_scaler.scale_.astype(np.float64).tolist(),
        "coefficients": meta_lr.coef_[0].astype(np.float64).tolist(),
        "intercept": float(meta_lr.intercept_[0]),
    },
}
full_model_path = OUT / "dart_teacher_v2_model.json"
full_model_path.write_text(
    json.dumps(full_teacher, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
    encoding="utf-8",
)

full_cases = []
for i, case in enumerate(valid_cases):
    score = float(meta_probabilities[i])
    class_id = int(score >= float(c.threshold))
    full_cases.append({
        "name": case["name"],
        "url": case["url"],
        "e2": [float(full_frame.iloc[i][name]) for name in feature_order],
        "svm_margin": float(svm_margins[i]),
        "hist_raw_score": float(hist_raw_scores[i]),
        "hist_probability": float(hist_probabilities[i]),
        "meta_raw_score": float(meta_raw_scores[i]),
        "meta_probability": score,
        "final_score": score,
        "class_id": class_id,
        "label": "phishing" if class_id == 1 else "benign",
    })
full_fixture = {
    "schema_version": "teacher-v2-full-reference-v1",
    "model_version": "teacher-stacking-v2",
    "source": "frozen fitted sklearn Teacher v2 pipeline",
    "absolute_tolerance": 1e-6,
    "cases": full_cases,
}
full_fixture_path = (
    ROOT / "mobile" / "packages" / "phishguard_features" / "test"
    / "fixtures" / "teacher_v2_pipeline_reference.json"
)
full_fixture_path.parent.mkdir(parents=True, exist_ok=True)
full_fixture_path.write_text(
    json.dumps(full_fixture, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
    encoding="utf-8",
)

manifest["full_teacher_export"] = {
    "artifact": full_model_path.name,
    "fixture": str(full_fixture_path.relative_to(ROOT)),
    "hist_tree_count": len(full_trees),
    "hist_node_count": sum(len(tree) for tree in full_trees),
    "meta_input_order": ["svm", "hist"],
}
manifest.setdefault("files", {})[full_model_path.name] = {
    "size_bytes": full_model_path.stat().st_size,
    "sha256": sha256(full_model_path),
}
with (OUT / "manifest.json").open("w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print("Full Teacher artifact:", full_model_path.name, full_model_path.stat().st_size, "bytes")
print("Full Teacher fixture cases:", len(full_cases))
print("HistGB nodes:", sum(len(tree) for tree in full_trees))
