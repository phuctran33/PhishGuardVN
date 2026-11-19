"""Export and check the fold-0 research TF-IDF LR Student. No model is fitted.

    python scripts/kd_bronze_lr_portable.py
    python scripts/kd_bronze_lr_portable.py --score-url https://example.org/Report
"""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from math import exp, isfinite, log, sqrt
from pathlib import Path
import platform
import sys
from time import perf_counter_ns
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from phishguard_vn.student import student_text

TAG = "tfidf_lr_large_B_0.9_0_0"
ART = ROOT / "artifacts/student_bronze_kd"
OUT = ART / "lr_portable"
PACKAGE = OUT / "student_score.zip"
PSL = "psl_icann_tldextract_5.4.0.txt"
SCHEMA = "bronze-kd-char-tfidf-lr-score-only-v1"
VALID = ("https://example.org/", "https://EXAMPLE.org:443/Report?Ref=%2F#here",
         "https://user:pass@example.org:8443/A?x=A", "https://bücher.de/Việt?x=🙂",
         "http://127.0.0.1:8080/a", "https://example.org/aa  aa?q=ZZZZ")
INVALID = ("", "http://", "https://example.org:65536", "http://[broken")

def digest(data):
    return sha256(data).hexdigest()

def load_score(package):
    """Verify package integrity, then expose only a raw URL -> uncalibrated score."""
    with ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if (manifest.get("schema") != SCHEMA or manifest.get("score_only") is not True
                or sorted(archive.namelist()) != sorted(("manifest.json", "model.json", PSL))
                or set(manifest["asset_sha256"]) != {"model.json", PSL}):
            raise ValueError("Unexpected research package")
        for name, expected in manifest["asset_sha256"].items():
            if digest(archive.read(name)) != expected:
                raise ValueError(f"Altered asset: {name}")
        parsed = json.loads(archive.read("model.json"))
    if (parsed["ngram_range"] != [3, 5] or parsed["sublinear_tf"] is not True
            or parsed["norm"] != "l2" or parsed["lowercase"] is not False):
        raise ValueError("Unsupported TF-IDF representation")
    terms, idfs, coef = parsed["terms"], parsed["idf"], parsed["coef"]
    if (not terms or len(set(terms)) != len(terms) or len(terms) != len(idfs)
            or any(not isinstance(term, str) or not 3 <= len(term) <= 5 for term in terms)
            or len(terms) != len(coef) or any(not isfinite(v) or v <= 0 for v in idfs)
            or not all(map(isfinite, coef)) or not isfinite(parsed["intercept"])):
        raise ValueError("Invalid linear weights or vocabulary")
    lookup = {term: (weight, slope) for term, weight, slope in zip(terms, idfs, coef)}
    bias = parsed["intercept"]
    def score(raw_url):
        text = student_text(raw_url)
        counts = Counter(text[i:i+n] for n in range(3, 6) for i in range(len(text)-n+1))
        dot = norm2 = 0.
        for term, count in counts.items():
            if term in lookup:
                idf, slope = lookup[term]
                value = (1 + log(count)) * idf
                dot += value * slope
                norm2 += value * value
        z = bias + (dot / sqrt(norm2) if norm2 else 0.)
        if z >= 0:
            return 1 / (1 + exp(-z))
        ez = exp(z)
        return ez / (1 + ez)
    return score

