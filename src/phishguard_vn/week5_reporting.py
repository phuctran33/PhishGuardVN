"""Persist the lexical-only week-5 experiment without changing E1 outputs."""
from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from phishguard_vn.reporting import _git_provenance, _hash, _source_hash

TABLE_KEYS = ("cv_metrics", "cv_summary", "validation_metrics", "inner_search", "selections", "fit_log", "split_audit")
INPUT_NAMES = ("core_gold_silver.csv", "03_matrix_X_features.csv", "03_registrable_domains.csv", "02_group_folds_train.csv")


def _clean_json(value):
    """Represent missing measurements as null; never emit NaN/Infinity in metadata."""
    if isinstance(value, dict):
        return {str(k): _clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(v) for v in value]
    if isinstance(value, np.generic):
        return _clean_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def _number(value, digits=4):
    return f"{value:.{digits}f}" if pd.notna(value) else "không xác định"


def _plot_week5(result, root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix, precision_recall_curve

    figures = root / "reports/figures"
    figures.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    for name, rows in result["cv_predictions"].groupby("model", sort=False):
        precision, recall, _ = precision_recall_curve(rows.true_label, rows.score)
        ap = average_precision_score(rows.true_label, rows.score)
        ax.step(recall, precision, where="post", label=f"{name} (pooled AP={ap:.3f})")
    ax.set(xlabel="Recall (phishing)", ylabel="Precision (phishing)", xlim=(0, 1), ylim=(0, 1.02),
           title="Week 5 lexical features: pooled OOF precision-recall")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(figures / "05_precision_recall_cv.png", dpi=150)
    plt.close(fig)

    selected = result["selected_model"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, key, title in zip(axes, ("cv_predictions", "validation_predictions"),
                              ("Pooled OOF", "Official validation (supplementary)")):
        predictions = result[key]
        rows = predictions.loc[predictions.model.eq(selected)] if not predictions.empty else predictions
        if rows.empty:
            ax.text(0.5, 0.5, "No predictions", ha="center")
        else:
            cm = confusion_matrix(rows.true_label, rows.predicted_label, labels=[0, 1])
            ConfusionMatrixDisplay(cm, display_labels=["benign", "phishing"]).plot(
                ax=ax, colorbar=False, values_format="d")
        ax.set_title(title)
    fig.suptitle(f"{selected}; threshold={result['decision_threshold']}")
    fig.tight_layout()
    fig.savefig(figures / "05_confusion_matrices.png", dpi=150)
    plt.close(fig)


def _report(result, config, root, metadata):
    scope = result["scope"]
    summary = result["cv_summary"]
    lines = [
        "# Tuần 5 — so sánh mô hình trên 12 lexical features", "",
        "Đây là phần có thể hoàn thành trước khi Hy bàn giao brand features. "
        "Chưa có ablation 12 vs 12+brand, chưa chốt Teacher cuối cùng, chưa huấn luyện KD hoặc triển khai mobile.", "",
        "## Giao thức", "",
        f"- Train đủ điều kiện: {scope.get('train_rows', 'xem metadata')} URL; phishing: {scope.get('train_phishing', 'xem metadata')}.",
        f"- Official validation bổ sung: {scope.get('validation_rows', 'xem metadata')} URL; phishing: {scope.get('validation_phishing', 'xem metadata')}.",
        f"- Dùng nguyên {config['evaluation']['n_splits']} outer domain folds của Hưng; chỉ train được dùng để fit/chọn cấu hình.",
        f"- Inner Group CV: {config['evaluation']['inner_splits']} folds để chọn cấu hình theo AP trung bình. Những bước fit ở inner fold không nhìn outer held-out fold.",
        f"- SVM dùng sigmoid calibration với {config['evaluation']['calibration_splits']} group folds riêng bên trong mỗi tập đang fit, scaler nằm trong base pipeline.",
        "- MLP và boosting tắt early stopping dùng holdout ngẫu nhiên; không dùng official validation để chọn cấu hình hoặc thời điểm dừng.",
        f"- Ngưỡng cố định: {result['decision_threshold']}. AP là average precision; phishing = 1.",
        "- Cùng ngưỡng 0,5 không bảo đảm cùng điểm vận hành giữa các thuật toán; đọc PR curve, Recall và FPR cùng nhau.\n- Official test không được dự đoán/chấm. Feature set chỉ gồm 12 lexical features, không có source/tier/split/label trong X.",
        "- Quyết định AP làm chính được Phúc xác nhận trước khi xem kết quả tuần 5; xem [giao thức](../docs/project/week5_protocol.md).", "",
        "## Outer Group CV", "",
        "Mỗi dòng dưới là trung bình ± độ lệch chuẩn mẫu qua các outer folds. "
        "AP/F1 từ OOF gộp có thể khác trung bình theo fold. "
        "So sánh này đánh giá cả quy trình chọn cấu hình trong train, không dùng cùng một cấu hình toàn train để nhìn trước các outer folds.", "",
        "| Mô hình | AP | Precision | Recall | F1 | FPR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        cells = [f"{_number(row.get(key+'_mean'))} ± {_number(row.get(key+'_std'))}"
                 for key in ("pr_auc", "precision_phishing", "recall_phishing", "f1_phishing", "false_positive_rate")]
        lines.append("| " + " | ".join([row["model"], *cells]) + " |")
    lines += ["", f"Ứng viên dẫn đầu trên lexical-only theo quy tắc AP: **{result['selected_model']}**.",
              "Đây là lựa chọn ứng viên để nghiên cứu tiếp, chưa phải phê duyệt Teacher hay lựa chọn triển khai. "
              "Điểm của family thắng đã tham gia quá trình chọn family, vì vậy không coi đó là ước lượng cuối cùng không thiên lệch cho model được chọn.", "",
              "## AP từ OOF gộp", "", "| Mô hình | Pooled OOF AP |", "|---|---:|"]
    for name, rows in result["cv_predictions"].groupby("model", sort=False):
        lines.append(f"| {name} | {average_precision_score(rows.true_label, rows.score):.4f} |")
    lines += ["", "Các score OOF đến từ nhiều model fit theo các outer folds; pooled AP được báo cáo mô tả, "
              "không thay thế tiêu chí AP trung bình folds đã chốt.", "", "## Official validation bổ sung", "",
              "Mỗi family được chọn cấu hình lại chỉ bằng Group CV trên toàn train, rồi fit toàn train và chấm validation. "
              "Validation không quyết định cấu hình, family, feature hoặc threshold.", "",
              "| Mô hình | AP | Precision | Recall | F1 | FPR | FP | FN |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["validation_metrics"].to_dict("records"):
        cells = [_number(row.get(key)) for key in ("pr_auc", "precision_phishing", "recall_phishing", "f1_phishing", "false_positive_rate")]
        lines.append("| " + " | ".join([row["model"], *cells, str(row["fp"]), str(row["fn"])]) + " |")
    lines += ["", "Validation nhỏ ở lớp phishing và khác phân bố nguồn; đọc cùng support, FP/FN và FPR. "
              "Không xem một chênh lệch điểm đơn lẻ là bằng chứng đã xử lý source bias.", "",
              "## Đối chiếu E1", "",
              "LR thường và balanced vẫn là các đối chứng C=1 nếu chạy config mặc định. "
              "E1 chọn LR bằng F1; tuần 5 chọn cấu hình/family bằng AP theo quyết định mới. "
              "Vì vậy không thay tên hoặc ghi đè winner E1 bằng winner tuần 5."]
    baseline = root / "reports/tables/04_cv_summary.csv"
    if baseline.is_file():
        old = pd.read_csv(baseline)
        reference = old.loc[old.model.isin(("logistic_regression", "logistic_regression_balanced"))]
        comparison = reference.merge(summary, on="model", suffixes=("_e1", "_week5"))
        if not comparison.empty:
            lines += ["", "| Đối chứng | Δ mean AP (tuần 5 − E1) | Δ mean F1 |", "|---|---:|---:|"]
            for row in comparison.to_dict("records"):
                lines.append(f"| {row['model']} | {row['pr_auc_mean_week5']-row['pr_auc_mean_e1']:+.8f} | {row['f1_phishing_mean_week5']-row['f1_phishing_mean_e1']:+.8f} |")
            lines += ["", "Các delta trên là đối chiếu output, không tự chứng minh hai lần chạy có cùng dữ liệu/thư viện; kiểm tra metadata khi có chênh lệch."]
    convergence = result["fit_log"]
    lines += ["", "## Tái lập và trạng thái", "",
              f"- Có {len(result['inner_search'])} dòng log inner search, {len(result['selections'])} lựa chọn outer/full-train và {len(convergence)} dòng fit log.",
              "- Xem 05_fit_log.csv để biết convergence warning; không che cảnh báo bằng cách bỏ dòng log. "
              "Cấu hình có cảnh báo phải được diễn giải cùng chính sách hợp lệ trong giao thức.",
              "- 05_split_audit.csv và 05_selections.csv cho phép kiểm tra cách chia/chọn; predictions giữ ID để Hưng phân tích source/fold errors.",
              f"- Runtime HEAD: `{metadata['git_revision']}`; source state: `{metadata['source_state']}`.",
              "- Metadata có hash source/config/handoff/model, phiên bản thư viện và runtime threads. HEAD là commit nền lúc chạy; hash xác định source thực tế nếu còn sửa.",
              "- E1 code/config/output không được ghi đè bởi script tuần 5. Mỗi lần chạy tuần 5 sẽ thay các output 05 của lần trước.", "",
              "```powershell", ".\.venv\Scripts\python.exe scripts/train_week5.py", "```", "",
              "## Việc chờ Hy và cả nhóm", "",
              "- Brand feature spec/dictionary/version và X E2 chưa được giả lập.",
              "- Chờ Hy bàn giao để kiểm tra ID/schema và chạy 12 vs 12+brand trên cùng samples/folds.",
              "- Cùng Hưng phân tích lỗi/robustness, cùng Khiêm đọc source bias/external evidence.",
              "- Chỉ chốt Teacher sau khi đánh giá trade-off precision/recall/FPR, tài nguyên và đủ các thí nghiệm cần thiết.", "",
              "![Precision–Recall OOF](figures/05_precision_recall_cv.png)", "",
              "![Confusion matrices](figures/05_confusion_matrices.png)", ""]
    return "\n".join(lines)


def save_week5_results(result, config, root, config_path):
    """Write only week-5 results. Return the local bundle path for inference."""
    root, config_path = Path(root).resolve(), Path(config_path).resolve()
    if not config_path.is_relative_to(root):
        raise ValueError("Week-5 config must be inside the project checkout.")
    for key in TABLE_KEYS + ("cv_predictions", "validation_predictions"):
        if not isinstance(result.get(key), pd.DataFrame):
            raise ValueError(f"Missing DataFrame result: {key}")
    if result["selected_model"] not in result["estimators"]:
        raise ValueError("Selected model has no full-train estimator.")
    sources = sorted((root / "src/phishguard_vn").glob("*.py")) + [config_path]
    sources += [p for p in (root / "scripts/train_week5.py", root / "scripts/predict_week5.py",
                           root / "reports/templates/feature_dictionary.csv") if p.is_file()]
    sources = sorted(set(sources))
    provenance = _git_provenance(root, sources)
    provenance["provenance_note"] = provenance["provenance_note"].replace("save_results", "save_week5_results")
    source_hashes = {p.relative_to(root).as_posix(): _source_hash(p) for p in sources}
    inputs = [root / "data/interim" / name for name in INPUT_NAMES]
    input_hashes = {p.relative_to(root).as_posix(): _hash(p) for p in inputs}
    e1_files = [root / "configs/baseline.toml", root / "reports/week4_baseline.md",
                root / "reports/week4_error_analysis.md"]
    e1_files += sorted((root / "reports/tables").glob("04_*"))
    e1_hashes = {p.relative_to(root).as_posix(): _hash(p) for p in e1_files if p.is_file()}
    tables, interim, models = root / "reports/tables", root / "data/interim", root / "models"
    for directory in (tables, interim, models):
        directory.mkdir(parents=True, exist_ok=True)
    for key in TABLE_KEYS:
        result[key].to_csv(tables / f"05_{key}.csv", index=False)
    for key in ("cv_predictions", "validation_predictions"):
        result[key].to_csv(interim / f"05_{key}.csv", index=False)
    artifact = {"estimators": result["estimators"], "selected_model": result["selected_model"],
                "feature_names": list(result["feature_names"]), "feature_set": "lexical_12",
                "decision_threshold": result["decision_threshold"], "positive_label": "phishing",
                "config": config, "status": "lexical-only candidate; brand ablation and Teacher decision pending"}
    artifact_path = models / "week5_lexical_models.joblib"
    joblib.dump(artifact, artifact_path)
    metadata = {"experiment": config["experiment"], "config": config,
                "selected_model": result["selected_model"], "selection_rule": result.get("selection_rule", "mean outer Group-CV AP; train-only inner selection"),
                "feature_set": "lexical_12", "feature_names": result["feature_names"],
                "scope": result["scope"], "threshold": result["decision_threshold"],
                "pr_auc_definition": "average_precision", "status": artifact["status"],
                "python": platform.python_version(),
                "versions": {p: version(p) for p in ("numpy", "scipy", "pandas", "scikit-learn", "joblib", "tldextract", "idna", "matplotlib", "threadpoolctl")},
                "runtime": result.get("runtime", {}), "source_sha256_lf": source_hashes,
                "source_manifest_sha256": hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
                "input_sha256": input_hashes, "artifact_sha256": _hash(artifact_path),
                "artifact_bytes": artifact_path.stat().st_size, "e1_snapshot_sha256": e1_hashes,
                "hash_conventions": {"source": "CRLF normalized to LF", "input": "raw bytes"}}
    metadata.update(provenance)
    metadata = _clean_json(metadata)
    metadata_text = json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (models / "week5_lexical_models_metadata.json").write_text(metadata_text, encoding="utf-8")
    (tables / "05_run_metadata.json").write_text(metadata_text, encoding="utf-8")
    _plot_week5(result, root)
    (root / "reports/week5_models.md").write_text(_report(result, config, root, metadata), encoding="utf-8")
    if any(_hash(root / path) != digest for path, digest in e1_hashes.items()):
        raise RuntimeError("An E1 output changed while writing week-5 results.")
    return artifact_path
