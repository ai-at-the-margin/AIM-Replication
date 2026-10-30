"""Raw descriptors (BUILD_BRIEF §7.2), computed on a dates x issuers return matrix.

Missing observations never become zeros: each descriptor needs at least
``min_obs_fraction`` of its window, otherwise it is NaN and flagged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ewma_weights(n: int, half_life: float) -> np.ndarray:
    """Weights for the last n observations, oldest first: w_t ∝ 2^{-(T-t)/h}."""
    ages = np.arange(n - 1, -1, -1, dtype=float)
    weights = np.power(2.0, -ages / float(half_life))
    return weights / weights.sum()


def _window(matrix: pd.DataFrame, end_pos: int, length: int) -> pd.DataFrame:
    start = max(0, end_pos - length + 1)
    return matrix.iloc[start:end_pos + 1]


def market_return(returns: pd.DataFrame, caps: pd.DataFrame, members: list[str]) -> pd.Series:
    """Cap-weighted universe return using the previous day's caps."""
    cols = []
    have = set(returns.columns)
    for i in range(len(members)):
        if members[i] in have and members[i] in caps.columns:
            cols.append(members[i])
    r = returns[cols]
    w = caps[cols].shift(1).reindex(r.index)
    valid = r.notna() & w.notna() & (w > 0)
    num = (r.where(valid, 0.0) * w.where(valid, 0.0)).sum(axis=1)
    den = w.where(valid, 0.0).sum(axis=1)
    return (num / den.replace(0.0, np.nan)).rename("mkt")


def beta_and_hsigma(excess: pd.DataFrame, mkt_excess: pd.Series, end_pos: int, window: int, half_life: float,
                    hsigma_half_life: float, min_frac: float) -> tuple[pd.Series, pd.Series]:
    Y = _window(excess, end_pos, window)
    x = mkt_excess.reindex(Y.index).to_numpy(dtype=float)
    n = len(Y)
    w = ewma_weights(n, half_life)
    wh = ewma_weights(n, hsigma_half_life)
    yv = Y.to_numpy(dtype=float)
    mask = np.isfinite(yv) & np.isfinite(x)[:, None]
    yv = np.where(mask, yv, 0.0)
    xv = np.where(mask, np.repeat(x[:, None], yv.shape[1], axis=1), 0.0)
    W = w[:, None] * mask
    sw = W.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        xm = (W * xv).sum(axis=0) / sw
        ym = (W * yv).sum(axis=0) / sw
        cov = (W * (xv - xm) * (yv - ym)).sum(axis=0) / sw
        var = (W * (xv - xm) ** 2).sum(axis=0) / sw
        beta = cov / var
        alpha = ym - beta * xm
        resid = np.where(mask, yv - alpha - beta * xv, 0.0)
        Wh = wh[:, None] * mask
        hsigma = np.sqrt((Wh * resid ** 2).sum(axis=0) / Wh.sum(axis=0))
    enough = mask.sum(axis=0) >= min_frac * window
    beta = np.where(enough, beta, np.nan)
    hsigma = np.where(enough, hsigma, np.nan)
    return pd.Series(beta, index=Y.columns), pd.Series(hsigma, index=Y.columns)


def rstr(log_excess: pd.DataFrame, end_pos: int, window: int, lag: int, half_life: float,
         min_frac: float) -> pd.Series:
    """Σ w_t [ln(1+r_t) - ln(1+rf_t)] over t in [T-L-W, T-L], rescaled over missing days."""
    last = end_pos - lag
    if last < 0:
        return pd.Series(np.nan, index=log_excess.columns)
    block = _window(log_excess, last, window)
    values = block.to_numpy(dtype=float)
    mask = np.isfinite(values)
    w = ewma_weights(len(block), half_life)
    W = w[:, None] * mask
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (W * np.where(mask, values, 0.0)).sum(axis=0) / W.sum(axis=0)
    out = np.where(mask.sum(axis=0) >= min_frac * window, out, np.nan)
    return pd.Series(out, index=log_excess.columns)


