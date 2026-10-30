"""I/B/E/S summary statistics: 12-month-forward EPS and analyst coverage."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .schema import TableMap


def statsum_sql(m: TableMap, table: str, asof: dt.date, lookback_days: int = 45) -> str:
    fields = ["ticker", "cusip", "statpers", "fpi", "fpedats", "meanest", "numest", "measure", "fiscalp", "currency"]
    where = [f"{m.c('statpers')} BETWEEN '{(asof - dt.timedelta(days=lookback_days)).isoformat()}' "
             f"AND '{asof.isoformat()}'", f"{m.c('fpi')} IN ('1', '2')"]
    if m.has("measure"):
        where.append(f"{m.c('measure')} = 'EPS'")
    if m.has("fiscalp"):
        where.append(f"{m.c('fiscalp')} = 'ANN'")
    return f"SELECT {m.select(fields)} FROM {m.library}.{table} WHERE {' AND '.join(where)}"


def forward_eps(frame: pd.DataFrame, asof: dt.date) -> pd.DataFrame:
    """12-month-forward consensus EPS interpolated between FY1 and FY2.

    fwd = w * FY1 + (1 - w) * FY2 with w = months from T to the FY1 period end / 12.
    """
    columns = ["ticker", "cusip", "fwd_eps", "numest", "currency"]
    if frame is None or len(frame) == 0:
        return pd.DataFrame(columns=columns)
    work = frame.copy()
    work["statpers"] = pd.to_datetime(work["statpers"], errors="coerce")
    work["fpedats"] = pd.to_datetime(work.get("fpedats"), errors="coerce")
    work["meanest"] = pd.to_numeric(work["meanest"], errors="coerce")
    work["numest"] = pd.to_numeric(work["numest"], errors="coerce")
    work["fpi"] = work["fpi"].astype(str)
    work = work.sort_values("statpers").drop_duplicates(subset=["ticker", "fpi"], keep="last")
    fy1 = work[work["fpi"] == "1"].set_index("ticker")
    fy2 = work[work["fpi"] == "2"].set_index("ticker")
    tickers = list(fy1.index)
    rows = []
    stamp = pd.Timestamp(asof)
    for i in range(len(tickers)):
        t = tickers[i]
        one = fy1.loc[t]
        eps1 = one["meanest"]
        if pd.isna(eps1):
            continue
        months = 12.0
        if pd.notna(one.get("fpedats")):
            months = max(0.0, min(12.0, (one["fpedats"] - stamp).days / 30.44))
        weight = months / 12.0
        eps2 = fy2.loc[t]["meanest"] if t in fy2.index else None
        if eps2 is None or pd.isna(eps2):
            fwd = eps1
        else:
            fwd = weight * eps1 + (1.0 - weight) * eps2
        rows.append({"ticker": t, "cusip": one.get("cusip"), "fwd_eps": float(fwd),
                     "numest": float(one["numest"]) if pd.notna(one["numest"]) else None,
                     "currency": one.get("currency")})
    return pd.DataFrame(rows, columns=columns)


def link_to_gvkey(estimates: pd.DataFrame, securities: pd.DataFrame) -> pd.DataFrame:
    """IBES 8-character CUSIP -> Compustat CUSIP[:8]; SEDOL / ISIN for international rows."""
    if estimates is None or len(estimates) == 0:
        return pd.DataFrame(columns=["gvkey", "fwd_eps", "numest", "currency"])
    sec = securities.copy()
    keys = []
    cusips = sec.get("cusip", pd.Series([None] * len(sec))).tolist()
    sedols = sec.get("sedol", pd.Series([None] * len(sec))).tolist()
    isins = sec.get("isin", pd.Series([None] * len(sec))).tolist()
    gvkeys = sec["gvkey"].tolist()
    lookup: dict[str, str] = {}
    for i in range(len(gvkeys)):
        for value in (cusips[i], sedols[i]):
            if value is not None and str(value) not in ("", "nan", "None"):
                lookup[str(value)[:8].upper()] = str(gvkeys[i]).zfill(6)
                lookup[str(value)[:6].upper()] = str(gvkeys[i]).zfill(6)
        if isins[i] is not None and str(isins[i]) not in ("", "nan", "None"):
            lookup[str(isins[i])[2:10].upper()] = str(gvkeys[i]).zfill(6)
    est_cusips = estimates["cusip"].tolist()
    for i in range(len(est_cusips)):
        value = str(est_cusips[i] or "").upper()
        keys.append(lookup.get(value[:8]) or lookup.get(value[:6]))
    out = estimates.copy()
    out["gvkey"] = keys
    out = out.dropna(subset=["gvkey"])
    return out.drop_duplicates(subset=["gvkey"], keep="first")[["gvkey", "fwd_eps", "numest", "currency"]]
