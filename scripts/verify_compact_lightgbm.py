"""Measure one smaller LightGBM candidate with the original hybrid inputs.

Train 100 trees with seven leaves, using the original objective, features,
verified fold-specific Teacher targets and FPR budget. The output is a
research comparison with the existing 400-tree Student.
"""

import json
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.sparse import csr_matrix, hstack
from threadpoolctl import threadpool_limits

from phishguard_vn.student import choose_threshold, metrics, sha256
from phishguard_vn.student_comparison import e2_matrix
from phishguard_vn.student_lightgbm import (
    HybridLightGBMStudent,
    export_booster,
    export_features,
)
from tiny_mlp_analysis import paired_domain_bootstrap
from train_lightgbm_student import (
    ART as ORIGINAL_ART,
    CACHE,
    PLAN,
    load_inputs,
    vectorizer,
    verify_cv_targets,
    write_csv,
    write_json,
)

OUT = ROOT / "reports/tables/student_tiny_mlp/compact_lightgbm"
ART = ROOT / "artifacts/student_tiny_mlp/compact_lightgbm"
SEED = 42
MODES = ("hard_only", "kd_mixed")


def aligned_teacher_scores(rows, target_path):
    targets = pd.read_csv(target_path, float_precision="round_trip")
    if len(targets) != len(rows):
        raise ValueError(f"Wrong target count in {target_path}")
    aligned = rows[["id", "target"]].merge(
        targets[["id", "target", "teacher_score"]],
        how="left",
        on="id",
        validate="one_to_one",
        suffixes=("", "_cached"),
    )
    scores = aligned["teacher_score"].to_numpy()
    if (
        not aligned["target"].eq(aligned["target_cached"]).all()
        or not np.isfinite(scores).all()
        or ((scores < 0) | (scores > 1)).any()
    ):
        raise ValueError(f"Misaligned or invalid targets in {target_path}")
    return scores


def released_target_path():
    manifest = json.loads(
        (ROOT / "artifacts/student_week7/manifest.json").read_text(encoding="utf-8")
    )
    paths = (
        "data/splits/url_train.csv",
        "data/splits/url_val.csv",
        "configs/teacher_lock.json",
        "models/teacher_v2_candidate.joblib",
    )
    for path in paths:
        if sha256(ROOT / path) != manifest["input_sha256"][path]:
            raise ValueError(f"Released targets no longer match {path}")
    target_file = ROOT / manifest["teacher_targets"]["path"]
    if sha256(target_file) != manifest["teacher_targets"]["sha256"]:
        raise ValueError("Released target file hash changed.")
    return target_file


def hybrid_inputs(tfidf, text, e2):
    return hstack([tfidf.transform(text), csr_matrix(e2)], format="csr")


