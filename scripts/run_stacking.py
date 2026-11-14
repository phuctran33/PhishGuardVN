"""Run the registered 11-pipeline/53-config Train-only experiment.

Read main() first: load Train -> each outer fold -> inner selection -> fitting OOF
threshold -> outer predictions. Fixed base fits are shared across meta LR grids.
No Validation/external/Test is read here.
"""
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
import argparse
import hashlib
import json
import subprocess
import sys
import time
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, ParameterGrid
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score, f1_score
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from phishguard_vn.stacking import (make_base, make_meta, FittedStack, score_model,
    choose_threshold, source_hashes, canonical_url)
from phishguard_vn.brand_features import E2_FEATURES, load_reference

OUT = ROOT / "reports/tables/stacking"
LOCAL = ROOT / "data/interim/stacking"
PLAN = ROOT / "configs/teacher_v2_plan.json"
LEDGER, PARTITIONS = [], []
BASE_CACHE = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def id_hash(frame):
    return hashlib.sha256("\n".join(frame.id.astype(str)).encode()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def write_csv(path, frame):
    compression = {"method": "gzip", "mtime": 0} if str(path).endswith(".gz") else None
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", compression=compression)


def load_train():
    # Reuse the already-audited eligibility join, not historical model predictions.
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_url_research import load_train as audited_join
    frame = audited_join()
    assert frame.target.value_counts().to_dict() == {0: 11004, 1: 2074}
    assert frame.registrable_domain.nunique() == 8835
    assert set(frame.fold_id) == {0, 1, 2}
    return frame


def X(frame):
    return frame[["url", *E2_FEATURES]]


def metrics(y, pred, score):
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return dict(ap=float(average_precision_score(y, score)),
        precision=float(precision_score(y, pred, zero_division=0)),
        recall=float(recall_score(y, pred, zero_division=0)), f1=float(f1_score(y, pred, zero_division=0)),
        fpr=float(fp / (fp + tn)), tp=int(tp), fn=int(fn), fp=int(fp), tn=int(tn))


def splits(frame, context, kind):
    frame = frame.reset_index(drop=True)
    result = list(StratifiedGroupKFold(2, shuffle=True, random_state=42).split(
        frame, frame.target, frame.registrable_domain))
    assignments = np.full(len(frame), -1)
    for fold, (a, b) in enumerate(result):
        assert set(frame.iloc[a].registrable_domain).isdisjoint(frame.iloc[b].registrable_domain)
        assert frame.iloc[a].target.nunique() == frame.iloc[b].target.nunique() == 2
        assignments[b] = fold
    rows = frame[["id", "registrable_domain"]].copy()
    rows["context"], rows["kind"], rows["held_fold"] = context, kind, assignments
    PARTITIONS.append(rows)
    write_csv(OUT / "partitions.csv.gz", pd.concat(PARTITIONS, ignore_index=True).drop_duplicates())
    return result


def fit(model, frame, context, stage, name, config=None):
    row = dict(context=context, stage=stage, model=name, parameters=json.dumps(config or {}, sort_keys=True),
        training_rows=len(frame), training_ids_sha256=id_hash(frame))
    start = time.perf_counter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(X(frame), frame.target)
        row.update(status="success", warnings=json.dumps(sorted({str(w.message) for w in caught})))
        return model
    except Exception as exc:
        row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        row["fit_seconds"] = time.perf_counter() - start
        LEDGER.append(row)
        write_csv(OUT / "fit_ledger.csv", pd.DataFrame(LEDGER))


def base_data(frame, context):
    """Fit each FIXED base once per partition. Share only within identical fitting IDs."""
    key = id_hash(frame)
    if key in BASE_CACHE:
        return BASE_CACHE[key]
    path = LOCAL / "base_cache" / (key + ".joblib")
    if path.exists():
        value = joblib.load(path)
        assert value["ids"] == frame.id.tolist()
        BASE_CACHE[key] = value
        return value
    members = ["svm", "hist", "extra", "lgbm", "hybrid_lr"]
    oof = np.full((len(frame), len(members)), np.nan)
    for fold, (a, b) in enumerate(splits(frame, context + "/meta", "meta")):
        for col, name in enumerate(members):
            model = fit(make_base(name), frame.iloc[a], context + f"/meta/{fold}",
                        "base_crossfit", name)
            oof[b, col] = score_model(model, X(frame.iloc[b]))
    assert np.isfinite(oof).all()
    bases = {name: fit(make_base(name), frame, context, "base_refit", name) for name in members}
    value = dict(ids=frame.id.tolist(), names=members, oof=oof, bases=bases)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(value, path)
    BASE_CACHE[key] = value
    return value


def fit_spec(spec, params, frame, context):
    if spec["kind"] != "stack":
        kind = {"text": "svm", "hist": "hist", "hybrid": "hybrid_svm"}[spec["kind"]]
        return fit(make_base(kind, params, spec), frame, context, "estimator", spec["id"], params)
    value = base_data(frame, context)
    columns = [value["names"].index(name) for name in spec["members"]]
    meta = make_meta(params["C"], params["scale"])
    # Meta fit intentionally gets only base OOF scores, never URL/group/source metadata.
    start = time.perf_counter()
    row = dict(context=context, stage="meta_lr", model=spec["id"],
               parameters=json.dumps(params, sort_keys=True), training_rows=len(frame),
               training_ids_sha256=id_hash(frame))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            meta.fit(value["oof"][:, columns], frame.target)
        row["status"] = "success"
    except Exception as exc:
        row.update(status="failed", error=str(exc))
        raise
    finally:
        row["fit_seconds"] = time.perf_counter() - start
        LEDGER.append(row)
        write_csv(OUT / "fit_ledger.csv", pd.DataFrame(LEDGER))
    return FittedStack(spec["members"], value["bases"], meta)


def select(spec, frame, context):
    trials = []
    partitions = splits(frame, context + "/inner", "inner")
    for config_id, params in enumerate(ParameterGrid(spec["grid"])):
        values = []
        for inner, (a, b) in enumerate(partitions):
            model = fit_spec(spec, params, frame.iloc[a], context + f"/inner/{inner}")
            ap = float(average_precision_score(frame.iloc[b].target, score_model(model, X(frame.iloc[b]))))
            values.append(ap)
            trials.append(dict(experiment=spec["id"], context=context, config_id=config_id,
                inner_fold=inner, parameters=json.dumps(params, sort_keys=True), ap=ap))
        print(spec["id"], context, params, "inner_AP", float(np.mean(values)), flush=True)
    trial_frame = pd.DataFrame(trials)
    path = OUT / (spec["id"] + "_" + context.replace("/", "_") + "_trials.csv")
    write_csv(path, trial_frame)
    means = trial_frame.groupby("config_id").ap.mean()
    best = int(means.idxmax())
    params = list(ParameterGrid(spec["grid"]))[best]
    return params, float(means.loc[best])


def fitting_oof(spec, params, frame, context):
    score = np.full(len(frame), np.nan)
    for fold, (a, b) in enumerate(splits(frame, context + "/threshold", "threshold")):
        model = fit_spec(spec, params, frame.iloc[a], context + f"/threshold/{fold}")
        score[b] = score_model(model, X(frame.iloc[b]))
    assert np.isfinite(score).all()
    return score


def run_outer(spec, train, fold):
    fitting = train.loc[train.fold_id.ne(fold)].reset_index(drop=True)
    held = train.loc[train.fold_id.eq(fold)].reset_index(drop=True)
    assert set(fitting.registrable_domain).isdisjoint(held.registrable_domain)
    context = f"outer{fold}"
    params, inner_ap = select(spec, fitting, context)
    # Fitting-side OOF labels may be used for threshold; outer labels never are.
    fs = fitting_oof(spec, params, fitting, context)
    thresholds = {str(p): choose_threshold(fitting.target, fs, p) for p in [.01, .02]}
    fp = fitting[["id", "target"]].rename(columns={"target": "y_true"}).copy()
    fp["score"] = fs
    write_csv(OUT / f'{spec["id"]}_outer{fold}_threshold_oof.csv.gz', fp)
    model = fit_spec(spec, params, fitting, context + "/refit")
    scores = score_model(model, X(held))
    prediction = model.predict(X(held))  # native estimator tie convention
    rows = held[["id", "fold_id", "target"]].rename(columns={"target": "y_true"})
    rows["experiment"], rows["score"], rows["prediction"] = spec["id"], scores, prediction
    for p, threshold in thresholds.items():
        rows["threshold_" + p] = threshold
        rows["prediction_" + p] = (scores >= threshold).astype(int)
    result = dict(experiment=spec["id"], fold=fold, params=params, inner_ap=inner_ap,
                  thresholds=thresholds, fitting_ids_sha256=id_hash(fitting),
                  held_ids_sha256=id_hash(held), native=metrics(held.target, prediction, scores),
                  threshold_metrics={p: metrics(held.target, scores >= t, scores) for p, t in thresholds.items()})
    joblib.dump(model, LOCAL / f'{spec["id"]}_outer{fold}.joblib')
    write_csv(OUT / f'{spec["id"]}_outer{fold}_oof.csv.gz', rows)
    write_json(OUT / f'{spec["id"]}_outer{fold}.json', result)
    print("OUTER", spec["id"], fold, result["native"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--experiments", nargs="*", help="Debug/subset only; final report requires all 11")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    train = load_train()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert sum(len(ParameterGrid(s["grid"])) for s in plan["experiments"]) == 53
    sources = ["configs/teacher_v2_plan.json", "scripts/run_stacking.py",
        "scripts/run_url_research.py", "src/phishguard_vn/research_preprocessing.py",
        "data/interim/core_gold_silver.csv", "data/interim/05_matrix_X_brand_trainval.csv",
        "data/interim/02_group_folds_train.csv", "data/interim/03_registrable_domains.csv"]
    fingerprint = {p: sha(ROOT / p) for p in sources}
    fingerprint.update({"runtime/" + k: v for k, v in source_hashes().items()})
    manifest = OUT / "execution_manifest.json"
    if manifest.exists():
        if not args.resume:
            raise ValueError("Existing run: use --resume (only identical source/data allowed)")
        assert json.loads(manifest.read_text(encoding="utf-8"))["input_sha256"] == fingerprint, "Changed code/data; do not mix runs"
        if (OUT / "fit_ledger.csv").exists():
            LEDGER.extend(pd.read_csv(OUT / "fit_ledger.csv", keep_default_na=False).to_dict("records"))
        if (OUT / "partitions.csv.gz").exists():
            PARTITIONS.append(pd.read_csv(OUT / "partitions.csv.gz"))
    else:
        assert not list(LOCAL.glob("base_cache/*.joblib")), "Unregistered cache must not be reused"
        write_json(manifest, dict(created_utc=datetime.now(timezone.utc).isoformat(),
            git_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            git_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            plan_registration_commit="64d97e1", input_sha256=fingerprint,
            versions={p: version(p) for p in ["scikit-learn", "numpy", "scipy", "pandas", "lightgbm", "joblib", "tldextract", "idna"]},
            train_rows=len(train), classes=train.target.value_counts().to_dict(), domains=train.registrable_domain.nunique(),
            train_ids_sha256=id_hash(train), reference_sha256=load_reference().sha256,
            reused_historical_model_predictions=False, official_test_evaluated=False))
        write_csv(OUT / "train_ids.csv.gz", train[["id", "target", "fold_id", "registrable_domain"]])
        write_json(OUT / "format_diagnostic.json", {
            str(label): {"n": int(len(g)), "explicit_scheme": int(g.url.str.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://").sum())}
            for label, g in train.groupby("target")})
        # Check eligibility and normalization without changing raw files.
        assert all(isinstance(canonical_url(u), str) for u in train.url)
    for spec in plan["experiments"]:
        if args.experiments and spec["id"] not in args.experiments:
            continue
        for fold in [0, 1, 2]:
            if args.resume and (OUT / f'{spec["id"]}_outer{fold}.json').exists():
                continue
            run_outer(spec, train, fold)
        # Avoid accumulating all 400-tree forest caches in RAM across families.
        BASE_CACHE.clear()
    print("Registered outer benchmark complete for requested families.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