def simple_momentum(returns: pd.DataFrame, end_pos: int, start_back: int, end_back: int,
                    min_frac: float) -> pd.Series:
    """Cumulative return from T-start_back to T-end_back (12-1 month: 252 -> 21)."""
    first = end_pos - start_back + 1
    last = end_pos - end_back
    if first < 0 or last < first:
        return pd.Series(np.nan, index=returns.columns)
    block = returns.iloc[first:last + 1]
    values = block.to_numpy(dtype=float)
    mask = np.isfinite(values)
    growth = np.prod(np.where(mask, 1.0 + values, 1.0), axis=0) - 1.0
    growth = np.where(mask.sum(axis=0) >= min_frac * (last - first + 1), growth, np.nan)
    return pd.Series(growth, index=returns.columns)


def dastd(excess: pd.DataFrame, end_pos: int, window: int, half_life: float, min_frac: float) -> pd.Series:
    block = _window(excess, end_pos, window)
    values = block.to_numpy(dtype=float)
    mask = np.isfinite(values)
    w = ewma_weights(len(block), half_life)
    W = w[:, None] * mask
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.sqrt((W * np.where(mask, values, 0.0) ** 2).sum(axis=0) / W.sum(axis=0))
    out = np.where(mask.sum(axis=0) >= min_frac * window, out, np.nan)
    return pd.Series(out, index=excess.columns)


def cmra(log_excess: pd.DataFrame, end_pos: int, months: int, days_per_month: int, min_frac: float) -> pd.Series:
    """Range of cumulative monthly excess log returns over the last 12 months."""
    length = months * days_per_month
    block = _window(log_excess, end_pos, length)
    values = block.to_numpy(dtype=float)
    mask = np.isfinite(values)
    filled = np.where(mask, values, 0.0)
    n = len(block)
    sums = []
    for m in range(months):
        stop = n - m * days_per_month
        start = max(0, stop - days_per_month)
        if stop <= 0:
            break
        sums.append(filled[start:stop].sum(axis=0))
    if len(sums) == 0:
        return pd.Series(np.nan, index=log_excess.columns)
    monthly = np.vstack(sums[::-1])
    cumulative = np.cumsum(monthly, axis=0)
    out = cumulative.max(axis=0) - cumulative.min(axis=0)
    out = np.where(mask.sum(axis=0) >= min_frac * length, out, np.nan)
    return pd.Series(out, index=log_excess.columns)


def price_descriptors(returns: pd.DataFrame, rf: pd.Series, mkt: pd.Series, asof: pd.Timestamp,
                      cfg: dict) -> pd.DataFrame:
    """beta, hsigma, rstr, mom_12_1, dastd, cmra for every column of ``returns``."""
    rows = returns.loc[:asof]
    if len(rows) == 0:
        return pd.DataFrame(index=returns.columns)
    end_pos = len(rows) - 1
    rf_aligned = rf.reindex(rows.index).fillna(0.0)
    excess = rows.sub(rf_aligned, axis=0)
    log_excess = np.log1p(rows).sub(np.log1p(rf_aligned), axis=0)
    mkt_excess = mkt.reindex(rows.index) - rf_aligned
    min_frac = float(cfg.get("min_obs_fraction", 0.5))
    b = cfg["beta"]
    beta, hsig = beta_and_hsigma(excess, mkt_excess, end_pos, int(b["window"]), float(b["half_life"]),
                                 float(cfg["resvol"]["hsigma"]["half_life"]), min_frac)
    m = cfg["momentum"]
    out = pd.DataFrame(index=returns.columns)
    out["beta_raw"] = beta
    out["hsigma_raw"] = hsig
    out["rstr_raw"] = rstr(log_excess, end_pos, int(m["window"]), int(m["lag"]), float(m["half_life"]), min_frac)
    s = m.get("simple_12_1", {"start": 252, "end": 21})
    out["mom_12_1_raw"] = simple_momentum(rows, end_pos, int(s["start"]), int(s["end"]), min_frac)
    d = cfg["resvol"]["dastd"]
    out["dastd_raw"] = dastd(excess, end_pos, int(d["window"]), float(d["half_life"]), min_frac)
    c = cfg["resvol"]["cmra"]
    out["cmra_raw"] = cmra(log_excess, end_pos, int(c["months"]), int(c["days_per_month"]), min_frac)
    return out


