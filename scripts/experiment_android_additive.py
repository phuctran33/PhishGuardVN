"""Compare a single sparse linear Android Student with and without distillation.

Run from the repo with .venv/Scripts/python scripts/experiment_android_additive.py.
Training fits term weights and E2 bins inside each domain fold. Inference is
a TF-IDF dot product plus 20 lookup-table contributions and a sigmoid.
"""
from collections import Counter
from importlib.metadata import version
import gzip
import json
from math import log
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.sparse import csr_matrix, hstack
from scipy.special import expit, logit
from sklearn.feature_extraction.text import TfidfVectorizer
from threadpoolctl import threadpool_limits

from train_lightgbm_student import ROOT, CACHE, load_inputs, verify_cv_targets, write_csv, write_json
from phishguard_vn.student import student_text, sha256, metrics, choose_threshold
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.brand_features import E2_FEATURES
from tiny_mlp_analysis import paired_domain_bootstrap
from tiny_mlp_export import ASSETS, benchmark

ART = ROOT / "artifacts/android_kd_additive"
OUT = ROOT / "reports/tables/android_kd_additive"
CAPS = (8192, 16384)
MODES = ("hard", "kd")
TEMPERATURE = 2.0
REGULARIZATION = 0.5  # coefficient of the L2 gradient for the summed loss


def read_targets(path, rows):
    cached = pd.read_csv(path).set_index("id")
    if not cached.index.is_unique or set(cached.index) != set(rows.id):
        raise ValueError("Teacher targets do not match the fitting IDs")
    aligned = cached.loc[rows.id]
    np.testing.assert_array_equal(aligned.target, rows.target)
    p = aligned.teacher_score.to_numpy()
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid Teacher scores")
    return p


def bin_columns(values, edges):
    return np.column_stack([np.searchsorted(cuts, column, side="right")
                            for cuts, column in zip(edges, values.T, strict=True)])


def bin_matrix(values, edges):
    widths = [len(cuts) + 1 for cuts in edges]
    offsets = np.cumsum([0, *widths[:-1]])
    columns = (bin_columns(values, edges) + offsets).ravel()
    rows = np.repeat(np.arange(len(values)), len(widths))
    return csr_matrix((np.ones(len(rows)), (rows, columns)), shape=(len(values), sum(widths)))


def build_features(fitting, held, e2_fit, e2_held, cap):
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), lowercase=False,
                          min_df=2, max_features=cap, sublinear_tf=True)
    tf = vec.fit_transform(fitting.text)
    # Count distinct training documents per class containing each term.
    presence = tf.copy()
    presence.data.fill(1.0)
    y = fitting.target.to_numpy()
    freq = [(np.asarray(presence[y == cls].sum(axis=0)).ravel() + 1) /
            (np.sum(y == cls) + 2) for cls in (0, 1)]
    scale = 1 + np.minimum(3.0, np.abs(np.log(freq[1] / freq[0])))
    edges = []
    for column in e2_fit.T:
        quantiles = np.unique(np.quantile(column, np.arange(1, 8) / 8))
        # A cut at the max distinguishes binary/rare indicators; a cut at min does not.
        if len(np.unique(column)) == 2:
            quantiles = np.array([column.max()])
        edges.append(quantiles[quantiles > column.min()])
    X = hstack([tf.multiply(scale), bin_matrix(e2_fit, edges)], format="csr")
    H = hstack([vec.transform(held.text).multiply(scale), bin_matrix(e2_held, edges)], format="csr")
    return X, H, vec, scale, edges


