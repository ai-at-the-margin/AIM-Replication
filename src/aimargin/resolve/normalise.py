"""Ticker-string and exchange-word normalisation (BUILD_BRIEF §6.4 step 1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..settings import CONFIG_DIR, load_yaml


@dataclass
class ExchangeTable:
    by_alias: dict[str, str]
    by_suffix: dict[str, str]
    by_ciq_symbol: dict[str, str]
    class_suffixes: set[str]
    info: dict[str, dict[str, Any]]


def _clean_word(text: str) -> str:
    return re.sub(r"[^a-z0-9&]+", " ", text.lower()).strip()


@lru_cache(maxsize=1)
def exchange_table() -> ExchangeTable:
    data = load_yaml(CONFIG_DIR / "exchanges.yaml")
    exchanges = data.get("exchanges", {})
    by_alias: dict[str, str] = {}
    by_suffix: dict[str, str] = {}
    by_ciq: dict[str, str] = {}
    codes = list(exchanges.keys())
    for i in range(len(codes)):
        code = codes[i]
        entry = exchanges[code]
        by_alias[_clean_word(code)] = code
        by_alias[_clean_word(str(entry.get("name", code)))] = code
        aliases = entry.get("aliases") or []
        for j in range(len(aliases)):
            by_alias[_clean_word(str(aliases[j]))] = code
        suffixes = entry.get("suffixes") or []
        for j in range(len(suffixes)):
            by_suffix[str(suffixes[j]).upper()] = code
        symbols = entry.get("ciq_symbols") or []
        for j in range(len(symbols)):
            by_ciq[str(symbols[j]).upper()] = code
    classes = set()
    raw_classes = data.get("class_suffixes") or []
    for i in range(len(raw_classes)):
        classes.add(str(raw_classes[i]).upper())
    return ExchangeTable(by_alias=by_alias, by_suffix=by_suffix, by_ciq_symbol=by_ciq,
                         class_suffixes=classes, info=exchanges)


def exchange_code(text: str | None) -> str | None:
    """Map a free-text exchange ('Nasdaq', 'HKEX', 'Euronext Amsterdam') to a canonical code."""
    if text is None:
        return None
    table = exchange_table()
    cleaned = _clean_word(str(text))
    if cleaned == "":
        return None
    if cleaned in table.by_alias:
        return table.by_alias[cleaned]
    upper = str(text).strip().upper()
    if upper in table.by_ciq_symbol:
        return table.by_ciq_symbol[upper]
    if upper in table.by_suffix and len(upper) >= 2:
        return table.by_suffix[upper]
    # Longest alias contained in the text ("Nasdaq Global Select Market" -> nasdaq).
    best = None
    best_len = 0
    aliases = list(table.by_alias.keys())
    for i in range(len(aliases)):
        alias = aliases[i]
        if len(alias) >= 3 and (" " + alias + " ") in (" " + cleaned + " ") and len(alias) > best_len:
            best = table.by_alias[alias]
            best_len = len(alias)
    return best


def ticker_key(ticker: str | None) -> str | None:
    """Canonical comparison key: upper case, '.' as class separator, numeric codes unpadded."""
    if ticker is None:
        return None
    text = str(ticker).strip().upper().replace("$", "")
    text = re.sub(r"[\s/\-_]+", ".", text)
    text = text.strip(".")
    if text == "":
        return None
    if text.isdigit():
        stripped = text.lstrip("0")
        return stripped if stripped else "0"
    return text


@dataclass
class ParsedTicker:
    raw: str | None
    key: str | None
    exchange: str | None
    exchange_source: str | None    # suffix | prefix | field | None


def parse_ticker(raw_ticker: str | None, raw_exchange: str | None = None) -> ParsedTicker:
    """Split forms like 0700.HK, 600519.SS, NOVO-B.CO, ASML NA, HKG:0700, NASDAQ:MSFT."""
    table = exchange_table()
    exchange_from_field = exchange_code(raw_exchange)
    if raw_ticker is None or str(raw_ticker).strip() == "":
        return ParsedTicker(raw=raw_ticker, key=None, exchange=exchange_from_field,
                            exchange_source="field" if exchange_from_field else None)
    text = str(raw_ticker).strip().upper().replace("$", "")
    text = re.sub(r"\s+(EQUITY|US EQUITY)$", "", text)
    exchange = None
    source = None
    # Prefix form EXCH:TICKER, or TICKER:EXCH.
    if ":" in text:
        left, right = text.split(":", 1)
        left_code = exchange_code(left)
        right_code = exchange_code(right)
        if left_code is not None:
            exchange, text, source = left_code, right.strip(), "prefix"
        elif right_code is not None:
            exchange, text, source = right_code, left.strip(), "suffix"
    # Bloomberg form "ASML NA" / "700 HK".
    if exchange is None and " " in text:
        parts = text.split()
        last = parts[-1]
        if len(parts) >= 2 and last in table.by_suffix and last not in table.class_suffixes:
            exchange = table.by_suffix[last]
            text = " ".join(parts[:-1])
            source = "suffix"
    # Dot suffix form 0700.HK / NOVO-B.CO / BRK.B
    if exchange is None and "." in text:
        root, _, suffix = text.rpartition(".")
        if suffix in table.class_suffixes and not root.isdigit():
            pass  # share class: keep BRK.B intact
        elif suffix in table.by_suffix:
            exchange = table.by_suffix[suffix]
            text = root
            source = "suffix"
    if exchange is None and exchange_from_field is not None:
        exchange = exchange_from_field
        source = "field"
    elif exchange is not None and exchange_from_field is not None and exchange != exchange_from_field:
        # Suffix and field disagree: trust the ticker suffix, it is more specific.
        source = source + "+field_conflict"
    return ParsedTicker(raw=raw_ticker, key=ticker_key(text), exchange=exchange, exchange_source=source)


LEGAL_WORDS = [
    "incorporated", "inc", "corporation", "corp", "company", "co", "plc", "ltd", "limited", "ag", "sa", "nv",
    "se", "spa", "asa", "ab", "oyj", "as", "a s", "holdings", "holding", "group", "the", "class a", "class b",
    "class c", "adr", "ads", "ordinary shares", "common stock", "shares", "sponsored", "kgaa", "bhd", "tbk",
    "pjsc", "llc", "lp", "sab de cv", "de cv", "sab", "co ltd", "kabushiki kaisha", "kk",
]


def name_key(name: str | None) -> str:
    """Normalised company name for fuzzy matching."""
    if name is None:
        return ""
    text = str(name).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = " " + re.sub(r"\s+", " ", text).strip() + " "
    for i in range(len(LEGAL_WORDS)):
        text = text.replace(" " + LEGAL_WORDS[i] + " ", " ")
    return re.sub(r"\s+", " ", text).strip()
