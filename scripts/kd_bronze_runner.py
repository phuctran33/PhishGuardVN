"""Resumable Train-only Student screen and seed verification.

python scripts/kd_bronze_runner.py --stage screen
Use --families to shard by model family. Each fold/recipe/seed saves one checkpoint.
"""
import argparse
from dataclasses import asdict, dataclass
import gzip
import hashlib
import io
import json
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import vstack
from scipy.special import expit
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from kd_bronze_data import DATA_CACHE, ROOT, verify_preparation
from kd_bronze_trees import FAMILIES as TREES, fit_tree
from kd_bronze_sparse import FAMILIES as SPARSE, fit_sparse
from kd_bronze_neural import FAMILIES as NEURAL, fit_neural
from phishguard_vn.student import sha256

PLAN_PATH = ROOT / "configs/kd_bronze_research.json"
OUT = ROOT / "reports/tables/student_bronze_kd"
MODULES = ("kd_bronze_runner", "kd_bronze_data", "kd_bronze_trees", "kd_bronze_sparse", "kd_bronze_neural")
FAMILIES = {**TREES, **SPARSE, **NEURAL}
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf8"))


@dataclass(frozen=True)
class Recipe:
    family: str
    profile: str
    mode: str
    alpha: float = 0.0
    extra_weight: float = 0.0
    extra_rows: int = 0

    @property
    def tag(self):
        return f"{self.family}_{self.profile}_{self.mode}_{self.alpha:g}_{self.extra_weight:g}_{self.extra_rows}"


def recipe(family, profile, mode, settings):
    if mode == "A":
        return Recipe(family, profile, mode)
    if mode == "B":
        return Recipe(family, profile, mode, settings["alpha"])
    return Recipe(family, profile, mode, **settings)


def encode_bytes(texts):
    tokens = np.zeros((len(texts), PLAN["byte_limit"]), dtype=np.uint16)
    for row, text in zip(tokens, texts, strict=True):
        text_bytes = np.frombuffer(text.encode("utf8")[:len(row)], dtype=np.uint8)
        row[:len(text_bytes)] = text_bytes.astype(np.uint16) + 1
    return tokens


def labels(cfg, y, teacher, extra):
    """Separate means: core weights 1; total bronze weight is lambda*N_core."""
    if cfg.mode not in "ABCD":
        raise ValueError("Unknown Student recipe")
    targets = (1 - cfg.alpha) * y + cfg.alpha * teacher
    weights = np.ones(len(y))
    if cfg.extra_rows:
        used = extra[:cfg.extra_rows]
        if len(used) != cfg.extra_rows:
            raise ValueError("Requested more bronze URLs than are eligible")
        if cfg.mode == "C":
            used = (used >= PLAN["hard_teacher_threshold"]).astype(float)
        targets = np.r_[targets, used]
        weights = np.r_[weights, np.full(len(used), cfg.extra_weight * len(y) / len(used))]
    return targets, weights


def check_loss():
    y = np.array([0., 1., 0.])
    teacher = np.array([.12, .83, .23])
    extra = np.array([.28, .77, .53, .29])
    z = np.array([.3, .6, -.9, 1., -.4, -.6, .3])
    term = lambda score, target: np.logaddexp(0, score) - target * score
    cfg = Recipe("unit", "small", "D", .9, .25, 4)
    q, w = labels(cfg, y, teacher, extra)
    core = .1*term(z[:3], y).mean() + .9*term(z[:3], teacher).mean()
    expected = core + .25*term(z[3:], extra).mean()
    np.testing.assert_allclose((term(z, q)*w).sum()/len(y), expected, atol=1e-14, rtol=0)
    q_hard, w_hard = labels(Recipe("unit","small","C",.9,.25,4), y, teacher, extra)
    np.testing.assert_array_equal(q[:len(y)], q_hard[:len(y)])
    np.testing.assert_array_equal(w, w_hard)
    np.testing.assert_array_equal(q_hard[len(y):], [0,1,1,0])
    # Check fractional BCE equals paired 0/1 weighted rows, including the gradient.
    np.testing.assert_allclose(term(z, q), q*term(z,1)+(1-q)*term(z,0), atol=1e-14)
    np.testing.assert_allclose(expit(z)-q, q*(expit(z)-1)+(1-q)*expit(z), atol=1e-14)


def representation(family):
    if family in TREES:
        return "e2"
    return "bytes" if family == "byte_cnn" else "tfidf"


