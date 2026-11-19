"""Construct the unchanged Train folds and fold-only Teacher targets for bronze KD."""
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.stacking import FittedStack, make_base, make_meta, raw_frame, score_model
from phishguard_vn.stacking_candidate import require_python_runtime
from phishguard_vn.student import sha256, student_text
from phishguard_vn.url_parser import parse_url
from train_lightgbm_student import CACHE, verify_cv_targets, write_json

DATA = ROOT / "data/splits/url_train.csv"
FOLD_IDS = ROOT / "reports/tables/stacking/train_ids.csv.gz"
TEACHER_LOCK = ROOT / "configs/teacher_v2_candidate_lock.json"
DATA_CACHE = ROOT / "data/interim/kd_bronze_research"
BRONZE_SALT = "kd-bronze-v1-fixed-pool"


def core_train():
    columns = ["id", "url", "label", "tier", "split"]
    data = pd.read_csv(DATA, usecols=columns, dtype=str)
    core = data.loc[data.tier.isin(["gold", "silver"])]
    if not core["split"].eq("train").all() or not core.id.is_unique:
        raise ValueError("Invalid Train core IDs")
    parsed = core.url.map(parse_url)
    core = core.loc[parsed.map(lambda p: p.is_valid and bool(p.registrable_domain))].copy()
    core["group"] = parsed.loc[core.index].map(lambda p: p.registrable_domain)
    core["target"] = core.label.map({"benign": 0, "phishing": 1})
    core["text"] = core.url.map(student_text)
    mapping = pd.read_csv(FOLD_IDS)
    train = core.merge(mapping, on="id", validate="one_to_one", suffixes=("", "_archive"))
    if (len(train) != len(core) or len(train) != len(mapping) or len(train) != 13078
            or train.target.value_counts().to_dict() != {0: 11004, 1: 2074}
            or not train.target.eq(train.target_archive).all()
            or not train.group.eq(train.registrable_domain).all()
            or not train.groupby("group").fold_id.nunique().eq(1).all()
            or set(train.fold_id) != {0, 1, 2}):
        raise ValueError("Train differs from archived fold map")
    return train.sort_values("id").reset_index(drop=True)


def bronze_pool(train):
    # Explicitly omit the bronze label column at read time.
    data = pd.read_csv(DATA, usecols=["id", "url", "tier", "split", "channel"], dtype=str)
    bronze = data.loc[data.tier.eq("bronze") & data["split"].eq("train")
                      & data.channel.eq("url"), ["id", "url"]].copy()
    bronze_rows = len(bronze)
    bronze["group"] = bronze.url.map(
        lambda raw: parse_url(raw).registrable_domain if isinstance(raw, str) else None)
    bronze = bronze.dropna(subset=["group"])
    valid_rows = len(bronze)
    bronze["text"] = bronze.url.map(student_text)
    # Drop matches against the entire canonical Train core and within bronze itself.
    bronze = bronze[~bronze.text.isin(train.text) & ~bronze.id.isin(train.id)]
    distinct = bronze.sort_values("id").drop_duplicates("text").copy()
    distinct["order"] = distinct.id.map(
        lambda key: hashlib.sha256((BRONZE_SALT + key).encode()).hexdigest())
    return distinct.sort_values("order").reset_index(drop=True), dict(
        bronze_train_raw=bronze_rows, valid_domain=valid_rows, distinct_after_core_dedup=len(distinct))


def refit_teacher(fitting, params):
    """Fixed archived recipe for a machine missing a historical fold bundle."""
    in_order = fitting.sort_values("id").reset_index(drop=True)
    def make(name):
        model = make_base(name)
        if name == "hist":
            model.set_params(model__early_stopping=False)
        return model
    X = in_order[["url", *E2_FEATURES]]
    split = StratifiedGroupKFold(n_splits=2, shuffle=True, random_state=42)
    members = ["svm", "hist"]
    base_oof = np.empty((len(in_order), len(members)))
    for fit, held in split.split(X, in_order.target, in_order.group):
        for i, key in enumerate(members):
            model = make(key).fit(X.iloc[fit], in_order.target.iloc[fit])
            base_oof[held, i] = score_model(model, X.iloc[held])
    bases = {key:make(key).fit(X, in_order.target) for key in members}
    meta = make_meta(params["C"], params["scale"]).fit(base_oof, in_order.target)
    return FittedStack(members, bases, meta)


