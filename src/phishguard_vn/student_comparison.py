"""Experimental compact E2 Students. Frozen Teacher/E2 and old LR stay untouched.

The JSON predictor is deliberately small: standardize + linear/MLP, or tree walk.
Training and selection remain explicit in scripts/compare_students.py.
"""
from pathlib import Path
import json
import sys
from importlib.metadata import version
import numpy as np
from scipy.special import expit

from phishguard_vn.brand_features import E2_FEATURES, load_reference
from phishguard_vn.stacking import raw_frame
from phishguard_vn.student import Student, sha256


def e2_matrix(urls):
    return raw_frame(list(urls))[list(E2_FEATURES)].to_numpy(dtype=float)


def weighted_copies(X, q):
    """Same fractional BCE as old LR; all families use identical target weights."""
    q = np.asarray(q, dtype=float)
    if q.shape != (len(X),) or not np.isfinite(q).all() or ((q < 0) | (q > 1)).any():
        raise ValueError("Targets must be finite in [0,1]")
    return np.concatenate([X, X]), np.r_[np.ones(len(q)), np.zeros(len(q))], np.r_[q, 1-q]


def export_e2(model, scaler, family, threshold):
    value = dict(schema="student-e2-small-v1", model_version="student-week7-"+family,
                 family=family, feature_order=list(E2_FEATURES), threshold=float(threshold),
                 score_kind="uncalibrated_sigmoid_or_vote", calibrated=False,
                 release_status="experimental", python_runtime="CPython 3.11",
                 numpy_version=version("numpy"), tldextract_version=version("tldextract"),
                 idna_version=version("idna"), reference_sha256=load_reference().sha256,
                 class_mapping={"benign":0,"phishing":1}, decision_rule="score >= threshold")
    if scaler is not None:
        value["mean"], value["scale"] = scaler.mean_.tolist(), scaler.scale_.tolist()
    if family == "e2_lr":
        value["coef"],value["intercept"] = model.coef_[0].tolist(),float(model.intercept_[0])
    elif family == "e2_mlp":
        value["weights"] = [w.tolist() for w in model.coefs_]
        value["biases"] = [b.tolist() for b in model.intercepts_]
        value["activation"] = "relu"
    elif family == "e2_hist":
        value["baseline"] = float(model._baseline_prediction[0,0])
        value["trees"] = []
        for iteration in model._predictors:
            nodes = iteration[0].nodes
            if nodes["is_categorical"].any():
                raise ValueError("Categorical splits are not supported")
            value["trees"].append([
                dict(leaf=bool(n["is_leaf"]),feature=int(n["feature_idx"]),
                     threshold=float(n["num_threshold"]),left=int(n["left"]),
                     right=int(n["right"]),value=float(n["value"])) for n in nodes])
        value["leaf_values_include_shrinkage"] = True
    elif family == "e2_extra":
        value["trees"] = []
        for estimator in model.estimators_:
            t=estimator.tree_
            value["trees"].append([
                dict(leaf=bool(t.children_left[i] == -1),feature=int(t.feature[i]),
                     threshold=float(t.threshold[i]),left=int(t.children_left[i]),
                     right=int(t.children_right[i]),
                     value=float(t.value[i,0,1]/t.value[i,0].sum())) for i in range(t.node_count)])
        value["routing_dtype"] = "float32"
    else:
        raise ValueError("Unknown E2 Student family")
    return value


