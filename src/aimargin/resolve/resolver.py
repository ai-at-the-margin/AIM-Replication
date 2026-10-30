"""Resolve raw (ticker, exchange, company) triples to trading items and issuers.

Order (BUILD_BRIEF §6.4): manual override -> CIQ ticker+exchange -> Compustat
ticker+exchange -> company-name match. Issuers collapse automatically through the
CIQ company id; ``crosslisting_overrides.csv`` handles the exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .ciq_resolver import Match, _prefer, match_ticker
from .comp_resolver import match_compustat
from .crosslist import apply_crosslist, load_crosslist_overrides, load_ticker_overrides
from .fuzzy import ACCEPT_SCORE, REVIEW_SCORE, best_name_match
from .master import SecurityMaster
from .normalise import exchange_table, name_key, parse_ticker

ACCEPT_CONFIDENCE = 0.75
MIN_CONFIDENCE = 0.6


@dataclass
class Resolution:
    status: str                    # resolved | resolved_low_confidence | unresolved
    method: str
    confidence: float
    fields: dict[str, Any] = field(default_factory=dict)
    note: str = ""


def _blank(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    text = str(value)
    if text in ("", "None", "nan", "<NA>"):
        return None
    return value


class Resolver:
    def __init__(self, master: SecurityMaster, manual_dir: Path):
        self.master = master
        self.manual_dir = manual_dir
        self.overrides = load_ticker_overrides(manual_dir)
        self.crosslist = load_crosslist_overrides(manual_dir)
        self.review: list[dict[str, Any]] = []
        self.cache: dict[tuple, Resolution] = {}
        self.item_index: dict[str, int] = {}
        items = master.frame["item_id"].tolist()
        for i in range(len(items)):
            self.item_index[str(items[i])] = i

    def _fields(self, row_index: int) -> dict[str, Any]:
        row = self.master.row(row_index)
        table = exchange_table()
        exchange = _blank(row.get("exchange_code"))
        info = table.info.get(str(exchange), {}) if exchange else {}
        issuer = apply_crosslist(_blank(row.get("issuer_id")), self.crosslist)
        return {
            "ciq_companyid": _blank(row.get("ciq_companyid")),
            "ciq_tradingitemid": _blank(row.get("ciq_tradingitemid")),
            "gvkey": str(row["gvkey"]).zfill(6) if _blank(row.get("gvkey")) else None,
            "iid": _blank(row.get("iid")),
            "issuer_id": issuer,
            "resolved_name": _blank(row.get("company_name")),
            "resolved_ticker": _blank(row.get("ticker")),
            "isin": _blank(row.get("isin")), "sedol": _blank(row.get("sedol")), "cusip": _blank(row.get("cusip")),
            "fic": _blank(row.get("fic")), "country": _blank(row.get("country")),
            "exchg": str(row.get("exchg")) if _blank(row.get("exchg")) is not None else None,
            "exchange_code": exchange,
            "gics_sector": str(row.get("gics_sector")) if _blank(row.get("gics_sector")) is not None else None,
            "is_adr": bool(row.get("is_adr")),
            "is_china_a_share": bool(info.get("china_a", False)),
            "is_hk_listed": exchange == "XHKG",
            "is_us_listed": bool(info.get("us", False)),
        }

    def _from_override(self, raw_ticker: str | None, raw_exchange: str | None) -> Resolution | None:
        key = (str(raw_ticker or "").strip().upper(), str(raw_exchange or "").strip().upper())
        entry = self.overrides.get(key) or self.overrides.get((key[0], ""))
        if entry is None:
            return None
        index = None
        if entry.get("item_id"):
            index = self.item_index.get(str(entry["item_id"]))
        if index is None and entry.get("gvkey"):
            rows = self.master.by_gvkey.get(str(entry["gvkey"]).zfill(6), [])
            for i in range(len(rows)):
                iid = self.master.frame["iid"].iat[rows[i]]
                if not entry.get("iid") or str(iid) == str(entry["iid"]):
                    index = rows[i]
                    break
        if index is None:
            return Resolution("unresolved", "override_unmatched", 0.0, note="override points to unknown security")
        return Resolution("resolved", "manual_override", 1.0, self._fields(index), entry.get("note", ""))

    def resolve(self, raw_ticker: str | None, raw_exchange: str | None, raw_name: str | None) -> Resolution:
        cache_key = (raw_ticker, raw_exchange, raw_name)
        if cache_key in self.cache:
            return self.cache[cache_key]
        result = self._resolve(raw_ticker, raw_exchange, raw_name)
        self.cache[cache_key] = result
        if result.status != "resolved":
            self._queue_review(raw_ticker, raw_exchange, raw_name, result)
        return result

    def _resolve(self, raw_ticker: str | None, raw_exchange: str | None, raw_name: str | None) -> Resolution:
        override = self._from_override(raw_ticker, raw_exchange)
        if override is not None:
            return override
        parsed = parse_ticker(raw_ticker, raw_exchange)
        match: Match | None = match_ticker(self.master, parsed, raw_name)
        if match is None:
            match = match_compustat(self.master, parsed, raw_name)
        names = best_name_match(self.master, raw_name) if raw_name else []
        if match is not None and match.note.startswith("name mismatch") and len(names) > 0:
            best_name, score, rows = names[0]
            if score >= ACCEPT_SCORE and len(rows) > 0:
                chosen, _ = _prefer(self.master, rows, raw_name)
                if self.master.frame["issuer_id"].iat[chosen] != self.master.frame["issuer_id"].iat[match.row_index]:
                    return self._finish(Match(chosen, "name_over_ticker", score / 100.0,
                                              f"ticker {parsed.key} pointed to another company"))
        if match is not None:
            return self._finish(match)
        if len(names) > 0:
            best_name, score, rows = names[0]
            if score >= REVIEW_SCORE and len(rows) > 0:
                chosen, _ = _prefer(self.master, rows, raw_name)
                return self._finish(Match(chosen, "name_fuzzy", score / 100.0, f"name score {score:.0f}"))
        return Resolution("unresolved", "none", 0.0, note=f"key={parsed.key} exch={parsed.exchange}")

    def _finish(self, match: Match) -> Resolution:
        if match.confidence >= ACCEPT_CONFIDENCE:
            status = "resolved"
        elif match.confidence >= MIN_CONFIDENCE:
            status = "resolved_low_confidence"
        else:
            return Resolution("unresolved", match.method, match.confidence, note=match.note)
        return Resolution(status, match.method, match.confidence, self._fields(match.row_index), match.note)

    def _queue_review(self, raw_ticker: str | None, raw_exchange: str | None, raw_name: str | None,
                      result: Resolution) -> None:
        suggestions = best_name_match(self.master, raw_name, limit=3) if raw_name else []
        suggested = []
        for i in range(len(suggestions)):
            rows = suggestions[i][2]
            if len(rows) > 0:
                suggested.append(f"{self.master.frame['company_name'].iat[rows[0]]} "
                                 f"[{self.master.frame['item_id'].iat[rows[0]]}] ({suggestions[i][1]:.0f})")
        self.review.append({
            "raw_ticker": raw_ticker, "raw_exchange": raw_exchange, "raw_name": raw_name,
            "status": result.status, "method": result.method, "confidence": round(result.confidence, 3),
            "resolved_name": result.fields.get("resolved_name"), "note": result.note,
            "suggestions": " | ".join(suggested), "name_key": name_key(raw_name),
        })

    def write_review(self, path: Path) -> int:
        if len(self.review) == 0:
            if path.exists():
                path.unlink()
            return 0
        frame = pd.DataFrame(self.review).drop_duplicates(subset=["raw_ticker", "raw_exchange", "raw_name"])
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return len(frame)
