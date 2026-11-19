"""Build and verify the Android MLP Student. Training uses the pinned research checkout."""
import argparse
import base64
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.feature_extraction.text import TfidfVectorizer
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from phishguard_vn.student import choose_threshold, metrics, sha256, student_text

ARTIFACT = ROOT / "artifacts/student_mlp_android"
MODEL_FILE = "student_mlp.json.gz"
MANIFEST_FILE = "manifest.json"
PSL_PATH = ROOT / "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt"
VERSION = "student-mlp-kd-int8-v1"
SCHEMA = "android-student-char-tfidf-mlp-int8-v1"
DECISION = "score >= threshold"
HIDDEN = 64
SEED = 49
EXTRA = 8192
ALPHA = 0.9
EXTRA_WEIGHT = 0.25
FPR_BUDGET = 0.01
REFERENCE_REV = "8389b371728d4aab8246c0cf9606eb788a8e0365"
RECIPE = "sparse_mlp_large_D_0.9_0.25_8192"


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))+"\n").encode("utf8")


def file_record(path):
    return dict(bytes=path.stat().st_size, sha256=sha256(path))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+"\n",
                    encoding="utf8", newline="\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf8"))


def id_hash(values):
    return hashlib.sha256("\n".join(values).encode("utf8")).hexdigest()


class StudentMlp:
    """Reference inference from data assets. There is no Teacher dependency."""

    def __init__(self, payload):
        if (payload["schema"] != SCHEMA or payload["model_version"] != VERSION
                or payload["ngram_range"] != [3, 5] or payload["hidden_units"] != HIDDEN
                or payload["decision_rule"] != DECISION
                or payload["weight_layout"] != "row_major_term_then_hidden"):
            raise ValueError("Unsupported Android MLP contract")
        terms = payload["terms"]
        self.indices = {term:i for i,term in enumerate(terms)}
        if (len(terms) != 4096 or len(self.indices) != len(terms)
                or any(not isinstance(term,str) or not 3 <= len(term) <= 5 for term in terms)):
            raise ValueError("Invalid vocabulary")
        self.idf = np.asarray(payload["idf"], dtype=np.float64)
        self.scale = np.asarray(payload["hidden_scales"], dtype=np.float64)
        self.hidden_bias = np.asarray(payload["hidden_bias"], dtype=np.float64)
        self.output_weight = np.asarray(payload["output_weight"], dtype=np.float64)
        self.output_bias = float(payload["output_bias"])
        self.threshold = float(payload["threshold"])
        codes = base64.b64decode(payload["weights_int8_base64"], validate=True)
        self.codes = np.frombuffer(codes, dtype=np.int8).reshape(len(terms), HIDDEN)
        arrays = ((self.idf,(len(terms),)), (self.scale,(HIDDEN,)), (self.hidden_bias,(HIDDEN,)),
                  (self.output_weight,(HIDDEN,)))
        if (any(x.shape != shape or not np.isfinite(x).all() for x,shape in arrays)
                or (self.idf <= 0).any() or (self.scale <= 0).any()
                or not np.isfinite(self.output_bias) or not 0 <= self.threshold <= 1):
            raise ValueError("Invalid MLP vectors or threshold")

    def score(self, url):
        text = student_text(url)
        counts = Counter(text[start:start+n] for n in range(3, 6)
                         for start in range(len(text)-n+1))
        hits = sorted((self.indices[term],count) for term,count in counts.items() if term in self.indices)
        if hits:
            columns, frequencies = zip(*hits)
            values = (1 + np.log(frequencies)) * self.idf[list(columns)]
            linear = (values @ self.codes[list(columns)]) / np.linalg.norm(values)
        else:
            linear = np.zeros(HIDDEN)
        hidden = np.maximum(linear * self.scale + self.hidden_bias, 0)
        return float(expit(hidden @ self.output_weight + self.output_bias))

    def predict(self, url):
        score = self.score(url)
        return dict(model_version=VERSION, decision_rule=DECISION, score_kind="uncalibrated_sigmoid",
                    score=score, threshold=self.threshold, class_id=int(score >= self.threshold))


