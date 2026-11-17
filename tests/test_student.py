"""Student contracts and real JSON parity; no project training in the tests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from phishguard_vn.student import (Student, choose_threshold, export_model,
                                   load_student, metrics, sha256, student_text)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("train_student", ROOT / "scripts/train_student.py")
training = importlib.util.module_from_spec(spec)
spec.loader.exec_module(training)
CONFIG = json.loads((ROOT / "configs/week7_student.json").read_text(encoding="utf-8"))


@pytest.fixture
def toy():
    urls = ["example.com/a", "example.org/b", "https://bank-login.net/A",
            "https://bücher.de/query?Q=%2F", "https://x.example.com/a"]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3,5), lowercase=False, sublinear_tf=True)
    X = vectorizer.fit_transform([student_text(u) for u in urls])
    return urls, vectorizer, X


def test_weighted_binary_copies_equal_hard_training(toy):
    _, _, X = toy
    y = np.array([0, 0, 1, 1, 0])
    weighted = training.fit_student(X, y, CONFIG)
    direct = LogisticRegression(C=CONFIG["C"], solver="liblinear",
                                max_iter=CONFIG["max_iter"], random_state=CONFIG["seed"]).fit(X, y)
    np.testing.assert_allclose(weighted.predict_proba(X), direct.predict_proba(X), atol=1e-7, rtol=0)


def test_fractional_targets_optimize_fractional_bce(toy):
    _, _, X = toy
    q = np.array([.1, .2, .8, .9, .25])
    model = training.fit_student(X, q, CONFIG)
    # liblinear also regularizes its synthetic intercept feature.
    p = model.predict_proba(X)[:,1]
    gradient = X.T @ (p-q) + model.coef_[0] / CONFIG["C"]
    assert np.max(np.abs(gradient)) < 1e-3
    assert abs(np.sum(p-q) + model.intercept_[0]/CONFIG["C"]) < 1e-3


def test_json_inference_matches_sklearn_on_unseen_inputs(toy):
    _, vectorizer, X = toy
    model = training.fit_student(X, np.array([0,0,1,1,0]), CONFIG)
    student = Student(export_model(vectorizer, model, .5, "toy", CONFIG))
    urls = ["https://EXAMPLE.com/A?Q=%2F", "//bücher.de/a", "http://127.0.0.1/",
            "http://[2001:db8::1]/A", "https://new.example.com/" + "x"*200,
            "https://user:pw@example.com:443/a#fragment"]
    expected = model.predict_proba(vectorizer.transform([student_text(u) for u in urls]))[:,1]
    np.testing.assert_allclose([student.score_one(u) for u in urls], expected, atol=1e-12, rtol=0)


@pytest.mark.parametrize("url", ["", " ", " example.com", "https://example.com:bad",
                                "https://", "example.com/\x00", None])
def test_invalid_urls_rejected(url):
    with pytest.raises((ValueError, TypeError)):
        student_text(url)


@pytest.mark.parametrize("scores,budget", [([.9,.9,.2,.3,.5,.6],0),
                                          ([.9,.9,.2,.3,.5,.6],.25),
                                          ([1.,1.,.2,.3,.5,.6],0)])
def test_threshold_handles_tied_benign_scores(scores, budget):
    y = np.array([0,0,0,0,1,1])
    t = choose_threshold(y, scores, budget)
    assert np.mean(np.array(scores[:4]) >= t) <= budget


def test_bad_targets_rejected(toy):
    _, _, X = toy
    for q in ([0, 1], [0,0,0,0,np.nan], [0,0,0,0,1.1]):
        with pytest.raises(ValueError, match="targets"):
            training.fit_student(X, q, CONFIG)


def test_metrics_use_ap_and_explicit_confusion_counts():
    result = metrics([0,0,1,1], [.1,.7,.8,.4], .5)
    assert (result["tp"],result["fp"],result["tn"],result["fn"]) == (1,1,1,1)
    assert result["fpr"] == .5 and result["recall"] == .5


def test_contract_rejects_corrupt_weights(toy):
    _, vectorizer, X = toy
    model = training.fit_student(X, np.array([0,0,1,1,0]), CONFIG)
    bundle = export_model(vectorizer, model, .5, "toy", CONFIG)
    for key,value in [("coef",[float("nan")]*len(bundle["coef"])),
                      ("terms",["same"]*len(bundle["terms"])),
                      ("threshold",2), ("calibrated",True)]:
        changed = deepcopy(bundle)
        changed[key] = value
        with pytest.raises(ValueError):
            Student(changed)


def write_fixture(root, overlap=False):
    folder = root / "data/splits"
    folder.mkdir(parents=True)
    for split,urls in [("train",["alpha.com/a","bravo.com/b"]),
                       ("val",["alpha.com/c" if overlap else "charlie.com/c","delta.com/d"])]:
        pd.DataFrame(dict(id=[split+"0",split+"1"],url=urls,label=["benign","phishing"],
                          tier=["gold","silver"],split=[split]*2,source=["fixture"]*2)).to_csv(
                              folder/f"url_{split}.csv",index=False)


def test_data_loader_rejects_domain_leakage(tmp_path):
    write_fixture(tmp_path, overlap=True)
    with pytest.raises(ValueError, match="overlap: group"):
        training.load_data(tmp_path)


def test_data_loader_does_not_need_official_test(tmp_path):
    write_fixture(tmp_path)
    train,val,excluded = training.load_data(tmp_path)
    assert len(train) == len(val) == 2 and excluded.empty
    assert not (tmp_path/"data/splits/url_test.csv").exists()


def test_teacher_failure_cannot_be_silently_imputed():
    class BadTeacher:
        def predict_batch(self, urls):
            return [dict(score=float("nan"),model_version="teacher-stacking-v2")]
    with pytest.raises(ValueError, match="Teacher output"):
        training.teacher_scores(BadTeacher(), pd.DataFrame({"url":["example.com"]}))


def test_real_artifacts_and_saved_metrics():
    manifest = json.loads((ROOT/"artifacts/student_week7/manifest.json").read_text(encoding="utf-8"))
    assert manifest["official_test_evaluated"] is False
    for relative,digest in manifest["output_sha256"].items():
        assert sha256(ROOT/relative) == digest
    target = manifest["teacher_targets"]
    assert sha256(ROOT/target["path"]) == target["sha256"]
    targets = pd.read_csv(ROOT/target["path"])
    assert len(targets) == 13078 and targets.id.is_unique
    assert "url" not in targets
    np.testing.assert_allclose(targets.kd_target,
        (1-CONFIG["kd_alpha"])*targets.target + CONFIG["kd_alpha"]*targets.teacher_score)
    raw = pd.read_csv(ROOT/"data/splits/url_val.csv", usecols=["id","url"], dtype=str)
    table = pd.read_csv(ROOT/"reports/tables/student_week7/benchmark.csv")
    for name in ("hard_only","kd_mixed"):
        model = load_student(ROOT,name)
        saved = pd.read_csv(ROOT/f"reports/tables/student_week7/{name}_validation.csv",
                            float_precision="round_trip")
        selected = saved.merge(raw,on="id",validate="one_to_one")
        assert len(selected) == 1585
        actual = np.array([model.score_one(u) for u in selected.url])
        np.testing.assert_allclose(actual,selected.score,rtol=0,atol=1e-12)
        np.testing.assert_array_equal(actual >= model.threshold,selected.prediction)
        for _, row in table.loc[table.candidate.eq(name)].iterrows():
            calculated = metrics(saved.y_true,saved.score,row.threshold)
            for key in ("ap","f1","precision","recall","fpr","tp","fp","tn","fn"):
                assert calculated[key] == pytest.approx(row[key], abs=1e-12)
            agreement = np.mean((saved.score >= row.threshold).astype(int) == saved.teacher_prediction)
            assert agreement == pytest.approx(row.agreement)


def test_loader_rejects_modified_model(tmp_path):
    folder = tmp_path/"artifacts/student_week7"
    folder.mkdir(parents=True)
    (folder/"model.json").write_text("{}",encoding="utf-8")
    manifest = dict(selected_candidate="hard_only",inference_source_sha256={},
                    models={"hard_only":dict(path="artifacts/student_week7/model.json",sha256="wrong")})
    (folder/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    with pytest.raises(ValueError,match="hash mismatch"):
        load_student(tmp_path)
