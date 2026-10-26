"""Reproduce descriptive FP/FN evidence from saved OOF/validation; never score test."""
from pathlib import Path
import hashlib
import json
import sys
import tomllib

import numpy as np

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from phishguard_vn.paths import get_project_root
from phishguard_vn.modeling import build_logistic_baseline


def build_diagnostics(root):
    interim = root / "data/interim"
    metadata = json.loads((root / "reports/tables/04_run_metadata.json").read_text(encoding="utf-8"))
    for name, digest in metadata["source_sha256_lf"].items():
        if hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() != digest:
            raise ValueError(f"Runtime source changed since baseline run: {name}")
    for name, digest in metadata["input_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Handoff changed since baseline run: {name}")
    core = pd.read_csv(interim / "core_gold_silver.csv", low_memory=False)
    features = pd.read_csv(interim / "03_matrix_X_features.csv")
    selected = metadata["selected_model"]
    outputs = {}
    for name, filename, split in [("cv", "04_cv_predictions.csv", "train"),
                                  ("validation", "04_validation_predictions.csv", "val")]:
        predictions = pd.read_csv(interim / filename)
        predictions = predictions.loc[predictions.model.eq(selected)]
        expected = core.loc[core.split.eq(split) & core.id.isin(features.id)]
        if predictions.id.duplicated().any() or set(predictions.id) != set(expected.id):
            raise ValueError(f"Unexpected prediction IDs for {split}")
        rows = predictions.merge(expected[["id", "source", "label"]], on="id", validate="one_to_one")
        if not rows.true_label.eq(rows.label.eq("phishing").astype(int)).all():
            raise ValueError("Prediction labels differ from the core")
        def describe(frame):
            negative = frame.loc[frame.true_label.eq(0)]
            positive = frame.loc[frame.true_label.eq(1)]
            fp, tp = int(negative.predicted_label.sum()), int(positive.predicted_label.sum())
            fn, tn = len(positive)-tp, len(negative)-fp
            return dict(rows=len(frame), phishing=len(positive), benign=len(negative),
                        prevalence=len(positive)/len(frame), tp=tp, fp=fp, fn=fn, tn=tn,
                        precision=tp/(tp+fp) if tp+fp else 0,
                        recall=tp/len(positive) if len(positive) else None,
                        f1=2*tp/(2*tp+fp+fn) if len(positive) and 2*tp+fp+fn else None,
                        false_positive_rate=fp/len(negative) if len(negative) else None)
        outputs[name] = {"pooled": describe(rows),
                         "by_source": {source: describe(group) for source, group in rows.groupby("source")}}
        joined = rows.merge(features, on="id", validate="one_to_one")
        outputs[name]["feature_means_by_label"] = joined.groupby("label")[[
            "url_len", "dom_len", "subdom_cnt", "digit_cnt", "entropy"]].mean().to_dict("index")
    train = core.loc[core.split.eq("train"), ["id", "label"]].merge(features, on="id", validate="one_to_one")
    examples = pd.read_csv(root / "reports/tables/04_error_examples.csv")
    columns = metadata["feature_names"]
    fold_ids = pd.read_csv(interim / "02_group_folds_train.csv")
    train = train.merge(fold_ids, on="id", validate="one_to_one")
    with (root / "configs/baseline.toml").open("rb") as handle:
        config = tomllib.load(handle)
    fold_models = {}
    for fold in sorted(examples.fold_id.unique()):
        fitting = train.loc[train.fold_id.ne(fold)]
        estimator = build_logistic_baseline(
            config["experiment"]["seed"], "balanced" if selected.endswith("_balanced") else None,
            config.get("model", {}).get("max_iter", 2000))
        estimator.fit(fitting[columns], fitting.label.eq("phishing").astype(int))
        fold_models[fold] = estimator
    collisions = []
    for example in examples.itertuples():
        row = train.loc[train.id.eq(example.id)]
        if len(row) != 1:
            raise ValueError("Error sample must be an eligible training row")
        same = train.loc[train[columns].eq(row.iloc[0][columns], axis="columns").all(axis=1)]
        estimator = fold_models[example.fold_id]
        score = float(estimator.predict_proba(row[columns])[0, list(estimator.classes_).index(1)])
        if not np.isclose(score, example.score, atol=1e-10, rtol=0):
            raise ValueError("Fold reconstruction differs from saved OOF prediction")
        terms = estimator["scaler"].transform(row[columns])[0] * estimator["model"].coef_[0]
        top = np.argsort(abs(terms))[::-1][:4]
        collisions.append({"id": example.id, "fold_id": int(example.fold_id),
                           "error_type": example.error_type, "reconstructed_oof_score": score,
                           "largest_absolute_logit_terms": {columns[i]: float(terms[i]) for i in top},
                           "interpretation": "z*coefficient terms relative to fold-training means, with correlated predictors; not causal effects or feature importance rankings",
                           "identical_feature_train_benign": int(same.label.eq("benign").sum()),
                           "identical_feature_train_phishing": int(same.label.eq("phishing").sum())})
    cv, val = outputs["cv"]["pooled"], outputs["validation"]["pooled"]
    pi, recall, fpr = val["prevalence"], cv["recall"], cv["false_positive_rate"]
    precision = pi*recall/(pi*recall+(1-pi)*fpr)
    outputs.update(selected_model=selected, error_sample_collisions=collisions,
                   prevalence_only_counterfactual={
                       "note": "Illustration only: keep pooled OOF TPR/FPR, replace class prevalence by validation prevalence; not a new evaluation or a causal decomposition.",
                       "precision": precision, "f1": 2*precision*recall/(precision+recall)},
                   baseline_provenance={key: metadata[key] for key in
                       ["git_revision", "source_manifest_sha256", "input_sha256"]},
                   predictions_sha256={name: hashlib.sha256((interim/name).read_bytes()).hexdigest()
                       for name in ["04_cv_predictions.csv", "04_validation_predictions.csv"]},
                   analysis_script_sha256_lf=hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest())
    return outputs


if __name__ == "__main__":
    root = get_project_root()
    output = root / "reports/tables/04_error_diagnostics.json"
    output.write_text(json.dumps(build_diagnostics(root), ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(output)
