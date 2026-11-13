"""Fit the selected two-branch research candidate; freeze BEFORE supplemental evaluation.

No promotion: v1 bundle/lock/CLI remain untouched.
"""
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_stacking as run
from phishguard_vn.stacking import (raw_frame, score_model, choose_threshold, make_base, make_meta, FittedStack,
    source_hashes, reference_fingerprint, PREPROCESSING_VERSION)
from phishguard_vn.stacking_candidate import load_candidate, MODEL_VERSION
from phishguard_vn.brand_features import E2_FEATURES, load_reference
from phishguard_vn.external_provenance import validate_audit_manifest
from phishguard_vn.external_pilot import evaluate_verified

OUT = run.OUT
CANDIDATE_OUT = OUT / "candidate"


BASES = {}


def candidate_base(name):
    model = make_base(name)
    if name == "hist":
        model.set_params(model__early_stopping=False)
    return model


def fit_candidate(frame, params, context):
    # Only the TWO chosen bases. Every new HistGB fit uses an explicit 300-round budget.
    key = run.id_hash(frame)
    if key not in BASES:
        oof = np.full((len(frame), 2), np.nan)
        for fold, (a, b) in enumerate(run.splits(frame, context + "/meta", "meta")):
            for column, name in enumerate(["svm", "hist"]):
                model = run.fit(candidate_base(name), frame.iloc[a], context + f"/meta/{fold}",
                    "candidate_base_crossfit", name, {"early_stopping": False} if name == "hist" else {})
                oof[b, column] = score_model(model, run.X(frame.iloc[b]))
        bases = {name: run.fit(candidate_base(name), frame, context, "candidate_base_refit", name,
            {"early_stopping": False} if name == "hist" else {}) for name in ["svm", "hist"]}
        assert np.isfinite(oof).all()
        BASES[key] = (oof, bases)
    oof, bases = BASES[key]
    meta = make_meta(params["C"], params["scale"])
    start = time.perf_counter()
    from sklearn.exceptions import ConvergenceWarning
    import warnings
    row = dict(context=context, stage="candidate_meta_lr", model="stack_hist",
        parameters=json.dumps(params, sort_keys=True), training_rows=len(frame), training_ids_sha256=key)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            meta.fit(oof, frame.target)
        row["status"] = "success"
    except Exception as exc:
        row.update(status="failed", error=str(exc))
        raise
    finally:
        row["fit_seconds"] = time.perf_counter() - start
        run.LEDGER.append(row)
        run.write_csv(OUT / "fit_ledger.csv", pd.DataFrame(run.LEDGER))
    return FittedStack(["svm", "hist"], bases, meta)


def select_candidate(spec, train):
    rows = []
    folds = run.splits(train, "full_train/inner", "inner")
    for index, params in enumerate(run.ParameterGrid(spec["grid"])):
        for inner, (a, b) in enumerate(folds):
            model = fit_candidate(train.iloc[a], params, f"full_train/inner/{inner}")
            ap = float(run.average_precision_score(train.iloc[b].target, score_model(model, run.X(train.iloc[b]))))
            rows.append(dict(config_id=index, inner_fold=inner, parameters=json.dumps(params, sort_keys=True), ap=ap))
        print("Candidate full-Train inner CV", params, flush=True)
    table = pd.DataFrame(rows)
    run.write_csv(CANDIDATE_OUT / "full_train_trials.csv", table)
    means = table.groupby("config_id").ap.mean()
    best = int(means.idxmax())
    return list(run.ParameterGrid(spec["grid"]))[best], float(means.loc[best])