def load_student(folder=ARTIFACT):
    manifest = read_json(folder / MANIFEST_FILE)
    if (manifest["schema"] != SCHEMA or manifest["model_version"] != VERSION
            or manifest["decision_rule"] != DECISION
            or manifest["classes"] != {"benign": 0, "phishing": 1}
            or manifest["score_kind"] != "uncalibrated_sigmoid"
            or manifest["model"] != file_record(folder / MODEL_FILE)
            or manifest["psl"] != file_record(PSL_PATH)):
        raise ValueError("Android student asset or parser hash mismatch")
    payload = json.loads(gzip.decompress((folder / MODEL_FILE).read_bytes()))
    model = StudentMlp(payload)
    if model.threshold != manifest["threshold"]:
        raise ValueError("Android student threshold mismatch")
    return model


def verified_research(research):
    folder = research / "reports/tables/student_bronze_kd"
    archive = read_json(folder / "research_manifest.json")
    for name in ("mlp_final_lock.json", "mlp_compression_oof.csv.gz"):
        if sha256(folder / name) != archive["output_sha256"][name]:
            raise ValueError("Changed research result: " + name)
    for name in ("kd_bronze_neural.py", "kd_bronze_data.py"):
        path = research / "scripts" / name
        if sha256(path) != archive["source_sha256"][name]:
            raise ValueError("Changed research source: " + name)
    for name, digest in archive["fold_preparation"]["inputs"].items():
        if sha256(research / name) != digest:
            raise ValueError("Changed training input: " + name)
    for name in ("data/splits/url_train.csv", "configs/teacher_lock.json", "src/phishguard_vn/student.py",
                 "src/phishguard_vn/stacking.py", "src/phishguard_vn/url_parser.py"):
        if sha256(ROOT / name) != sha256(research / name):
            raise ValueError("Release branch and research checkout disagree: " + name)
    lock = read_json(folder / "mlp_final_lock.json")
    recipe = lock["kd_recipe"]
    if (recipe != dict(family="sparse_mlp",profile="large",mode="D",alpha=ALPHA,
                       extra_weight=EXTRA_WEIGHT,extra_rows=EXTRA)
            or lock["verification_seeds"][0] != SEED or lock["optimizer_steps"] != 384
            or lock["batch_size"] != 128):
        raise ValueError("Unexpected locked MLP recipe")
    return folder, archive


def threshold_from_oof(folder, core):
    path = folder / "mlp_compression_oof.csv.gz"
    preds = pd.read_csv(path)
    subset = preds[preds.seed.eq(SEED) & preds.encoding.eq("int8")].set_index("id")
    if not subset.index.is_unique or set(subset.index) != set(core.id):
        raise ValueError("Int8 OOF must cover exactly the frozen Core IDs")
    aligned = subset.loc[core.id]
    np.testing.assert_array_equal(aligned.y_true, core.target)
    np.testing.assert_array_equal(aligned.fold_id, core.fold_id)
    threshold = choose_threshold(aligned.y_true, aligned.score, FPR_BUDGET)
    return threshold, dict(scope="pooled_train_group_oof_int8", seed=SEED, rows=len(core),
                           target_fpr=FPR_BUDGET, oof_file_sha256=sha256(path),
                           fitted_oof_metrics=metrics(aligned.y_true,aligned.score,threshold))


