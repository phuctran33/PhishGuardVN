"""Audit persisted OOF, measure format stress/resources, and paired domain bootstrap.

No fitting or model/threshold selection from Validation/external/stress occurs here.
"""
from pathlib import Path
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit
import hashlib
import argparse
import json
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_stacking as run
from phishguard_vn.stacking import raw_frame, score_model, choose_threshold, canonical_url
from phishguard_vn.brand_features import E2_FEATURES, load_reference
from phishguard_vn.url_parser import SCHEME_RE

OUT, LOCAL = run.OUT, run.LOCAL


_FRAME_CACHE = {}
_SPLIT_CACHE = {}


def audit_splits(frame):
    key = run.id_hash(frame)
    if key not in _SPLIT_CACHE:
        _SPLIT_CACHE[key] = list(StratifiedGroupKFold(2, shuffle=True, random_state=42).split(
            frame, frame.target, frame.registrable_domain))
    return _SPLIT_CACHE[key]


def partition_frame(train, context):
    key = (run.id_hash(train), context)
    if key in _FRAME_CACHE:
        return _FRAME_CACHE[key]
    pieces = context.split("/")
    frame = train if pieces[0] == "full_train" else train.loc[train.fold_id.ne(int(pieces[0][5:]))]
    frame = frame.reset_index(drop=True)
    i = 1
    while i + 1 < len(pieces):
        if pieces[i] in {"inner", "threshold", "meta"} and pieces[i + 1].isdigit():
            splits = audit_splits(frame)
            frame = frame.iloc[splits[int(pieces[i + 1])][0]].reset_index(drop=True)
            i += 2
        else:
            i += 1
    _FRAME_CACHE[key] = frame
    return frame