def main():
    assert json.loads((OUT / "audit.json").read_text())["status"] == "PASS"
    assert (OUT / "paired_bootstrap.csv").exists() and (OUT / "stress.csv").exists()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-frozen", action="store_true", help="Verify an existing frozen bundle, never refit or overwrite it")
    args = parser.parse_args()
    train = run.load_train()
    plan = json.loads(run.PLAN.read_text(encoding="utf-8"))
    spec = next(s for s in plan["experiments"] if s["id"] == "stack_hist")
    CANDIDATE_OUT.mkdir(exist_ok=True)
    run.LEDGER.extend(pd.read_csv(OUT / "fit_ledger.csv", keep_default_na=False).to_dict("records"))
    run.PARTITIONS.append(pd.read_csv(OUT / "partitions.csv.gz"))
    training_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    path = ROOT / "models/teacher_v2_candidate.joblib"
    lock_path = ROOT / "configs/teacher_v2_candidate_lock.json"
    if lock_path.exists():
        assert args.resume_frozen, "Frozen candidate exists: use --resume-frozen, never overwrite"
        candidate = load_candidate(ROOT)
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        model, reference = candidate.model, candidate.reference
        # Resume preserves the fit provenance; it must not relabel old weights as new fits.
        training_revision = candidate.bundle.get("training_code_revision")
        old_metadata = CANDIDATE_OUT / "metadata.json"
        if not training_revision and old_metadata.exists():
            training_revision = json.loads(old_metadata.read_text(encoding="utf-8"))["training_code_revision"]
        if not training_revision:
            raise ValueError("Frozen legacy bundle has no fit revision; recover its original evidence before resuming")
        threshold = candidate.threshold
        table = pd.read_csv(CANDIDATE_OUT / "full_train_trials.csv")
        means = table.groupby("config_id").ap.mean()
        best = int(means.idxmax())
        params = json.loads(table.loc[table.config_id.eq(best), "parameters"].iloc[0])
        inner_ap = float(means.loc[best])
        assert model.meta.named_steps["lr"].C == params["C"]
        assert (model.meta.named_steps["scale"] != "passthrough") == params["scale"]
        saved = pd.read_csv(CANDIDATE_OUT / "train_threshold_oof.csv.gz", float_precision="round_trip")
        assert saved.id.tolist() == train.id.tolist() and saved.y_true.tolist() == train.target.tolist()
        fs = saved.score.to_numpy()
        assert choose_threshold(train.target, fs, .01) == threshold
        print("Resume frozen candidate: NO refitting and NO bundle/lock overwrite.", flush=True)
    else:
        assert not args.resume_frozen, "No frozen candidate to resume"
        params, inner_ap = select_candidate(spec, train)
        fs = np.full(len(train), np.nan)
        for fold, (a, b) in enumerate(run.splits(train, "full_train/threshold", "threshold")):
            fitted = fit_candidate(train.iloc[a], params, f"full_train/threshold/{fold}")
            fs[b] = score_model(fitted, run.X(train.iloc[b]))
        assert np.isfinite(fs).all()
        threshold = choose_threshold(train.target, fs, .01)
        model = fit_candidate(train, params, "full_train/refit")
        assert model.bases["hist"].named_steps["model"].early_stopping is False
        assert model.bases["hist"].named_steps["model"].n_iter_ == 300
        run.write_csv(CANDIDATE_OUT / "train_threshold_oof.csv.gz", pd.DataFrame({
            "id": train.id, "y_true": train.target, "score": fs, "prediction": fs >= threshold}))
        reference = load_reference()
        runtime = {p: version(p) for p in ["scikit-learn", "numpy", "scipy", "pandas", "joblib", "tldextract", "idna"]}
        bundle = dict(model=model, reference=reference, model_version=MODEL_VERSION,
            training_code_revision=training_revision,
            candidate_only=True, promoted=False, preprocessing_version=PREPROCESSING_VERSION,
            selected_by="core_train_group_cv", primary_metric="mean_outer_average_precision",
            validation_used_for_selection=False, external_used_for_selection=False, official_test_evaluated=False,
            decision_rule="score >= threshold", operating_point_scope="full_train_group_oof_fpr_target_0.01",
            score_kind="probability", calibrated=False, feature_names=list(E2_FEATURES),
            class_mapping={"benign": 0, "phishing": 1}, threshold=threshold,
            source_sha256=source_hashes(), reference_sha256=reference.sha256,
            reference_fingerprint=reference_fingerprint(reference), runtime_versions=runtime)
        path = ROOT / "models/teacher_v2_candidate.joblib"
        joblib.dump(bundle, path)
        lock = {k: v for k, v in bundle.items() if k not in {"model", "reference"}}
        lock["bundle"] = dict(path=path.relative_to(ROOT).as_posix(), sha256=run.sha(path))
        run.write_json(ROOT / "configs/teacher_v2_candidate_lock.json", lock)
    candidate = load_candidate(ROOT)
    # Parity across all eligible Train URLs. Extraction included, no training on examples.
    expected = score_model(model, run.X(train))
    actual = candidate.predict_batch(train.url.tolist())
    scores = np.array([r["score"] for r in actual])
    np.testing.assert_allclose(expected, scores, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(expected >= threshold, [r["class_id"] for r in actual])
    from predict_stacking_candidate import EXAMPLES
    urls = EXAMPLES
    results = candidate.predict_batch(urls)
    singles = [candidate.predict_one(u) for u in urls]
    np.testing.assert_allclose([r["score"] for r in results], [r["score"] for r in singles], rtol=0, atol=1e-12)
    assert [{k:v for k,v in r.items() if k != "score"} for r in results] == [{k:v for k,v in r.items() if k != "score"} for r in singles]
    single_batch_error = max(abs(a["score"] - b["score"]) for a,b in zip(results, singles))
    # A real portable process gets only runtime sources, bundle and lock, no reports/data.
    with tempfile.TemporaryDirectory(prefix="phishguard-stacking-portable-") as directory:
        portable = Path(directory)
        (portable / "models").mkdir()
        (portable / "configs").mkdir()
        (portable / "scripts").mkdir()
        (portable / "src/phishguard_vn").mkdir(parents=True)
        for name in ["__init__.py", "stacking.py", "stacking_candidate.py",
                     "url_parser.py", "features.py", "brand_features.py"]:
            shutil.copyfile(ROOT / "src/phishguard_vn" / name, portable / "src/phishguard_vn" / name)
        shutil.copyfile(path, portable / "models" / path.name)
        shutil.copyfile(ROOT / "configs/teacher_v2_candidate_lock.json", portable / "configs/teacher_v2_candidate_lock.json")
        shutil.copyfile(ROOT / "scripts/predict_stacking_candidate.py", portable / "scripts/predict_stacking_candidate.py")
        result = subprocess.run([sys.executable, "-X", "utf8", "scripts/predict_stacking_candidate.py", "--examples"],
            cwd=portable, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr
        portable_results = json.loads(result.stdout)
        np.testing.assert_allclose([r["score"] for r in portable_results], [r["score"] for r in results], rtol=0, atol=1e-12)
        assert [r["class_id"] for r in portable_results] == [r["class_id"] for r in results]
    meta = dict(candidate="stack_hist", params=params, resumed_frozen_bundle=args.resume_frozen,
        training_code_revision=training_revision, full_train_inner_mean_ap=inner_ap,
        hist_parameters=model.bases["hist"].named_steps["model"].get_params(),
        hist_fitted_iterations=int(model.bases["hist"].named_steps["model"].n_iter_),
        hist_effective_early_stopping=bool(model.bases["hist"].named_steps["model"].do_early_stopping_),
        threshold=threshold, threshold_target_fpr=.01,
        threshold_oof_metrics_descriptive=run.metrics(train.target, fs >= threshold, fs),
        threshold_scope="hyperparameters and threshold selected using Train labels; not independent performance",
        training_ids_sha256=run.id_hash(train), training_rows=len(train),
        model_sha256=run.sha(path), bytes=path.stat().st_size, promoted=False,
        runtime_git_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        runtime_git_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        packaged_utc=datetime.now(timezone.utc).isoformat(), bundle_lock=lock,
        adapter_sha256=run.sha(ROOT / "src/phishguard_vn/stacking_candidate.py"),
        package_script_sha256=run.sha(Path(__file__)),
        parity=dict(inputs=len(train), score_max_abs_error=float(np.max(abs(expected - scores))),
            labels_equal=True, single_batch_labels_equal=True,
            single_batch_score_max_abs_error=single_batch_error, score_absolute_tolerance=1e-12,
            portable_cli_examples=len(urls)),
        decision_reason="Competitive Train Group CV, two complementary branches, modest size; format robustness is diagnostic, no independent final-test or promotion claim.")
    run.write_json(CANDIDATE_OUT / "metadata.json", meta)
    # Error notes use the candidate's outer OOF, not the full-Train model coefficients.
    oof = pd.concat([pd.read_csv(OUT / f"stack_hist_outer{f}_oof.csv.gz", float_precision="round_trip")
                     for f in [0, 1, 2]], ignore_index=True)
    wrong = oof.loc[oof.y_true.ne(oof.prediction)].copy()
    wrong["error"] = np.where(wrong.y_true.eq(0), "FP", "FN")
    cases = wrong.sort_values("id").groupby(["fold_id", "error"]).head(2).merge(
        train[["id", "url"]], on="id", validate="one_to_one")
    cases["url"] = cases.url.str.replace(".", "[.]", regex=False)
    cases["observation"] = cases.apply(lambda r: f"{r.error}; fold {r.fold_id}; native meta-LR score {r.score:.6f}; label {r.y_true}", axis=1)
    cases["hypothesis"] = np.where(cases.error.eq("FP"),
        "Benign hostname may share character/brand cues with phishing; source label is retained.",
        "Phishing hostname may lack discriminative character/brand cues; format/source shift remains possible.")
    cases["next_check"] = "Inspect this outer model's two base scores and fitting-side source/format counts offline; do not change labels or tune to this case."
    assert len(cases) == 12 and set(cases.fold_id) == {0, 1, 2}
    run.write_csv(CANDIDATE_OUT / "error_cases.csv", cases)

    # ONLY NOW read previously observed Validation and audited external cohort.
    core = pd.read_csv(ROOT / "data/interim/core_gold_silver.csv", encoding="utf-8")
    eligible = pd.read_csv(ROOT / "data/interim/05_matrix_X_brand_trainval.csv", usecols=["id"])
    val = core.loc[core.split.eq("val") & core.id.isin(eligible.id)].sort_values("id")
    assert len(val) == 1585
    r = candidate.predict_batch(val.url.tolist())
    vp = pd.DataFrame(dict(id=val.id.to_numpy(), y_true=val.label.map({"benign": 0, "phishing": 1}).to_numpy(),
        score=[x["score"] for x in r], prediction=[x["class_id"] for x in r]))
    run.write_csv(CANDIDATE_OUT / "validation_predictions.csv", vp)
    saved = pd.read_csv(CANDIDATE_OUT / "validation_predictions.csv", float_precision="round_trip")
    manifest = json.loads((ROOT / "reports/tables/external_pilot/manifest.json").read_text(encoding="utf-8"))
    validate_audit_manifest(ROOT, manifest)
    ledger = pd.read_csv(ROOT / "data/external/derived/k53_candidates.csv", keep_default_na=False, encoding="utf-8")
    both, ep = evaluate_verified(ledger, candidate.predict_one, representation="host_only", two_class=True)
    recall, _ = evaluate_verified(ledger, candidate.predict_one, representation="host_only")
    assert len(ep) == 99 and ep.label.value_counts().to_dict() == {"phishing": 92, "benign": 7}
    run.write_csv(CANDIDATE_OUT / "external_predictions.csv", ep)
    es = pd.read_csv(CANDIDATE_OUT / "external_predictions.csv", float_precision="round_trip")
    evaluation = dict(bundle_sha256=run.sha(path), lock_sha256=run.sha(ROOT / "configs/teacher_v2_candidate_lock.json"),
        frozen_before_supplemental=True, validation_previously_observed=True,
        validation=run.metrics(saved.y_true, saved.prediction, saved.score),
        external=run.metrics(es.label.eq("phishing").astype(int), es.prediction.eq("phishing").astype(int), es.score),
        external_audit=both, external_recall=recall, pending_not_ground_truth=int(ledger.review_status.eq("pending").sum()),
        external_scope="99 historical-hostname records including 92 positives; overlapping cohorts, not independent tests",
        source_sha256=dict(audit_manifest=run.sha(ROOT / "reports/tables/external_pilot/manifest.json"),
            ledger=run.sha(ROOT / "data/external/derived/k53_candidates.csv")),
        official_test_evaluated=False, no_retuning=True)
    run.write_json(CANDIDATE_OUT / "evaluation.json", evaluation)
    print(json.dumps(dict(params=params, threshold=threshold, sha256=run.sha(path),
        parity=meta["parity"], validation=evaluation["validation"], external=evaluation["external"]), indent=2))


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
