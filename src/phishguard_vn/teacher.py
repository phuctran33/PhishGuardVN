"""Teacher text inference: raw strings -> frozen TF-IDF -> LinearSVC. No fitting/network."""
from pathlib import Path
import hashlib,json
from importlib.metadata import version
import joblib
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.feature_extraction.text import TfidfVectorizer

MODEL_VERSION="teacher-tfidf-svm-v1"
PREPROCESSING_VERSION="raw-char-3-5-v1"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_pipeline(model):
    if not isinstance(model,Pipeline) or list(model.named_steps)!=["tfidf","model"]:
        raise ValueError("Expected frozen TF-IDF/LinearSVC pipeline")
    vectorizer=model.named_steps["tfidf"];classifier=model.named_steps["model"]
    expected=dict(analyzer="char",ngram_range=(3,5),min_df=2,max_features=50000,
                  lowercase=False,sublinear_tf=True,use_idf=True,norm="l2")
    if not isinstance(vectorizer,TfidfVectorizer) or any(vectorizer.get_params()[k]!=v for k,v in expected.items()):
        raise ValueError("Teacher preprocessing differs from selected candidate")
    if not isinstance(classifier,LinearSVC) or classifier.C!=0.5 or list(classifier.classes_)!=[0,1]:
        raise ValueError("Teacher classifier/config/classes mismatch")
    if classifier.n_features_in_!=len(vectorizer.vocabulary_) or len(vectorizer.idf_)!=classifier.n_features_in_:
        raise ValueError("Teacher vocabulary/IDF/classifier dimensions differ")

class Teacher:
    def __init__(self,bundle):
        if bundle.get("model_version")!=MODEL_VERSION or bundle.get("preprocessing_version")!=PREPROCESSING_VERSION:
            raise ValueError("Unknown Teacher model/preprocessing version")
        self.bundle=bundle;self.pipeline=bundle["pipeline"]
        validate_pipeline(self.pipeline)
    def predict_batch(self,urls):
        if not isinstance(urls,(list,tuple)) or not urls:
            raise TypeError("urls must be a nonempty list/tuple of strings")
        if any(not isinstance(u,str) for u in urls):
            raise TypeError("Every URL must be a string")
        if any(not u.strip() or "\x00" in u for u in urls):
            raise ValueError("Empty/whitespace-only or NUL-containing input is invalid")
        # Validation never strips, normalizes, lowercases or changes the input.
        margins=np.asarray(self.pipeline.decision_function(urls))
        labels=self.pipeline.predict(urls)  # estimator owns boundary/tie behavior
        if not np.isfinite(margins).all():
            raise ValueError("Teacher returned non-finite margins")
        return [{"label":"phishing" if int(y) else "benign","class_id":int(y),
                 "margin":float(s),"score":float(s),"score_kind":"decision_function",
                 "decision_rule":"estimator.predict","model": "tfidf_linear_svm",
                 "model_version":MODEL_VERSION,"preprocessing_version":PREPROCESSING_VERSION,
                 "score_definition":"Signed SVM margin; positive favors phishing, not a probability"}
                for y,s in zip(labels,margins)]
    def predict_one(self,url):
        return self.predict_batch([url])[0]

def load_teacher(root,lock=None):
    root=Path(root)
    if lock is None:
        lock=json.loads((root/"configs/week6_teacher_lock.json").read_text(encoding="utf-8"))
    if (lock.get("teacher_finalized") is not True or lock.get("selected_by")!="core_train_group_cv"
        or lock.get("external_used_for_selection") is not False
        or lock.get("feature_set")!="url_raw_char_3_5" or lock.get("threshold")!=0
        or lock.get("decision_rule")!="estimator.predict"):
        raise ValueError("Teacher text lock is not finalized under the selected Core protocol")
    for key in ["bundle","selection_record"]:
        path=root/lock[key]["path"]
        if not path.is_file() or sha(path)!=lock[key]["sha256"]:
            raise ValueError(f"Missing or changed Teacher {key}")
    metadata=json.loads((root/lock["selection_record"]["path"]).read_text(encoding="utf-8"))
    if metadata["versions"]["scikit-learn"]!=version("scikit-learn"):
        raise RuntimeError("Incompatible scikit-learn; install the exact version in Teacher metadata")
    if metadata.get("teacher_finalized") is not True or metadata["model_sha256"]!=lock["bundle"]["sha256"]:
        raise ValueError("Teacher metadata/lock mismatch")
    bundle=joblib.load(root/lock["bundle"]["path"])  # only this trusted, hash-checked project bundle
    teacher=Teacher(bundle)
    if bundle["feature_fingerprint"]!=feature_fingerprint(teacher.pipeline):
        raise ValueError("Vocabulary/IDF/classifier fingerprint mismatch")
    return teacher

def feature_fingerprint(pipeline):
    v=pipeline.named_steps["tfidf"];c=pipeline.named_steps["model"]
    return {"vocabulary_sha256":hashlib.sha256(json.dumps({k:int(i) for k,i in v.vocabulary_.items()},sort_keys=True).encode()).hexdigest(),
            "idf_sha256":hashlib.sha256(v.idf_.tobytes()).hexdigest(),
            "coefficient_sha256":hashlib.sha256(c.coef_.tobytes()+c.intercept_.tobytes()).hexdigest()}