def audit(train, specs):
    manifest = json.loads((OUT / "execution_manifest.json").read_text(encoding="utf-8"))
    from phishguard_vn.stacking import source_hashes
    for path, digest in manifest["input_sha256"].items():
        actual = source_hashes()[path[8:]] if path.startswith("runtime/") else run.sha(ROOT / path)
        assert actual == digest, path
    partitions = pd.read_csv(OUT / "partitions.csv.gz")
    for context, g in partitions.groupby("context"):
        expected = partition_frame(train, context)
        assert set(g.id) == set(expected.id), context
        assert g.id.is_unique and g.groupby("registrable_domain").held_fold.nunique().eq(1).all()
        assert set(g.held_fold) == {0, 1}
        expected_folds = np.full(len(expected), -1)
        for fold, (_, b) in enumerate(audit_splits(expected)):
            expected_folds[b] = fold
        actual_folds = g.set_index("id").loc[expected.id, "held_fold"].to_numpy()
        np.testing.assert_array_equal(actual_folds, expected_folds)
    ledger = pd.read_csv(OUT / "fit_ledger.csv", keep_default_na=False)
    assert ledger.status.eq("success").all()
    for row in ledger.to_dict("records"):
        fitting = partition_frame(train, row["context"])
        assert len(fitting) == row["training_rows"], row
        assert run.id_hash(fitting) == row["training_ids_sha256"], row
    predictions, summaries = [], []
    for spec in specs:
        name = spec["id"]
        folds = []
        for fold in [0, 1, 2]:
            record = json.loads((OUT / f"{name}_outer{fold}.json").read_text(encoding="utf-8"))
            oof = pd.read_csv(OUT / f"{name}_outer{fold}_oof.csv.gz", float_precision="round_trip")
            expected = train.loc[train.fold_id.eq(fold)].sort_values("id")
            assert oof.id.is_unique and oof.id.tolist() == expected.id.tolist()
            assert oof.y_true.tolist() == expected.target.tolist() and oof.fold_id.eq(fold).all()
            assert np.isfinite(oof.score).all() and oof.prediction.isin([0, 1]).all()
            assert run.id_hash(expected) == record["held_ids_sha256"]
            actual = run.metrics(oof.y_true, oof.prediction, oof.score)
            for k, v in actual.items():
                assert abs(v - record["native"][k]) < 1e-12, (name, fold, k)
            fitting = train.loc[train.fold_id.ne(fold)]
            assert set(fitting.registrable_domain).isdisjoint(expected.registrable_domain)
            t_oof = pd.read_csv(OUT / f"{name}_outer{fold}_threshold_oof.csv.gz", float_precision="round_trip")
            assert t_oof.id.is_unique and t_oof.id.tolist() == fitting.id.tolist()
            assert t_oof.y_true.tolist() == fitting.target.tolist()
            assert run.id_hash(fitting) == record["fitting_ids_sha256"]
            for p in [.01, .02]:
                t = choose_threshold(t_oof.y_true, t_oof.score, p)
                assert t == record["thresholds"][str(p)]
                assert (oof["prediction_" + str(p)] == (oof.score >= t)).all()
                recomputed = run.metrics(oof.y_true, oof["prediction_" + str(p)], oof.score)
                for k, v in recomputed.items():
                    assert abs(v - record["threshold_metrics"][str(p)][k]) < 1e-12
            folds.append(dict(experiment=name, fold=fold, inner_ap=record["inner_ap"], **actual,
                recall_fpr1=record["threshold_metrics"]["0.01"]["recall"],
                fpr_at1=record["threshold_metrics"]["0.01"]["fpr"],
                recall_fpr2=record["threshold_metrics"]["0.02"]["recall"],
                fpr_at2=record["threshold_metrics"]["0.02"]["fpr"]))
            predictions.append(oof)
        ff = pd.DataFrame(folds)
        summaries.append(dict(experiment=name, **ff.drop(columns=["experiment", "fold"]).mean().to_dict()))
    all_oof = pd.concat(predictions, ignore_index=True)
    assert not all_oof.duplicated(["experiment", "id"]).any()
    assert len(all_oof) == len(specs) * len(train)
    summary = pd.DataFrame(summaries).sort_values("ap", ascending=False)
    run.write_csv(OUT / "summary.csv", summary)
    run.write_json(OUT / "audit.json", dict(status="PASS", pipelines=len(specs),
        configurations=sum(len(run.ParameterGrid(s["grid"])) for s in specs),
        oof_rows=len(all_oof), fits=len(ledger), failed_fits=0,
        benchmark_fits=int(ledger.context.str.startswith("outer").sum()),
        candidate_fits=int(ledger.context.str.startswith("full_train").sum()),
        partition_contexts=partitions.context.nunique(), partition_rows=len(partitions),
        checks=["IDs/labels/folds", "outer/inner/meta/threshold domain isolation",
                "fitting-ID hashes", "round-trip CSV metrics", "fitting-only threshold constraints",
                "registered source/data fingerprints"], official_test_evaluated=False))
    return all_oof, summary


def transform_url(value, mode):
    if mode == "add_https":
        return "https://" + SCHEME_RE.sub("", value, count=1).removeprefix("//")
    if mode == "remove_scheme":
        return SCHEME_RE.sub("", value, count=1).removeprefix("//")
    working = value if SCHEME_RE.match(value) else ("http:" + value if value.startswith("//") else "//" + value)
    p = urlsplit(working)
    # Uppercase host only; preserve userinfo, ports, path/query/fragment byte content.
    netloc = p.netloc
    prefix, sep, hostpart = netloc.rpartition("@")
    if not sep:
        hostpart, prefix = netloc, ""
    if hostpart.startswith("["):
        end = hostpart.index("]")
        hostpart = hostpart[:end + 1].upper() + hostpart[end + 1:]
    else:
        host, colon, port = hostpart.partition(":")
        hostpart = host.upper() + (colon + port if colon else "")
    netloc = (prefix + "@" if sep else "") + hostpart
    output = urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))
    if not SCHEME_RE.match(value) and not value.startswith("//"):
        output = output.removeprefix("//")
    return output


