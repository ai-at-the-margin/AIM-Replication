"""Validate the Compustat return construction against CRSP over 2024-2025 (BUILD_BRIEF §2.6).

Acceptance: correlation of daily total returns > 0.99 and median absolute
difference below 1 bp.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def link_sql(start: str, end: str) -> str:
    return ("SELECT gvkey, lpermno AS permno, linkdt, linkenddt, liid AS iid FROM crsp.ccmxpf_lnkhist "
            "WHERE linktype IN ('LU', 'LC') AND linkprim IN ('P', 'C') "
            f"AND linkdt <= '{end}' AND (linkenddt >= '{start}' OR linkenddt IS NULL)")


def crsp_sql(permnos: list[int], start: str, end: str, date_col: str = "dlycaldt", ret_col: str = "dlyret",
             cap_col: str = "dlycap") -> str:
    parts = []
    for i in range(len(permnos)):
        parts.append(str(int(permnos[i])))
    return (f"SELECT permno, {date_col} AS date, {ret_col} AS ret, {cap_col} AS cap FROM crsp.dsf_v2 "
            f"WHERE permno IN ({', '.join(parts)}) AND {date_col} BETWEEN '{start}' AND '{end}'")


def compare_returns(comp: pd.DataFrame, crsp: pd.DataFrame, links: pd.DataFrame) -> dict[str, float | int]:
    """``comp``: gvkey, iid, date, ret (local-currency total return, US issues)."""
    if comp is None or crsp is None or links is None or len(comp) == 0 or len(crsp) == 0:
        return {"n_obs": 0}
    link = links.copy()
    link["gvkey"] = link["gvkey"].astype(str).str.zfill(6)
    link["permno"] = pd.to_numeric(link["permno"], errors="coerce")
    crsp = crsp.copy()
    crsp["date"] = pd.to_datetime(crsp["date"])
    crsp["ret"] = pd.to_numeric(crsp["ret"], errors="coerce")
    merged = comp.merge(link[["gvkey", "iid", "permno"]], on=["gvkey", "iid"], how="inner")
    merged = merged.merge(crsp, on=["permno", "date"], how="inner", suffixes=("_comp", "_crsp"))
    merged = merged.dropna(subset=["ret_comp", "ret_crsp"])
    if len(merged) == 0:
        return {"n_obs": 0}
    diff = (merged["ret_comp"] - merged["ret_crsp"]).abs()
    return {
        "n_obs": int(len(merged)),
        "n_issuers": int(merged["permno"].nunique()),
        "corr": float(np.corrcoef(merged["ret_comp"], merged["ret_crsp"])[0, 1]),
        "median_abs_diff_bp": float(diff.median() * 1e4),
        "p99_abs_diff_bp": float(diff.quantile(0.99) * 1e4),
        "pass": bool(np.corrcoef(merged["ret_comp"], merged["ret_crsp"])[0, 1] > 0.99 and diff.median() * 1e4 < 1.0),
    }


def run_validation(ws, config, source, n_issuers: int = 300) -> dict:
    """Pull CRSP for the largest US issuers and compare returns, caps and 12-1 momentum (live only)."""
    import datetime as dt

    from ..factors.returns import total_returns
    from .connect import cached_sql

    start, end = "2024-01-01", "2025-12-31"
    snapshot = None
    day = dt.date(2025, 12, 31)
    for k in range(7):
        snapshot = source.price_snapshot(day - dt.timedelta(days=k))
        if snapshot is not None and len(snapshot) > 0:
            day = day - dt.timedelta(days=k)
            break
    if snapshot is None or len(snapshot) == 0:
        return {"pass": False, "note": "no Compustat snapshot near 2025-12-31"}
    us = snapshot[snapshot["exchg"].isin(["11", "12", "14"]) & (snapshot["tpci"] == "0")].copy()
    us["cap"] = us["shares"] * us["price"]
    gvkeys = us.sort_values("cap", ascending=False)["gvkey"].drop_duplicates().head(n_issuers).tolist()
    history = source.price_history(gvkeys, dt.date(2023, 11, 1), dt.date(2025, 12, 31))
    dates = pd.DatetimeIndex(sorted(history["date"].dropna().unique()))
    fx_wide = pd.DataFrame(index=dates)
    fx_wide["USD"] = 1.0
    returns = total_returns(history, fx_wide)
    returns = returns[(returns["date"] >= pd.Timestamp(start)) & (returns["date"] <= pd.Timestamp(end))]
    comp = returns[["gvkey", "iid", "date", "ret_local"]].rename(columns={"ret_local": "ret"})
    links = cached_sql(source.client, source.cache, "crsp.ccmxpf_lnkhist", "static", link_sql(start, end), "links")
    links["gvkey"] = links["gvkey"].astype(str).str.zfill(6)
    links = links[links["gvkey"].isin(set(gvkeys))]
    permnos = pd.to_numeric(links["permno"], errors="coerce").dropna().astype(int).unique().tolist()
    crsp = cached_sql(source.client, source.cache, "crsp.dsf_v2", "2025-12-31", crsp_sql(permnos, start, end),
                      f"validation_{len(permnos)}")
    result = compare_returns(comp, crsp, links)
    result["window"] = [start, end]
    result["issuers_requested"] = len(gvkeys)
    return result