def fundamental_descriptors(annual: pd.DataFrame, book: pd.DataFrame, caps_usd: pd.Series,
                            fx_at_t: dict[str, float], gvkey_to_issuer: dict[str, str],
                            price_currency: dict[str, str], cfg: dict) -> pd.DataFrame:
    """btop, etop, roa, roe, gpa, debt_assets, earn_var, accruals per issuer."""
    q = cfg.get("quality", {})
    years = int(q.get("earnings_variability_years", 5))
    min_years = int(q.get("earnings_variability_min_years", 3))
    rows: dict[str, dict[str, float]] = {}
    annual_sorted = annual.sort_values(["gvkey", "datadate"]) if len(annual) > 0 else annual
    groups = annual_sorted.groupby("gvkey") if len(annual_sorted) > 0 else None
    keys = list(groups.groups.keys()) if groups is not None else []
    for i in range(len(keys)):
        g = groups.get_group(keys[i])
        issuer = gvkey_to_issuer.get(keys[i])
        if issuer is None:
            continue
        last = g.iloc[-1]
        currency = str(last.get("currency") or price_currency.get(keys[i]) or "USD")
        fx = fx_at_t.get(currency)
        at = last.get("at")
        ceq = last.get("ceq")
        ib = last.get("ib")
        rec: dict[str, float] = {}
        rec["roa"] = ib / at if _ok(ib) and _ok(at) and at > 0 else np.nan
        rec["roe"] = ib / ceq if _ok(ib) and _ok(ceq) and ceq > 0 else np.nan
        gp = last.get("revt") - last.get("cogs") if _ok(last.get("revt")) and _ok(last.get("cogs")) else np.nan
        rec["gpa"] = gp / at if _ok(gp) and _ok(at) and at > 0 else np.nan
        debt = 0.0
        have_debt = False
        for item in ("dltt", "dlc"):
            if _ok(last.get(item)):
                debt += float(last.get(item))
                have_debt = True
        rec["debt_assets"] = debt / at if have_debt and _ok(at) and at > 0 else np.nan
        oancf = last.get("oancf")
        rec["accruals"] = (ib - oancf) / at if _ok(ib) and _ok(oancf) and _ok(at) and at > 0 else np.nan
        tail = g.tail(years + 1)
        changes = []
        ibs = tail["ib"].tolist()
        ats = tail["at"].tolist()
        for k in range(1, len(ibs)):
            if _ok(ibs[k]) and _ok(ibs[k - 1]) and _ok(ats[k]) and ats[k] > 0:
                changes.append((ibs[k] - ibs[k - 1]) / ats[k])
        rec["earn_var"] = float(np.std(changes, ddof=1)) if len(changes) >= min_years else np.nan
        cap = caps_usd.get(issuer)
        rec["etop"] = (ib * fx) / cap if _ok(ib) and fx and _ok(cap) and cap > 0 else np.nan
        rec["book_annual_usd"] = ceq * fx if _ok(ceq) and fx else np.nan
        rows[issuer] = rec
    if len(book) > 0:
        latest = book.sort_values(["gvkey", "available_date", "datadate"]).drop_duplicates(subset=["gvkey"], keep="last")
        records = latest.to_dict("records")
        for i in range(len(records)):
            issuer = gvkey_to_issuer.get(records[i]["gvkey"])
            if issuer is None or not _ok(records[i].get("ceq")):
                continue
            currency = str(records[i].get("currency") or price_currency.get(records[i]["gvkey"]) or "USD")
            fx = fx_at_t.get(currency)
            if fx:
                rows.setdefault(issuer, {})["book_q_usd"] = float(records[i]["ceq"]) * fx
    out = pd.DataFrame.from_dict(rows, orient="index")
    for column in ("book_q_usd", "book_annual_usd", "roa", "roe", "gpa", "debt_assets", "accruals", "earn_var", "etop"):
        if column not in out.columns:
            out[column] = np.nan
    book_usd = out["book_q_usd"].fillna(out["book_annual_usd"])
    caps = caps_usd.reindex(out.index)
    out["btop"] = book_usd / caps.where(caps > 0)
    return out


def _ok(value: object) -> bool:
    if value is None:
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
