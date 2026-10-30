"""Daily FX from comp.g_exrt_dly (GBP-based) -> USD per unit of each currency."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .schema import TableMap


def fx_sql(m: TableMap, start: dt.date, end: dt.date) -> str:
    return (f"SELECT {m.select(['date', 'from_currency', 'to_currency', 'rate'])} FROM {m.fq} "
            f"WHERE {m.c('date')} BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'")


def usd_per_unit(frame: pd.DataFrame) -> pd.DataFrame:
    """exratd is units of ``to_currency`` per 1 GBP, so USD/X = rate(USD) / rate(X)."""
    if frame is None or len(frame) == 0:
        return pd.DataFrame(columns=["date", "currency", "usd_per_unit"])
    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["rate"] = pd.to_numeric(work["rate"], errors="coerce")
    work = work[(work["rate"] > 0) & work["date"].notna()]
    usd = work[work["to_currency"] == "USD"][["date", "rate"]].rename(columns={"rate": "usd_rate"})
    usd = usd.drop_duplicates(subset=["date"], keep="last")
    merged = work.merge(usd, on="date", how="inner")
    merged["usd_per_unit"] = merged["usd_rate"] / merged["rate"]
    out = merged[["date", "to_currency", "usd_per_unit"]].rename(columns={"to_currency": "currency"})
    return out.drop_duplicates(subset=["date", "currency"], keep="last").reset_index(drop=True)


def align_to_dates(rates: pd.DataFrame, dates: pd.DatetimeIndex, max_gap_days: int = 7) -> pd.DataFrame:
    """Forward-fill each currency onto the trading calendar (gaps up to ``max_gap_days``).

    Returns a wide frame: index = date, columns = currency, values = USD per unit.
    USD itself is always 1.0.
    """
    if rates is None or len(rates) == 0:
        wide = pd.DataFrame(index=dates)
        wide["USD"] = 1.0
        return wide
    wide = rates.pivot_table(index="date", columns="currency", values="usd_per_unit", aggfunc="last")
    union = wide.index.union(dates)
    wide = wide.reindex(union).sort_index().ffill(limit=max_gap_days)
    wide = wide.reindex(dates)
    wide["USD"] = 1.0
    return wide
