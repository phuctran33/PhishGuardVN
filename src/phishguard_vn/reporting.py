"""Save measured baseline results and reproducibility metadata."""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from importlib.metadata import version
import json
import platform
import subprocess
import joblib
import pandas as pd

def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()



def _plot_results(result, root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix
    from sklearn.metrics import average_precision_score, precision_recall_curve
    figures=root/"reports/figures"
    figures.mkdir(parents=True,exist_ok=True)
    selected=result["selected_model"]
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,key,title in zip(axes,["cv_predictions","validation_predictions"],
                            ["Group CV: pooled OOF", "Official validation: supplementary"]):
        rows=result[key]
        if rows.empty:
            ax.text(0.5,0.5,"No validation data",ha="center");continue
        rows=rows.loc[rows.model.eq(selected)]
        cm=confusion_matrix(rows.true_label,rows.predicted_label,labels=[0,1])
        ConfusionMatrixDisplay(cm,display_labels=["benign","phishing"]).plot(ax=ax,colorbar=False,values_format="d")
        ax.set_title(title)
    fig.suptitle(f"{selected}; threshold={result['decision_threshold']}")
    fig.tight_layout();fig.savefig(figures/"04_confusion_matrices.png",dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,5))
    short={"dummy_most_frequent":"Dummy","logistic_regression":"LR standard",
           "logistic_regression_balanced":"LR balanced"}
    for model,rows in result["cv_predictions"].groupby("model",sort=False):
        precision,recall,_=precision_recall_curve(rows.true_label,rows.score)
        ap=average_precision_score(rows.true_label,rows.score)
        ax.step(recall,precision,where="post",label=f"{short[model]} (pooled AP={ap:.3f})")
    ax.set(xlabel="Recall (phishing)",ylabel="Precision (phishing)",xlim=(0,1),ylim=(0,1.02),
           title="Group CV: precision-recall from pooled OOF predictions")
    ax.legend();ax.grid(alpha=0.2);fig.tight_layout()
    fig.savefig(figures/"04_precision_recall_cv.png",dpi=150);plt.close(fig)



NOTE_KEYS = ["model", "id", "error_type"]
NOTE_COLUMNS = ["observation", "hypothesis", "next_check"]


def _read_error_notes(tables):
    """Preserve analyst notes, including examples no longer selected in this run.

    The current examples CSV is editable; the notes CSV is an automatic archive.
    Read both before writing any generated result so malformed manual edits fail safely.
    """
    collected = {}
    for name in ("04_error_notes.csv", "04_error_examples.csv"):
        path = tables / name
        if not path.is_file():
            continue
        prior = pd.read_csv(path, keep_default_na=False, dtype={"id": "string"})
        if prior.empty:
            continue
        if not set(NOTE_KEYS).issubset(prior.columns):
            raise ValueError(f"Cannot preserve error notes: missing key columns in {path}")
        if prior.duplicated(NOTE_KEYS).any():
            raise ValueError(f"Cannot preserve error notes: duplicate annotation keys in {path}")
        for record in prior.to_dict("records"):
            key = tuple(record[c] for c in NOTE_KEYS)
            collected[key] = {c: str(record.get(c, "")) for c in NOTE_COLUMNS}
    rows = [{**dict(zip(NOTE_KEYS, key)), **notes} for key, notes in collected.items()
            if any(v.strip() for v in notes.values())]
    return pd.DataFrame(rows, columns=NOTE_KEYS + NOTE_COLUMNS)


def _source_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def select_error_examples(predictions, selected_model, per_type=5):
    """Deterministic round robin across available folds, separately for FP/FN.

    Within a fold use ascending ID, not score. This is a qualitative sample,
    not a random or statistically representative estimate of the error population.
    """
    errors = predictions.loc[predictions.model.eq(selected_model) &
                             predictions.true_label.ne(predictions.predicted_label)].copy()
    errors["error_type"] = errors.predicted_label.map({1: "false_positive", 0: "false_negative"})
    errors = errors.sort_values(["error_type", "fold_id", "id"])
    errors["_rank_in_fold"] = errors.groupby(["error_type", "fold_id"]).cumcount()
    return (errors.sort_values(["error_type", "_rank_in_fold", "fold_id", "id"])
            .groupby("error_type", sort=True).head(per_type)
            .drop(columns="_rank_in_fold").reset_index(drop=True))