class E2Student:
    def __init__(self, bundle):
        expected = dict(schema="student-e2-small-v1",feature_order=list(E2_FEATURES),
                        release_status="experimental",calibrated=False,
                        class_mapping={"benign":0,"phishing":1},decision_rule="score >= threshold",
                        python_runtime="CPython 3.11",numpy_version=version("numpy"),
                        tldextract_version=version("tldextract"),idna_version=version("idna"),
                        reference_sha256=load_reference().sha256)
        if any(bundle.get(k) != v for k,v in expected.items()):
            raise ValueError("E2 Student runtime/feature/reference contract mismatch")
        if sys.version_info[:2] != (3,11):
            raise RuntimeError("Frozen E2 reference arithmetic requires CPython 3.11")
        self.bundle = bundle
        self.family = bundle["family"]
        if self.family not in ("e2_lr","e2_mlp","e2_hist","e2_extra"):
            raise ValueError("Unknown E2 Student family")
        self.threshold = float(bundle["threshold"])
        if not np.isfinite(self.threshold) or not 0 <= self.threshold <= np.nextafter(1.,np.inf):
            raise ValueError("Invalid threshold")
        if self.family in ("e2_lr","e2_mlp"):
            self.mean,self.scale = np.asarray(bundle["mean"]),np.asarray(bundle["scale"])
            if (self.mean.shape!=(20,) or self.scale.shape!=(20,)
                    or not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all()
                    or (self.scale<=0).any()):
                raise ValueError("Invalid scaler")

    @staticmethod
    def tree_values(tree, X):
        values=[]
        for row in X:
            index=0
            # Exports are trusted, hash-checked local model artifacts.
            for _ in range(len(tree)):
                node=tree[index]
                if node["leaf"]:
                    values.append(node["value"])
                    break
                index=node["left"] if row[node["feature"]] <= node["threshold"] else node["right"]
            else:
                raise ValueError("Invalid cyclic tree")
        return np.asarray(values)

    def score_features(self, X):
        X=np.asarray(X,dtype=float)
        if X.ndim!=2 or X.shape[1]!=20 or not np.isfinite(X).all():
            raise ValueError("Expected finite N x 20 E2 matrix")
        b=self.bundle
        if self.family in ("e2_lr","e2_mlp"):
            X=(X-self.mean)/self.scale
        if self.family=="e2_lr":
            result=expit(X @ np.asarray(b["coef"]) + b["intercept"])
        elif self.family=="e2_mlp":
            for i,(w,bias) in enumerate(zip(b["weights"],b["biases"])):
                X=X @ np.asarray(w) + np.asarray(bias)
                X=np.maximum(X,0) if i<len(b["weights"])-1 else expit(X)
            result=X[:,0]
        elif self.family=="e2_hist":
            result=expit(b["baseline"]+sum(self.tree_values(t,X) for t in b["trees"]))
        else:
            # sklearn ExtraTrees routes float32 input, even with float64 thresholds.
            X=X.astype(np.float32)
            result=sum(self.tree_values(t,X) for t in b["trees"])/len(b["trees"])
        if not np.isfinite(result).all() or ((result<0)|(result>1)).any():
            raise ValueError("Invalid Student scores")
        return result

    def predict_batch(self, urls):
        scores=self.score_features(e2_matrix(urls))
        return [dict(score=float(s),label="phishing" if s>=self.threshold else "benign",
                     class_id=int(s>=self.threshold),threshold=self.threshold,
                     model_version=self.bundle["model_version"],calibrated=False,
                     release_status="experimental",android_verified=False) for s in scores]

    def predict_one(self,url):
        return self.predict_batch([url])[0]


def load_comparison_student(root,candidate=None):
    root=Path(root)
    manifest=json.loads((root/"artifacts/student_comparison/manifest.json").read_text(encoding="utf-8"))
    candidate=candidate or manifest["selected_candidate"]
    for p,digest in manifest["inference_source_sha256"].items():
        if sha256(root/p)!=digest:
            raise ValueError("Inference source hash mismatch: "+p)
    # Feature assets are needed for all input validation and E2 extraction.
    for p,record in manifest["required_assets"].items():
        if sha256(root/p)!=record["sha256"]:
            raise ValueError("Required asset hash mismatch: "+p)
    if candidate not in manifest["models"]:
        raise ValueError("Unknown candidate")
    record=manifest["models"][candidate]
    p=root/record["path"]
    if sha256(p)!=record["sha256"]:
        raise ValueError("Student model hash mismatch")
    bundle=json.loads(p.read_text(encoding="utf-8"))
    return Student(bundle) if record["family"]=="text_lr" else E2Student(bundle)