def fit_student(x, labels, teacher_scores, mode, alpha, parameters):
    targets = labels if mode == "hard_only" else (
        (1 - alpha) * labels + alpha * teacher_scores
    )
    model = LGBMRegressor(**parameters, random_state=SEED)
    model.fit(x, targets)
    if model.booster_.num_trees() != parameters["n_estimators"]:
        raise RuntimeError("Compact LightGBM did not meet the fixed tree budget.")
    return model


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    parameters = {**plan["lightgbm"], "n_estimators": 100, "num_leaves": 7}
    train, validation, _ = load_inputs()
    if verify_cv_targets(train) is None:
        raise ValueError("Verified frozen CV targets are required for the comparison.")
    release_targets = released_target_path()
    train_e2 = e2_matrix(train["url"])
    alpha = plan["alpha"]

    cv_rows, oof_rows = [], []
    for fold in plan["outer_folds"]:
        fitting = train.loc[train["fold_id"].ne(fold)]
        held = train.loc[train["fold_id"].eq(fold)]
        tfidf = vectorizer(plan).fit(fitting["text"])
        x_fit = hybrid_inputs(tfidf, fitting["text"], train_e2[fitting.index])
        x_held = hybrid_inputs(tfidf, held["text"], train_e2[held.index])
        teacher_scores = aligned_teacher_scores(
            fitting, CACHE / f"outer{fold}_fitting_targets.csv.gz"
        )
        for mode in MODES:
            model = fit_student(
                x_fit, fitting["target"].to_numpy(), teacher_scores, mode, alpha, parameters
            )
            scores = model.predict(x_held)
            fold_metrics = metrics(held["target"], scores, plan["cv_threshold"])
            cv_rows.append({"mode": mode, "fold_id": fold, "seed": SEED, **fold_metrics})
            predictions = held[["id", "fold_id", "target"]].rename(columns={"target": "y_true"})
            predictions = predictions.assign(candidate=mode, seed=SEED, score=scores)
            oof_rows.append(predictions)
            print(f"CV fold {fold} {mode} AP = {fold_metrics['ap']:.5f}", flush=True)

    oof = pd.concat(oof_rows, ignore_index=True)
    write_csv(OUT / "cv_metrics.csv", pd.DataFrame(cv_rows))
    write_csv(OUT / "cv_predictions.csv.gz", oof)
    cv_summary = pd.DataFrame(cv_rows).groupby("mode", as_index=False).agg(
        ap_mean=("ap", "mean"),
        recall_mean=("recall", "mean"),
        fpr_mean=("fpr", "mean"),
        precision_mean=("precision", "mean"),
        f1_mean=("f1", "mean"),
    )
    thresholds = {}
    oof_operating = []
    for mode in MODES:
        rows = oof.loc[oof["candidate"].eq(mode)]
        if len(rows) != len(train) or not rows["id"].is_unique:
            raise ValueError("Expected one OOF prediction per Train ID and mode.")
        thresholds[mode] = choose_threshold(rows["y_true"], rows["score"], plan["fpr_budget"])
        oof_operating.append({"mode": mode, **metrics(rows["y_true"], rows["score"], thresholds[mode])})
    write_csv(OUT / "cv_summary.csv", cv_summary)
    write_csv(OUT / "train_oof_at_locked_threshold.csv", pd.DataFrame(oof_operating))
    write_json(
        OUT / "threshold_lock.json",
        {"seed": SEED, "fpr_budget": plan["fpr_budget"], "thresholds": thresholds,
         "fit_scope": "Pooled Train OOF only. Validation excluded."},
    )

    original_oof_file = ROOT / "reports/tables/student_lightgbm/cv_predictions.csv.gz"
    original = pd.read_csv(original_oof_file, float_precision="round_trip")
    original = original.loc[original["family"].eq("hybrid_lightgbm") & original["seed"].eq(SEED)]
    original = original.assign(candidate="400_tree_" + original["mode"])
    paired_domain_bootstrap(
        pd.concat([oof, original[oof.columns]], ignore_index=True),
        train.set_index("id")["group"],
        [("kd_mixed", "hard_only"), ("kd_mixed", "400_tree_kd_mixed")],
        output_path=OUT / "paired_bootstrap.csv",
    )

    # Final fit uses the released Teacher. Validation is scored after threshold lock.
    tfidf = vectorizer(plan).fit(train["text"])
    x_train = hybrid_inputs(tfidf, train["text"], train_e2)
    validation_e2 = e2_matrix(validation["url"])
    x_val = hybrid_inputs(tfidf, validation["text"], validation_e2)
    teacher_scores = aligned_teacher_scores(train, release_targets)
    features = export_features(tfidf)
    write_json(ART / "features.json", features, compact=True)

    common_artifacts = [
        ART / "features.json",
        ORIGINAL_ART / "brand_reference_v1.csv",
        ORIGINAL_ART / "psl_icann_tldextract_5.4.0.txt",
    ]
    common_bytes = sum(path.stat().st_size for path in common_artifacts)
    validation_rows, validation_predictions = [], []
    file_paths = common_artifacts.copy()
    for mode in MODES:
        model = fit_student(
            x_train, train["target"].to_numpy(), teacher_scores, mode, alpha, parameters
        )
        scores = model.predict(x_val)
        bundle = export_booster(model, thresholds[mode], mode)
        bundle["model_version"] = f"lightgbm-student-100x7-{mode}"
        model_path = ART / f"{mode}.json"
        write_json(model_path, bundle, compact=True)
        file_paths.append(model_path)
        portable = HybridLightGBMStudent(features, bundle)
        portable_scores = np.array([
            portable.score_row(portable.vector(url, e2))
            for url, e2 in zip(validation["url"], validation_e2)
        ])
        np.testing.assert_allclose(portable_scores, scores, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(
            portable_scores >= thresholds[mode], scores >= thresholds[mode]
        )
        row = {
            "mode": mode,
            "seed": SEED,
            **metrics(validation["target"], scores, thresholds[mode]),
            "model_json_bytes": model_path.stat().st_size,
            "inference_data_bytes": common_bytes + model_path.stat().st_size,
            "json_parity_max_abs_diff": float(np.max(np.abs(portable_scores - scores))),
        }
        validation_rows.append(row)
        predictions = validation[["id", "target"]].rename(columns={"target": "y_true"})
        validation_predictions.append(
            predictions.assign(mode=mode, score=scores, prediction=scores >= thresholds[mode])
        )
        print(f"Validation {mode}: {row}", flush=True)

    write_csv(OUT / "validation_metrics.csv", pd.DataFrame(validation_rows))
    write_csv(OUT / "validation_predictions.csv.gz", pd.concat(validation_predictions, ignore_index=True))
    write_json(
        ART / "manifest.json",
        {
            "seed": SEED,
            "lightgbm_parameters": parameters,
            "lightgbm_version": version("lightgbm"),
            "alpha": alpha,
            "thresholds": thresholds,
            "teacher_cv_targets_hash": sha256(CACHE / "manifest.json"),
            "teacher_release_targets_hash": sha256(release_targets),
            "source_plan_hash": sha256(PLAN),
            "artifact_sha256": {
                path.relative_to(ROOT).as_posix(): sha256(path) for path in file_paths
            },
            "input_feature_count": len(features["terms"]) + len(features["feature_order"]),
            "cv_ids": len(train),
            "validation_ids": len(validation),
            "teacher_retrained": False,
            "official_test_evaluated": False,
            "android_verified": False,
        },
    )


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
