"""Four small Student families on a frozen, nonnegative TF-IDF matrix.

fit_sparse() consumes one positive-class target and one loss weight per row.
score() returns one *uncalibrated* score in [0, 1] per row.  Training is local;
each exported scorer contains every fitted parameter after the TF-IDF stage.
Run this file directly to check soft-label equivalence and the FM gradient.
"""
from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.optimize import minimize
from scipy.special import expit, logit
from threadpoolctl import threadpool_limits


FAMILIES = {family: ("small", "large") for family in
            ("tfidf_lr", "multinomial_nb", "factorization_machine", "rbf_random_features")}
# L2 is relative to mean loss; NB smooths normalized feature-mass counts.
CONFIG = {
    "tfidf_lr": {"small": {"l2": 1e-4}, "large": {"l2": 1.25e-5}},
    "multinomial_nb": {"small": {"alpha": 1e-4}, "large": {"alpha": 1e-5}},
    "factorization_machine": {"small": {"rank": 4}, "large": {"rank": 12}},
    "rbf_random_features": {"small": {"components": 96}, "large": {"components": 256}},
}
FM_STEPS = 160
FM_BATCH = 384
FM_L2 = 1e-4
FM_RATE = 0.025
RBF_GAMMA = 1.0
RBF_L2 = 1e-4


