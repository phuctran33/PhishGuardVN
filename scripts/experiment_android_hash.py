"""Vocabulary-free offline linear Student, paired hard vs temperature-2 distillation.

Run without arguments for the bounded Group CV experiment.
Use --predict URL to load the selected experimental KD bundle locally.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import time
import zipfile

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.sparse import csr_matrix
from scipy.special import expit, logit
from sklearn.feature_extraction.text import TfidfTransformer
from threadpoolctl import threadpool_limits

from train_lightgbm_student import CACHE, ROOT, load_inputs, verify_cv_targets, write_csv, write_json
from phishguard_vn.student import choose_threshold, metrics, sha256, student_text
from verify_compact_lightgbm import aligned_teacher_scores, released_target_path
from tiny_mlp_analysis import paired_domain_bootstrap

OUT = ROOT / "reports/tables/android_kd_hash"
ART = ROOT / "artifacts/android_kd_hash"
PSL = ROOT / "mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt"
WIDTHS = (32768, 65536)
MODES = ("hard", "kd")
TEMPERATURE = 2.0
ALPHA = 0.5
C = 8.0
FNV_OFFSET = 2166136261
FNV_PRIME = 16777619


def counts_for_text(text, width):
    """FNV-1a over UTF-8 bytes of each 2..5 codepoint gram; unsigned bucket."""
    chars = [char.encode("utf-8") for char in text]
    counts = Counter()
    for start in range(len(chars) - 1):
        value = FNV_OFFSET
        for offset, char in enumerate(chars[start:start + 5]):
            for byte in char:
                value = ((value ^ byte) * FNV_PRIME) & 0xffffffff
            if offset >= 1:
                counts[value % width] += 1
    return counts


def hash_matrix(texts, width):
    indices, data, offsets = [], [], [0]
    for text in texts:
        for column, count in sorted(counts_for_text(text, width).items()):
            indices.append(column)
            data.append(count)
        offsets.append(len(indices))
    return csr_matrix((np.array(data, dtype=float), indices, offsets), shape=(len(texts), width))


def fit_linear(x, y, teacher_scores, mode):
    """Convex loss summed over examples plus ||w||²/(2C); bias unregularized."""
    y = np.asarray(y, dtype=float)
    alpha = ALPHA if mode == "kd" else 0.0
    soft = expit(logit(np.clip(teacher_scores, 1e-7, 1 - 1e-7)) / TEMPERATURE)
    def objective(parameters):
        w, bias = parameters[:-1], parameters[-1]
        z = x @ w + bias
        warm = z / TEMPERATURE
        losses = (1 - alpha) * (np.logaddexp(0., z) - y * z)
        losses += alpha * TEMPERATURE**2 * (np.logaddexp(0., warm) - soft * warm)
        errors = (1 - alpha) * (expit(z) - y) + alpha * TEMPERATURE * (expit(warm) - soft)
        gradient = np.r_[x.T @ errors + w / C, errors.sum()]
        return losses.sum() + w @ w / (2*C), gradient
    result = minimize(objective, np.zeros(x.shape[1] + 1), jac=True, method="L-BFGS-B",
                      options={"maxiter": 600, "ftol": 1e-10, "gtol": 1e-5})
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(f"Linear optimization failed: {result.message}")
    return result.x, result.nit


def save_bundle(path, w, idf, threshold, mode):
    contract = dict(schema="hash-student-v1", n_buckets=len(idf), mode=mode, ngram_range=[2, 5],
                    hash="FNV-1a-32-unsigned-mod-width", input="student_text", char_unit="Unicode code point",
                    bytes="UTF-8", transform="sublinear term frequency times smoothed IDF, L2 normalized",
                    score="uncalibrated sigmoid", positive_if="score >= threshold", threshold=threshold,
                    bias=float(w[-1]), dtype="little-endian float32", weight_file="coef.f32le",
                    idf_file="idf.f32le", psl_asset=PSL.name, psl_sha256=sha256(PSL))
    files = {"contract.json": json.dumps(contract, indent=2).encode("utf-8"),
             "idf.f32le": np.asarray(idf, dtype="<f4").tobytes(),
             "coef.f32le": np.asarray(w[:-1], dtype="<f4").tobytes()}
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)


class HashReference:
    """Independent per-gram implementation matching the portable byte contract."""
    def __init__(self, path):
        with zipfile.ZipFile(path) as archive:
            self.meta = json.loads(archive.read("contract.json"))
            self.idf = np.frombuffer(archive.read("idf.f32le"), dtype="<f4")
            self.w = np.frombuffer(archive.read("coef.f32le"), dtype="<f4")
        self.width = self.meta["n_buckets"]
        if (self.meta["schema"] != "hash-student-v1" or len(self.idf) != self.width or
                len(self.w) != self.width or not np.isfinite(self.w).all() or
                not np.isfinite(self.idf).all() or self.idf.min() <= 0):
            raise ValueError("Invalid hash Student package")
        if sha256(PSL) != self.meta["psl_sha256"]:
            raise ValueError("Changed public suffix asset")

    def score(self, url):
        text = student_text(url)
        counts = Counter()
        for length in range(2, 6):
            for i in range(len(text) - length + 1):
                value = FNV_OFFSET
                for byte in text[i:i+length].encode("utf-8"):
                    value = ((value ^ byte) * FNV_PRIME) & 0xffffffff
                counts[value % self.width] += 1
        keys = list(counts)
        tfidf = (1.0 + np.log(list(counts.values()))) * self.idf[keys]
        norm = np.linalg.norm(tfidf)
        margin = self.meta["bias"] + (tfidf @ self.w[keys] / norm if norm else 0.0)
        return float(expit(margin))


def experiment():
    train, validation, _ = load_inputs()
    if not verify_cv_targets(train):
        raise ValueError("Missing frozen fold Teacher targets")
    release_targets = released_target_path()
    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    rows, predictions = [], []
    for width in WIDTHS:
        counts = hash_matrix(train.text, width)
        for fold in (0, 1, 2):
            fit = train[train.fold_id.ne(fold)]
            held = train[train.fold_id.eq(fold)]
            target = aligned_teacher_scores(fit, CACHE / f"outer{fold}_fitting_targets.csv.gz")
            tfidf = TfidfTransformer(sublinear_tf=True)
            x = tfidf.fit_transform(counts[fit.index])
            h = tfidf.transform(counts[held.index])
            for mode in MODES:
                w, iterations = fit_linear(x, fit.target, target, mode)
                scores = expit(h @ w[:-1] + w[-1])
                candidate = f"{width}_{mode}"
                result = metrics(held.target, scores, .5)
                rows.append(dict(candidate=candidate, width=width, mode=mode, fold_id=fold,
                                 iterations=iterations, **result))
                predictions.append(pd.DataFrame(dict(id=held.id, fold_id=fold, candidate=candidate,
                                                      seed=42, y_true=held.target, score=scores)))
                print(f"{candidate} fold {fold} AP={result['ap']:.6f} iters={iterations}", flush=True)
    oof = pd.concat(predictions, ignore_index=True)
    runs = pd.DataFrame(rows)
    summary = runs.groupby(["width", "mode"], as_index=False).ap.mean()
    width = int(summary[summary["mode"].eq("kd")].sort_values(["ap","width"], ascending=[False,True]).iloc[0].width)
    thresholds = {}
    for mode in MODES:
        cohort = oof[oof.candidate.eq(f"{width}_{mode}")]
        if len(cohort) != len(train) or not cohort.id.is_unique:
            raise ValueError("Expected one OOF score per train ID")
        thresholds[mode] = choose_threshold(cohort.y_true, cohort.score, .01)
    write_csv(OUT / "cv_runs.csv", runs)
    write_csv(OUT / "cv_summary.csv", summary)
    write_csv(OUT / "oof.csv.gz", oof)
    write_json(OUT / "selection.json", dict(width=width, thresholds=thresholds, selected_by="mean 3-fold Train KD AP",
               threshold_source="Train OOF with FPR <= 1%", temperatures=[TEMPERATURE], seed=42, deterministic=True,
               modes=list(MODES), alpha=ALPHA, C=C, widths=list(WIDTHS), source_sha256=sha256(Path(__file__)),
               train_fold_manifest_sha256=sha256(CACHE/"manifest.json"), final_train_targets_sha256=sha256(release_targets)))
    comparisons = [(f"{w}_kd", f"{w}_hard") for w in WIDTHS]
    paired_domain_bootstrap(oof, train.set_index("id").group, comparisons, output_path=OUT/"paired_ci.csv")
    # All model selection and operating points are now frozen.
    counts = hash_matrix(train.text, width)
    tfidf = TfidfTransformer(sublinear_tf=True)
    x = tfidf.fit_transform(counts)
    h = tfidf.transform(hash_matrix(validation.text, width))
    target = aligned_teacher_scores(train, release_targets)
    sample = validation.sort_values("id").sample(n=250, random_state=42).url.tolist()
    measured, answers = [], []
    for mode in MODES:
        w, iterations = fit_linear(x, train.target, target, mode)
        native = expit(h @ w[:-1] + w[-1])
        threshold = thresholds[mode]
        path = ART / f"{mode}.zip"
        save_bundle(path, w, tfidf.idf_, threshold, mode)
        ref = HashReference(path)
        scores = np.asarray([ref.score(url) for url in validation.url])
        np.testing.assert_allclose(scores, native, atol=2e-6, rtol=0)
        np.testing.assert_array_equal(scores >= threshold, native >= threshold)
        # Include non-ASCII code points and schemes outside this cohort.
        urls = ["https://example.org/Đăng-Nhập?q=😀", "https://例子.com/Aa?x=%2F",
                "HTTP://[2001:db8::1]:80/X", "http://EXAMPLE.org:80/X#fragment"]
        probe = tfidf.transform(hash_matrix([student_text(u) for u in urls], width))
        np.testing.assert_allclose([ref.score(u) for u in urls], expit(probe @ w[:-1] + w[-1]), atol=2e-6)
        write_json(OUT / f"example_{mode}.json", [dict(url=url, score=ref.score(url), positive=ref.score(url) >= threshold) for url in urls])
        for invalid in (" ", "https://example.org:99999", "example.test/", None):
            try:
                ref.score(invalid)
            except (TypeError, ValueError):
                continue
            raise ValueError("Invalid URL accepted by offline reference")
        for url in sample[:30]:
            ref.score(url)
        times = []
        for url in sample:
            before = time.perf_counter_ns()
            ref.score(url)
            times.append((time.perf_counter_ns() - before) / 1e6)
        measured.append(dict(mode=mode, width=width, iterations=iterations,
            **metrics(validation.target, scores, threshold), p50_ms=np.percentile(times,50),
            p95_ms=np.percentile(times,95), model_bytes=path.stat().st_size, shared_psl_bytes=PSL.stat().st_size,
            package_bytes=path.stat().st_size + PSL.stat().st_size, sha256=sha256(path),
            max_abs_parity_error=float(np.max(abs(scores-native))), parity_labels_different=0))
        answers.append(pd.DataFrame(dict(id=validation.id, y_true=validation.target, mode=mode, score=scores)))
    write_csv(OUT / "validation.csv", pd.DataFrame(measured))
    write_csv(OUT / "validation_predictions.csv.gz", pd.concat(answers, ignore_index=True))
    print(pd.DataFrame(measured).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predict", help="Score one raw URL using the locally exported KD Student")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        if args.predict:
            ref = HashReference(ART / "kd.zip")
            score = ref.score(args.predict)
            print(json.dumps({"score": score, "positive": score >= ref.meta["threshold"]}))
        else:
            experiment()