def stress_and_resources(train, specs):
    reference = load_reference()
    # All models share these exact input frames, including freshly extracted raw E2.
    original = raw_frame(train.url.tolist(), reference)
    assert list(original) == ["url", *E2_FEATURES]
    np.testing.assert_allclose(original[list(E2_FEATURES)], train[list(E2_FEATURES)], rtol=0, atol=1e-12)
    modes = ["add_https", "remove_scheme", "uppercase_hostname"]
    frames, changes = {}, {}
    for mode in modes:
        path = LOCAL / ("stress_" + mode + ".joblib")
        urls = [transform_url(u, mode) for u in train.url]
        if path.exists():
            frame = joblib.load(path)
            assert frame.url.tolist() == urls
        else:
            frame = raw_frame(urls, reference)
            joblib.dump(frame, path)
        frames[mode] = frame
        delta = abs(frame[list(E2_FEATURES)].to_numpy() - original[list(E2_FEATURES)].to_numpy())
        changes[mode] = dict(raw_strings_changed=int(np.sum(frame.url != original.url)),
            canonical_text_changed=int(np.sum([canonical_url(a) != canonical_url(b) for a, b in zip(original.url, frame.url)])),
            e2_rows_changed=int(np.any(delta > 1e-12, axis=1).sum()),
            e2_max_abs_delta=float(delta.max()))
    run.write_json(OUT / "stress_input_changes.json", changes)
    stress, resources = [], []
    sample = train.url.iloc[:16].tolist()
    for spec in specs:
        name = spec["id"]
        numeric = spec["kind"] != "text"
        for fold in [0, 1, 2]:
            model = joblib.load(LOCAL / f"{name}_outer{fold}.joblib")
            mask = train.fold_id.eq(fold).to_numpy()
            native_scores = score_model(model, original.loc[mask])
            native_labels = model.predict(original.loc[mask])
            persisted = pd.read_csv(OUT / f"{name}_outer{fold}_oof.csv.gz", float_precision="round_trip")
            np.testing.assert_allclose(native_scores, persisted.score, rtol=0, atol=1e-12)
            np.testing.assert_array_equal(native_labels, persisted.prediction)
            for mode in modes:
                frame = frames[mode].loc[mask]
                score = score_model(model, frame)
                pred = model.predict(frame)
                stress.append(dict(experiment=name, fold=fold, transform=mode,
                    prediction_flips=int(np.sum(pred != native_labels)), n=int(mask.sum()),
                    score_delta_mean_abs=float(np.mean(abs(score - native_scores))),
                    score_delta_max_abs=float(np.max(abs(score - native_scores))),
                    **run.metrics(train.loc[mask, "target"], pred, score)))
            # Sequential, warm desktop CPU, SAME 16 URLs for every model/fold.
            durations = []
            for repeat in range(18):
                start = time.perf_counter()
                score_model(model, raw_frame(sample, reference, numeric=numeric))
                if repeat >= 3:
                    durations.append((time.perf_counter() - start) * 1000)
            stream = BytesIO()
            joblib.dump(model, stream)
            resources.append(dict(experiment=name, fold=fold, batch_size=len(sample),
                p50_ms=float(np.median(durations)), p95_ms=float(np.quantile(durations, .95)),
                model_bytes=stream.tell(), threads=2, warmup=3, repeats=15,
                scope="warm desktop CPU raw URL -> required E2/preprocessing -> score; excludes startup/load"))
        print("Measured stress/resources", name, flush=True)
    run.write_csv(OUT / "stress.csv", pd.DataFrame(stress))
    run.write_csv(OUT / "resources.csv", pd.DataFrame(resources))


