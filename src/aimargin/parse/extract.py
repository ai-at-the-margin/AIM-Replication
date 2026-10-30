"""Extract the proposed portfolio from a model's final text.

Order of attempts:
1. The **last** JSON block that contains a portfolio (fenced or bare).
2. Deterministic fallback: a markdown table with a ticker column.
3. Deterministic fallback: a numbered / bulleted list ``Name (TICKER) - 12%``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..utils import to_float

FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_-]*)[ \t]*\n?(.*?)```", re.S)
TICKER_KEYS = ["ticker", "symbol", "tic", "code", "stock_ticker"]
EXCHANGE_KEYS = ["exchange", "market", "listing", "venue", "exchange_name"]
NAME_KEYS = ["company", "name", "company_name", "security", "stock"]
WEIGHT_KEYS = ["weight_pct", "weight", "weight_percent", "allocation_pct", "allocation", "percent", "pct", "weighting"]
AMOUNT_KEYS = ["amount", "amount_usd", "usd", "dollars", "investment"]


@dataclass
class RawHolding:
    position_idx: int
    ticker: str | None
    exchange: str | None
    name: str | None
    weight: float | None


@dataclass
class ExtractResult:
    holdings: list[RawHolding]
    method: str                    # json | fallback_table | fallback_list | none
    n_json_blocks: int = 0
    notes: list[str] = field(default_factory=list)


def lenient_json(text: str) -> Any:
    """json.loads with repairs for the usual LLM slips (smart quotes, trailing commas, comments)."""
    candidate = text.strip()
    if candidate.lower().startswith("json"):
        candidate = candidate[4:].strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass
    repaired = candidate.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    repaired = re.sub(r"//[^\n]*", "", repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    try:
        return json.loads(repaired)
    except Exception:
        pass
    if "'" in repaired and '"' not in repaired:
        try:
            return json.loads(repaired.replace("'", '"'))
        except Exception:
            pass
    return None


def _balanced_objects(text: str, anchor: str) -> list[str]:
    """Every balanced {...} object that starts at the brace before ``anchor``."""
    found: list[str] = []
    start = 0
    while True:
        index = text.find(anchor, start)
        if index < 0:
            break
        brace = text.rfind("{", 0, index)
        if brace < 0:
            start = index + 1
            continue
        depth = 0
        in_string = False
        escape = False
        end = -1
        for k in range(brace, len(text)):
            char = text[k]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end > brace:
            found.append(text[brace:end + 1])
        start = index + 1
    return found


def json_candidates(text: str) -> list[str]:
    """Fenced blocks first (in document order), then bare objects containing "portfolio"."""
    out: list[str] = []
    matches = FENCE_RE.findall(text or "")
    for i in range(len(matches)):
        body = matches[i][1]
        if "{" in body or "[" in body:
            out.append(body)
    if len(out) == 0:
        bare = _balanced_objects(text or "", '"portfolio"')
        for i in range(len(bare)):
            out.append(bare[i])
    return out


def _pick(item: dict[str, Any], keys: list[str]) -> Any:
    lowered: dict[str, Any] = {}
    item_keys = list(item.keys())
    for i in range(len(item_keys)):
        lowered[str(item_keys[i]).strip().lower()] = item[item_keys[i]]
    for i in range(len(keys)):
        if keys[i] in lowered and lowered[keys[i]] not in (None, ""):
            return lowered[keys[i]]
    return None


def holdings_from_obj(obj: Any) -> list[RawHolding]:
    rows: Any = None
    if isinstance(obj, dict):
        for key in ("portfolio", "holdings", "positions", "stocks"):
            if isinstance(obj.get(key), list):
                rows = obj[key]
                break
    elif isinstance(obj, list):
        rows = obj
    if not isinstance(rows, list):
        return []
    holdings: list[RawHolding] = []
    amounts: list[float | None] = []
    for i in range(len(rows)):
        item = rows[i]
        if not isinstance(item, dict):
            continue
        ticker = _pick(item, TICKER_KEYS)
        name = _pick(item, NAME_KEYS)
        if ticker is None and name is None:
            continue
        weight = to_float(_pick(item, WEIGHT_KEYS))
        amounts.append(to_float(_pick(item, AMOUNT_KEYS)))
        exchange = _pick(item, EXCHANGE_KEYS)
        holdings.append(RawHolding(
            position_idx=len(holdings),
            ticker=str(ticker).strip() if ticker is not None else None,
            exchange=str(exchange).strip() if exchange is not None else None,
            name=str(name).strip() if name is not None else None,
            weight=weight,
        ))
    _rescale_weights(holdings, amounts)
    return holdings


def _rescale_weights(holdings: list[RawHolding], amounts: list[float | None]) -> None:
    """Fractions (sum ~1) become percentages; dollar amounts become percentages."""
    weights: list[float] = []
    for i in range(len(holdings)):
        if holdings[i].weight is not None:
            weights.append(holdings[i].weight)
    if len(weights) == len(holdings) and len(weights) > 0:
        total = sum(weights)
        if 0.9 <= total <= 1.1:
            for i in range(len(holdings)):
                holdings[i].weight = holdings[i].weight * 100.0
        elif total > 1000.0:
            for i in range(len(holdings)):
                holdings[i].weight = holdings[i].weight * 100.0 / total
        return
    usable: list[float] = []
    for i in range(len(amounts)):
        if amounts[i] is not None and amounts[i] > 0:
            usable.append(amounts[i])
    if len(usable) == len(holdings) and len(holdings) > 0 and len(weights) == 0:
        total = sum(usable)
        for i in range(len(holdings)):
            holdings[i].weight = amounts[i] * 100.0 / total


TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
LIST_PATTERNS = [
    # 1. **Microsoft** (MSFT, NASDAQ) - 12%   /  - Apple Inc. (AAPL): 10%
    re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+\**(?P<name>[^(\n*|]+?)\**\s*\((?P<ticker>[A-Za-z0-9.\-:]{1,15})"
               r"(?:\s*[,;/]\s*(?P<exch>[^)]+))?\)\**\s*[-–—:|]*\s*(?:\**\s*)?(?P<weight>\d+(?:\.\d+)?)?\s*%?"),
    # 1. MSFT - Microsoft - 12%
    re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+\**(?P<ticker>[A-Z0-9.\-]{1,12})\**\s*[-–—:]\s*(?P<name>[^\n\-–—:]+?)"
               r"\s*[-–—:]\s*(?P<weight>\d+(?:\.\d+)?)\s*%"),
]


def _split_row(line: str) -> list[str]:
    match = TABLE_ROW_RE.match(line)
    if match is None:
        return []
    parts = match.group(1).split("|")
    out = []
    for i in range(len(parts)):
        out.append(parts[i].strip().strip("*").strip())
    return out


def holdings_from_table(text: str) -> list[RawHolding]:
    lines = (text or "").splitlines()
    best: list[RawHolding] = []
    i = 0
    while i < len(lines):
        header = _split_row(lines[i])
        lowered = []
        for k in range(len(header)):
            lowered.append(header[k].lower())
        ticker_col = -1
        for k in range(len(lowered)):
            if "ticker" in lowered[k] or "symbol" in lowered[k]:
                ticker_col = k
                break
        if ticker_col < 0:
            i += 1
            continue
        name_col = -1
        exch_col = -1
        weight_col = -1
        for k in range(len(lowered)):
            if name_col < 0 and ("company" in lowered[k] or lowered[k] == "name" or "stock" in lowered[k]) and k != ticker_col:
                name_col = k
            if exch_col < 0 and ("exchange" in lowered[k] or "market" in lowered[k] or "listing" in lowered[k]):
                exch_col = k
            if weight_col < 0 and ("weight" in lowered[k] or "%" in lowered[k] or "alloc" in lowered[k]):
                weight_col = k
        rows: list[RawHolding] = []
        amounts: list[float | None] = []
        j = i + 1
        while j < len(lines):
            cells = _split_row(lines[j])
            if len(cells) == 0:
                break
            joined = "".join(cells).replace("-", "").replace(":", "").strip()
            if joined == "":
                j += 1
                continue
            if ticker_col >= len(cells):
                j += 1
                continue
            ticker = cells[ticker_col] or None
            if ticker is not None and ticker.lower() in ("total", ""):
                j += 1
                continue
            weight = to_float(cells[weight_col]) if 0 <= weight_col < len(cells) else None
            rows.append(RawHolding(
                position_idx=len(rows), ticker=ticker,
                exchange=cells[exch_col] if 0 <= exch_col < len(cells) else None,
                name=cells[name_col] if 0 <= name_col < len(cells) else None,
                weight=weight,
            ))
            amounts.append(None)
            j += 1
        if len(rows) > len(best):
            _rescale_weights(rows, amounts)
            best = rows
        i = j
    return best


def holdings_from_list(text: str) -> list[RawHolding]:
    lines = (text or "").splitlines()
    rows: list[RawHolding] = []
    for i in range(len(lines)):
        for p in range(len(LIST_PATTERNS)):
            match = LIST_PATTERNS[p].match(lines[i])
            if match is None:
                continue
            groups = match.groupdict()
            ticker = (groups.get("ticker") or "").strip() or None
            if ticker is not None and ":" in ticker:
                ticker = ticker.split(":")[-1]
            rows.append(RawHolding(
                position_idx=len(rows), ticker=ticker, exchange=(groups.get("exch") or "").strip() or None,
                name=(groups.get("name") or "").strip() or None, weight=to_float(groups.get("weight")),
            ))
            break
    amounts: list[float | None] = []
    for _i in range(len(rows)):
        amounts.append(None)
    _rescale_weights(rows, amounts)
    return rows


def extract_portfolio(text: str | None) -> ExtractResult:
    if text is None or text.strip() == "":
        return ExtractResult(holdings=[], method="none", notes=["empty text"])
    candidates = json_candidates(text)
    notes: list[str] = []
    for k in range(len(candidates) - 1, -1, -1):
        obj = lenient_json(candidates[k])
        if obj is None:
            notes.append(f"json block {k} unparseable")
            continue
        holdings = holdings_from_obj(obj)
        if len(holdings) > 0:
            return ExtractResult(holdings=holdings, method="json", n_json_blocks=len(candidates), notes=notes)
    table = holdings_from_table(text)
    if len(table) >= 3:
        return ExtractResult(holdings=table, method="fallback_table", n_json_blocks=len(candidates), notes=notes)
    listed = holdings_from_list(text)
    if len(listed) >= 3:
        return ExtractResult(holdings=listed, method="fallback_list", n_json_blocks=len(candidates), notes=notes)
    return ExtractResult(holdings=[], method="none", n_json_blocks=len(candidates), notes=notes)
