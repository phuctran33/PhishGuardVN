"""Portable hybrid Student: canonical char TF-IDF + raw E2 -> LightGBM trees.

No LightGBM or Teacher model is needed for this JSON inference reference.
Training is explicit in scripts/train_lightgbm_student.py.
"""
from collections import Counter
from pathlib import Path
import json,sys
from importlib.metadata import version
import numpy as np
from scipy.special import expit
from phishguard_vn.student import student_text,sha256
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.brand_features import E2_FEATURES


def export_features(vectorizer):
    return dict(schema="hybrid-student-features-v1",terms=vectorizer.get_feature_names_out().tolist(),
                idf=vectorizer.idf_.tolist(),ngram_range=list(vectorizer.ngram_range),
                sublinear_tf=True,norm="l2",lowercase=False,feature_order=list(E2_FEATURES),
                normalization="canonical-reference-v1; whitespace-collapse-v1")


def export_booster(model,threshold,mode):
    dump=model.booster_.dump_model()
    if dump["num_tree_per_iteration"]!=1 or dump["average_output"]:
        raise ValueError("Only binary GBDT sum-of-trees is supported")
    trees=[]
    for tree in dump["tree_info"]:
        nodes=[]
        def visit(node):
            index=len(nodes);nodes.append({})
            if "leaf_value" in node:
                nodes[index]=dict(leaf=True,value=float(node["leaf_value"]))
            else:
                if node["decision_type"]!="<=":
                    raise ValueError("Categorical/non-numeric split is unsupported")
                left,right=visit(node["left_child"]),visit(node["right_child"])
                nodes[index]=dict(leaf=False,feature=int(node["split_feature"]),
                    threshold=float(node["threshold"]),left=left,right=right,
                    default_left=bool(node["default_left"]),missing_type=node["missing_type"])
            return index
        visit(tree["tree_structure"]);trees.append(nodes)
    return dict(schema="hybrid-lightgbm-student-v1",model_version="lightgbm-student-"+mode,
                mode=mode,trees=trees,tree_count=len(trees),threshold=float(threshold),
                objective="cross_entropy",leaf_values_include_shrinkage_and_initial_score=True,
                sigmoid=1.0,release_status="experimental",calibrated=False,
                decision_rule="score >= threshold",class_mapping={"benign":0,"phishing":1},
                python_runtime="CPython 3.11",numpy_version=version("numpy"),
                idna_version=version("idna"),tldextract_version=version("tldextract"))


class HybridLightGBMStudent:
    def __init__(self,features,bundle):
        expected=dict(schema="hybrid-lightgbm-student-v1",objective="cross_entropy",
            leaf_values_include_shrinkage_and_initial_score=True,sigmoid=1.0,
            release_status="experimental",calibrated=False,decision_rule="score >= threshold",
            class_mapping={"benign":0,"phishing":1},python_runtime="CPython 3.11",
            numpy_version=version("numpy"),idna_version=version("idna"),
            tldextract_version=version("tldextract"))
        if any(bundle.get(k)!=v for k,v in expected.items()):
            raise ValueError("LightGBM Student runtime/model contract mismatch")
        if sys.version_info[:2]!=(3,11):
            raise RuntimeError("Frozen E2 requires Python 3.11")
        if (features["schema"]!="hybrid-student-features-v1"
                or features["feature_order"]!=list(E2_FEATURES)
                or features["normalization"]!="canonical-reference-v1; whitespace-collapse-v1"
                or features["sublinear_tf"] is not True or features["norm"]!="l2"):
            raise ValueError("Hybrid feature contract mismatch")
        self.terms=features["terms"]
        self.idf=np.asarray(features["idf"],dtype=float)
        if (len(set(self.terms))!=len(self.terms) or not len(self.terms)
                or self.idf.shape!=(len(self.terms),)
                or not np.isfinite(self.idf).all() or (self.idf<=0).any()):
            raise ValueError("Invalid vocabulary/IDF")
        self.index={term:i for i,term in enumerate(self.terms)}
        self.low,self.high=features["ngram_range"]
        self.bundle=bundle
        self.threshold=float(bundle["threshold"])
        if not np.isfinite(self.threshold) or not 0<=self.threshold<=np.nextafter(1.,np.inf):
            raise ValueError("Invalid threshold")
        if not bundle["trees"] or len(bundle["trees"])!=bundle["tree_count"]:
            raise ValueError("Invalid tree count")

    def vector(self,url,e2):
        text=student_text(url)
        counts=Counter(text[i:i+n] for n in range(self.low,self.high+1)
                       for i in range(len(text)-n+1))
        selected=sorted((self.index[t],count) for t,count in counts.items() if t in self.index)
        row={}
        if selected:
            indices=np.array([i for i,_ in selected])
            weights=(1+np.log([count for _,count in selected]))*self.idf[indices]
            weights/=np.linalg.norm(weights)
            row.update(zip(indices.tolist(),weights.tolist()))
        row.update({len(self.terms)+i:float(value) for i,value in enumerate(e2)})
        return row

    def score_row(self,row):
        total=0.
        for tree in self.bundle["trees"]:
            index=0
            for _ in range(len(tree)):
                node=tree[index]
                if node["leaf"]:
                    total+=node["value"];break
                value=row.get(node["feature"],0.)
                missing=np.isnan(value) or (node["missing_type"]=="Zero" and value==0)
                left=node["default_left"] if missing else value<=node["threshold"]
                index=node["left"] if left else node["right"]
            else:raise ValueError("Invalid cyclic tree")
        return float(expit(total))

    def predict_batch(self,urls):
        urls=list(urls)
        E=e2_matrix(urls)
        result=[]
        for url,e2 in zip(urls,E):
            score=self.score_row(self.vector(url,e2))
            result.append(dict(score=score,score_kind="uncalibrated_sigmoid",calibrated=False,
                label="phishing" if score>=self.threshold else "benign",
                class_id=int(score>=self.threshold),threshold=self.threshold,
                model_version=self.bundle["model_version"],release_status="experimental",
                android_verified=False))
        return result

    def predict_one(self,url):
        return self.predict_batch([url])[0]


def load_lightgbm_student(root,mode=None):
    root=Path(root)
    folder=root/"artifacts/student_lightgbm"
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    mode=mode or manifest["selected_mode"]
    if mode not in manifest["models"]:raise ValueError("Unknown LightGBM Student mode")
    for relative,digest in manifest["inference_source_sha256"].items():
        if sha256(root/relative)!=digest:raise ValueError("Inference source changed: "+relative)
    for name,digest in manifest["inference_files_sha256"].items():
        if sha256(folder/name)!=digest:raise ValueError("Artifact changed: "+name)
    for relative,digest in manifest["runtime_assets_sha256"].items():
        if sha256(root/relative)!=digest:raise ValueError("Runtime asset changed: "+relative)
    features=json.loads((folder/"features.json").read_text(encoding="utf-8"))
    model=json.loads((folder/manifest["models"][mode]["json"]).read_text(encoding="utf-8"))
    return HybridLightGBMStudent(features,model)
