"""Two fixed-budget CPU Student families for the Bronze KD benchmark.

The same weighted binary cross-entropy handles either hard labels or fractional
Teacher targets. This module only consumes fitting arrays and makes predictions.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import sparse
from scipy.special import expit
from threadpoolctl import threadpool_limits


FAMILIES = {
    "byte_cnn": ("small", "large"),
    "sparse_mlp": ("small", "large"),
}
PROFILES = {
    "byte_cnn": {
        "small": {"embedding_dim": 6, "channels": 16, "kernel_size": 5, "max_bytes": 128},
        "large": {"embedding_dim": 8, "channels": 24, "kernel_size": 5, "max_bytes": 128},
    },
    "sparse_mlp": {
        "small": {"hidden_units": 32},
        "large": {"hidden_units": 64},
    },
}
TRAINING = {
    "steps": 384,
    "batch_size": 128,
    "learning_rate": 0.003,
    "optimizer": "Adam",
    "dropout": 0.0,
}


def _normal_weights(rng, shape, fan_in):
    return (rng.standard_normal(shape, dtype=np.float32) * np.sqrt(2.0 / fan_in)).astype(
        np.float32
    )


class _Student:
    @property
    def parameter_bytes(self):
        return sum(value.nbytes for value in self.parameters.values())

    def score(self, X):
        result = self._prediction_input(X)
        with threadpool_limits(limits=1, user_api="blas"):
            return np.concatenate(
                [expit(self._forward(result[start : start + 128])[0])
                 for start in range(0, len_rows(result), 128)]
            ) if len_rows(result) else np.empty(0, dtype=np.float32)


def len_rows(X):
    return X.shape[0]


class _SparseMLP(_Student):
    def __init__(self, rng, input_features, hidden_units):
        self.input_features = input_features
        self.parameters = {
            "first_weight": _normal_weights(rng, (input_features, hidden_units), input_features),
            "first_bias": np.zeros(hidden_units, dtype=np.float32),
            "output_weight": _normal_weights(rng, (hidden_units,), hidden_units),
            "output_bias": np.zeros(1, dtype=np.float32),
        }

    def _prediction_input(self, X):
        if not sparse.issparse(X) or X.ndim != 2 or X.shape[1] != self.input_features:
            raise ValueError("Expected a sparse TF-IDF matrix with the fitted feature count.")
        matrix = sparse.csr_matrix(X, dtype=np.float32)
        if not np.isfinite(matrix.data).all():
            raise ValueError("Sparse TF-IDF values must be finite.")
        return matrix

    def _forward(self, X):
        par = self.parameters
        hidden = np.maximum(X @ par["first_weight"] + par["first_bias"], 0)
        logits = hidden @ par["output_weight"] + par["output_bias"]
        return logits, hidden

    def gradient(self, X, target, weight):
        logits, hidden = self._forward(X)
        output_grad = _weighted_logit_gradient(logits, target, weight)
        hidden_grad = output_grad[:, None] * self.parameters["output_weight"]
        hidden_grad *= hidden > 0
        return {
            "first_weight": X.T @ hidden_grad,
            "first_bias": hidden_grad.sum(axis=0),
            "output_weight": hidden.T @ output_grad,
            "output_bias": np.array([output_grad.sum()], dtype=np.float32),
        }


class _ByteCNN(_Student):
    def __init__(self, rng, embedding_dim, channels, kernel_size, max_bytes):
        self.embedding_dim = embedding_dim
        self.channels = channels
        self.kernel_size = kernel_size
        self.max_bytes = max_bytes
        kernel_inputs = kernel_size * embedding_dim
        self.parameters = {
            "embedding": _normal_weights(rng, (257, embedding_dim), embedding_dim),
            "kernel": _normal_weights(rng, (kernel_inputs, channels), kernel_inputs),
            "conv_bias": np.zeros(channels, dtype=np.float32),
            "output_weight": _normal_weights(rng, (channels,), channels),
            "output_bias": np.zeros(1, dtype=np.float32),
        }
        self.parameters["embedding"][0] = 0

    def _prediction_input(self, X):
        tokens = np.asarray(X)
        if (tokens.ndim != 2 or not np.issubdtype(tokens.dtype, np.integer)
                or tokens.shape[1] == 0 or np.any((tokens < 0) | (tokens > 256))):
            raise ValueError("Expected 0 padding or 1..256 byte tokens in a matrix.")
        tokens = tokens[:, : self.max_bytes]
        if np.any((tokens[:, :-1] == 0) & (tokens[:, 1:] != 0)):
            raise ValueError("Byte tokens must use right padding.")
        return tokens

    def _forward(self, X):
        par = self.parameters
        # Omit the common all-padding suffix. Pad the end so that even very
        # short URL inputs still have a convolution window.
        used = max(1, int(np.count_nonzero(X, axis=1).max()))
        padded = np.pad(X[:, :used], ((0, 0), (0, self.kernel_size - 1)))
        windows = sliding_window_view(padded, self.kernel_size, axis=1)
        embedded = par["embedding"][windows].reshape(len(X), used, -1)
        conv = embedded @ par["kernel"] + par["conv_bias"]
        conv[windows[:, :, 0] == 0] = -np.inf
        winners = conv.argmax(axis=1)
        row = np.arange(len(X))[:, None]
        channel = np.arange(self.channels)
        hidden = np.maximum(conv[row, winners, channel], 0)
        logits = hidden @ par["output_weight"] + par["output_bias"]
        return logits, hidden, windows[row, winners]

    def gradient(self, X, target, weight):
        logits, hidden, winning_tokens = self._forward(X)
        par = self.parameters
        output_grad = _weighted_logit_gradient(logits, target, weight)
        winner_grad = output_grad[:, None] * par["output_weight"] * (hidden > 0)

        # Global max pooling sends a gradient only to the winning position of
        # each filter. Its token sequence supplies the shared filter gradient.
        winning_embeddings = par["embedding"][winning_tokens].reshape(len(X), self.channels, -1)
        kernel_grad = np.einsum("bci,bc->ic", winning_embeddings, winner_grad)
        token_grad = winner_grad[:, :, None, None] * par["kernel"].T.reshape(
            self.channels, self.kernel_size, self.embedding_dim
        )
        embedding_grad = np.zeros_like(par["embedding"])
        np.add.at(embedding_grad, winning_tokens, token_grad)
        embedding_grad[0] = 0
        return {
            "embedding": embedding_grad,
            "kernel": kernel_grad,
            "conv_bias": winner_grad.sum(axis=0),
            "output_weight": hidden.T @ output_grad,
            "output_bias": np.array([output_grad.sum()], dtype=np.float32),
        }


def _weighted_logit_gradient(logits, target, normalized_weight):
    # d BCE(logit, q) / d logit = sigmoid(logit) - q. The weight scale
    # comes from the full fitting set and each batch is the same length.
    return (expit(logits) - target) * normalized_weight / len(target)


def _batches(rng, rows, batch_size, steps):
    """Cycle shuffled fitting rows and carry leftovers across permutations."""
    order = np.empty(0, dtype=np.int64)
    for _ in range(steps):
        while len(order) < batch_size:
            order = np.concatenate([order, rng.permutation(rows)])
        indices, order = order[:batch_size], order[batch_size:]
        yield indices


def fit_neural(family, profile, X, q, weights, seed):
    """Fit a named Student with an equal update budget across target modes.

    X is right-padded UTF-8 tokens for byte_cnn and CSR TF-IDF for sparse_mlp.
    q contains binary or fractional targets and weights are fitting-row weights.
    No validation rows, model selection, dropout, or early stopping are used.
    """
    capacity = PROFILES[family][profile]
    rng = np.random.default_rng(seed)
    if family == "byte_cnn":
        model = _ByteCNN(rng, **capacity)
    else:
        model = _SparseMLP(rng, X.shape[1], **capacity)
    X = model._prediction_input(X)
    targets = np.asarray(q, dtype=np.float32)
    sample_weights = np.asarray(weights, dtype=np.float32)
    if targets.shape != (len_rows(X),) or sample_weights.shape != targets.shape:
        raise ValueError("Targets and weights must contain one value per fitting row.")
    if (not len(targets) or not np.isfinite(targets).all()
            or np.any((targets < 0) | (targets > 1))):
        raise ValueError("Expected finite targets in [0, 1].")
    if (not np.isfinite(sample_weights).all() or np.any(sample_weights < 0)
            or not np.any(sample_weights > 0)):
        raise ValueError("Expected finite nonnegative weights with positive total weight.")
    sample_weights = sample_weights / sample_weights.mean(dtype=np.float64)
    sample_weights = sample_weights.astype(np.float32)
    first_moment = {name: np.zeros_like(value) for name, value in model.parameters.items()}
    second_moment = {name: np.zeros_like(value) for name, value in model.parameters.items()}
    batches = _batches(rng, len(targets), TRAINING["batch_size"], TRAINING["steps"])
    with threadpool_limits(limits=1, user_api="blas"):
        for step, idx in enumerate(batches, start=1):
            gradients = model.gradient(X[idx], targets[idx], sample_weights[idx])
            step_size = TRAINING["learning_rate"] * np.sqrt(1 - 0.999**step) / (1 - 0.9**step)
            eps = 1e-8 * np.sqrt(1 - 0.999**step)
            for name, value in model.parameters.items():
                gradient = gradients[name]
                first_moment[name] *= 0.9
                first_moment[name] += 0.1 * gradient
                second_moment[name] *= 0.999
                second_moment[name] += 0.001 * gradient**2
                value -= step_size * first_moment[name] / (np.sqrt(second_moment[name]) + eps)
    if any(not np.isfinite(value).all() for value in model.parameters.values()):
        raise RuntimeError("Non-finite Student parameters after fixed budget.")
    return model
