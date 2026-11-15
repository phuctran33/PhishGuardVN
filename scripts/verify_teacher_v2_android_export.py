from pathlib import Path
import json
import hashlib
import numpy as np

from phishguard_vn.stacking_candidate import load_candidate
from phishguard_vn.stacking import raw_frame

ROOT = Path.cwd()
OUT = ROOT / "artifacts" / "teacher_v2_android"

c = load_candidate(ROOT)
model = c.model

# Load exported artifacts
manifest = json.loads((OUT / "manifest.json").read_text())
vocab = json.loads((OUT / "svm_vocabulary.json").read_text())
data = np.load(OUT / "teacher_numeric.npz", allow_pickle=False)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

# Verify artifact hashes
for filename, info in manifest["files"].items():
    actual = sha256(OUT / filename)
    assert actual == info["sha256"], f"Hash mismatch: {filename}"

# Verify SVM parameters
svm_pipe = model.bases["svm"]
text_pipe = svm_pipe.named_steps["features"].named_transformers_["text"]
tfidf = text_pipe.named_steps["tfidf"]
canonical = text_pipe.named_steps["canonical"]

assert vocab == {k: int(v) for k, v in tfidf.vocabulary_.items()}
assert np.array_equal(data["svm_idf"], tfidf.idf_)
assert np.array_equal(
    data["svm_coef"], svm_pipe.named_steps["model"].coef_[0]
)

# Verify all exported HistGB trees
hist_pipe = model.bases["hist"]
hist = hist_pipe.named_steps["model"]

for i, iteration in enumerate(hist._predictors):
    assert np.array_equal(
        data[f"tree_{i:03d}"],
        iteration[0].nodes
    ), f"Tree mismatch: {i}"

# Verify baseline, meta parameters and threshold
assert np.array_equal(
    data["hist_baseline"], hist._baseline_prediction
)
assert np.array_equal(
    data["meta_mean"], model.meta.named_steps["scale"].mean_
)
assert np.array_equal(
    data["meta_scale"], model.meta.named_steps["scale"].scale_
)
assert np.array_equal(
    data["meta_coef"], model.meta.named_steps["lr"].coef_[0]
)
assert np.array_equal(
    data["meta_intercept"], model.meta.named_steps["lr"].intercept_
)
assert manifest["threshold"] == c.threshold

# End-to-end reconstruction from exported parameters
urls = [
    "https://www.vietcombank.com.vn/vi-VN/",
    "https://example.com/",
    "http://login-vietcombank.example.org/verify",
]

frame = raw_frame(urls, c.reference, numeric=True)

# SVM: original canonicalization/vectorization, exported coefficients
canonical_urls = canonical.transform(frame["url"])
X_text = tfidf.transform(canonical_urls)

svm_custom = (
    np.asarray(X_text @ data["svm_coef"]).ravel()
    + float(data["svm_intercept"][0])
)

# HistGB: exported nodes
hist_features = hist_pipe.named_steps["features"]
X_hist = np.asarray(hist_features.transform(frame), dtype=np.float64)

def hist_probability(x):
    score = float(data["hist_baseline"][0, 0])

    for i in range(300):
        nodes = data[f"tree_{i:03d}"]
        idx = 0

        while not nodes[idx]["is_leaf"]:
            node = nodes[idx]
            value = x[int(node["feature_idx"])]

            if np.isnan(value):
                left = bool(node["missing_go_to_left"])
            else:
                left = value <= node["num_threshold"]

            idx = int(node["left"] if left else node["right"])

        score += float(nodes[idx]["value"])

    return 1.0 / (1.0 + np.exp(-score))

hist_custom = np.array([
    hist_probability(row) for row in X_hist
])

# Meta LR: exported parameters
base = np.column_stack([svm_custom, hist_custom])
scaled = (base - data["meta_mean"]) / data["meta_scale"]
meta_raw = scaled @ data["meta_coef"] + data["meta_intercept"]
meta_custom = 1.0 / (1.0 + np.exp(-meta_raw.ravel()))

# Compare with original Teacher
svm_original = svm_pipe.decision_function(frame)
hist_original = hist_pipe.predict_proba(frame)[:, 1]
meta_original = model.meta.predict_proba(
    np.column_stack([svm_original, hist_original])
)[:, 1]

print("=== ARTIFACT INTEGRITY ===")
print("Vocabulary:", len(vocab))
print("HistGB trees:", len(hist._predictors))
print("All tree nodes:", sum(
    len(data[f"tree_{i:03d}"].tolist()) for i in range(300)
))
print("Hashes and parameters: PASS")

print("\n=== END-TO-END RECONSTRUCTION ===")
for i, url in enumerate(urls):
    print("\nURL:", url)
    print("SVM error:", abs(float(svm_original[i] - svm_custom[i])))
    print("HistGB error:", abs(float(hist_original[i] - hist_custom[i])))
    print("Meta error:", abs(float(meta_original[i] - meta_custom[i])))
    print("Original score:", repr(float(meta_original[i])))
    print("Export score:", repr(float(meta_custom[i])))

max_error = max(
    np.max(np.abs(svm_original - svm_custom)),
    np.max(np.abs(hist_original - hist_custom)),
    np.max(np.abs(meta_original - meta_custom)),
)

print("\nMaximum error:", float(max_error))
print("RESULT:", "PASS" if max_error < 1e-12 else "FAIL")