def fit(X, y, teacher, mode):
    y = np.asarray(y, dtype=float)
    alpha = 0.5 if mode == "kd" else 0.0
    soft = expit(logit(np.clip(teacher, 1e-8, 1 - 1e-8)) / TEMPERATURE)

    def objective(params):
        w, b = params[:-1], params[-1]
        z = X @ w + b
        s = z / TEMPERATURE
        loss = (1 - alpha) * (np.logaddexp(0, z) - y * z)
        loss += alpha * TEMPERATURE ** 2 * (np.logaddexp(0, s) - soft * s)
        error = (1 - alpha) * (expit(z) - y) + alpha * TEMPERATURE * (expit(s) - soft)
        penalty = 0.5 * REGULARIZATION * (w @ w)
        grad = np.r_[X.T @ error + REGULARIZATION * w, error.sum()]
        return (loss.sum() + penalty) / len(y), grad / len(y)

    result = minimize(objective, np.zeros(X.shape[1] + 1), jac=True, method="L-BFGS-B",
                      options={"maxiter": 1200, "ftol": 1e-11, "gtol": 1e-7})
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(str(result.message))
    return result.x


class PortableAdditive:
    """One offline URL score. Only the frozen model and E2 reference are required."""

    def __init__(self, bundle):
        if bundle["schema"] != "android-research-additive-v1" or bundle["e2_order"] != list(E2_FEATURES):
            raise ValueError("Wrong feature contract")
        self.vocab = {term: (idf, weight) for term, idf, weight in
                      zip(bundle["terms"], bundle["idf"], bundle["weights"], strict=True)}
        self.edges = [np.array(x) for x in bundle["edges"]]
        self.tables = bundle["tables"]
        self.bias = bundle["intercept"]
        self.threshold = bundle["threshold"]

    def predict_proba(self, urls):
        urls = list(urls)
        if not urls:
            return np.array([])
        texts = [student_text(url) for url in urls]
        bins = bin_columns(e2_matrix(urls), self.edges)
        scores = []
        for text, indices in zip(texts, bins):
            counts = Counter(text[i:i+n] for n in range(2, 6) for i in range(len(text)-n+1))
            norm_sq = numerator = 0.0
            for term, count in counts.items():
                entry = self.vocab.get(term)
                if entry is not None:
                    idf, weight = entry
                    value = (1 + log(count)) * idf
                    numerator += value * weight
                    norm_sq += value * value
            score = self.bias + sum(table[idx] for table, idx in zip(self.tables, indices))
            if norm_sq:
                score += numerator / np.sqrt(norm_sq)
            scores.append(expit(score))
        return np.array(scores)


def export(vec, scale, edges, params, threshold):
    n = len(scale)
    tables = np.split(params[n:-1], np.cumsum([len(x) + 1 for x in edges])[:-1])
    return dict(schema="android-research-additive-v1", ngram_range=[2, 5],
                normalization="student_text, sublinear TF, IDF, L2",
                terms=vec.get_feature_names_out().tolist(), idf=vec.idf_.tolist(),
                weights=(params[:n] * scale).tolist(), intercept=float(params[-1]),
                e2_order=list(E2_FEATURES), edges=[x.tolist() for x in edges],
                tables=[x.tolist() for x in tables], threshold=threshold,
                decision_rule="score >= threshold", android_verified=False)


