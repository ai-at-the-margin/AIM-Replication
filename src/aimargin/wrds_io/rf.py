"""Daily risk-free rate, forward-filled past the source's last date (BUILD_BRIEF §2.2).

ff.factors_daily stops at 2026-09-30. Daily rf is about 0.015%, so carrying the last
value forward for a month or two is negligible for every descriptor; filled days
carry ``rf_filled = True`` and the fill is listed in DEVIATIONS.md.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .schema import TableMap


def rf_sql(m: TableMap, start: dt.date, end: dt.date) -> str:
    return (f"SELECT {m.select(['date', 'rf'])} FROM {m.fq} "
            f"WHERE {m.c('date')} BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'")


def prepare_rf(frame: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Daily decimal rf on the trading calendar with an ``rf_filled`` flag."""
    out = pd.DataFrame(index=dates)
    if frame is None or len(frame) == 0:
        out["rf"] = 0.0
        out["rf_filled"] = True
        return out
    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["rf"] = pd.to_numeric(work["rf"], errors="coerce")
    work = work.dropna(subset=["date", "rf"]).drop_duplicates(subset=["date"], keep="last").set_index("date")
    series = work["rf"].sort_index()
    if len(series) > 0 and float(series.abs().median()) > 0.01:
        series = series / 100.0  # source in percent
    observed = series.reindex(dates)
    out["rf_filled"] = observed.isna()
    union = series.index.union(dates)
    out["rf"] = series.reindex(union).sort_index().ffill().reindex(dates).fillna(0.0)
    return out