def prepare():
    record = json.loads(TEACHER_LOCK.read_text(encoding="utf8"))
    require_python_runtime(record["python_runtime"])
    for lib, expected in record["runtime_versions"].items():
        if version(lib) != expected:
            raise RuntimeError(f"Frozen Teacher requires {lib} {expected}")
    train = core_train()
    ledger = verify_cv_targets(train)
    if ledger is None:
        raise ValueError("The archived fold lineage and held-score references are required")
    bronze, counts = bronze_pool(train)
    core_matrix = raw_frame(train.url.tolist())
    bronze_matrix = raw_frame(bronze.url.tolist())
    DATA_CACHE.mkdir(parents=True, exist_ok=True)
    manifest = dict(inputs={str(p.relative_to(ROOT)).replace(chr(92),"/"):sha256(p) for p in
         (DATA, FOLD_IDS, TEACHER_LOCK, CACHE / "manifest.json", Path(__file__))}, **counts, folds={})
    for fold in (0, 1, 2):
        fitting = train[train.fold_id != fold].copy()
        held = train[train.fold_id == fold].copy()
        extra = bronze[~bronze.group.isin(held.group)].copy()
        if set(fitting.group) & set(held.group) or set(extra.group) & set(held.group):
            raise ValueError("Held-domain leakage")
        note = ledger["folds"][str(fold)]
        archive = ROOT / note["teacher_path"]
        params = note["parameters"]
        if archive.is_file():
            if sha256(archive) != note["teacher_model_sha256"]:
                raise ValueError("Historical fold model checksum changed: " + str(archive))
            teacher = joblib.load(archive)
            origin = "archived"
        else:
            teacher = refit_teacher(fitting.join(core_matrix[list(E2_FEATURES)]), params)
            origin = "refit_fixed_recipe"
        ref = pd.read_csv(CACHE / f"outer{fold}_held_reference.csv.gz").set_index("id")
        aligned = ref.loc[held.id]
        np.testing.assert_array_equal(held.target, aligned.target)
        held_score = score_model(teacher, core_matrix.loc[held.index])
        max_difference = float(np.max(np.abs(aligned.teacher_score - held_score)))
        if origin == "archived":
            np.testing.assert_allclose(held_score, aligned.teacher_score, atol=1e-12, rtol=0)
            fitting_targets = pd.read_csv(CACHE / f"outer{fold}_fitting_targets.csv.gz").set_index("id")
            wanted = fitting_targets.loc[fitting.id]
            np.testing.assert_array_equal(wanted.target, fitting.target)
            np.testing.assert_allclose(score_model(teacher, core_matrix.loc[fitting.index]),
                                       wanted.teacher_score, atol=1e-12, rtol=0)
            core_scores = wanted.teacher_score.to_numpy()
        else:
            core_scores = score_model(teacher, core_matrix.loc[fitting.index])
        extra_scores = score_model(teacher, bronze_matrix.loc[extra.index])
        for scores in (core_scores, extra_scores):
            if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
                raise ValueError("Invalid Teacher scores")
        rows = dict(
            fitting=fitting[["id","url","text","target"]].reset_index(drop=True),
            held=held[["id","url","text","target"]].reset_index(drop=True),
            extra=extra[["id","url","text"]].reset_index(drop=True),
            e2_fit=core_matrix.loc[fitting.index, list(E2_FEATURES)].to_numpy(float),
            e2_held=core_matrix.loc[held.index, list(E2_FEATURES)].to_numpy(float),
            e2_extra=bronze_matrix.loc[extra.index, list(E2_FEATURES)].to_numpy(float),
            core_scores=core_scores,
            extra_scores=extra_scores,
        )
        path = DATA_CACHE / f"fold{fold}.joblib"
        temp = path.with_suffix(".tmp")
        joblib.dump(rows, temp, compress=0)
        temp.replace(path)
        manifest["folds"][str(fold)] = dict(
            teacher=origin, teacher_archived_sha256=note["teacher_model_sha256"],
            historical_max_abs_score_difference=max_difference, teacher_params=params,
            core_fitting=len(fitting), held=len(held), bronze_eligible=len(extra),
            bronze_held_domain_removed=len(bronze)-len(extra),
            bronze_mean_score=float(extra_scores.mean()), bronze_predicted_positive=int((extra_scores>=.5).sum()),
            cache_sha256=sha256(path))
        print(f"Fold {fold} ready. Bronze {len(extra):,}; Teacher {origin}; max held diff {max_difference:.2g}",
              flush=True)
    write_json(DATA_CACHE / "preparation.json", manifest)


def verify_preparation():
    manifest = json.loads((DATA_CACHE / "preparation.json").read_text(encoding="utf8"))
    for name, expected in manifest["inputs"].items():
        if sha256(ROOT / name) != expected:
            raise ValueError("Preparation input changed: " + name)
    for fold, record in manifest["folds"].items():
        if sha256(DATA_CACHE / f"fold{fold}.joblib") != record["cache_sha256"]:
            raise ValueError("Preparation cache changed: " + fold)
    return manifest


if __name__ == "__main__":
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1):
        prepare()