def _git_provenance(root, sources):
    """HEAD is a base revision; source hashes identify any uncommitted runtime code."""
    def git(*args):
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else "unavailable"
    paths = sorted(p.relative_to(root).as_posix() for p in sources)
    source_status = git("status", "--porcelain", "--untracked-files=all", "--", *paths)
    return {
        "git_revision": git("rev-parse", "HEAD"),
        "git_worktree_status": git("status", "--porcelain", "--untracked-files=all"),
        "git_source_worktree_status": source_status,
        "source_state": ("unavailable" if source_status == "unavailable" else
                         "modified_from_head" if source_status else "matches_head"),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance_note": (
            "Captured before save_results writes generated outputs. git_revision is HEAD at run time, "
            "not a claim that the run used a clean commit or the eventual report commit. "
            "source_state concerns only files in source_sha256_lf; that manifest identifies runtime "
            "sources/config (CRLF normalized to LF), including uncommitted changes. "
            "input_sha256 identifies handoff bytes; neither a later commit nor edited metadata "
            "retroactively changes the provenance of an earlier run."
        ),
    }


def save_results(result, config, root, config_path):
    tables, interim, models = root/"reports/tables", root/"data/interim", root/"models"
    sources = sorted((root/"src/phishguard_vn").glob("*.py")) + [config_path]
    sources += [p for p in [root/"scripts/train_baseline.py", root/"reports/templates/feature_dictionary.csv"] if p.is_file()]
    provenance = _git_provenance(root, sources)
    source_hashes = {p.relative_to(root).as_posix(): _source_hash(p) for p in sources}
    notes = _read_error_notes(tables)
    for folder in (tables, interim, models):
        folder.mkdir(parents=True, exist_ok=True)
    for key in ("cv_metrics", "cv_summary", "validation_metrics"):
        result[key].to_csv(tables/f"04_{key}.csv", index=False)
    for key in ("cv_predictions", "validation_predictions"):
        result[key].to_csv(interim/f"04_{key}.csv", index=False)
    examples = select_error_examples(result["cv_predictions"], result["selected_model"])
    examples = examples.merge(notes, on=NOTE_KEYS, how="left", validate="one_to_one")
    for column in NOTE_COLUMNS:
        examples[column] = examples[column].fillna("")
    if not notes.empty or (tables/"04_error_notes.csv").exists():
        notes.to_csv(tables/"04_error_notes.csv", index=False)
    examples.to_csv(tables/"04_error_examples.csv", index=False)
    artifact = {"pipeline": result["pipeline"], "feature_names": result["feature_names"],
                "decision_threshold": result["decision_threshold"], "positive_label": "phishing",
                "selected_model": result["selected_model"], "config": config}
    artifact_path=models/"week4_lr_baseline.joblib"
    joblib.dump(artifact, artifact_path)
    inputs = [interim/name for name in ["core_gold_silver.csv", "03_matrix_X_features.csv",
                                       "03_registrable_domains.csv", "02_group_folds_train.csv"]]
    metadata = {"selected_model": result["selected_model"], "selection_rule": result["selection_rule"],
                "feature_names": result["feature_names"], "scope": result["scope"],
                "threshold": result["decision_threshold"], "pr_auc_definition": "average_precision",
                "python": platform.python_version(),
                "versions": {p: version(p) for p in ["numpy", "scipy", "pandas", "scikit-learn", "joblib", "tldextract", "idna", "matplotlib"]},
                "source_sha256_lf": source_hashes,
                "source_manifest_sha256": hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
                "input_sha256": {p.relative_to(root).as_posix(): _hash(p) for p in inputs},
                "hash_conventions": {"source": "CRLF normalized to LF", "input": "raw bytes"},
                "artifact_sha256": _hash(artifact_path)}
    metadata.update(provenance)
    metadata_text=json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    (models/"week4_lr_baseline_metadata.json").write_text(metadata_text,encoding="utf-8")
    (tables/"04_run_metadata.json").write_text(metadata_text,encoding="utf-8")
    _plot_results(result,root)
    summary=result["cv_summary"]
    lines=["# Week 4 - E1 baseline", "", "PR-AUC = average precision; phishing = 1.",
           "", "## Evaluation", "",
           f"Core train: {result['scope']['train_rows']} rows; phishing: {result['scope']['train_phishing']}.",
           f"Official validation: {result['scope']['validation_rows']} rows; phishing: {result['scope']['validation_phishing']}.",
           f"{config.get('evaluation',{}).get('n_splits',3)} fixed domain folds supplied by Hung; scaler fitted only inside each training fold.",
           f"Fixed decision threshold: {result['decision_threshold']}.",
           "Official test was not predicted or scored.", "",
           "## Group CV (mean +/- sample standard deviation)", "",
           "| Configuration | Precision | Recall | F1 | AP |", "|---|---:|---:|---:|---:|"]
    for row in summary.to_dict("records"):
        values=[f"{row[m+'_mean']:.4f} +/- {row[m+'_std']:.4f}" for m in
                ["precision_phishing","recall_phishing","f1_phishing","pr_auc"]]
        lines.append("| "+" | ".join([row["model"],*values])+" |")
    lines += ["", f"Selected LR configuration: **{result['selected_model']}**.",
              "Selection uses mean CV phishing F1, with CV AP as tie breaker. No selection uses official validation.",
              "Dummy is a reference; standard and balanced LR are two configurations of the same algorithm.",
              "", "## Supplementary official validation", "",
              "| Configuration | Precision | Recall | F1 | AP | FP | FN |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for row in result["validation_metrics"].to_dict("records"):
        lines.append("| "+" | ".join([row["model"],*[f"{row[m]:.4f}" if row[m] is not None else "undefined"
                       for m in ["precision_phishing","recall_phishing","f1_phishing","pr_auc"]],str(row["fp"]),str(row["fn"])])+" |")
    chosen=summary.loc[summary.model.eq(result["selected_model"])].iloc[0]
    lines += ["", f"Selected model CV false-positive rate: {chosen['false_positive_rate_mean']:.2%}.",
              "This saved model is an experimental baseline, not a final deployment choice.",
              f"Validation contains {result['scope']['validation_phishing']} phishing samples; interpret metrics with their class supports and source composition.",
              "Scores are model outputs, not calibrated real-world risk probabilities.",
              "Labels retain the anti-fraud/abuse scope and uncertainty of PhishVN.",
              f"Excluded from X/CV: {len(result['scope']['excluded_ids'])} core rows; the original core is preserved and excluded IDs are recorded in the handoff.",
              "", "## Outputs", "", "- reports/tables/04_cv_metrics.csv and 04_cv_summary.csv",
              "- reports/tables/04_validation_metrics.csv, 04_error_examples.csv and 04_run_metadata.json",
              "- data/interim/04_cv_predictions.csv and 04_validation_predictions.csv (ignored)",
              "- models/week4_lr_baseline.joblib and metadata JSON (ignored)",
              "", "## Error analysis", "", "The CSV contains up to five false positives and five false negatives from the selected model's OOF predictions.",
              "Selection cycles through available folds (0, 1, 2), with ascending IDs within each fold. With five examples per error type the allocation is 2/2/1 when every fold has enough errors.",
              "This small deterministic sample is for qualitative inspection, not an unbiased sample or an estimate of error-category frequency.",
              "See [measured FP/FN analysis and CV-validation gap](week4_error_analysis.md). Observations, hypotheses and next checks are recorded in the CSV; no labels were changed.",
              "Manual notes in 04_error_examples.csv survive reruns; 04_error_notes.csv automatically archives notes for examples not currently selected.",
              "", "## Provenance", "",
              f"Runtime HEAD (base revision): `{metadata['git_revision']}`; runtime source state: `{metadata['source_state']}`.",
              "The source SHA256 manifest, handoff hashes and capture time are in reports/tables/04_run_metadata.json. A dirty run is not presented as a clean-commit run; generated-output changes are separate from runtime-source changes.",
              "The previous snapshot recorded d5555da because the baseline source was then uncommitted on top of Hung's branch. It was a run-time base revision, not the baseline implementation commit. This snapshot comes from a fresh run; the old SHA was not manually replaced.",
              "", "Reproduce: python scripts/train_baseline.py (from the project environment).", ""]
    lines += ["", "![Confusion matrices](figures/04_confusion_matrices.png)",
              "", "![OOF precision-recall](figures/04_precision_recall_cv.png)", ""]
    (root/"reports/week4_baseline.md").write_text("\n".join(lines),encoding="utf-8")
    return artifact_path
