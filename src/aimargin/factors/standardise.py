"""Winsorise, standardise (cap-weighted mean, equal-weighted sd), composite (BUILD_BRIEF §7.1).

    z_i = (d_i - Σ_{j∈U} w_cap_j d_j) / sqrt( (1/N) Σ_{j∈U} (d_j - d̄)^2 )

so the cap-weighted universe exposure is zero and loadings are in standard
deviations. Stocks outside the estimation universe are scored with the
universe's statistics. Missing stays missing: never zero-filled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def winsorise(values: pd.Series, universe: pd.Series, lo: float, hi: float) -> pd.Series:
    base = values[universe & values.notna()]
    if len(base) < 5:
        return values
    low = base.quantile(lo)
    high = base.quantile(hi)
    return values.clip(lower=low, upper=high)


def standardise(values: pd.Series, cap: pd.Series, universe: pd.Series, lo: float = 0.01,
                hi: float = 0.99) -> pd.Series:
    clipped = winsorise(values, universe, lo, hi)
    mask = universe & clipped.notna() & cap.notna() & (cap > 0)
    if mask.sum() < 3:
        return pd.Series(np.nan, index=values.index)
    base = clipped[mask]
    weights = cap[mask] / cap[mask].sum()
    mean_cap = float((base * weights).sum())
    sd = float(np.sqrt(((base - base.mean()) ** 2).mean()))
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=values.index)
    return (clipped - mean_cap) / sd


def composite(parts: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    """Weighted average over whichever parts are available (weights re-normalised per row)."""
    columns = list(parts.columns)
    if weights is None:
        weights = {}
        for i in range(len(columns)):
            weights[columns[i]] = 1.0
    w = pd.Series(weights).reindex(columns).fillna(0.0)
    values = parts[columns]
    present = values.notna()
    num = (values.fillna(0.0) * w).sum(axis=1)
    den = (present * w).sum(axis=1)
    return (num / den.replace(0.0, np.nan)).where(den > 0)


def orthogonalise(y: pd.Series, regressors: pd.DataFrame, universe: pd.Series) -> pd.Series:
    """Residual of y on the regressors (OLS fitted on the universe, applied to everyone)."""
    data = pd.concat([y.rename("_y"), regressors], axis=1)
    fit = data[universe & data.notna().all(axis=1)]
    if len(fit) < regressors.shape[1] + 5:
        return y
    X = np.column_stack([np.ones(len(fit)), fit[regressors.columns].to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(X, fit["_y"].to_numpy(dtype=float), rcond=None)
    full = regressors.fillna(regressors[universe].mean())
    Xall = np.column_stack([np.ones(len(full)), full.to_numpy(dtype=float)])
    fitted = pd.Series(Xall @ coef, index=y.index)
    return y - fitted
