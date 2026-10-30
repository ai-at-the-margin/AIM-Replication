"""Search-query classification (BUILD_BRIEF §8.6, Figure 7).

Classes: single_stock_check, screen_or_list, factor_or_market_data, macro_news,
other. Rules first; an optional LLM classifier can be plugged in. Agreement is
measured against a hand-labelled gold set with Cohen's kappa.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..resolve.normalise import name_key, ticker_key
from ..store.db import Store

CLASSES = ["single_stock_check", "screen_or_list", "factor_or_market_data", "macro_news", "other"]
FINANCE_RE = re.compile(r"^\s*finance:\s*([A-Za-z0-9.\-]+)", re.I)
FACTOR_RE = re.compile(r"\b(msci|acwi|s&p ?500|s&p|index|benchmark|factor|sector weights?|today'?s date|"
                       r"current date|what date|market level|dow jones|nasdaq composite|constituents)\b", re.I)
SCREEN_RE = re.compile(r"\b(best|top|highest|cheapest|leading|biggest|winners|screen(er)?|52[- ]week highs?|"
                       r"new highs|outperform\w*|ranked|list of|stocks to buy|momentum stocks|value stocks)\b", re.I)
MACRO_RE = re.compile(r"\b(econom\w*|inflation|interest rates?|federal reserve|fed|recession|gdp|outlook|"
                      r"central bank|tariffs?|geopolitic\w*)\b", re.I)
QUOTE_RE = re.compile(r"\b(stock price|share price|p/?e( ratio)?|market cap|earnings|quote|valuation|dividend|"
                      r"price to book|price target|12 month return|revenue|guidance)\b", re.I)
STOPWORDS = {"THE", "AND", "FOR", "TOP", "BEST", "USD", "ETF", "CEO", "AI", "PE", "P", "E", "IPO", "GDP", "MSCI",
             "ACWI", "ROE", "ROA", "YTD", "Q1", "Q2", "Q3", "Q4", "US", "UK", "EU", "S", "A", "IT", "ON", "ALL"}


class MentionIndex:
    """Ticker and company-name lookups for detecting which stock a query is about."""

    def __init__(self, master: pd.DataFrame | None, holdings: pd.DataFrame):
        self.by_ticker: dict[str, str] = {}
        self.by_name: dict[str, str] = {}
        self.by_first: dict[str, str] = {}
        frames = []
        if master is not None and len(master) > 0:
            frames.append(master[["ticker", "company_name", "issuer_id"]].rename(columns={"company_name": "name"}))
        if len(holdings) > 0:
            frames.append(holdings[["raw_ticker", "resolved_name", "issuer_id"]].rename(
                columns={"raw_ticker": "ticker", "resolved_name": "name"}))
        if len(frames) == 0:
            return
        frame = pd.concat(frames, ignore_index=True).dropna(subset=["issuer_id"])
        tickers = frame["ticker"].tolist()
        names = frame["name"].tolist()
        issuers = frame["issuer_id"].tolist()
        for i in range(len(issuers)):
            key = ticker_key(tickers[i])
            if key and len(key) >= 2 and key not in STOPWORDS:
                self.by_ticker.setdefault(key, str(issuers[i]))
                self.by_ticker.setdefault(key.split(".")[0], str(issuers[i]))
            nk = name_key(names[i])
            if nk:
                self.by_name.setdefault(nk, str(issuers[i]))
                first = nk.split()[0]
                if len(first) >= 5:
                    self.by_first.setdefault(first, str(issuers[i]))

    def find(self, query: str) -> list[str]:
        found: list[str] = []
        match = FINANCE_RE.match(query or "")
        if match:
            issuer = self.by_ticker.get(str(ticker_key(match.group(1))))
            if issuer:
                found.append(issuer)
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-]*", query or "")
        for i in range(len(tokens)):
            token = tokens[i]
            if token.isupper() and 2 <= len(token) <= 10:
                issuer = self.by_ticker.get(str(ticker_key(token)))
                if issuer and issuer not in found:
                    found.append(issuer)
        nk = name_key(query)
        words = nk.split()
        for i in range(len(words)):
            issuer = self.by_first.get(words[i])
            if issuer and issuer not in found:
                found.append(issuer)
            if i + 1 < len(words):
                issuer = self.by_name.get(words[i] + " " + words[i + 1])
                if issuer and issuer not in found:
                    found.append(issuer)
        return found


def classify_rule(query: str | None, mentions: list[str]) -> str:
    if query is None or str(query).strip() == "":
        return "other"
    text = str(query)
    if FINANCE_RE.match(text):
        return "single_stock_check"
    if len(mentions) > 0 and not SCREEN_RE.search(text.split(" ")[0] if text else ""):
        return "single_stock_check"
    if FACTOR_RE.search(text):
        return "factor_or_market_data"
    if SCREEN_RE.search(text):
        return "screen_or_list"
    if MACRO_RE.search(text):
        return "macro_news"
    if QUOTE_RE.search(text):
        return "single_stock_check"
    return "other"


def classify_all(store: Store, master: pd.DataFrame | None) -> dict[str, Any]:
    events = store.table("search_events")
    if len(events) == 0:
        return {"classified": 0}
    holdings = store.query("SELECT call_id, raw_ticker, resolved_name, issuer_id FROM holdings")
    index = MentionIndex(master, holdings)
    classes = []
    mentioned = []
    queries = events["query_text"].tolist()
    for i in range(len(queries)):
        found = index.find(queries[i] or "")
        classes.append(classify_rule(queries[i], found))
        mentioned.append(json.dumps(found))
    events["query_class"] = classes
    events["mentioned_tickers_json"] = mentioned
    events["class_method"] = "rules"
    store.upsert("search_events", events)
    return {"classified": len(events)}


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if len(a) == 0 or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b))
    position = {}
    for i in range(len(labels)):
        position[labels[i]] = i
    matrix = np.zeros((len(labels), len(labels)))
    for i in range(len(a)):
        matrix[position[a[i]], position[b[i]]] += 1
    total = matrix.sum()
    observed = np.trace(matrix) / total
    expected = float((matrix.sum(axis=0) * matrix.sum(axis=1)).sum() / (total * total))
    if expected >= 1.0:
        return 1.0
    return float((observed - expected) / (1.0 - expected))


def gold_agreement(store: Store, gold_path: Path) -> dict[str, Any]:
    if not gold_path.exists():
        return {"n": 0, "kappa": None, "note": "no gold file"}
    gold = pd.read_csv(gold_path, dtype=str).dropna(subset=["gold_class"])
    if len(gold) == 0:
        return {"n": 0, "kappa": None, "note": "gold file empty: label at least 200 queries"}
    events = store.query("SELECT call_id, event_idx, query_class FROM search_events")
    events["event_idx"] = events["event_idx"].astype(str)
    gold["event_idx"] = gold["event_idx"].astype(str)
    merged = gold.merge(events, on=["call_id", "event_idx"], how="inner")
    kappa = cohen_kappa(merged["gold_class"].tolist(), merged["query_class"].tolist())
    accuracy = float((merged["gold_class"] == merged["query_class"]).mean()) if len(merged) else None
    labellers = sorted(gold["labeller"].dropna().unique().tolist()) if "labeller" in gold.columns else []
    return {"n": int(len(merged)), "kappa": kappa, "accuracy": accuracy, "labellers": labellers,
            "meets_minimum": len(merged) >= 200}


def query_analysis(store: Store, gold_path: Path) -> dict[str, Any]:
    events = store.query(
        "SELECT s.*, c.provider, c.model_requested, c.prompt_id, c.stage, c.search_tool_version "
        "FROM search_events s JOIN calls c USING (call_id) WHERE c.stage = 'C'")
    out: dict[str, Any] = {"classes": CLASSES}
    if len(events) == 0:
        out["by_prompt"] = []
        return out
    visible = events[events["query_visible"] == True]  # noqa: E712
    rows = []
    prompts = ["L1", "L2", "L3", "L4", "VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"]
    for p in range(len(prompts)):
        cell = visible[visible["prompt_id"] == prompts[p]]
        if len(cell) == 0:
            continue
        row: dict[str, Any] = {"prompt_id": prompts[p], "n": int(len(cell))}
        for c in range(len(CLASSES)):
            row[CLASSES[c]] = float((cell["query_class"] == CLASSES[c]).mean())
        rows.append(row)
    out["by_prompt"] = rows
    by_provider = []
    providers = sorted(visible["provider"].dropna().unique().tolist())
    for p in range(len(providers)):
        cell = visible[visible["provider"] == providers[p]]
        row = {"provider": providers[p], "n": int(len(cell))}
        for c in range(len(CLASSES)):
            row[CLASSES[c]] = float((cell["query_class"] == CLASSES[c]).mean())
        by_provider.append(row)
    out["by_provider"] = by_provider
    holdings = store.query("SELECT call_id, issuer_id FROM holdings WHERE issuer_id IS NOT NULL")
    books: dict[str, set[str]] = {}
    calls = holdings["call_id"].tolist()
    issuers = holdings["issuer_id"].tolist()
    for i in range(len(calls)):
        books.setdefault(calls[i], set()).add(str(issuers[i]))
    lookup_rows = []
    singles = visible[visible["query_class"] == "single_stock_check"]
    for p in range(len(providers)):
        cell = singles[singles["provider"] == providers[p]]
        hits = 0
        total = 0
        ids = cell["call_id"].tolist()
        mentions = cell["mentioned_tickers_json"].tolist()
        for i in range(len(ids)):
            found = json.loads(mentions[i] or "[]")
            if len(found) == 0:
                continue
            total += 1
            if str(found[0]) in books.get(ids[i], set()):
                hits += 1
        lookup_rows.append({"provider": providers[p], "lookups_with_named_stock": total,
                            "in_final_book": hits, "share": hits / total if total else None})
    out["lookup_to_portfolio"] = lookup_rows
    first_screen_before = 0
    both = 0
    grouped = visible.sort_values("event_idx").groupby("call_id")
    keys = list(grouped.groups.keys())
    for k in range(len(keys)):
        classes = grouped.get_group(keys[k])["query_class"].tolist()
        screen_pos = None
        single_pos = None
        for i in range(len(classes)):
            if classes[i] == "screen_or_list" and screen_pos is None:
                screen_pos = i
            if classes[i] == "single_stock_check" and single_pos is None:
                single_pos = i
        if screen_pos is not None and single_pos is not None:
            both += 1
            if screen_pos < single_pos:
                first_screen_before += 1
    p_value = float(stats.binomtest(first_screen_before, both, 0.5).pvalue) if both > 0 else None
    out["ordering"] = {"calls_with_both": both, "screen_first": first_screen_before,
                       "share_screen_first": first_screen_before / both if both else None, "p_binomial": p_value}
    anthropic = events[events["provider"] == "anthropic"]
    tool_rows = []
    versions = sorted(anthropic["search_tool_version"].dropna().unique().tolist())
    for v in range(len(versions)):
        cell = anthropic[anthropic["search_tool_version"] == versions[v]]
        tool_rows.append({"tool_version": versions[v], "events": int(len(cell)),
                          "calls": int(cell["call_id"].nunique()),
                          "share_with_caller": float(cell["caller"].notna().mean()) if len(cell) else None,
                          "share_errors": float(cell["error_code"].notna().mean()) if len(cell) else None})
    out["anthropic_tool_versions"] = tool_rows
    out["gold"] = gold_agreement(store, gold_path)
    return out
