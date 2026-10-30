"""Daily USD total returns per (gvkey, iid) (BUILD_BRIEF §2.5, §2.4 rule 3).

r_t = [(prccd_t / ajexdi_t) * trfd_t] / [(prccd_{t-1} / ajexdi_{t-1}) * trfd_{t-1}] - 1,
converted to USD with the daily cross-rate. Missing trfd falls back to the price
return (flagged). |r| > 100% is flagged and dropped when it reverses the next day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def total_returns(prices: pd.DataFrame, fx_wide: pd.DataFrame) -> pd.DataFrame:
    """Long frame: gvkey, iid, date, currency, ret_local, ret_usd, price_only, usd_price, shares."""
    if prices is None or len(prices) == 0:
        return pd.DataFrame(columns=["gvkey", "iid", "date", "currency", "ret_local", "ret_usd", "price_only",
                                     "usd_price", "shares"])
    work = prices.sort_values(["gvkey", "iid", "date"]).reset_index(drop=True).copy()
    adj = work["adj"].where(work["adj"] > 0, 1.0).fillna(1.0)
    adj_price = work["price"] / adj
    work["price_only"] = work["trfd"].isna()
    tri = adj_price * work["trfd"].fillna(1.0)
    same = (work["gvkey"] == work["gvkey"].shift(1)) & (work["iid"] == work["iid"].shift(1))
    same_currency = same & (work["currency"] == work["currency"].shift(1))
    prev_tri = tri.shift(1)
    prev_adj_price = adj_price.shift(1)
    # Total return where both days have trfd; price return otherwise (flagged).
    both_tr = work["trfd"].notna() & work["trfd"].shift(1).notna()
    ret_tr = tri / prev_tri - 1.0
    ret_px = adj_price / prev_adj_price - 1.0
    ret_local = ret_tr.where(both_tr, ret_px)
    work["price_only"] = ~both_tr
    ret_local = ret_local.where(same_currency)
    work["ret_local"] = ret_local.replace([np.inf, -np.inf], np.nan)

    fx_long = fx_wide.stack().rename("usd_per_unit").reset_index()
    fx_long.columns = ["date", "currency", "usd_per_unit"]
    work = work.merge(fx_long, on=["date", "currency"], how="left")
    prev_fx = work["usd_per_unit"].shift(1).where(same_currency)
    fx_ratio = work["usd_per_unit"] / prev_fx
    work["ret_usd"] = (1.0 + work["ret_local"]) * fx_ratio - 1.0
    work["usd_price"] = work["price"] * work["usd_per_unit"]
    return work[["gvkey", "iid", "date", "currency", "ret_local", "ret_usd", "price_only", "usd_price", "shares"]]


def sanity_filter(returns: pd.DataFrame, threshold: float = 1.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flag |r| > threshold; drop the spike and its next-day reversal. Returns (clean, flagged log)."""
    if len(returns) == 0:
        return returns, pd.DataFrame(columns=["gvkey", "iid", "date", "ret_usd", "action"])
    work = returns.copy()
    same_next = (work["gvkey"] == work["gvkey"].shift(-1)) & (work["iid"] == work["iid"].shift(-1))
    big = work["ret_local"].abs() > threshold
    nxt = work["ret_local"].shift(-1)
    reverses = big & same_next & (np.sign(nxt) == -np.sign(work["ret_local"])) & (nxt.abs() > 0.4)
    log_rows = work.loc[big, ["gvkey", "iid", "date", "ret_usd"]].copy()
    log_rows["action"] = np.where(reverses[big], "dropped_reversal", "flagged_kept")
    drop_index = work.index[reverses]
    next_index = drop_index + 1
    work.loc[drop_index, ["ret_local", "ret_usd"]] = np.nan
    valid_next = next_index[next_index < len(work)]
    work.loc[valid_next, ["ret_local", "ret_usd"]] = np.nan
    return work, log_rows


def to_wide(returns: pd.DataFrame, primary: pd.DataFrame, column: str = "ret_usd") -> pd.DataFrame:
    """Dates x issuer_id matrix using each issuer's primary issue."""
    keys = primary[["gvkey", "iid", "issuer_id"]].drop_duplicates(subset=["issuer_id"])
    merged = returns.merge(keys, on=["gvkey", "iid"], how="inner")
    wide = merged.pivot_table(index="date", columns="issuer_id", values=column, aggfunc="last")
    return wide.sort_index()
