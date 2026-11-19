"""Weighted binary Students on the frozen E2 matrix.

Each fit gets one target in [0, 1] and one weight per URL. Boosters with a
native fractional binary-cross-entropy objective consume those arrays directly.
Other classifiers see weighted copies of the two labels for each URL.

Run this file directly to check the seven families on a known soft-label case.
"""
from dataclasses import dataclass

import numpy as np
from scipy.special import expit
from threadpoolctl import threadpool_limits


FAMILIES = dict.fromkeys(
    ("lightgbm", "xgboost", "catboost", "histgb", "rf", "extratrees", "cart"),
    ("small", "large"),
)
# Boosting compares 48 shallow trees against 120 deeper trees. For bagged-style
# ensembles use 32 versus 72 randomized trees. CART fits a single tree.
CAPACITY = {
    "small": dict(rounds=48, leaves=8, depth=3, forest_trees=32, forest_depth=5),
    "large": dict(rounds=120, leaves=16, depth=4, forest_trees=72, forest_depth=9),
}


@dataclass
class TreeStudent:
    family: str
    model: object

    def score(self, X):
        """Return one class-1 score per row; no Teacher is used at inference."""
        X = np.asarray(X, dtype=np.float64)
        if self.family == "constant":
            return np.full(len(X), self.model, dtype=float)
        if self.family == "lightgbm":
            return self.model.booster_.predict(X, num_threads=1)
        if self.family == "xgboost":
            return self.model.predict(X).astype(float)
        if self.family == "catboost":
            logits = self.model.predict(X, prediction_type="RawFormulaVal", thread_count=1)
            return expit(logits)
        if self.family == "histgb":
            with threadpool_limits(limits=1, user_api="openmp"):
                return self.model.predict_proba(X)[:, 1]
        return self.model.predict_proba(X)[:, 1]


def _paired_labels(X, targets, weights):
    """Two hard labels give BCE(q,p) = (1-q)*BCE(0,p) + q*BCE(1,p).

    Retain both copies even when one has zero weight. HistGB's quantile/bin and
    count-based leaf rules then see the same input rows in paired hard/KD fits.
    Keep total sample mass unchanged.
    """
    n = len(targets)
    labels = np.repeat([0, 1], n)
    mass = np.concatenate((weights * (1 - targets), weights * targets))
    return np.concatenate((X, X)), labels, mass


def fit_tree(family, profile, X, q, weights, seed):
    """Fit a hard, soft or mixed target using exactly the supplied sample mass."""
    if family not in FAMILIES or profile not in FAMILIES[family]:
        raise ValueError(f"Unknown tree family/profile: {family}/{profile}")
    X = np.asarray(X, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if X.ndim != 2 or q.shape != (len(X),) or w.shape != q.shape:
        raise ValueError("X, q and weights must align row by row")
    if (not np.isfinite(X).all() or not np.isfinite(q).all()
            or np.any((q < 0) | (q > 1)) or not np.isfinite(w).all()
            or np.any(w < 0) or not np.any(w > 0)):
        raise ValueError("Expected finite features, targets in [0,1] and positive total weight")
    if not np.all(w > 0):
        active = w > 0
        X, q, w = X[active], q[active], w[active]
    if np.all(q == q[0]):
        return TreeStudent("constant", float(q[0]))
    cap = CAPACITY[profile]

    if family == "lightgbm":
        from lightgbm import LGBMRegressor
        model = LGBMRegressor(
            objective="cross_entropy", n_estimators=cap["rounds"], num_leaves=cap["leaves"],
            max_depth=cap["depth"], max_bin=63, learning_rate=0.08, reg_lambda=1,
            min_child_samples=15, force_col_wise=True, deterministic=True, verbosity=-1,
            random_state=seed, n_jobs=1,
        )
    elif family == "xgboost":
        from xgboost import XGBRegressor
        model = XGBRegressor(
            objective="reg:logistic", n_estimators=cap["rounds"], max_depth=cap["depth"],
            tree_method="hist", max_bin=63, learning_rate=0.08, reg_lambda=1,
            min_child_weight=3, random_state=seed, n_jobs=1, verbosity=0,
        )
    elif family == "catboost":
        from catboost import CatBoost
        model = CatBoost(dict(
            loss_function="CrossEntropy", iterations=cap["rounds"], depth=cap["depth"],
            border_count=63, learning_rate=0.08, l2_leaf_reg=1, random_seed=seed,
            bootstrap_type="No", random_strength=0, thread_count=1,
            verbose=False, allow_writing_files=False,
        ))
    else:
        X, q, w = _paired_labels(X, q, w)
        if family == "histgb":
            from sklearn.ensemble import HistGradientBoostingClassifier
            model = HistGradientBoostingClassifier(
                loss="log_loss", max_iter=cap["rounds"], max_leaf_nodes=cap["leaves"],
                max_depth=cap["depth"], max_bins=63, learning_rate=0.08,
                min_samples_leaf=30, l2_regularization=1, early_stopping=False,
                categorical_features=None, random_state=seed,
            )
        else:
            from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
            from sklearn.tree import DecisionTreeClassifier
            # An entropy split and the weighted leaf frequency minimize binary
            # log loss. A minimum *weight* fraction does not depend on whether
            # a URL has mass on one label or on both labels.
            settings = dict(criterion="entropy", max_depth=cap["forest_depth"],
                            min_weight_fraction_leaf=0.0005, random_state=seed)
            if family == "cart":
                model = DecisionTreeClassifier(**settings)
            else:
                cls = RandomForestClassifier if family == "rf" else ExtraTreesClassifier
                # Sample features at each split. Sampling pseudo rows independently
                # would change a URL's hard/soft weights within each tree.
                model = cls(**settings, n_estimators=cap["forest_trees"], max_features="sqrt",
                            bootstrap=False, n_jobs=1)

    with threadpool_limits(limits=1):
        model.fit(X, q, sample_weight=w)
    return TreeStudent(family, model)


def probe():
    """Verify fractional targets and nonuniform row weights against known optima."""
    # Each feature group has the same number of observations but unequal weights.
    # The optimal Bernoulli scores are 0.325 / 0.675, or 0.25 / 0.75 if weights
    # are accidentally ignored. Quantizing the labels to 0/1 also fails this test.
    first = np.tile([-1.0, -1.0, 1.0, 1.0], 128)
    X = np.zeros((len(first), 20))
    X[:, 0] = first
    targets = np.tile([0.1, 0.4, 0.6, 0.9], 128)
    weights = np.tile([1.0, 3.0, 3.0, 1.0], 128)
    for family, profiles in FAMILIES.items():
        for profile in profiles:
            model = fit_tree(family, profile, X, targets, weights, seed=42)
            scores = model.score(X[[0, 2]])
            np.testing.assert_allclose(scores, [0.325, 0.675], atol=0.035, rtol=0)
            hard = fit_tree(family, profile, X, (first > 0).astype(float), weights, seed=42)
            assert list(hard.score(X[[0, 2]]) >= 0.5) == [False, True]
            print(f"{family:10} {profile:5} soft={np.round(scores, 4)} hard=ok")
    print("Fractional BCE and hard-label probes passed for all 14 configurations.")


if __name__ == "__main__":
    probe()
