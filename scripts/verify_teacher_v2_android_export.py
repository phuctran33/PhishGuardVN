from pathlib import Path
import json
import hashlib

import numpy as np

from phishguard_vn.stacking_candidate import load_candidate
from phishguard_vn.stacking import raw_frame

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "teacher_v2_android"

c = load_candidate(ROOT)
model = c.model
manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
vocab = json.loads((OUT / "svm_vocabulary.json").read_text(encoding="utf-8"))
data = np.load(OUT / "teacher_numeric.npz", allow_pickle=False)
dart_model = json.loads((OUT / "dart_svm_model.json").read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


for filename, info in manifest["files"].items():
    actual = sha256(OUT / filename)
    assert actual == info["sha256"], f"Hash mismatch: {filename}"

svm_pipe = model.bases["svm"]
text_pipe = svm_pipe.named_steps["features"].named_transformers_["text"]
tfidf = text_pipe.named_steps["tfidf"]
canonical = text_pipe.named_steps["canonical"]
linear = svm_pipe.named_steps["model"]
assert vocab == {key: int(value) for key, value in tfidf.vocabulary_.items()}
assert np.array_equal(data["svm_idf"], tfidf.idf_)
assert np.array_equal(data["svm_coef"], linear.coef_[0])
assert np.array_equal(data["svm_intercept"], linear.intercept_)
assert dart_model["vocabulary"] == vocab
assert np.array_equal(np.asarray(dart_model["idf"], dtype=np.float64), tfidf.idf_)
assert np.array_equal(np.asarray(dart_model["coefficients"], dtype=np.float64), linear.coef_[0])
assert dart_model["intercept"] == float(linear.intercept_[0])
assert dart_model["config"]["canonical_enabled"] == canonical.enabled

hist_pipe = model.bases["hist"]
hist = hist_pipe.named_steps["model"]
for i, iteration in enumerate(hist._predictors):
    assert np.array_equal(data[f"tree_{i:03d}"], iteration[0].nodes), f"Tree mismatch: {i}"

assert np.array_equal(data["hist_baseline"], hist._baseline_prediction)
assert np.array_equal(data["meta_mean"], model.meta.named_steps["scale"].mean_)
assert np.array_equal(data["meta_scale"], model.meta.named_steps["scale"].scale_)
assert np.array_equal(data["meta_coef"], model.meta.named_steps["lr"].coef_[0])
assert np.array_equal(data["meta_intercept"], model.meta.named_steps["lr"].intercept_)
assert manifest["threshold"] == c.threshold

# Export integrity check uses sklearn's vectorizer but the serialized weight
# arrays. Full Dart-vs-Python margins are independently checked in Dart tests.
urls = [
    "https://www.vietcombank.com.vn/vi-VN/",
    "https://example.com/",
    "http://login-vietcombank.example.org/verify",
]
frame = raw_frame(urls, c.reference, numeric=False)
canonical_urls = canonical.transform(frame["url"])
X_text = tfidf.transform(canonical_urls)
svm_custom = np.asarray(X_text @ data["svm_coef"]).ravel() + float(data["svm_intercept"][0])
svm_original = svm_pipe.decision_function(frame)
np.testing.assert_allclose(svm_original, svm_custom, rtol=0, atol=1e-12)

fixture_path = ROOT / "mobile" / "packages" / "phishguard_features" / "test" / "fixtures" / "svm_reference_margins.json"
fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
fixture_urls = [case["url"] for case in fixture["cases"]]
reference = np.asarray(svm_pipe.decision_function(raw_frame(fixture_urls, c.reference, numeric=False)))
np.testing.assert_allclose(reference, [case["margin"] for case in fixture["cases"]], rtol=0, atol=0)

print("Artifact hashes, SVM JSON arrays, NPZ parameters, and HistGB parameters: PASS")
print("SVM reconstruction max absolute error:", float(np.max(np.abs(svm_original - svm_custom))))
print("Python reference fixture cases:", len(fixture_urls))
print("Vocabulary:", len(vocab))
print("HistGB trees:", len(hist._predictors))
print("Threshold:", c.threshold)