def bootstrap(train, oof, names, draws=2000):
    """Weighted AP equals explicit domain-cluster replication, including score ties."""
    rng = np.random.default_rng(42)
    samples = np.zeros((draws, len(names)))
    observed = {name: [] for name in names}
    for fold in [0, 1, 2]:
        held = train.loc[train.fold_id.eq(fold)].reset_index(drop=True)
        groups, unique = pd.factorize(held.registrable_domain)
        prepared = {}
        for name in names:
            pred = oof.loc[oof.experiment.eq(name) & oof.fold_id.eq(fold)].sort_values("id")
            score, y = pred.score.to_numpy(), pred.y_true.to_numpy()
            order = np.argsort(-score, kind="stable")
            ends = np.r_[np.flatnonzero(score[order][:-1] != score[order][1:]), len(score) - 1]
            prepared[name] = (y[order], groups[order], ends)
            observed[name].append(average_precision_score(y, score))
        for draw in range(draws):
            count = np.bincount(rng.integers(0, len(unique), len(unique)), minlength=len(unique))
            for j, name in enumerate(names):
                y, group, ends = prepared[name]
                weights = count[group]
                tp = np.cumsum(weights * y)[ends]
                total = np.cumsum(weights)[ends]
                positive = tp[-1]
                ap = np.sum(np.diff(np.r_[0, tp]) * np.divide(tp, total,
                    out=np.zeros(len(total), float), where=total != 0)) / positive
                samples[draw, j] += ap / 3
    rows = []
    for baseline in ["raw_svm", "canonical_svm", "stack_hist"]:
        for j, name in enumerate(names):
            delta = samples[:, j] - samples[:, names.index(baseline)]
            rows.append(dict(experiment=name, baseline=baseline,
                delta_ap=float(np.mean(observed[name]) - np.mean(observed[baseline])),
                ci_low=float(np.quantile(delta, .025)), ci_high=float(np.quantile(delta, .975)),
                draws=draws, seed=42,
                scope="paired domain clusters within outer folds; conditional on fitted models/folds; no refit or multiplicity correction"))
    run.write_csv(OUT / "paired_bootstrap.csv", pd.DataFrame(rows))