def _inputs(X, q, weights):
    X = sparse.csr_matrix(X, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if X.shape[0] == 0 or X.shape[1] == 0 or q.shape != (X.shape[0],) or weights.shape != q.shape:
        raise ValueError("Expected a nonempty matrix and one target and weight per row")
    if (not np.isfinite(X.data).all() or (X.data < 0).any() or
            not np.isfinite(q).all() or ((q < 0) | (q > 1)).any() or
            not np.isfinite(weights).all() or (weights < 0).any() or
            not np.isfinite(weights.sum()) or weights.sum() <= 0):
        raise ValueError("Require finite nonnegative TF-IDF, probability targets, and positive total weight")
    return X, q, weights / weights.sum()


def _initial_bias(q, weights):
    return float(logit(np.clip(weights @ q, 1e-6, 1 - 1e-6)))


@dataclass
class LinearScore:
    coefficient: np.ndarray
    intercept: float

    def score(self, X):
        return expit(X @ self.coefficient + self.intercept)


def _linear_objective(parameters, X, q, weights, l2):
    coefficient, intercept = parameters[:-1], parameters[-1]
    z = X @ coefficient + intercept
    loss = weights @ (np.logaddexp(0., z) - q * z) + .5 * l2 * (coefficient @ coefficient)
    residual = weights * (expit(z) - q)
    return loss, np.r_[X.T @ residual + l2 * coefficient, residual.sum()]


def _fit_linear(X, q, weights, l2):
    initial = np.r_[np.zeros(X.shape[1]), _initial_bias(q, weights)]
    result = minimize(_linear_objective, initial, args=(X, q, weights, l2), jac=True,
                      method="L-BFGS-B", options={"maxiter": 600, "ftol": 1e-11, "gtol": 1e-7})
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError("Logistic optimization failed: " + str(result.message))
    return LinearScore(result.x[:-1], float(result.x[-1]))


def _fit_nb(X, q, weights, alpha):
    # A soft row is exactly q positive mass and (1-q) negative mass.
    # Normalize each smoothed class-term vector to a multinomial distribution.
    positive = weights * q
    negative = weights * (1 - q)
    log_terms = []
    for class_mass in (negative, positive):
        counts = np.asarray(X.T @ class_mass).ravel() + alpha
        log_terms.append(np.log(counts / counts.sum()))
    prior = (positive.sum() + alpha) / (negative.sum() + alpha)
    return LinearScore(log_terms[1] - log_terms[0], float(np.log(prior)))


@dataclass
class FactorizationScore:
    linear: np.ndarray
    factors: np.ndarray
    intercept: float

    def score(self, X):
        squared = X.multiply(X)
        z, _ = _fm_logits(X, squared, self.linear, self.factors, self.intercept)
        return expit(z)


def _fm_logits(X, squared, linear, factors, intercept):
    # sum over i < j of x_i*x_j*dot(v_i,v_j) without constructing any pairs
    projected = X @ factors
    diagonal = squared @ (factors * factors).sum(axis=1)
    interaction = .5 * ((projected * projected).sum(axis=1) - diagonal)
    return X @ linear + intercept + interaction, projected


def _fm_loss_grad(X, squared, q, weights, linear, factors, intercept, l2):
    z, projected = _fm_logits(X, squared, linear, factors, intercept)
    residual = weights * (expit(z) - q)
    factor_grad = X.T @ (projected * residual[:, None]) - (squared.T @ residual)[:, None] * factors
    loss = weights @ (np.logaddexp(0., z) - q*z) + .5*l2*((linear**2).sum() + (factors**2).sum())
    return loss, (X.T @ residual + l2*linear, factor_grad + l2*factors, np.array([residual.sum()]))


def _fit_fm(X, q, weights, rank, seed):
    rng = np.random.default_rng(seed)
    X = X.astype(np.float32, copy=False)
    squared = X.multiply(X).tocsr()
    linear = np.zeros(X.shape[1], dtype=np.float32)
    factors = rng.normal(0, .03, (X.shape[1], rank)).astype(np.float32)
    intercept = np.array([_initial_bias(q, weights)], dtype=np.float32)
    q = q.astype(np.float32)
    parameters = (linear, factors, intercept)
    first = [np.zeros_like(p) for p in parameters]
    second = [np.zeros_like(p) for p in parameters]
    mean_weight = np.full(FM_BATCH, 1/FM_BATCH, dtype=np.float32)
    for step in range(1, FM_STEPS + 1):
        # Rows are drawn in proportion to their objective mass, so a plain
        # batch mean estimates the desired weighted gradient for every recipe.
        batch = rng.choice(X.shape[0], size=FM_BATCH, replace=True, p=weights)
        _, gradients = _fm_loss_grad(X[batch], squared[batch], q[batch], mean_weight,
                                     linear, factors, intercept[0], FM_L2)
        rate = FM_RATE * np.sqrt(1-.999**step)/(1-.9**step)
        for p, g, m, v in zip(parameters, gradients, first, second):
            m *= .9
            m += .1*g
            v *= .999
            v += .001*(g*g)
            p -= rate * m / (np.sqrt(v) + 1e-8)
    if not all(np.isfinite(p).all() for p in parameters):
        raise ValueError("Nonfinite FM parameters")
    return FactorizationScore(linear, factors, float(intercept[0]))


@dataclass
class RbfScore:
    frequencies: np.ndarray
    phases: np.ndarray
    head: LinearScore

    def score(self, X):
        return self.head.score(_fourier_features(X, self.frequencies, self.phases))


def _fourier_features(X, frequencies, phases):
    # CSR @ frequencies avoids allocating a dense n-rows by n-terms matrix.
    values = X.astype(np.float32, copy=False) @ frequencies
    values += phases
    np.cos(values, out=values)
    values *= np.sqrt(2./len(phases))
    return values


def _fit_rbf(X, q, weights, components, seed):
    rng = np.random.default_rng(seed)
    frequencies = rng.normal(0, np.sqrt(2*RBF_GAMMA), (X.shape[1], components)).astype(np.float32)
    phases = rng.uniform(0, 2*np.pi, components).astype(np.float32)
    features = _fourier_features(X, frequencies, phases).astype(np.float64)
    head = _fit_linear(features, q, weights, RBF_L2)
    return RbfScore(frequencies, phases, head)


def fit_sparse(family, profile, X, q, weights, seed):
    """Fit a Student using q as positive-class probability, preserving row-mass ratios."""
    if family not in CONFIG or profile not in CONFIG[family]:
        raise ValueError(f"Unknown Student family/profile: {family} / {profile}")
    X, q, weights = _inputs(X, q, weights)
    config = CONFIG[family][profile]
    with threadpool_limits(limits=1):
        if family == "tfidf_lr":
            return _fit_linear(X, q, weights, config["l2"])
        if family == "multinomial_nb":
            return _fit_nb(X, q, weights, config["alpha"])
        if family == "factorization_machine":
            return _fit_fm(X, q, weights, config["rank"], seed)
        return _fit_rbf(X, q, weights, config["components"], seed)


def self_test():
    import pickle
    from scipy.optimize._numdiff import approx_derivative

    X = sparse.csr_matrix([[0., 1., .3], [.65, .2, 0], [1., 0, .8], [.2, .3, .5]])
    q = np.array([.91, .37, .12, .79])
    weights = np.array([.1, .4, .3, .2])
    expanded = sparse.vstack([X, X], format="csr")
    hard = np.repeat([1., 0.], len(q))
    masses = np.r_[weights*q, weights*(1-q)]
    linear = np.array([.3, -.1, .4])
    factors = np.array([[.1, .2], [.3, -.12], [.05, -.2]])
    bias = -.17
    square = X.multiply(X)
    # Direct pair expansion validates the fast FM identity.
    expected = X @ linear + bias
    for i in range(X.shape[1]):
        for j in range(i+1, X.shape[1]):
            expected += X[:, i].multiply(X[:, j]).toarray().ravel() * (factors[i] @ factors[j])
    np.testing.assert_allclose(_fm_logits(X, square, linear, factors, bias)[0], expected)
    p = np.r_[linear, factors.ravel(), bias]
    def unpack(p):
        loss, grads = _fm_loss_grad(X, square, q, weights, p[:3], p[3:-1].reshape(3, 2), p[-1], FM_L2)
        return loss, np.concatenate([g.ravel() for g in grads])
    numeric = approx_derivative(lambda p: unpack(p)[0], p)
    np.testing.assert_allclose(unpack(p)[1], numeric.ravel(), rtol=1e-6, atol=1e-8)
    expanded_loss, expanded_grad = _fm_loss_grad(expanded, expanded.multiply(expanded), hard, masses,
                                                 linear, factors, bias, FM_L2)
    np.testing.assert_allclose(unpack(p)[0], expanded_loss)
    np.testing.assert_allclose(unpack(p)[1], np.concatenate([g.ravel() for g in expanded_grad]))
    for family in FAMILIES:
        for profile in FAMILIES[family]:
            model = fit_sparse(family, profile, X, q, weights, 42)
            scores = model.score(X)
            if not (np.isfinite(scores).all() and scores.shape == (4,) and ((scores >= 0) & (scores <= 1)).all()):
                raise AssertionError("Invalid scores: " + family)
            np.testing.assert_array_equal(scores, pickle.loads(pickle.dumps(model)).score(X))
            if family != "factorization_machine":
                paired = fit_sparse(family, profile, expanded, hard, masses, 42)
                np.testing.assert_allclose(scores, paired.score(X), rtol=0, atol=2e-6)
    print("PASS: 4 families x 2 profiles, scalar scores, pickle parity, soft row expansion, FM identity/gradient")


if __name__ == "__main__":
    self_test()

