"""Bootstrap confidence intervals and permutation tests (BUILD_BRIEF §8).

Repetitions are resampled within cells. Everything is vectorised with numpy so
2,000 draws stay fast.
"""

from __future__ import annotations

import numpy as np


def mean_ci(values: np.ndarray, draws: int, rng: np.random.Generator, alpha: float = 0.05) -> dict[str, float | None]:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n == 0:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    if n == 1:
        return {"mean": float(clean[0]), "lo": None, "hi": None, "n": 1}
    idx = rng.integers(0, n, size=(draws, n))
    means = clean[idx].mean(axis=1)
    return {"mean": float(clean.mean()), "lo": float(np.quantile(means, alpha / 2)),
            "hi": float(np.quantile(means, 1 - alpha / 2)), "n": int(n)}


def diff_ci(a: np.ndarray, b: np.ndarray, draws: int, rng: np.random.Generator,
            alpha: float = 0.05) -> dict[str, float | None]:
    """mean(a) - mean(b), resampling each cell independently."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0:
        return {"diff": None, "lo": None, "hi": None, "n_a": len(a), "n_b": len(b)}
    da = a[rng.integers(0, len(a), size=(draws, len(a)))].mean(axis=1)
    db = b[rng.integers(0, len(b), size=(draws, len(b)))].mean(axis=1)
    diffs = da - db
    return {"diff": float(a.mean() - b.mean()), "lo": float(np.quantile(diffs, alpha / 2)),
            "hi": float(np.quantile(diffs, 1 - alpha / 2)), "n_a": int(len(a)), "n_b": int(len(b))}


def permutation_p(a: np.ndarray, b: np.ndarray, draws: int, rng: np.random.Generator) -> float | None:
    """Two-sided permutation test for a difference in means."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return None
    pooled = np.concatenate([a, b])
    observed = abs(a.mean() - b.mean())
    n_a = len(a)
    count = 0
    for _i in range(draws):
        perm = rng.permutation(pooled)
        if abs(perm[:n_a].mean() - perm[n_a:].mean()) >= observed - 1e-12:
            count += 1
    return (count + 1) / (draws + 1)


def resample_counts(n: int, draws: int, rng: np.random.Generator) -> np.ndarray:
    """draws x n matrix of multinomial counts (a bootstrap resample of n items)."""
    if n == 0:
        return np.zeros((draws, 0))
    return rng.multinomial(n, np.full(n, 1.0 / n), size=draws).astype(float)


def cross_pair_mean_draws(block: np.ndarray, counts_a: np.ndarray, counts_b: np.ndarray) -> np.ndarray:
    """Mean of J over (i in A*, j in B*) for each bootstrap draw."""
    na = counts_a.sum(axis=1)
    nb = counts_b.sum(axis=1)
    totals = np.einsum("di,ij,dj->d", counts_a, block, counts_b)
    return totals / (na * nb)


def within_pair_mean_draws(block: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Mean of J over distinct pairs within a resampled cell (duplicate reps excluded)."""
    zero_diag = block.copy()
    np.fill_diagonal(zero_diag, 0.0)
    totals = np.einsum("di,ij,dj->d", counts, zero_diag, counts)
    n = counts.sum(axis=1)
    pairs = n * n - (counts * counts).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return totals / pairs