def encode_model(vectorizer, params, threshold):
    first = params["first_weight"]
    scale = np.max(np.abs(first), axis=0) / 127.0
    scale[scale == 0] = 1.0
    codes = np.clip(np.rint(first / scale), -127, 127).astype(np.int8)
    model = dict(schema=SCHEMA, model_version=VERSION, decision_rule=DECISION,
                 threshold=threshold, ngram_range=[3,5], hidden_units=HIDDEN,
                 terms=vectorizer.get_feature_names_out().tolist(), idf=vectorizer.idf_.tolist(),
                 weights_int8_base64=base64.b64encode(codes.tobytes(order="C")).decode("ascii"),
                 weight_layout="row_major_term_then_hidden",
                 hidden_scales=scale.tolist(), hidden_bias=params["first_bias"].tolist(),
                 output_weight=params["output_weight"].tolist(),
                 output_bias=float(params["output_bias"][0]))
    return model


def fixtures(model):
    """Synthetic shared cases for Android. Targets are Python outputs, not ground truth."""
    hosts = ["example.com", "sub.example.org", "BÜCHER.de", "xn--bcher-kva.de", "127.0.0.1",
             "[2001:db8::1]", "user:pass@EXAMPLE.com:443", "example.org:8080"]
    tails = ["/", "/A%2FB?Ref=Q#ignore", "/Đăng-nhập?q=🙂", "/abc  xyz?a=x%20y",
             "/a"*90+"?redirect=%2F", "/login/verify?email=test%40example.com"]
    valid = [f"https://{host}{tail}" for host in hosts for tail in tails]
    valid += ["example.com/Case?x=1", "//example.org/path", "http://EXAMPLE.com:80/A",
              "https://example.com:443/", "https://sub.example.com/c?q", "https://example.com/?q=hello"]
    # An offline client must reject these without returning a benign label.
    invalid = ["", "  ", "https://", "https://example.org:65536/", "https://example.org:bad/",
               " https://example.org", "https://[broken", "https://example.org\n/a", "invalid_url"]
    cases = [dict(url=url, status="classified", **model.predict(url)) for url in valid]
    for url in invalid:
        try:
            model.predict(url)
        except (TypeError, ValueError):
            cases.append(dict(url=url, status="rejected"))
        else:
            raise ValueError("Unexpected acceptance for invalid fixture")
    return dict(schema=SCHEMA, score_absolute_tolerance=2e-6, cases=cases)


