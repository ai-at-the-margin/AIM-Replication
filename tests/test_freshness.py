"""Effective latest date and coverage gate (BUILD_BRIEF §2.4)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from aimargin.wrds_io.freshness import coverage_gate, effective_latest_date


def _counts(dates, values):
    return pd.DataFrame({"date": dates, "n": values})


def test_future_dated_rows_are_ignored():
    days = list(pd.bdate_range("2026-09-01", "2026-10-28").date)
    counts = [30000] * len(days)
    days.append(dt.date(2027, 11, 12))
    counts.append(1)
    result = effective_latest_date(_counts(days, counts), dt.date(2026, 10, 29))
    assert result.effective_latest_date == dt.date(2026, 10, 28)
    assert result.future_rows == 1
    assert result.raw_max_date == dt.date(2027, 11, 12)


def test_thin_last_day_is_skipped():
    days = list(pd.bdate_range("2026-09-01", "2026-10-28").date)
    counts = [30000] * len(days)
    counts[-1] = 900  # partial load
    result = effective_latest_date(_counts(days, counts), dt.date(2026, 10, 29))
    assert result.effective_latest_date == days[-2]


def test_coverage_gate_moves_asof_back():
    asof, notes = coverage_gate(dt.date(2026, 10, 29), {"prices_na": dt.date(2026, 10, 28),
                                                        "fx": dt.date(2026, 10, 27)})
    assert asof == dt.date(2026, 10, 27)
    assert "as-of moved back from 2026-10-29 to 2026-10-27" in notes
