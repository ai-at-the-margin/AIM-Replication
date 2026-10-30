"""Returns, descriptors and standardisation on synthetic inputs (BUILD_BRIEF §7.3)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from aimargin.factors.descriptors import beta_and_hsigma, ewma_weights, simple_momentum
from aimargin.factors.returns import sanity_filter, total_returns
from aimargin.factors.standardise import composite, orthogonalise, standardise
from aimargin.wrds_io.prices import dedupe


def _prices():
    dates = pd.bdate_range("2026-01-01", periods=4)
    return pd.DataFrame({
        "gvkey": "000001", "iid": "01", "date": dates, "price": [100.0, 110.0, 55.0, 60.5],
        "adj": [1.0, 1.0, 0.5, 0.5], "trfd": [1.0, 1.0, 1.0, 1.01], "shares": 1e6, "currency": "EUR",
        "exchg": "121", "tpci": "0",
    })


def test_total_return_formula_with_split_and_fx():
    prices = _prices()
    fx = pd.DataFrame({"EUR": [1.10, 1.10, 1.21, 1.21], "USD": 1.0}, index=prices["date"])
    out = total_returns(prices, fx)
    r = out["ret_local"].tolist()
    assert np.isnan(r[0])
    assert abs(r[1] - 0.10) < 1e-12
    assert abs(r[2] - 0.0) < 1e-12          # 2:1 split: adjusted price unchanged
    assert abs(r[3] - (60.5 / 0.5 * 1.01 / (55.0 / 0.5 * 1.0) - 1)) < 1e-12
    usd = out["ret_usd"].tolist()
    assert abs(usd[2] - (1.0 * 1.21 / 1.10 - 1)) < 1e-12


def test_sanity_filter_drops_spike_and_reversal():
    prices = _prices()
    prices.loc[2, ["price", "adj"]] = [1100.0, 1.0]   # bad print, reverses next day
    prices.loc[3, ["adj"]] = [1.0]
    prices.loc[3, "price"] = 112.0
    fx = pd.DataFrame({"EUR": 1.0, "USD": 1.0}, index=prices["date"])
    clean, flagged = sanity_filter(total_returns(prices, fx))
    assert flagged["action"].tolist() == ["dropped_reversal"]
    assert clean["ret_local"].isna().sum() == 3


def test_dedupe_prefers_complete_rows():
    prices = pd.concat([_prices(), _prices().assign(trfd=np.nan)], ignore_index=True)
    clean, removed = dedupe(prices)
    assert removed == 4 and clean["trfd"].notna().all()


def test_ewma_weights_halve_every_half_life():
    w = ewma_weights(253, 126)
    assert abs(w.sum() - 1) < 1e-12
    assert abs(w[-1] / w[-127] - 2.0) < 1e-9


def test_beta_regression_recovers_known_beta():
    rng = np.random.default_rng(0)
    n = 400
    mkt = pd.Series(rng.normal(0, 0.01, n))
    betas = np.array([0.5, 1.0, 1.5])
    excess = pd.DataFrame(np.outer(mkt.to_numpy(), betas) + rng.normal(0, 0.002, (n, 3)), columns=["a", "b", "c"])
    beta, hsigma = beta_and_hsigma(excess, mkt, n - 1, 252, 63, 63, 0.5)
    assert np.allclose(beta.to_numpy(), betas, atol=0.05)
    assert (hsigma > 0).all()


def test_simple_momentum_and_missing_data():
    returns = pd.DataFrame({"x": [0.01] * 300, "y": [np.nan] * 300})
    mom = simple_momentum(returns, 299, 252, 21, 0.5)
    assert abs(mom["x"] - (1.01 ** 231 - 1)) < 1e-9
    assert np.isnan(mom["y"])


def test_standardise_gives_zero_cap_weighted_mean_and_keeps_missing():
    rng = np.random.default_rng(1)
    values = pd.Series(rng.normal(0, 1, 200))
    values.iloc[5] = np.nan
    cap = pd.Series(rng.lognormal(0, 1, 200))
    universe = pd.Series(True, index=values.index)
    z = standardise(values, cap, universe)
    ok = z.notna()
    weighted = float((z[ok] * cap[ok]).sum() / cap[ok].sum())
    assert abs(weighted) < 1e-10
    assert np.isnan(z.iloc[5])


def test_composite_reweights_available_parts_and_orthogonalise():
    parts = pd.DataFrame({"a": [1.0, np.nan, 2.0], "b": [3.0, 4.0, np.nan]})
    out = composite(parts)
    assert out.tolist() == [2.0, 4.0, 2.0]
    rng = np.random.default_rng(2)
    x = pd.DataFrame({"size": rng.normal(0, 1, 100)})
    y = 2 * x["size"] + rng.normal(0, 0.1, 100)
    resid = orthogonalise(y, x, pd.Series(True, index=y.index))
    assert abs(np.corrcoef(resid, x["size"])[0, 1]) < 1e-6
