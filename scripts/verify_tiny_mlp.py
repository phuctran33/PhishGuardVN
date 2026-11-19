"""Controlled follow-up to the Tiny MLP proposal, using frozen Train folds."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import chi2
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from train_lightgbm_student import CACHE, ROOT, load_inputs, verify_cv_targets, write_csv, write_json
from phishguard_vn.student import choose_threshold, metrics, sha256
from phishguard_vn.student_comparison import e2_matrix

PLAN_PATH = ROOT / "configs/week7_tiny_mlp.json"
OUT = ROOT / "reports/tables/student_tiny_mlp"
ART = ROOT / "artifacts/student_tiny_mlp"


def loss_and_gradient(z, y, teacher_score, teacher_logit, mode, alpha, logit_variance):
    cross_entropy = np.logaddexp(0., z) - y * z
    residual = expit(z) - y
    if mode == "hard":
        return cross_entropy, residual
    if mode == "score_kd":
        q = (1 - alpha) * y + alpha * teacher_score
        return np.logaddexp(0., z) - q * z, expit(z) - q
    error = z - teacher_logit
    logit_loss = .5 * error ** 2 / logit_variance
    logit_gradient = error / logit_variance
    if mode == "logit_only":
        return logit_loss, logit_gradient
    if mode == "mixed_logit":
        return ((1 - alpha) * cross_entropy + alpha * logit_loss,
                (1 - alpha) * residual + alpha * logit_gradient)
    raise ValueError("Unknown loss mode: " + mode)


def logits(X, weights):
    W, b, u, c = weights
    return np.maximum(X @ W + b, 0) @ u + c[0]


def fit_mlp(X, y, teacher_score, mode, seed, plan):
    """One ReLU layer, same initialization and minibatch order within each seed."""
    rng = np.random.default_rng(seed)
    width = plan["hidden_units"]
    W = (rng.standard_normal((X.shape[1], width)) * np.sqrt(2 / X.shape[1])).astype(np.float32)
    b = np.zeros(width, dtype=np.float32)
    u = (rng.standard_normal(width) / np.sqrt(width)).astype(np.float32)
    c = np.zeros(1, dtype=np.float32)
    weights = W, b, u, c
    first = [np.zeros_like(w) for w in weights]
    second = [np.zeros_like(w) for w in weights]
    teacher_logits = logit(np.clip(teacher_score, 1e-6, 1 - 1e-6)).astype(np.float32)
    variance = max(float(np.var(teacher_logits)), 1.0)
    y = np.asarray(y, dtype=np.float32)
    step = 0
    for _ in range(plan["epochs"]):
        order = rng.permutation(len(y))
        for start in range(0, len(y), plan["batch_size"]):
            batch = order[start:start + plan["batch_size"]]
            xb = X[batch]
            hidden = np.maximum(xb @ W + b, 0)
            z = hidden @ u + c[0]
            _, dz = loss_and_gradient(z, y[batch], teacher_score[batch],
                                      teacher_logits[batch], mode, plan["alpha"], variance)
            dz /= len(batch)
            dh = (dz[:, None] * u) * (hidden > 0)
            gradients = (xb.T @ dh, dh.sum(axis=0), hidden.T @ dz, np.array([dz.sum()]))
            step += 1
            rate = plan["learning_rate"] * np.sqrt(1 - .999 ** step) / (1 - .9 ** step)
            for param, gradient, m, v in zip(weights, gradients, first, second):
                m *= .9
                m += .1 * gradient
                v *= .999
                v += .001 * gradient ** 2
                param -= rate * m / (np.sqrt(v) + 1e-8)
    losses, _ = loss_and_gradient(logits(X, weights), y, teacher_score, teacher_logits,
                                  mode, plan["alpha"], variance)
    if not np.isfinite(losses).all():
        raise ValueError("Nonfinite training loss")
    return weights, float(losses.mean())


def build_inputs(fitting, held, e2, held_e2, plan):
    """Fit TF-IDF/selection/scaler solely on fitting rows in this context."""
    opts = dict(analyzer="char", ngram_range=(3, 5), min_df=2,
                sublinear_tf=True, lowercase=False, dtype=np.float32)
    vec = TfidfVectorizer(**opts, max_features=plan["text_features"])
    train_text = vec.fit_transform(fitting.text)
    # Select the compact vocabulary on fitting labels, then recompute L2 there.
    # Only these terms and their IDF must be shipped for the compact variant.
    relevance, _ = chi2(train_text, fitting.target)
    relevance = np.nan_to_num(relevance, nan=-np.inf)
    order = np.lexsort((np.arange(len(relevance)), -relevance))
    keep = np.sort(order[:plan["compact_features"]])
    terms = vec.get_feature_names_out()[keep]
    compact_vec = TfidfVectorizer(**opts, vocabulary={term: i for i, term in enumerate(terms)})
    compact_train = compact_vec.fit_transform(fitting.text)
    scaler = StandardScaler().fit(e2)
    train_e2 = csr_matrix(scaler.transform(e2).astype(np.float32))
    test_e2 = csr_matrix(scaler.transform(held_e2).astype(np.float32))
    return {
        name: (hstack([text, train_e2], format="csr"),
               hstack([vectorizer.transform(held.text), test_e2], format="csr"), vectorizer, scaler)
        for name, text, vectorizer in (("full", train_text, vec), ("compact", compact_train, compact_vec))
    }


def read_targets(path, fitting):
    scores = pd.read_csv(path, usecols=["id", "target", "teacher_score"])
    aligned = fitting[["id", "target"]].merge(scores, on="id", validate="one_to_one",
                                               suffixes=("", "_cache"), sort=False)
    q = aligned.teacher_score.to_numpy(dtype=np.float32)
    if (len(scores) != len(fitting) or len(aligned) != len(fitting)
            or not aligned.target.eq(aligned.target_cache).all()
            or not aligned.id.equals(fitting.id.reset_index(drop=True))
            or not np.isfinite(q).all() or np.any((q < 0) | (q > 1))):
        raise ValueError("Invalid/misaligned targets: " + str(path))
    return q


def fit_arguments(plan):
    for family, modes in plan["variants"].items():
        for mode in modes:
            yield family, mode


def cv_run(train, train_e2, plan, out):
    runs, predictions = [], []
    for fold in plan["folds"]:
        fitting, held = train.loc[train.fold_id.ne(fold)], train.loc[train.fold_id.eq(fold)]
        targets = read_targets(CACHE / f"outer{fold}_fitting_targets.csv.gz", fitting)
        features = build_inputs(fitting, held, train_e2[fitting.index], train_e2[held.index], plan)
        for family, mode in fit_arguments(plan):
            X, H, _, _ = features[family]
            name = f"{family}__{mode}"
            for seed in plan["seeds"]:
                t0 = time.perf_counter()
                weights, train_loss = fit_mlp(X, fitting.target, targets, mode, seed, plan)
                score = expit(logits(H, weights))
                record = dict(candidate=name, seed=seed, fold_id=fold,
                              train_loss=train_loss, fit_seconds=time.perf_counter() - t0,
                              **metrics(held.target, score, .5))
                runs.append(record)
                predictions.append(pd.DataFrame(dict(candidate=name, seed=seed, fold_id=fold,
                    id=held.id.to_numpy(), y_true=held.target.to_numpy(), score=score)))
                print(f"CV {name} fold={fold} seed={seed}: AP {record['ap']:.5f}, {record['fit_seconds']:.1f}s", flush=True)
        write_csv(out / "cv_runs.csv", pd.DataFrame(runs))
        write_csv(out / "cv_predictions.csv.gz", pd.concat(predictions, ignore_index=True))
    return pd.DataFrame(runs), pd.concat(predictions, ignore_index=True)


def summarize_cv(runs, oof, plan, out):
    by_seed = runs.groupby(["candidate", "seed"], as_index=False).agg(
        ap=("ap", "mean"), recall=("recall", "mean"), precision=("precision", "mean"),
        fpr=("fpr", "mean"), f1=("f1", "mean"))
    summary = by_seed.groupby("candidate", as_index=False).agg(mean_ap=("ap", "mean"),
        seed_sd=("ap", "std"), recall_at_half=("recall", "mean"), fpr_at_half=("fpr", "mean"),
        precision_at_half=("precision", "mean"), f1_at_half=("f1", "mean"))
    summary = summary.sort_values(["mean_ap", "candidate"], ascending=[False, True])
    write_csv(out / "cv_summary.csv", summary)
    # Train-OOF thresholds for optional final-Validation models. Never applied as
    # if they were an independently chosen outer-CV operating point.
    export_rows = oof.loc[oof.seed.eq(plan["export_seed"])]
    thresholds = {name: choose_threshold(group.y_true, group.score, plan["fpr_budget"])
                  for name, group in export_rows.groupby("candidate")}
    write_json(out / "selection.json", dict(
        ranking=summary.candidate.tolist(), primary="mean Train fold AP across matched seeds",
        thresholds=thresholds, threshold_source="Train OOF seed 42", validation_used_for_selection=False))
    return thresholds


def final_run(train, val, train_e2, plan, thresholds, out, art):
    from tiny_mlp_export import bundle, load_bundle

    baseline = json.loads((ROOT / "artifacts/student_week7/manifest.json").read_text(encoding="utf-8"))
    target_record = baseline["teacher_targets"]
    target_path = ROOT / target_record["path"]
    if sha256(target_path) != target_record["sha256"]:
        raise ValueError("Released Teacher target artifact changed")
    for file, digest in baseline["input_sha256"].items():
        if sha256(ROOT / file) != digest:
            raise ValueError("Released Teacher input changed: " + file)
    targets = read_targets(target_path, train)
    val_e2 = e2_matrix(val.url)
    features = build_inputs(train, val, train_e2, val_e2, plan)
    records, predictions = [], []
    for family, mode in fit_arguments(plan):
        X, H, vec, scaler = features[family]
        name = f"{family}__{mode}"
        weights, _ = fit_mlp(X, train.target, targets, mode, plan["export_seed"], plan)
        native_score = expit(logits(H, weights))
        threshold = thresholds[name]
        for quantized in (False, True):
            # Both formats retain the same predeclared threshold.
            dtype = "int8" if quantized else "float32"
            path = art / f"{name}__{dtype}.npz"
            sizes = bundle(path, vec, None, scaler, weights, threshold, quantized=quantized)
            predictor = load_bundle(path)
            portable_score = np.asarray(predictor.predict_proba(val.url.tolist()))
            if not quantized:
                np.testing.assert_allclose(portable_score, native_score, atol=2e-6, rtol=0)
                np.testing.assert_array_equal(portable_score >= threshold, native_score >= threshold)
            evaluation = metrics(val.target, portable_score, threshold)
            records.append(dict(candidate=name, encoding=dtype, seed=plan["export_seed"],
                **evaluation, **sizes, max_abs_score_delta=float(np.max(abs(portable_score-native_score))),
                decision_flips=int(np.sum((portable_score>=threshold) != (native_score>=threshold))),
                sha256=sha256(path), file=path.name))
            predictions.append(pd.DataFrame(dict(candidate=name, encoding=dtype, id=val.id,
                                               y_true=val.target, score=portable_score)))
            print(f"Validation {name} {dtype}: AP {evaluation['ap']:.5f}, TP/FP {evaluation['tp']}/{evaluation['fp']}", flush=True)
    write_csv(out / "validation_metrics.csv", pd.DataFrame(records))
    write_csv(out / "validation_predictions.csv.gz", pd.concat(predictions, ignore_index=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--analysis-only", action="store_true", help="Use saved CV; run final export and bootstrap only")
    args = parser.parse_args()
    out = args.output_root.resolve() / OUT.relative_to(ROOT)
    art = args.output_root.resolve() / ART.relative_to(ROOT)
    out.mkdir(parents=True, exist_ok=True)
    art.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    train, val, _ = load_inputs()
    if not verify_cv_targets(train):
        raise ValueError("Verified fold Teacher targets are required")
    train_e2 = e2_matrix(train.url)
    inputs = ["data/splits/url_train.csv", "data/splits/url_val.csv",
              "artifacts/student_lightgbm/cv_targets/manifest.json",
              "artifacts/student_week7/teacher_targets.csv.gz",
              "reports/tables/stacking/train_ids.csv.gz", "configs/teacher_lock.json",
              "models/teacher_v2_candidate.joblib", str(PLAN_PATH.relative_to(ROOT)).replace("\\","/")]
    source = Path(__file__)
    fingerprints = {p: sha256(ROOT / p) for p in inputs}
    cv_provenance = dict(inputs=fingerprints, runner_sha256=sha256(source))
    with threadpool_limits(limits=1):
        if args.analysis_only:
            record = json.loads((out / "cv_provenance.json").read_text(encoding="utf-8"))
            for key,value in cv_provenance.items():
                if record[key] != value:
                    raise ValueError("Saved CV provenance mismatch: " + key)
            for file,digest in record["cv_output_sha256"].items():
                if sha256(out / file) != digest:
                    raise ValueError("Saved CV output changed: " + file)
            runs = pd.read_csv(out / "cv_runs.csv")
            oof = pd.read_csv(out / "cv_predictions.csv.gz")
        else:
            runs, oof = cv_run(train, train_e2, plan, out)
            cv_provenance["cv_output_sha256"] = {file:sha256(out / file)
                for file in ("cv_runs.csv","cv_predictions.csv.gz")}
            write_json(out / "cv_provenance.json", cv_provenance)
            thresholds = summarize_cv(runs, oof, plan, out)
            return
        thresholds = summarize_cv(runs, oof, plan, out)
        final_run(train, val, train_e2, plan, thresholds, out, art)
        from tiny_mlp_analysis import paired_domain_bootstrap
        paired_domain_bootstrap(oof, train.set_index("id")["group"], plan["bootstrap_pairs"],
                                replicates=1000, random_state=42, output_path=out / "paired_bootstrap.csv")
    write_json(art / "manifest.json", dict(
        plan=plan, created_utc=datetime.now(timezone.utc).isoformat(),
        revision=subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip(),
        source_sha256={f"scripts/{file}": sha256(ROOT/"scripts"/file) for file in
                       ("verify_tiny_mlp.py","tiny_mlp_analysis.py","tiny_mlp_export.py")},
        input_sha256=fingerprints, output_sha256={p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file()},
        artifact_sha256={p.name:sha256(p) for p in sorted(art.glob("*.npz"))},
        train_rows=len(train), validation_rows=len(val), validation_positives=int(val.target.sum()),
        platform=platform.platform(), python=sys.version,
        libraries={p:version(p) for p in ("numpy","scipy","scikit-learn","pandas")},
        teacher_updated=False, android_verified=False, official_test_evaluated=False))


if __name__ == "__main__":
    main()
