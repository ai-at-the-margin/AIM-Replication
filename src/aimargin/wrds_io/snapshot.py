"""Point-in-time fundamentals from Compustat Snapshot (comp_snapshot).

A Snapshot row is the value that was in the database between ``pit_start`` and
``pit_end``. The version valid at the as-of date T satisfies
``pit_start <= T < pit_end`` (open-ended when pit_end is null), so restatements
after T never leak into descriptors.
"""

from __future__ import annotations

import datetime as dt

from .fundamentals import ANNUAL_ITEMS, _filters
from .prices import _in_list
from .schema import TableMap


def _pit_clause(m: TableMap, asof: dt.date) -> str:
    clause = f"{m.c('pit_start')} <= '{asof.isoformat()}'"
    if m.has("pit_end"):
        clause += f" AND ({m.c('pit_end')} > '{asof.isoformat()}' OR {m.c('pit_end')} IS NULL)"
    return clause


def annual_pit_sql(m: TableMap, gvkeys: list[str], start: dt.date, asof: dt.date) -> str:
    fields = ["gvkey", "datadate", "currency", "pit_start"] + ANNUAL_ITEMS
    return (f"SELECT {m.select(fields)} FROM {m.fq} WHERE {m.c('gvkey')} IN ({_in_list(gvkeys)}) "
            f"AND {m.c('datadate')} BETWEEN '{start.isoformat()}' AND '{asof.isoformat()}' "
            f"AND {_pit_clause(m, asof)}{_filters(m, 'na')}")


def quarterly_pit_sql(m: TableMap, gvkeys: list[str], start: dt.date, asof: dt.date) -> str:
    fields = ["gvkey", "datadate", "currency", "ceq", "pit_start"]
    return (f"SELECT {m.select(fields)} FROM {m.fq} WHERE {m.c('gvkey')} IN ({_in_list(gvkeys)}) "
            f"AND {m.c('datadate')} BETWEEN '{start.isoformat()}' AND '{asof.isoformat()}' "
            f"AND {_pit_clause(m, asof)}")


def with_available_date(frame):
    """Snapshot rows become available on their pit_start date."""
    out = frame.copy()
    if "pit_start" in out.columns:
        out["available_date"] = out["pit_start"]
    return out