def candidate_notes(train):
    """Twelve real outer errors at the candidate's 1% fitting-OOF policy."""
    folder = OUT / "candidate"
    if not (folder / "metadata.json").exists():
        return
    oof = pd.concat([pd.read_csv(OUT / f"stack_hist_outer{f}_oof.csv.gz", float_precision="round_trip")
                     for f in range(3)], ignore_index=True)
    oof["prediction"] = oof["prediction_0.01"]
    wrong = oof.loc[oof.y_true.ne(oof.prediction)].copy()
    wrong["error"] = np.where(wrong.y_true.eq(0), "FP", "FN")
    cases = wrong.sort_values("id").groupby(["fold_id", "error"]).head(2).merge(
        train[["id", "url", "susp_token_cnt", "brand_domain_mismatch", "digit_cnt", "url_len"]],
        on="id", validate="one_to_one")
    cases["base_svm_margin"], cases["base_hist_score"] = np.nan, np.nan
    for fold in range(3):
        mask = cases.fold_id.eq(fold)
        model = joblib.load(LOCAL / f"stack_hist_outer{fold}.joblib")
        frame = raw_frame(cases.loc[mask, "url"].tolist())
        cases.loc[mask, "base_svm_margin"] = score_model(model.bases["svm"], frame)
        cases.loc[mask, "base_hist_score"] = score_model(model.bases["hist"], frame)
    cases["operating_point"] = "outer-fitting Group OOF FPR target 0.01, actual outer FPR may differ"
    cases["observation"] = cases.apply(lambda r: (
        f"{r.error}; fold={r.fold_id}; meta={r.score:.6f}, threshold={r['threshold_0.01']:.6f}; "
        f"SVM margin={r.base_svm_margin:.6f}, HistGB={r.base_hist_score:.6f}; "
        f"suspicious tokens={r.susp_token_cnt}, brand mismatch={r.brand_domain_mismatch}, digits={r.digit_cnt}"), axis=1)
    def hypothesis(r):
        disagree = (r.base_svm_margin > 0) != (r.base_hist_score > .5)
        if disagree:
            return "The two branches disagree; their combination and the fitting-selected operating point may explain this error. This is a hypothesis, not feature attribution."
        if r.error == "FN":
            return "Both branches favor benign or have weak evidence; a phishing hostname can share benign-looking text/numeric patterns. Source/format bias may remain."
        return "Both branches favor phishing; benign text/brand patterns can overlap phishing. The source label is retained; no live-site judgment is made."
    cases["hypothesis"] = cases.apply(hypothesis, axis=1)
    cases["next_check"] = "Inspect this outer fold's fitting-side n-grams, brand matches and source/format counts offline. Do not retune from the case or change its label."
    cases["url"] = cases.url.str.replace(".", "[.]", regex=False)
    assert len(cases) == 12 and cases.observation.str.len().gt(0).all()
    run.write_csv(folder / "error_cases.csv", cases)
    from phishguard_vn.stacking_candidate import load_candidate
    candidate = load_candidate(ROOT)
    durations = []
    urls = train.url.iloc[:16].tolist()
    for repeat in range(18):
        start = time.perf_counter()
        candidate.predict_batch(urls)
        if repeat >= 3:
            durations.append((time.perf_counter() - start) * 1000)
    import subprocess
    preserved = {}
    for path in ["configs/week6_teacher_lock.json", "models/teacher_tfidf_svm_v1.joblib",
                 "src/phishguard_vn/teacher.py", "scripts/predict_teacher.py"]:
        before = subprocess.check_output(["git", "show", "35c7d8d:" + path], cwd=ROOT)
        preserved[path] = hashlib.sha256(before).hexdigest() == run.sha(ROOT / path)
    assert all(preserved.values())
    run.write_json(folder / "verification.json", dict(
        v1_files_unchanged=preserved, errors=12, error_policy="outer-fitting OOF FPR target 0.01",
        source_sha256=run.sha(Path(__file__)), model_sha256=run.sha(ROOT / "models/teacher_v2_candidate.joblib"),
        p50_batch16_ms=float(np.median(durations)), p95_batch16_ms=float(np.quantile(durations, .95)),
        bytes=(ROOT / "models/teacher_v2_candidate.joblib").stat().st_size,
        scope="candidate warm desktop CPU raw URL -> full offline pipeline -> score/label; batch16 threads2 warmup3 repeats15; excludes load/startup/network/Android/peak RAM"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-only", action="store_true", help="Preserve existing stress/resources/bootstrap; audit CSV and candidate only")
    args = parser.parse_args()
    train = run.load_train()
    specs = json.loads(run.PLAN.read_text(encoding="utf-8"))["experiments"]
    oof, summary = audit(train, specs)
    print(summary.to_string(index=False), flush=True)
    if args.audit_only:
        candidate_notes(train)
        run.write_json(OUT / "audit_provenance.json", dict(
            source_sha256=run.sha(Path(__file__)), generated_utc=run.datetime.now(run.timezone.utc).isoformat(),
            preserved_analysis_provenance_sha256=run.sha(OUT / "analysis_provenance.json"),
            benchmark_refitted=False, original_stress_resources_bootstrap_preserved=True))
        print("Audit-only complete; no benchmark/stress/bootstrap refit or overwrite.", flush=True)
        return
    stress_and_resources(train, specs)
    bootstrap(train, oof, [s["id"] for s in specs])
    run.write_json(OUT / "analysis_provenance.json", dict(
        source_sha256=run.sha(Path(__file__)), benchmark_manifest_sha256=run.sha(OUT / "execution_manifest.json"),
        generated_utc=run.datetime.now(run.timezone.utc).isoformat(), training_stopped_before_measurement=True))
    print("Audit, format stress, resources and paired bootstrap complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
