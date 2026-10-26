"""Binary metrics: phishing=1; PR-AUC is explicitly average precision."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix
from sklearn.metrics import f1_score, precision_score, recall_score


def summarize_predictions(y_true, y_pred, y_score) -> dict:
    truth, pred, score = (np.asarray(a) for a in (y_true, y_pred, y_score))
    if any(a.ndim != 1 for a in (truth, pred, score)) or not len(truth):
        raise ValueError("Predictions must be non-empty one-dimensional arrays.")
    if not (len(truth) == len(pred) == len(score)):
        raise ValueError("Prediction arrays must have the same length.")
    if not set(truth).issubset({0, 1}) or not set(pred).issubset({0, 1}):
        raise ValueError("Use benign=0, phishing=1 without missing labels.")
    score = score.astype(float)
    if not np.isfinite(score).all() or ((score < 0) | (score > 1)).any():
        raise ValueError("Scores must be finite numbers in [0, 1].")
    tn, fp, fn, tp = confusion_matrix(truth, pred, labels=[0, 1]).ravel()
    positives, negatives = int((truth == 1).sum()), int((truth == 0).sum())
    return {
        "n_rows": len(truth), "n_benign": negatives, "n_phishing": positives,
        "accuracy": float(accuracy_score(truth, pred)),
        "precision_phishing": float(precision_score(truth, pred, zero_division=0)),
        "recall_phishing": float(recall_score(truth, pred, zero_division=0)) if positives else None,
        "f1_phishing": float(f1_score(truth, pred, zero_division=0)) if positives else None,
        "pr_auc": float(average_precision_score(truth, score)) if positives else None,
        "pr_auc_definition": "average_precision",
        "false_positive_rate": float(fp / negatives) if negatives else None,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }
