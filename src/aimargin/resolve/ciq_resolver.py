"""Ticker + exchange matching against the security master (CIQ rows first)."""

from __future__ import annotations

from dataclasses import dataclass

from .fuzzy import name_similarity
from .master import SecurityMaster
from .normalise import ParsedTicker, exchange_table


@dataclass
class Match:
    row_index: int
    method: str
    confidence: float
    note: str = ""


def _filter_sources(master: SecurityMaster, rows: list[int], sources: tuple[str, ...]) -> list[int]:
    out = []
    source_values = master.frame["source"]
    for i in range(len(rows)):
        if str(source_values.iat[rows[i]]) in sources:
            out.append(rows[i])
    return out


def _prefer(master: SecurityMaster, rows: list[int], raw_name: str | None) -> tuple[int, float]:
    """Pick the best row: active, primary, best name similarity, US listing as tie-break."""
    table = exchange_table()
    best = rows[0]
    best_score = -1.0
    best_sim = 0.0
    frame = master.frame
    for i in range(len(rows)):
        r = rows[i]
        score = 0.0
        if bool(frame["active"].iat[r]):
            score += 4.0
        if bool(frame["is_primary"].iat[r]):
            score += 1.0
        sim = name_similarity(raw_name, frame["company_name"].iat[r]) if raw_name else 0.0
        score += sim / 25.0
        exchange = frame["exchange_code"].iat[r]
        info = table.info.get(str(exchange), {}) if exchange is not None else {}
        if info.get("us"):
            score += 0.5
        if score > best_score:
            best_score = score
            best = r
            best_sim = sim
    return best, best_sim


def match_ticker(master: SecurityMaster, parsed: ParsedTicker, raw_name: str | None,
                 sources: tuple[str, ...] = ("ciq", "synthetic")) -> Match | None:
    if parsed.key is None:
        return None
    label = "ciq" if "ciq" in sources or "synthetic" in sources else sources[0]
    # 1. ticker + exchange
    if parsed.exchange is not None:
        rows = _filter_sources(master, master.by_key_exchange.get((parsed.key, parsed.exchange), []), sources)
        if len(rows) > 0:
            chosen, sim = _prefer(master, rows, raw_name)
            confidence = 1.0
            note = ""
            if raw_name and sim < 50.0:
                confidence = 0.7
                note = f"name mismatch ({sim:.0f})"
            return Match(chosen, f"{label}_ticker_exchange", confidence, note)
    # 2. ticker only (no exchange given, or not found on the stated exchange)
    rows = _filter_sources(master, master.by_key.get(parsed.key, []), sources)
    if len(rows) == 0:
        return None
    chosen, sim = _prefer(master, rows, raw_name)
    if parsed.exchange is not None:
        # The model named an exchange we could not match: accept only with name support.
        if raw_name and sim >= 80.0:
            return Match(chosen, f"{label}_ticker_other_exchange", 0.85, f"stated exchange {parsed.exchange}")
        if not raw_name and len(rows) == 1:
            return Match(chosen, f"{label}_ticker_other_exchange", 0.6, f"stated exchange {parsed.exchange}")
        return None
    issuers = set()
    issuer_values = master.frame["issuer_id"]
    for i in range(len(rows)):
        issuers.add(issuer_values.iat[rows[i]])
    if len(issuers) == 1:
        confidence = 0.95
    else:
        confidence = 0.8 if (raw_name and sim >= 80.0) else 0.65
    note = ""
    if raw_name and sim < 50.0:
        confidence = min(confidence, 0.6)
        note = f"name mismatch ({sim:.0f})"
    return Match(chosen, f"{label}_ticker_only", confidence, note)