def build_assets(research, output):
    folder, archive = verified_research(research)
    sys.path.insert(0,str(research / "scripts"))
    from kd_bronze_data import bronze_pool, core_train
    from kd_bronze_neural import PROFILES, TRAINING, fit_neural
    from phishguard_vn.released_teacher import load_released_teacher
    if (TRAINING["steps"],TRAINING["batch_size"],TRAINING["learning_rate"],
            PROFILES["sparse_mlp"]["large"]["hidden_units"]) != (384,128,0.003,HIDDEN):
        raise ValueError("Research MLP training configuration differs")
    core = core_train()
    pool, _ = bronze_pool(core)
    bronze = pool.head(EXTRA)
    if len(bronze) != EXTRA or set(bronze.text) & set(core.text) or set(bronze.id) & set(core.id):
        raise ValueError("Invalid full-Train Bronze supplement")
    threshold, operating_point = threshold_from_oof(folder, core)
    teacher = load_released_teacher(ROOT)
    def teacher_scores(urls):
        values=[]
        for start in range(0, len(urls), 1024):
            values.extend(r["score"] for r in teacher.predict_batch(urls[start:start+1024]))
        scores=np.asarray(values)
        if scores.shape != (len(urls),) or not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
            raise ValueError("Teacher produced invalid soft targets")
        return scores

    print("Scoring 13,078 Gold/Silver and 8,192 Bronze Train URLs with released Teacher v2.",flush=True)
    q_core = (1-ALPHA)*core.target.to_numpy() + ALPHA*teacher_scores(core.url.tolist())
    q_bronze = teacher_scores(bronze.url.tolist())
    all_text = pd.concat([core.text,bronze.text],ignore_index=True)
    vectorizer = TfidfVectorizer(analyzer="char",ngram_range=(3,5),lowercase=False, max_features=4096,
                                 min_df=2,sublinear_tf=True,norm="l2")
    vectorizer.fit(core.text)
    X = vectorizer.transform(all_text)
    target = np.r_[q_core,q_bronze]
    sample_weights = np.r_[np.ones(len(core)),np.full(len(bronze),EXTRA_WEIGHT*len(core)/len(bronze))]
    print("Fitting full-Train Student and exporting first-layer int8 weights.",flush=True)
    model = fit_neural("sparse_mlp","large",X,target,sample_weights,SEED)
    payload = encode_model(vectorizer,model.parameters,threshold)
    output.mkdir(parents=True,exist_ok=True)
    (output/MODEL_FILE).write_bytes(gzip.compress(json_bytes(payload),compresslevel=6,mtime=0))
    lock = read_json(ROOT/"configs/teacher_lock.json")
    manifest = dict(schema=SCHEMA,model_version=VERSION,decision_rule=DECISION,
        score_kind="uncalibrated_sigmoid",threshold=threshold,classes={"benign":0,"phishing":1},
        model=file_record(output/MODEL_FILE),psl=file_record(PSL_PATH),
        teacher=dict(model_version=lock["model_version"],bundle_sha256=lock["bundle"]["sha256"],
                     lock_sha256=sha256(ROOT/"configs/teacher_lock.json")),
        research_revision=REFERENCE_REV,research_fingerprint=archive["benchmark_fingerprint"],
        training=dict(recipe=RECIPE, seed=SEED, core_rows=len(core),bronze_rows=len(bronze),
          train_source_sha256=sha256(ROOT/"data/splits/url_train.csv"),
          core_ids_sha256=id_hash(core.id),bronze_ids_sha256=id_hash(bronze.id),
          alpha=ALPHA,bronze_weight=EXTRA_WEIGHT,training=TRAINING,fit_scope="full_train"),
        operating_point=operating_point,android_verified=False)
    write_json(output/MANIFEST_FILE,manifest)
    reopened=load_student(output)
    native = expit(np.maximum((X[:len(core)] @ reopened.codes)*reopened.scale + reopened.hidden_bias,0)
                   @ reopened.output_weight + reopened.output_bias)
    portable = np.asarray([reopened.score(url) for url in core.url])
    np.testing.assert_allclose(portable,native,atol=2e-6,rtol=0)
    np.testing.assert_array_equal(portable >= threshold,native >= threshold)
    write_json(output/"python_reference.json",fixtures(reopened))
    write_json(output/"verification.json",dict(full_train_score_parity_rows=len(core),
        max_score_error=float(np.max(np.abs(portable-native))), decision_differences=0,
        model_data_bytes=(output/MODEL_FILE).stat().st_size,android_verified=False))
    return manifest


def build(research, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".student-mlp-") as staging:
        directory = Path(staging)
        manifest = build_assets(research, directory)
        output.mkdir(parents=True, exist_ok=True)
        # Publish the checksum manifest last. A concurrent reader can reject
        # an incomplete generation instead of accepting a mismatched model.
        for name in (MODEL_FILE, "python_reference.json", "verification.json", MANIFEST_FILE):
            (directory / name).replace(output / name)
        return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root",type=Path,help="Checkout of research/student-bronze-kd")
    parser.add_argument("--output",type=Path,default=ARTIFACT)
    parser.add_argument("--predict",nargs="+",help="Read packaged assets and score URLs offline")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        if args.predict:
            model = load_student(args.output)
            print(json.dumps([model.predict(url) for url in args.predict]))
        elif args.research_root:
            report = build(args.research_root.resolve(),args.output)
            print(json.dumps(dict(model=report["model_version"],threshold=report["threshold"],
                                  model_bytes=report["model"]["bytes"]),indent=2))
        else:
            parser.error("Specify --research-root to build or --predict to score.")