def matrices(kind, rows, max_extra):
    if kind == "e2":
        return rows["e2_fit"], rows["e2_held"], rows["e2_extra"][:max_extra], None
    fit, held, extra = rows["fitting"].text, rows["held"].text, rows["extra"].text[:max_extra]
    if kind == "bytes":
        return encode_bytes(fit), encode_bytes(held), encode_bytes(extra), None
    opts = {**PLAN["tfidf"], "ngram_range": tuple(PLAN["tfidf"]["ngram_range"])}
    vectorizer = TfidfVectorizer(**opts)
    X = vectorizer.fit_transform(fit)
    E = vectorizer.transform(extra) if max_extra else None
    return X, vectorizer.transform(held), E, vectorizer


def fit_once(cfg, seed, rows, features):
    x, _, extra, _ = features
    if cfg.extra_rows:
        joined = (np.concatenate((x, extra[:cfg.extra_rows])) if isinstance(x, np.ndarray)
                  else vstack((x, extra[:cfg.extra_rows]), format="csr"))
    else:
        joined = x
    q, weights = labels(cfg, rows["fitting"].target.to_numpy(float),
                        rows["core_scores"], rows["extra_scores"])
    if cfg.family in TREES:
        fit = fit_tree
    elif cfg.family in SPARSE:
        fit = fit_sparse
    else:
        fit = fit_neural
    return fit(cfg.family, cfg.profile, joined, q, weights, seed)


def screen_grid():
    return [recipe(family, profile, mode, PLAN["screen"])
            for family, profiles in FAMILIES.items() for profile in profiles for mode in "ABCD"]


def suite(stage):
    if stage == "screen":
        return screen_grid(), [PLAN["screen_seed"]]
    lock = json.loads((OUT / (stage + "_lock.json")).read_text(encoding="utf8"))
    if lock["benchmark_fingerprint"] != fingerprint():
        raise ValueError("Stage lock refers to a different benchmark")
    return [Recipe(**value) for value in lock["recipes"]], lock["seeds"]


def fingerprint():
    files = [PLAN_PATH, DATA_CACHE / "preparation.json"]
    files.extend(ROOT / "scripts" / (name + ".py") for name in MODULES)
    return hashlib.sha256("".join(sha256(path) for path in files).encode()).hexdigest()


def destination(stage, cfg, seed, fold):
    return DATA_CACHE / "runs" / stage / f"{cfg.tag}_s{seed}_f{fold}.npz"


def checkpoint(path, score, payload, signature):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".partial")
    with temp.open("wb") as file:
        np.savez_compressed(file, score=score, payload=json.dumps(payload), signature=signature)
    temp.replace(path)


def read_run(path, signature):
    with np.load(path, allow_pickle=False) as file:
        if file["signature"].item() != signature:
            raise ValueError("Checkpoint was generated with another runner/config: " + str(path))
        return file["score"], json.loads(file["payload"].item())


def run(stage, families=None):
    check_loss()
    verify_preparation()
    signature = fingerprint()
    configs, seeds = suite(stage)
    if families:
        unknown = set(families) - set(FAMILIES)
        if unknown:
            raise ValueError("Unknown families: " + str(unknown))
        configs = [cfg for cfg in configs if cfg.family in families]
    if not configs:
        return
    for fold in PLAN["folds"]:
        rows = joblib.load(DATA_CACHE / f"fold{fold}.joblib")
        for kind in ("e2", "tfidf", "bytes"):
            sub = [cfg for cfg in configs if representation(cfg.family) == kind]
            if not sub:
                continue
            features = matrices(kind, rows, max(c.extra_rows for c in sub))
            for cfg in sub:
                for seed in seeds:
                    save = destination(stage, cfg, seed, fold)
                    if save.exists():
                        read_run(save, signature)
                        continue
                    start = perf_counter()
                    model = fit_once(cfg, seed, rows, features)
                    seconds = perf_counter() - start
                    score = np.asarray(model.score(features[1]), dtype=float)
                    if score.shape != (len(rows["held"]),) or not np.isfinite(score).all():
                        raise ValueError("Invalid scores: " + cfg.tag)
                    ap = float(average_precision_score(rows["held"].target, score))
                    payload = dict(**asdict(cfg), stage=stage, seed=seed, fold=fold, ap=ap,
                                   representation=kind, fit_seconds=seconds)
                    checkpoint(save, score, payload, signature)
                    print(f"{stage} fold{fold} seed{seed} {cfg.tag}: AP={ap:.6f} ({seconds:.2f}s)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="screen", choices=("screen","sweep","confirm","final"))
    parser.add_argument("--families", nargs="+")
    options = parser.parse_args()
    with threadpool_limits(limits=1):
        run(options.stage, options.families)
