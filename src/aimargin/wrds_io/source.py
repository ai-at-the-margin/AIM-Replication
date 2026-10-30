"""DataSource: the one interface the factor engine and resolver read from.

``WrdsSource`` implements it on live WRDS (choosing primary/fallback tables from the
Phase 0 verification state); ``aimargin.demo.world.SyntheticSource`` implements it
on the synthetic demo world. Every frame comes back in the same standard shape.
"""

from __future__ import annotations

import abc
import datetime as dt
from typing import Any

import pandas as pd

from ..settings import Config, Workspace
from ..utils import get_logger, read_json, stable_hash
from . import ciq as ciq_mod
from . import fundamentals as fund_mod
from . import fx as fx_mod
from . import ibes as ibes_mod
from . import prices as price_mod
from . import rf as rf_mod
from . import snapshot as snap_mod
from .connect import QueryCache, WrdsClient, cached_sql
from .schema import TableMap, load_maps

log = get_logger(__name__)


class DataSource(abc.ABC):
    name = "abstract"
    is_synthetic = False

    def __init__(self) -> None:
        self.log_rows: list[dict[str, Any]] = []

    def note(self, input_name: str, source_used: str | None, fallback_used: bool, rows: int,
             notes: str = "", effective_latest_date: str | None = None) -> None:
        self.log_rows.append({"input": input_name, "source_used": source_used, "fallback_used": fallback_used,
                              "rows": int(rows), "notes": notes, "effective_latest_date": effective_latest_date})

    @abc.abstractmethod
    def latest_dates(self) -> dict[str, dt.date | None]: ...

    @abc.abstractmethod
    def security_master(self, asof: dt.date) -> pd.DataFrame: ...

    @abc.abstractmethod
    def companies(self) -> pd.DataFrame: ...

    @abc.abstractmethod
    def price_snapshot(self, date: dt.date) -> pd.DataFrame: ...

    @abc.abstractmethod
    def price_history(self, gvkeys: list[str], start: dt.date, end: dt.date) -> pd.DataFrame: ...

    @abc.abstractmethod
    def fx_rates(self, start: dt.date, end: dt.date) -> pd.DataFrame: ...

    @abc.abstractmethod
    def rf_rates(self, start: dt.date, end: dt.date) -> pd.DataFrame: ...

    @abc.abstractmethod
    def fundamentals_annual(self, gvkeys: list[str], asof: dt.date, years: int, pit: bool = True) -> pd.DataFrame: ...

    @abc.abstractmethod
    def book_equity(self, gvkeys: list[str], asof: dt.date, pit: bool = True) -> pd.DataFrame: ...

    def forward_eps(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        return pd.DataFrame(columns=["gvkey", "fwd_eps", "numest", "currency"])

    def news_counts(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        return pd.DataFrame(columns=["gvkey", "news_count_30d"])

    def finratio(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        return pd.DataFrame(columns=["gvkey", "roa", "roe", "debt_assets"])

    def index_members(self, asof: dt.date) -> pd.DataFrame:
        return pd.DataFrame(columns=["gvkey", "index_name"])


def chunks(values: list[str], size: int) -> list[list[str]]:
    out = []
    for start in range(0, len(values), size):
        out.append(values[start:start + size])
    return out


class WrdsSource(DataSource):
    """Live WRDS, primary -> fallback per input as chosen by `aim verify`."""

    name = "wrds"

    def __init__(self, ws: Workspace, config: Config, client: WrdsClient | None = None):
        super().__init__()
        self.ws = ws
        self.config = config
        self.client = client or WrdsClient()
        self.cache = QueryCache(ws)
        self.maps: dict[str, TableMap] = load_maps(config.schema)
        state = read_json(ws.processed / "phase0_state.json", default={}) or {}
        self.choices: dict[str, dict[str, Any]] = {}
        rows = state.get("wrds", {}).get("sources", [])
        for i in range(len(rows)):
            self.choices[rows[i]["input"]] = rows[i]
        self.exchg_map: dict[str, str] = state.get("wrds", {}).get("exchg_map", {})
        self.today = dt.date.today()

    def chosen(self, input_name: str) -> str | None:
        entry = self.choices.get(input_name)
        if entry is None:
            # verify has not run: assume the primary candidate
            candidates = self.config.sources.get("inputs", {}).get(input_name, {}).get("candidates", [])
            return candidates[0] if len(candidates) > 0 else None
        return entry.get("source_used")

    def _sql(self, key: str, asof: str, sql: str, tag: str = "") -> pd.DataFrame:
        mapping = self.maps[key]
        return cached_sql(self.client, self.cache, mapping.fq, asof, sql, tag)

    # ------------------------------------------------------------------ dates
    def latest_dates(self) -> dict[str, dt.date | None]:
        out: dict[str, dt.date | None] = {}
        for name in ("prices_na", "prices_global", "fx"):
            entry = self.choices.get(name) or {}
            value = entry.get("effective_latest_date")
            out[name] = dt.date.fromisoformat(value) if value else None
        return out

    # --------------------------------------------------------------- reference
    def companies(self) -> pd.DataFrame:
        mapping = self.maps["comp_company"]
        frames = []
        for global_tables in (False, True):
            sql = ciq_mod.companies_sql(mapping, global_tables)
            frames.append(self._sql("comp_company", "static", sql, "global" if global_tables else "na"))
        frame = pd.concat(frames, ignore_index=True)
        frame["gvkey"] = frame["gvkey"].astype(str).str.zfill(6)
        frame = frame.drop_duplicates(subset=["gvkey"], keep="first")
        frame["gics_sector"] = frame["gsector"]
        frame["country"] = frame["loc"]
        self.note("gics", "comp_company", False, len(frame))
        return frame

    def security_master(self, asof: dt.date) -> pd.DataFrame:
        sec = self.maps["comp_security_master"]
        comp = self.maps["comp_company"]
        pieces = []
        for global_tables in (False, True):
            sql = ciq_mod.comp_master_sql(sec, comp, global_tables)
            pieces.append(self._sql("comp_security_master", "static", sql, "global" if global_tables else "na"))
        comp_rows = pd.concat(pieces, ignore_index=True)
        comp_master = ciq_mod.build_comp_master(comp_rows, self.exchg_map)
        choice = self.chosen("security_master")
        if choice == "ciq_master":
            try:
                mapping = self.maps["ciq_master"]
                items = self._sql("ciq_master", "static", ciq_mod.ciq_items_sql(mapping), "items")
                links = self._sql("ciq_master", "static", ciq_mod.gvkey_link_sql(mapping), "gvkey_link")
                ciq_master = ciq_mod.build_ciq_master(items, links, comp_master, asof.isoformat())
                self.note("security_master", "ciq_master", False, len(ciq_master))
                return pd.concat([ciq_master, comp_master], ignore_index=True)
            except Exception as exc:
                log.warning("CIQ master failed (%s); falling back to Compustat security tables", exc)
                self.note("security_master", "comp_security_master", True, len(comp_master), f"CIQ failed: {exc}")
                return comp_master
        self.note("security_master", "comp_security_master", choice != "comp_security_master", len(comp_master))
        return comp_master

    # ----------------------------------------------------------------- prices
    def price_snapshot(self, date: dt.date) -> pd.DataFrame:
        frames = []
        for input_name, region in (("prices_na", "na"), ("prices_global", "global")):
            key = self.chosen(input_name)
            if key not in ("comp_secd", "comp_g_secd"):
                log.warning("%s: snapshot needs Compustat daily; source %s cannot build a universe", input_name, key)
                continue
            mapping = self.maps[key]
            raw = self._sql(key, date.isoformat(), price_mod.snapshot_sql(mapping, date), "snapshot")
            frames.append(price_mod.standardise(raw, region))
        if len(frames) == 0:
            return pd.DataFrame(columns=price_mod.PRICE_FIELDS + ["region"])
        frame = pd.concat(frames, ignore_index=True)
        frame, removed = price_mod.dedupe(frame)
        return frame

    def price_history(self, gvkeys: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        frames = []
        groups = chunks(sorted(set(gvkeys)), 400)
        for input_name, region in (("prices_na", "na"), ("prices_global", "global")):
            key = self.chosen(input_name)
            if key not in ("comp_secd", "comp_g_secd"):
                continue
            mapping = self.maps[key]
            for g in range(len(groups)):
                tag = f"hist_{start}_{stable_hash(groups[g], 10)}"
                raw = self._sql(key, end.isoformat(), price_mod.history_sql(mapping, groups[g], start, end), tag)
                if len(raw) > 0:
                    frames.append(price_mod.standardise(raw, region))
        if len(frames) == 0:
            return pd.DataFrame(columns=price_mod.PRICE_FIELDS + ["region"])
        frame = pd.concat(frames, ignore_index=True)
        frame, future = price_mod.drop_future(frame, self.today)
        frame, dupes = price_mod.dedupe(frame)
        self.note("prices", "comp_secd+comp_g_secd", False, len(frame),
                  f"discarded {future} future-dated rows, {dupes} duplicates")
        return frame

    def fx_rates(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        key = self.chosen("fx")
        if key != "comp_g_exrt_dly":
            raise RuntimeError(f"FX source {key} not supported for rate construction")
        mapping = self.maps[key]
        raw = self._sql(key, end.isoformat(), fx_mod.fx_sql(mapping, start, end), f"fx_{start}")
        rates = fx_mod.usd_per_unit(raw)
        self.note("fx", key, False, len(rates))
        return rates

    def rf_rates(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        key = self.chosen("rf") or "ff_factors_daily"
        mapping = self.maps[key]
        raw = self._sql(key, end.isoformat(), rf_mod.rf_sql(mapping, start, end), f"rf_{start}")
        self.note("rf", key, key != "ff_factors_daily", len(raw))
        return raw

    # ----------------------------------------------------------- fundamentals
    def fundamentals_annual(self, gvkeys: list[str], asof: dt.date, years: int, pit: bool = True) -> pd.DataFrame:
        start = dt.date(asof.year - years, 1, 1)
        lags = self.config.factors.get("annual_entry_lag_days", {"na": 90, "global": 120})
        frames = []
        groups = chunks(sorted(set(gvkeys)), 400)
        for input_name, region in (("fundamentals_na", "na"), ("fundamentals_global", "global")):
            key = self.chosen(input_name) if pit else ("comp_fund_na" if region == "na" else "comp_fund_global")
            if key is None:
                continue
            mapping = self.maps[key]
            for g in range(len(groups)):
                tag = f"annual_{'pit' if pit else 'restated'}_{stable_hash(groups[g], 10)}"
                if key.startswith("snapshot"):
                    raw = self._sql(key, asof.isoformat(), snap_mod.annual_pit_sql(mapping, groups[g], start, asof), tag)
                    raw = snap_mod.with_available_date(raw)
                else:
                    raw = self._sql(key, asof.isoformat(),
                                    fund_mod.annual_sql(mapping, groups[g], start, asof, region), tag)
                if len(raw) > 0:
                    frames.append(fund_mod.standardise_annual(raw, int(lags.get(region, 90)), key))
            total_rows = 0
            for f in range(len(frames)):
                total_rows += len(frames[f])
            self.note(input_name if pit else input_name + "_restated", key, key.startswith("comp_") and pit,
                      total_rows)
        if len(frames) == 0:
            return pd.DataFrame(columns=["gvkey", "datadate", "available_date", "currency"] + fund_mod.ANNUAL_ITEMS)
        frame = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["gvkey", "datadate"], keep="first")
        return fund_mod.as_known_at(frame, asof)

    def book_equity(self, gvkeys: list[str], asof: dt.date, pit: bool = True) -> pd.DataFrame:
        start = dt.date(asof.year - 2, 1, 1)
        lags = self.config.factors.get("annual_entry_lag_days", {"na": 90, "global": 120})
        frames = []
        groups = chunks(sorted(set(gvkeys)), 400)
        plan = [("na", "snapshot_na_q" if pit and self.chosen("fundamentals_na") == "snapshot_na" else "comp_fundq_na"),
                ("global", "comp_fundq_global")]
        for p in range(len(plan)):
            region, key = plan[p]
            mapping = self.maps[key]
            for g in range(len(groups)):
                tag = f"book_{'pit' if pit else 'restated'}_{stable_hash(groups[g], 10)}"
                if key.startswith("snapshot"):
                    raw = self._sql(key, asof.isoformat(), snap_mod.quarterly_pit_sql(mapping, groups[g], start, asof), tag)
                    raw = snap_mod.with_available_date(raw)
                else:
                    raw = self._sql(key, asof.isoformat(),
                                    fund_mod.quarterly_book_sql(mapping, groups[g], start, asof, region), tag)
                if len(raw) > 0:
                    frames.append(fund_mod.standardise_book(raw, int(lags.get(region, 90)), key))
        if len(frames) == 0:
            return pd.DataFrame(columns=["gvkey", "datadate", "available_date", "currency", "ceq", "source"])
        frame = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["gvkey", "datadate"], keep="first")
        return fund_mod.as_known_at(frame, asof)

    def forward_eps(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        key = self.chosen("forward_earnings")
        if key is None:
            return super().forward_eps(gvkeys, asof)
        mapping = self.maps[key]
        pieces = []
        for table in (mapping.table, mapping.extra.get("intl_table")):
            if not table:
                continue
            try:
                raw = cached_sql(self.client, self.cache, f"{mapping.library}.{table}", asof.isoformat(),
                                 ibes_mod.statsum_sql(mapping, table, asof))
                pieces.append(ibes_mod.forward_eps(raw, asof))
            except Exception as exc:
                log.warning("I/B/E/S %s unavailable: %s", table, exc)
        if len(pieces) == 0:
            return super().forward_eps(gvkeys, asof)
        estimates = pd.concat(pieces, ignore_index=True)
        master = self.security_master(asof)
        linked = ibes_mod.link_to_gvkey(estimates, master[master["source"] == "comp"])
        wanted = set(gvkeys)
        linked = linked[linked["gvkey"].isin(wanted)]
        self.note("forward_earnings", key, key != "ibes_statsum", len(linked))
        return linked

    def news_counts(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        from .ravenpack import news_counts

        if self.chosen("news") != "ravenpack":
            return super().news_counts(gvkeys, asof)
        master = self.security_master(asof)
        subset = master[(master["source"] == "comp") & master["gvkey"].isin(set(gvkeys))].dropna(subset=["isin"])
        counts = news_counts(self.client, subset["isin"].astype(str).unique().tolist(), asof)
        merged = subset[["gvkey", "isin"]].merge(counts, on="isin", how="inner")
        out = merged.groupby("gvkey", as_index=False)["news_count_30d"].max()
        self.note("news", "ravenpack", False, len(out))
        return out

    def finratio(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        if self.chosen("finratio") is None:
            return super().finratio(gvkeys, asof)
        mapping = self.maps["wrds_finratio"]
        sql = (f"SELECT {mapping.select(['gvkey', 'public_date', 'roa', 'roe', 'debt_assets'])} FROM {mapping.fq} "
               f"WHERE {mapping.c('public_date')} BETWEEN '{asof - dt.timedelta(days=62)}' AND '{asof}'")
        raw = self._sql("wrds_finratio", asof.isoformat(), sql)
        raw["gvkey"] = raw["gvkey"].astype(str).str.zfill(6)
        raw = raw.sort_values("public_date").drop_duplicates(subset=["gvkey"], keep="last")
        return raw[raw["gvkey"].isin(set(gvkeys))]