def main():
    train, val, _ = load_inputs()
    if not verify_cv_targets(train):
        raise ValueError("Missing verified fold Teachers")
    e2 = e2_matrix(train.url)
    summary, rows = [], []
    with threadpool_limits(limits=1):
        for fold in (0, 1, 2):
            fitting, held = train[train.fold_id != fold], train[train.fold_id == fold]
            teacher = read_targets(CACHE / f"outer{fold}_fitting_targets.csv.gz", fitting)
            for cap in CAPS:
                X, H, *_ = build_features(fitting, held, e2[fitting.index], e2[held.index], cap)
                for mode in MODES:
                    name = f"add{cap}_{mode}"
                    params = fit(X, fitting.target, teacher, mode)
                    score = expit(H @ params[:-1] + params[-1])
                    values = metrics(held.target, score, 0.5)
                    print(name, fold, "AP", round(values["ap"], 5), flush=True)
                    summary.append(dict(candidate=name, cap=cap, mode=mode, fold_id=fold, **values))
                    rows.append(pd.DataFrame(dict(candidate=name, seed=42, fold_id=fold,
                                id=held.id, y_true=held.target, score=score)))
        oof = pd.concat(rows, ignore_index=True)
        runs = pd.DataFrame(summary)
        write_csv(OUT / "runs.csv", runs)
        write_csv(OUT / "oof.csv.gz", oof)
        ranking = runs.groupby(["cap", "mode"]).ap.mean().unstack()
        # Select KD within this family on Train CV; hard control uses the same dimensions.
        cap = int(ranking.sort_values("kd", ascending=False, kind="stable").index[0])
        thresholds = {}
        for mode in MODES:
            sample = oof[oof.candidate == f"add{cap}_{mode}"]
            thresholds[mode] = choose_threshold(sample.y_true, sample.score, 0.01)
        write_json(OUT / "selection.json", dict(cap=cap, thresholds=thresholds,
                   criterion="max mean three-fold Train AP for KD; smaller cap on tie",
                   threshold_source="pooled Train OOF, FPR target 1%"))
        paired_domain_bootstrap(oof, train.set_index("id").group,
                                [(f"add{cap}_kd", f"add{cap}_hard")],
                                output_path=OUT / "paired_bootstrap.csv")
        base = json.loads((ROOT / "artifacts/student_week7/manifest.json").read_text(encoding="utf8"))
        for path, digest in base["input_sha256"].items():
            if sha256(ROOT / path) != digest:
                raise ValueError("Changed Teacher input: " + path)
        record = base["teacher_targets"]
        path = ROOT / record["path"]
        if sha256(path) != record["sha256"]:
            raise ValueError("Changed released Teacher targets")
        teacher = read_targets(path, train)
        X, H, vec, scale, edges = build_features(train, val, e2, e2_matrix(val.url), cap)
        final, preds = [], []
        for mode in MODES:
            params = fit(X, train.target, teacher, mode)
            artifact = ART / f"{mode}.json"
            write_json(artifact, export(vec, scale, edges, params, thresholds[mode]), compact=True)
            model = PortableAdditive(json.loads(artifact.read_text(encoding="utf8")))
            expected = expit(H @ params[:-1] + params[-1])
            scores = model.predict_proba(val.url)
            np.testing.assert_allclose(expected, scores, rtol=0, atol=1e-10)
            np.testing.assert_array_equal(expected >= model.threshold, scores >= model.threshold)
            files = (artifact, *ASSETS)
            final.append(dict(mode=mode, cap=cap, mean_cv_ap=ranking.loc[cap, mode],
                              **metrics(val.target, scores, model.threshold), sha256=sha256(artifact),
                              package_bytes=sum(p.stat().st_size for p in files),
                              gzip_bytes=sum(len(gzip.compress(p.read_bytes(), compresslevel=6, mtime=0)) for p in files),
                              max_score_diff=float(abs(expected-scores).max()),
                              **benchmark(model, val.sample(n=250, random_state=42).url, warmup=30)))
            preds.append(pd.DataFrame(dict(mode=mode, id=val.id, y_true=val.target, score=scores)))
        write_csv(OUT / "validation.csv", pd.DataFrame(final))
        write_csv(OUT / "validation_predictions.csv.gz", pd.concat(preds, ignore_index=True))
        write_json(ART / "manifest.json", dict(train=len(train), validation=len(val),
                   source_sha256=sha256(__file__), train_target_sha256=sha256(path),
                   cv_target_manifest_sha256=sha256(CACHE / "manifest.json"),
                   models={m:sha256(ART / f"{m}.json") for m in MODES},
                   assets={str(p.relative_to(ROOT)):sha256(p) for p in ASSETS},
                   temperature=TEMPERATURE, alpha=0.5, l2=REGULARIZATION,
                   libraries={x:version(x) for x in ("numpy","scipy","scikit-learn")},
                   external_evaluated=False, official_test_evaluated=False, android_verified=False))


if __name__ == "__main__":
    main()