def export():
    import joblib
    import numpy as np
    import pandas as pd
    from threadpoolctl import threadpool_limits
    from kd_bronze_cost import PREFLIGHT, as_json, shared_assets, store_bytes
    from kd_bronze_data import DATA_CACHE, FOLD_IDS, verify_preparation

    verify_preparation()
    original = ART / "screen" / (TAG + ".joblib")
    cost = json.loads(original.with_suffix(".cost.json").read_text(encoding="utf8"))
    source_hash = digest(original.read_bytes())
    if cost["joblib_sha256"] != source_hash:
        raise ValueError("Archived fold-0 model differs from its cost record")
    # Load only the local, hash-checked research artifact. The exported scorer needs no pickle.
    fitted = joblib.load(original)
    vec, lr = fitted["vectorizer"], fitted["model"]
    assets = shared_assets("tfidf")
    if (fitted["family"] != "tfidf_lr" or fitted["representation"] != "tfidf"
            or not fitted["score_only"] or set(assets) != {PSL}
            or fitted["assets_sha256"] != {PSL: digest(assets[PSL])}
            or vec.analyzer != "char" or vec.ngram_range != (3, 5) or vec.lowercase
            or not vec.sublinear_tf or vec.norm != "l2"):
        raise ValueError("Unexpected fitted representation")
    model = dict(terms=vec.get_feature_names_out().tolist(), idf=vec.idf_.tolist(),
                 coef=lr.coefficient.tolist(), intercept=float(lr.intercept),
                 ngram_range=list(vec.ngram_range), sublinear_tf=True, norm="l2", lowercase=False)
    files = {"model.json": as_json(model), **assets}
    files["manifest.json"] = as_json(dict(
        schema=SCHEMA, candidate=TAG, fold=0, seed=42, score_only=True,
        fit_scope="screen: Train core excluding outer domain fold 0; no Bronze rows",
        source_joblib_sha256=source_hash, android_verified=False, released=False,
        output="uncalibrated sigmoid margin; no threshold or class decision",
        preprocessing="student_text: validate using offline ICANN PSL, canonicalize host/port with IDNA, omit scheme/userinfo/fragment, preserve path/query case and escapes, collapse repeated Unicode whitespace",
        score="character 3-5 grams by Unicode code point; known terms only; x=(1+ln(tf))*idf; L2-normalize x; sigmoid(intercept+dot(x,coef)); empty known terms use intercept",
        asset_sha256={name:digest(data) for name, data in files.items()}))
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data, compress_type=ZIP_DEFLATED, compresslevel=6)
    encoded = buffer.getvalue()
    score = load_score(BytesIO(encoded))

    held = joblib.load(DATA_CACHE / "fold0.joblib")["held"].sort_values("id")
    original_ids = pd.read_csv(FOLD_IDS).query("fold_id == 0").id
    if len(held) != 4359 or not held.id.is_unique or set(held.id) != set(original_ids):
        raise ValueError("Expected the frozen 4,359 fold-0 IDs")
    native = lr.score(vec.transform(held.url.map(student_text)))
    portable = np.asarray([score(u) for u in held.url])
    np.testing.assert_allclose(portable, native, rtol=0, atol=1e-12)
    archive_path = ROOT / "reports/tables/student_bronze_kd/screen_oof.csv.gz"
    cols = ["candidate", "seed", "fold_id", "id", "score"]
    slices = [chunk.loc[chunk.candidate.eq(TAG) & chunk.seed.eq(42) & chunk.fold_id.eq(0), ["id","score"]]
              for chunk in pd.read_csv(archive_path, usecols=cols, chunksize=150000)]
    archived = pd.concat(slices).set_index("id")
    if not archived.index.is_unique or set(archived.index) != set(held.id):
        raise ValueError("Archived scores cover different IDs")
    archived_scores = archived.loc[held.id].score.to_numpy()
    np.testing.assert_allclose(archived_scores, portable, rtol=0, atol=1e-12)

    states = []
    for url in VALID:
        reference = float(lr.score(vec.transform([student_text(url)]))[0])
        np.testing.assert_allclose(score(url), reference, rtol=0, atol=1e-12)
        states.append(dict(url=url, canonical=student_text(url), expected_score=reference))
    for url in INVALID:
        try:
            score(url)
        except (TypeError, ValueError):
            states.append(dict(url=url, expected="reject"))
        else:
            raise AssertionError(f"Accepted invalid fixture: {url}")

    drawn = held.sample(n=250, random_state=2357)
    ids_hash = digest(as_json(drawn.id.tolist()))
    if ids_hash != cost["sample_ids_sha256"] or digest(as_json(drawn.url.tolist())) != cost["sample_sha256"]:
        raise ValueError("Timing inputs differ from the original sample")
    with threadpool_limits(limits=1):
        for _ in range(3):
            for url in PREFLIGHT:
                score(url)
        times = []
        for url in drawn.url:
            start = perf_counter_ns()
            score(url)
            times.append((perf_counter_ns() - start) / 1e6)

    report = dict(candidate=TAG, fold=0, seed=42, data_zip_sha256=digest(encoded),
                  data_zip_bytes=len(encoded), terms=len(model["terms"]), parity_rows=len(held),
                  native_max_error=float(np.max(abs(portable-native))),
                  archived_oof_max_error=float(np.max(abs(portable-archived_scores))),
                  p50_ms=float(np.median(times)), p95_ms=float(np.percentile(times,95)),
                  runtime=platform.platform(), python=platform.python_version(), sample_size=len(times),
                  sample_ids_sha256=ids_hash, warmup=3*len(PREFLIGHT), threads=1,
                  timing_scope="warm Python raw URL to score excluding ZIP load; no Android runtime",
                  score_only=True, android_verified=False, synthetic_cases=states)
    store_bytes(PACKAGE, encoded)
    store_bytes(OUT / "verification.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf8"))
    print(json.dumps({key:value for key,value in report.items() if key != "synthetic_cases"}, indent=2))

if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--score-url", action="append", help="Score a URL offline with the exported fold-0 ZIP")
    args = parser.parse_args()
    if args.score_url:
        scorer = load_score(PACKAGE)
        for raw in args.score_url:
            print(json.dumps(scorer(raw)))
    else:
        export()
