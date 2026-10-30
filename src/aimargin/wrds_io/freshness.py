"""Effective latest date and the coverage gate (BUILD_BRIEF §2.4 rules 1-2).

The effective latest date of a table is the most recent date d <= today with
    n(d) >= 0.5 * median{ n(d') : d' in the previous 20 trading days },
which ignores the handful of erroneous future-dated rows seen in comp.secd/g_secd.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..utils import as_date


@dataclass
class Freshness:
    effective_latest_date: dt.date | None
    raw_max_date: dt.date | None
    future_rows: int
    future_dates: int
    detail: str


def effective_latest_date(counts: pd.DataFrame, today: dt.date, window: int = 20,
                          threshold: float = 0.5) -> Freshness:
    """``counts`` has columns date, n (rows per date)."""
    if counts is None or len(counts) == 0:
        return Freshness(None, None, 0, 0, "no rows")
    frame = counts.copy()
    dates = []
    raw_dates = frame["date"].tolist()
    for i in range(len(raw_dates)):
        dates.append(as_date(raw_dates[i]))
    frame["date"] = dates
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    raw_max = frame["date"].max() if len(frame) > 0 else None
    future = frame[frame["date"] > today]
    current = frame[frame["date"] <= today].reset_index(drop=True)
    future_rows = int(future["n"].sum()) if len(future) > 0 else 0
    if len(current) == 0:
        return Freshness(None, raw_max, future_rows, len(future), "no rows on or before today")
    values = current["n"].astype(float).to_numpy()
    chosen = None
    for k in range(len(current) - 1, -1, -1):
        start = max(0, k - window)
        previous = values[start:k]
        if len(previous) == 0:
            chosen = k
            break
        median = float(np.median(previous))
        if values[k] >= threshold * median:
            chosen = k
            break
    if chosen is None:
        return Freshness(None, raw_max, future_rows, len(future), "no date passes the coverage rule")
    detail = (f"n={int(values[chosen])} on effective date; discarded {future_rows} future-dated rows "
              f"on {len(future)} dates")
    return Freshness(current["date"].iat[chosen], raw_max, future_rows, len(future), detail)


def coverage_gate(target: dt.date, latest_by_input: dict[str, dt.date | None]) -> tuple[dt.date | None, list[str]]:
    """Move the as-of date back to the latest date every price/FX input covers."""
    notes: list[str] = []
    usable: list[dt.date] = []
    names = list(latest_by_input.keys())
    for i in range(len(names)):
        latest = latest_by_input[names[i]]
        if latest is None:
            notes.append(f"{names[i]}: no effective latest date")
            continue
        usable.append(latest)
        if latest < target:
            notes.append(f"{names[i]} effective latest {latest} < requested {target}")
    if len(usable) == 0:
        return None, notes
    common = min(usable)
    if common >= target:
        return target, notes
    notes.append(f"as-of moved back from {target} to {common}")
    return common, notes


def last_trading_day_on_or_before(dates: list[dt.date], target: dt.date) -> dt.date | None:
    best = None
    for i in range(len(dates)):
        if dates[i] is not None and dates[i] <= target and (best is None or dates[i] > best):
            best = dates[i]
    return best
