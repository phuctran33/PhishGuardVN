"""Protect week-5 reporting boundaries, provenance and inference artifacts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import joblib
import pandas as pd
import pytest

from phishguard_vn.experiments import run_experiments
from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.modeling import predict_url
from phishguard_vn.week5_reporting import save_week5_results


@pytest.fixture
def reporting_run(tmp_path):
    features, targets, folds = [], [], []
    for group in range(12):
        for label in range(2):
            row_id = f"train-{group:02}-{label}"
            values = {name: float(1 + label * 5 + group / 10) for name in CANDIDATE_FEATURES}
            values.update(id=row_id, url_len=float(10 + group + label * 10))
            features.append(values)
            targets.append(dict(id=row_id, label="phishing" if label else "benign", tier="gold",
                                split="train", registrable_domain=f"group-{group}.example"))
            folds.append(dict(id=row_id, fold_id=group % 3))
    for split in ("val", "test"):
        for label in range(2):
            row_id = f"{split}-{label}"
            values = {name: float(1 + label * 5) for name in CANDIDATE_FEATURES}
            values.update(id=row_id, url_len=float(10 + label * 10))
            features.append(values)
            targets.append(dict(id=row_id, label="phishing" if label else "benign", tier="silver",
                                split=split, registrable_domain=f"{split}-{label}.example"))
    X, y, f = pd.DataFrame(features), pd.DataFrame(targets), pd.DataFrame(folds)
    config = {
        "experiment": {"name": "fixture", "seed": 42, "feature_set": "lexical_12", "threads": 1},
        "evaluation": {"n_splits": 3, "inner_splits": 2, "calibration_splits": 2,
                       "primary_metric": "average_precision", "decision_threshold": 0.5,
                       "use_test": False, "validation_role": "supplementary"},
        "candidates": {"logistic_regression": [{"class_weight": "none", "C": 1.0, "max_iter": 2000}]},
    }
    config_path = tmp_path / "configs/e2_models.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("[experiment]\nname='fixture'\nseed=42\nfeature_set='lexical_12'\n", encoding="utf-8")
    interim = tmp_path / "data/interim"
    interim.mkdir(parents=True)
    X.to_csv(interim / "03_matrix_X_features.csv", index=False)
    y.to_csv(interim / "core_gold_silver.csv", index=False)
    y[["id", "registrable_domain"]].to_csv(interim / "03_registrable_domains.csv", index=False)
    f.to_csv(interim / "02_group_folds_train.csv", index=False)
    # Every sentinel represents an E1 source, config, artifact or report that week 5 must preserve.
    sentinels = {
        "configs/baseline.toml": "E1 config\n",
        "src/phishguard_vn/modeling.py": "# E1 source sentinel\n",
        "notebooks/04_baseline_ml.ipynb": "E1 notebook\n",
        "models/week4_lr_baseline.joblib": "E1 artifact\n",
        "models/week4_lr_baseline_metadata.json": "E1 metadata\n",
        "data/interim/04_cv_predictions.csv": "E1 predictions\n",
        "reports/week4_baseline.md": "E1 report\n",
        "reports/week4_error_analysis.md": "E1 notes\n",
        "reports/tables/04_cv_summary.csv": "model,pr_auc_mean,f1_phishing_mean\nlogistic_regression,0.5,0.5\n",
        "reports/tables/04_error_examples.csv": "E1 examples\n",
        "reports/figures/04_confusion_matrices.png": "E1 figure\n",
    }
    for name, content in sentinels.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    snapshots = {name: (tmp_path / name).read_bytes() for name in sentinels}
    result = run_experiments(X, y, f, config)
    return tmp_path, config_path, config, result, snapshots


def test_reporting_preserves_every_e1_sentinel_and_writes_only_week5_outputs(reporting_run):
    root, config_path, config, result, snapshots = reporting_run
    before = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    save_week5_results(result, config, root, config_path)
    for name, content in snapshots.items():
        assert (root / name).read_bytes() == content, name
    added = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - before
    assert added
    assert all(Path(name).name.startswith(("05_", "week5_")) for name in added)
    assert (root / "reports/tables/05_split_audit.csv").is_file()
    assert (root / "reports/tables/05_selections.csv").is_file()
    assert (root / "data/interim/05_cv_predictions.csv").is_file()


def test_artifact_hash_reload_predictions_and_finite_metadata(reporting_run):
    root, config_path, config, result, _ = reporting_run
    artifact = save_week5_results(result, config, root, config_path)
    def bad_constant(value):
        raise AssertionError(f"Nonfinite JSON constant: {value}")
    metadata = json.loads((root / "reports/tables/05_run_metadata.json").read_text(encoding="utf-8"),
                          parse_constant=bad_constant)
    assert metadata["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert metadata["artifact_bytes"] == artifact.stat().st_size
    assert metadata["pr_auc_definition"] == "average_precision"
    assert metadata["scope"]["test_evaluated"] is False
    assert json.dumps(metadata, allow_nan=False)
    bundle = joblib.load(artifact)
    assert bundle["feature_names"] == list(CANDIDATE_FEATURES)
    name = bundle["selected_model"]
    original = predict_url("https://example.com/a", result["estimators"][name], result["feature_names"], 0.5)
    loaded = predict_url("https://example.com/a", bundle["estimators"][name], bundle["feature_names"], bundle["decision_threshold"])
    assert original == loaded
    sources = metadata["source_sha256_lf"]
    assert metadata["source_manifest_sha256"] == hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    for name, digest in metadata["input_sha256"].items():
        assert digest == hashlib.sha256((root / name).read_bytes()).hexdigest()


def test_provenance_capture_precedes_all_generated_outputs(reporting_run, monkeypatch):
    import phishguard_vn.week5_reporting as reporting
    root, config_path, config, result, _ = reporting_run
    captured = []
    original = reporting._git_provenance
    def capture(checkout, sources):
        assert not list((checkout / "reports/tables").glob("05_*"))
        assert not (checkout / "models/week5_lexical_models.joblib").exists()
        captured.append(True)
        return original(checkout, sources)
    monkeypatch.setattr(reporting, "_git_provenance", capture)
    save_week5_results(result, config, root, config_path)
    assert captured == [True]
    metadata = json.loads((root / "reports/tables/05_run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["captured_at_utc"]
    assert "before save_week5_results writes" in metadata["provenance_note"]


def test_report_marks_brand_teacher_pending_and_uses_actual_supports(reporting_run):
    root, config_path, config, result, _ = reporting_run
    save_week5_results(result, config, root, config_path)
    text = (root / "reports/week5_models.md").read_text(encoding="utf-8")
    assert "Train đủ điều kiện: 24 URL; phishing: 12" in text
    assert "Official validation bổ sung: 2 URL; phishing: 1" in text
    assert "Chưa có ablation 12 vs 12+brand" in text
    assert "chưa chốt Teacher cuối cùng" in text
    assert "Chờ Hy bàn giao" in text
    assert "Cùng ngưỡng 0,5 không bảo đảm cùng điểm vận hành" in text
    assert "không thiên lệch" in text
    assert "13.078" not in text and "24 phishing" not in text


def test_metadata_distinguishes_dirty_sources_from_generated_outputs(reporting_run):
    root, config_path, config, result, _ = reporting_run
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)
    git("init")
    git("add", ".")
    git("-c", "user.name=Week5 Test", "-c", "user.email=week5@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
    head = git("rev-parse", "HEAD").stdout.strip()
    save_week5_results(result, config, root, config_path)
    clean = json.loads((root / "reports/tables/05_run_metadata.json").read_text(encoding="utf-8"))
    assert clean["git_revision"] == head and clean["source_state"] == "matches_head"
    source = root / "src/phishguard_vn/modeling.py"
    source.write_text(source.read_text(encoding="utf-8") + "# uncommitted runtime change\n", encoding="utf-8")
    save_week5_results(result, config, root, config_path)
    dirty = json.loads((root / "reports/tables/05_run_metadata.json").read_text(encoding="utf-8"))
    assert dirty["git_revision"] == head and dirty["source_state"] == "modified_from_head"
    assert "modeling.py" in dirty["git_source_worktree_status"]
    assert clean["source_sha256_lf"] != dirty["source_sha256_lf"]


def test_invalid_result_fails_before_any_generated_writes(reporting_run):
    root, config_path, config, result, _ = reporting_run
    malformed = copy.copy(result)
    malformed["cv_metrics"] = None
    with pytest.raises(ValueError, match="Missing DataFrame result"):
        save_week5_results(malformed, config, root, config_path)
    assert not list((root / "reports/tables").glob("05_*"))
