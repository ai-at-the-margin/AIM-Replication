"""Simulated LLM transport for the demo workspace.

``SimulatedTransport`` answers the same HTTP calls the real adapters make
(``POST /responses``, ``POST /messages``, ``GET /models``) with payloads in each
provider's wire format, so normalisation, retries, pause_turn continuation,
refusal handling, parsing and resolution all run exactly as they would live.

Behavioural profiles are invented for illustration. They are loosely shaped like
the patterns the paper reports (high overlap on bare requests, stale momentum
offline, uneven search invocation) so the dashboard has structure to show.
Nothing here describes how any real model behaves.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from ..prompts import FREEFORM_IDS, MANDATE_IDS, build_prompt
from ..providers.base import CALL_CONTEXT, Transport, TransportError, TransportResponse
from ..settings import Config
from .world import LoadedWorld

PROFILES: dict[str, dict[str, Any]] = {
    "gpt-6-astra": {"knowledge": "2026-05-31", "temp": 0.55, "refuse_l1": 0.08, "fmt": 0.008,
                    "search": {"L": 1.0, "VALUE": 1.0, "QUALITY": 1.0, "MOMENTUM": 1.0, "UNCONSTRAINED": 1.0},
                    "searches": (4, 9), "reason_words": (260, 640), "adr": 0.55, "style": "conviction"},
    "gpt-6.1-sol": {"knowledge": "2026-06-30", "temp": 0.6, "refuse_l1": 0.12, "fmt": 0.01,
                    "search": {"L": 0.35, "VALUE": 0.55, "QUALITY": 0.3, "MOMENTUM": 1.0, "UNCONSTRAINED": 0.4},
                    "searches": (3, 7), "reason_words": (180, 480), "adr": 0.6, "style": "conviction"},
    "gpt-6.1-terra": {"knowledge": "2026-06-30", "temp": 0.7, "refuse_l1": 0.18, "fmt": 0.015,
                      "searches": (2, 5), "reason_words": (120, 360), "adr": 0.65, "style": "round"},
    "gpt-6-luna": {"knowledge": "2026-03-31", "temp": 0.95, "refuse_l1": 0.32, "fmt": 0.03,
                   "searches": (1, 4), "reason_words": (60, 220), "adr": 0.75, "style": "equal"},
    "gpt-5.6-sol": {"knowledge": "2026-02-28", "temp": 0.65, "refuse_l1": 0.2, "fmt": 0.012,
                    "searches": (2, 6), "reason_words": (150, 420), "adr": 0.6, "style": "conviction"},
    "gpt-5.5": {"knowledge": "2025-10-31", "temp": 0.75, "refuse_l1": 0.28, "fmt": 0.02,
                "searches": (2, 5), "reason_words": (120, 380), "adr": 0.65, "style": "round"},
    "chat-latest": {"knowledge": "2026-06-30", "temp": 0.7, "refuse_l1": 0.2, "fmt": 0.01,
                    "searches": (2, 5), "reason_words": (100, 300), "adr": 0.7, "style": "round"},
    "claude-fable-5-1": {"knowledge": "2026-06-30", "temp": 0.4, "refuse_l1": 0.22, "fmt": 0.006,
                         "search": {"L1": 0.12, "L": 0.0, "VALUE": 0.0, "QUALITY": 0.0, "MOMENTUM": 1.0,
                                    "UNCONSTRAINED": 0.0},
                         "searches": (5, 10), "reason_words": (420, 980), "adr": 0.5, "style": "conviction",
                         "thinking": True},
    "claude-opus-5-5": {"knowledge": "2026-06-30", "temp": 0.5, "refuse_l1": 0.3, "fmt": 0.008,
                        "search": {"L": 1.0, "VALUE": 0.0, "QUALITY": 0.0, "MOMENTUM": 0.0, "UNCONSTRAINED": 0.0},
                        "searches": (3, 8), "reason_words": (250, 700), "adr": 0.55, "style": "conviction",
                        "thinking": True},
    "claude-sonnet-5-5": {"knowledge": "2026-03-31", "temp": 0.65, "refuse_l1": 0.35, "fmt": 0.012,
                          "searches": (2, 6), "reason_words": (150, 420), "adr": 0.6, "style": "round"},
    "claude-haiku-5-5": {"knowledge": "2026-01-31", "temp": 0.9, "refuse_l1": 0.45, "fmt": 0.025,
                         "searches": (1, 4), "reason_words": (60, 200), "adr": 0.7, "style": "equal"},
    "claude-fable-5": {"knowledge": "2026-01-31", "temp": 0.5, "refuse_l1": 0.3, "fmt": 0.01,
                       "searches": (3, 7), "reason_words": (300, 800), "adr": 0.55, "style": "conviction",
                       "thinking": True},
    "claude-opus-4-8": {"knowledge": "2025-09-30", "temp": 0.7, "refuse_l1": 0.38, "fmt": 0.015,
                        "searches": (2, 6), "reason_words": (160, 420), "adr": 0.6, "style": "round"},
}

FRAMING = {
    "L1": {"fam": 4.4, "size": 0.6, "global": -0.4, "cap": 10, "quality": 0.0},
    "L2": {"fam": 3.6, "size": 0.55, "global": -0.25, "cap": 4, "quality": 0.0},
    "L3": {"fam": 2.7, "size": 0.45, "global": 0.45, "cap": 3, "quality": 0.2},
    "L4": {"fam": 2.3, "size": 0.35, "global": 0.85, "cap": 3, "quality": 0.4},
    "VALUE": {"fam": 1.8, "size": 0.3, "global": 0.6, "cap": 3, "quality": -0.2},
    "QUALITY": {"fam": 2.0, "size": 0.35, "global": 0.6, "cap": 3, "quality": 0.55},
    "MOMENTUM": {"fam": 1.9, "size": 0.3, "global": 0.5, "cap": 3, "quality": 0.1},
    "UNCONSTRAINED": {"fam": 2.1, "size": 0.35, "global": 0.7, "cap": 3, "quality": 0.4},
}

QUERY_MIX = {
    "VALUE": [("single_stock_check", 0.80), ("screen_or_list", 0.09), ("factor_or_market_data", 0.07),
              ("macro_news", 0.01), ("other", 0.03)],
    "QUALITY": [("single_stock_check", 0.35), ("screen_or_list", 0.05), ("factor_or_market_data", 0.35),
                ("macro_news", 0.0), ("other", 0.25)],
    "MOMENTUM": [("single_stock_check", 0.49), ("screen_or_list", 0.17), ("factor_or_market_data", 0.23),
                 ("macro_news", 0.01), ("other", 0.10)],
    "UNCONSTRAINED": [("single_stock_check", 0.76), ("screen_or_list", 0.05), ("factor_or_market_data", 0.02),
                      ("macro_news", 0.12), ("other", 0.05)],
    "FREEFORM": [("single_stock_check", 0.55), ("screen_or_list", 0.2), ("factor_or_market_data", 0.1),
                 ("macro_news", 0.1), ("other", 0.05)],
}

EXCHANGE_DISPLAY = {
    "XNAS": "NASDAQ", "XNYS": "NYSE", "XASE": "NYSE American", "XTSE": "TSX", "XLON": "London Stock Exchange",
    "XETR": "Xetra", "XPAR": "Euronext Paris", "XAMS": "Euronext Amsterdam", "XMIL": "Borsa Italiana",
    "XMAD": "BME", "XSWX": "SIX Swiss Exchange", "XCSE": "Nasdaq Copenhagen", "XSTO": "Nasdaq Stockholm",
    "XHEL": "Nasdaq Helsinki", "XOSL": "Oslo Bors", "XTKS": "Tokyo Stock Exchange", "XHKG": "HKEX",
    "XSHG": "Shanghai Stock Exchange", "XSHE": "Shenzhen Stock Exchange", "XTAI": "TWSE", "XKRX": "KRX",
    "XNSE": "NSE", "XASX": "ASX", "XSES": "SGX", "XJSE": "JSE", "BVMF": "B3", "XMEX": "BMV", "XSAU": "Tadawul",
}
EXCHANGE_SUFFIX = {
    "XTSE": "TO", "XLON": "L", "XETR": "DE", "XPAR": "PA", "XAMS": "AS", "XMIL": "MI", "XMAD": "MC", "XSWX": "SW",
    "XCSE": "CO", "XSTO": "ST", "XHEL": "HE", "XOSL": "OL", "XTKS": "T", "XHKG": "HK", "XSHG": "SS", "XSHE": "SZ",
    "XTAI": "TW", "XKRX": "KS", "XNSE": "NS", "XASX": "AX", "XSES": "SI", "XJSE": "JO", "BVMF": "SA", "XMEX": "MX",
    "XSAU": "SR",
}
SECTOR_WORDS = {"10": "energy", "15": "materials", "20": "industrial", "25": "consumer", "30": "staples",
                "35": "healthcare", "40": "financial", "45": "technology", "50": "communication",
                "55": "utility", "60": "real-estate"}


def _seed(*parts: Any) -> int:
    text = json.dumps(parts, default=str)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:15], 16)


def _search_prob(profile: dict[str, Any], prompt_id: str) -> float:
    table = profile.get("search")
    if table is None:
        return 0.3
    if prompt_id in table:
        return float(table[prompt_id])
    if prompt_id.startswith("L"):
        return float(table.get("L", 0.3))
    return 0.3


class SimulatedTransport(Transport):
    name = "simulated"

    def __init__(self, config: Config, world: LoadedWorld, asof: dt.date, error_rate: float = 0.03):
        self.config = config
        self.world = world
        self.asof = asof
        self.error_rate = error_rate
        self.pending: dict[str, list[dict[str, Any]]] = {}
        self.counters: dict[str, int] = {}
        self.gold: dict[tuple[str, str], str] = {}
        self.prompt_lookup: dict[str, tuple[str, str]] = {}
        for i in range(len(FREEFORM_IDS)):
            for language in ("en", "zh"):
                self.prompt_lookup[build_prompt(config, FREEFORM_IDS[i], language).text] = (FREEFORM_IDS[i], language)
        for i in range(len(MANDATE_IDS)):
            self.prompt_lookup[build_prompt(config, MANDATE_IDS[i], "en").text] = (MANDATE_IDS[i], "en")
        self._prepare_world()
        self.knowledge_cache: dict[str, dict[str, np.ndarray]] = {}

    # ------------------------------------------------------------ world views
    def _prepare_world(self) -> None:
        w = self.world
        companies = w.company_frame.reset_index(drop=True)
        self.n = len(companies)
        self.fam = companies["familiarity"].to_numpy(dtype=float)
        self.sector = companies["gsector"].astype(str).to_numpy()
        self.country = companies["country"].astype(str).to_numpy()
        self.names = companies["name"].astype(str).to_numpy()
        self.gvkeys = companies["gvkey"].astype(str).to_numpy()
        self.value = w.traits["value_trait"].to_numpy(dtype=float)
        self.quality = w.traits["quality_trait"].to_numpy(dtype=float)
        self.mom_now = self._z(w.momentum_at(w.r_usd.index[-1]).to_numpy(dtype=float))
        master = w.master
        self.listings: dict[str, list[dict[str, Any]]] = {}
        rows = master.to_dict("records")
        for i in range(len(rows)):
            self.listings.setdefault(str(rows[i]["gvkey"]), []).append(rows[i])
        self.mcap_now = w.mcap_at(w.r_usd.index[-1]).to_numpy(dtype=float)

    @staticmethod
    def _z(values: np.ndarray) -> np.ndarray:
        clean = np.where(np.isfinite(values), values, np.nanmedian(values))
        sd = np.std(clean)
        if sd <= 0:
            return np.zeros_like(clean)
        return (clean - np.mean(clean)) / sd

    def _knowledge(self, model: str) -> dict[str, np.ndarray]:
        if model in self.knowledge_cache:
            return self.knowledge_cache[model]
        profile = PROFILES.get(model, PROFILES["gpt-6.1-sol"])
        date = pd.Timestamp(profile["knowledge"])
        index = self.world.r_usd.index
        if date > index[-1]:
            date = index[-1]
        mom = self._z(self.world.momentum_at(date).to_numpy(dtype=float))
        mcap = self.world.mcap_at(date).to_numpy(dtype=float)
        rng = np.random.default_rng(_seed("taste", model))
        provider = "anthropic" if model.startswith("claude") else "openai"
        prng = np.random.default_rng(_seed("taste", provider))
        taste = rng.normal(0.0, 0.32, self.n) + prng.normal(0.0, 0.25, self.n)
        value_known = self.value + rng.normal(0.0, 0.55, self.n)
        out = {"mom": mom, "mcap": mcap, "taste": taste, "value": value_known}
        self.knowledge_cache[model] = out
        return out

    # ---------------------------------------------------------------- routing
    async def request(self, method: str, url: str, headers: dict[str, str], json_body: Any = None,
                      content: bytes | None = None, files: Any = None, data: Any = None) -> TransportResponse:
        if method == "GET" and url.endswith("/models"):
            ids = []
            models = self.config.model_list(include_optional=True)
            for i in range(len(models)):
                ids.append({"id": models[i]["id"], "object": "model"})
            return TransportResponse(200, {}, {"data": ids}, json.dumps({"data": ids}))
        context = CALL_CONTEXT.get() or {}
        call_id = str(context.get("call_id") or self._fallback_id(json_body))
        attempt = int(context.get("attempt") or 1)
        rng = np.random.default_rng(_seed("err", call_id, attempt))
        if attempt == 1 and rng.random() < self.error_rate:
            status = 429 if rng.random() < 0.7 else 529
            raise TransportError(f"HTTP {status}: simulated {'rate limit' if status == 429 else 'overloaded'}",
                                 status=status, retry_after=0.01, retryable=True)
        if url.endswith("/responses"):
            body = self._openai(json_body, call_id, context)
        elif url.endswith("/messages"):
            body = self._anthropic(json_body, call_id, context)
        else:
            raise TransportError(f"HTTP 404: simulated transport has no route for {url}", status=404,
                                 retryable=False)
        return TransportResponse(200, {}, body, "")

    def _fallback_id(self, body: Any) -> str:
        key = json.dumps(body, sort_keys=True, default=str)[:4000]
        count = self.counters.get(key, 0)
        self.counters[key] = count + 1
        return hashlib.sha256((key + str(count)).encode()).hexdigest()[:16]

    # ---------------------------------------------------------------- answers
    def _prompt_of(self, text: str, context: dict[str, Any]) -> tuple[str, str]:
        if text in self.prompt_lookup:
            return self.prompt_lookup[text]
        return str(context.get("prompt_id") or "L1"), str(context.get("language") or "en")

    def _answer(self, model: str, prompt_text: str, search_available: bool, call_id: str,
                context: dict[str, Any]) -> dict[str, Any]:
        """Decide the outcome, holdings, searches and texts for one call."""
        prompt_id, language = self._prompt_of(prompt_text, context)
        profile = PROFILES.get(model, PROFILES["gpt-6.1-sol"])
        rng = np.random.default_rng(_seed("call", call_id))
        invoked = search_available and rng.random() < _search_prob(profile, prompt_id)
        refuse_p = float(profile["refuse_l1"]) if prompt_id == "L1" else 0.012
        if prompt_id == "L2":
            refuse_p = float(profile["refuse_l1"]) * 0.12
        if language == "zh" and prompt_id == "L1":
            refuse_p = min(0.9, refuse_p * 1.4)
        outcome = "valid"
        draw = rng.random()
        if draw < refuse_p:
            outcome = "refusal"
        elif draw < refuse_p + float(profile["fmt"]):
            outcome = "format_failure"
        elif draw < refuse_p + float(profile["fmt"]) + 0.008:
            outcome = "nine_names"
        picks = self._pick(model, prompt_id, language, invoked, rng)
        searches = self._searches(model, prompt_id, picks, rng, profile) if invoked else []
        for k in range(len(searches)):
            self.gold[(call_id, searches[k]["query"])] = searches[k]["kind"]
        return {"prompt_id": prompt_id, "language": language, "outcome": outcome, "picks": picks,
                "searches": searches, "invoked": invoked, "profile": profile, "rng": rng}

    def _pick(self, model: str, prompt_id: str, language: str, searched: bool,
              rng: np.random.Generator) -> list[int]:
        profile = PROFILES.get(model, PROFILES["gpt-6.1-sol"])
        know = self._knowledge(model)
        frame = FRAMING.get(prompt_id, FRAMING["L4"])
        fam_weight = frame["fam"] * (1.25 if profile.get("style") == "equal" else 1.0)
        mcap = self.mcap_now if searched else know["mcap"]
        score = fam_weight * np.log(self.fam + 0.02) + frame["size"] * np.log(np.maximum(mcap, 0.05))
        score += know["taste"]
        score += frame["global"] * (self.country != "USA")
        score += frame["quality"] * self.quality
        if prompt_id == "VALUE":
            score += 1.05 * know["value"] - 0.25 * self.quality
        elif prompt_id == "MOMENTUM":
            if searched:
                score += 1.25 * self.mom_now + 0.3 * self.fam
            else:
                score += 1.2 * know["mom"] + 0.9 * self.fam
        if language == "zh":
            score += 1.1 * np.isin(self.country, ["CHN", "HKG"])
        if prompt_id in MANDATE_IDS:
            score = np.where(mcap >= 5.5, score, -np.inf)
        temp = float(profile["temp"])
        noisy = score + temp * rng.gumbel(size=self.n)
        order = np.argsort(-noisy)
        cap = int(frame["cap"])
        chosen: list[int] = []
        per_sector: dict[str, int] = {}
        for k in range(len(order)):
            idx = int(order[k])
            if not np.isfinite(noisy[idx]):
                break
            sector = self.sector[idx]
            if per_sector.get(sector, 0) >= cap:
                continue
            chosen.append(idx)
            per_sector[sector] = per_sector.get(sector, 0) + 1
            if len(chosen) == 10:
                break
        return chosen

    def _listing_for(self, company: int, prompt_id: str, profile: dict[str, Any],
                     rng: np.random.Generator) -> tuple[str, str, str]:
        """(ticker string, exchange string, company name) as a model might write them."""
        lines = self.listings.get(self.gvkeys[company], [])
        primary = None
        us_lines = []
        for i in range(len(lines)):
            if lines[i]["is_primary"]:
                primary = lines[i]
            if lines[i]["exchange_code"] in ("XNYS", "XNAS", "XASE") and not lines[i]["is_primary"]:
                us_lines.append(lines[i])
        if primary is None and len(lines) > 0:
            primary = lines[0]
        name = self.names[company]
        if rng.random() < 0.5:
            for suffix in (", Inc.", " Inc.", " Corporation", " plc", " PLC", " Limited", " Ltd.", " S.A.", " SE",
                           " AG", " N.V.", " Co., Ltd."):
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
        adr_p = float(profile.get("adr", 0.6)) * (1.2 if prompt_id in ("L1", "L2") else 0.8)
        line = primary
        if len(us_lines) > 0 and rng.random() < adr_p:
            line = us_lines[0]
        ticker = str(line["ticker"])
        exchange = str(line["exchange_code"])
        if ticker == "GOOGL" and rng.random() < 0.2:
            ticker = "GOOG"
        if ticker == "BRK.B" and rng.random() < 0.4:
            ticker = "BRK-B"
        if ticker == "NOVO.B":
            ticker = "NOVO-B"
        display = EXCHANGE_DISPLAY.get(exchange, exchange)
        suffix = EXCHANGE_SUFFIX.get(exchange)
        form = rng.random()
        if suffix and form < 0.5:
            return f"{ticker}.{suffix}", display, name
        if suffix and form < 0.58:
            short = ticker.lstrip("0") if ticker.isdigit() and exchange == "XHKG" else ticker
            return f"{short} {suffix if len(suffix) == 2 else exchange[1:3]}", display if rng.random() < 0.5 else "", name
        return ticker, display, name

    def _weights(self, n: int, profile: dict[str, Any], prompt_id: str, rng: np.random.Generator) -> list[float | None]:
        style = profile.get("style", "conviction")
        if style == "equal" or (prompt_id == "L1" and rng.random() < 0.4):
            raw = np.full(n, 100.0 / n)
        else:
            raw = np.exp(rng.normal(0.0, 0.35, n))
            raw = raw / raw.sum() * 100.0
        if prompt_id in MANDATE_IDS and rng.random() > 0.08:
            raw = np.clip(raw, 5.0, 15.0)
            raw = raw / raw.sum() * 100.0
        step = 5.0 if style == "round" else 1.0
        rounded = np.round(raw / step) * step
        rounded = np.where(rounded <= 0, step, rounded)
        rounded[-1] = rounded[-1] + (100.0 - rounded.sum())
        if rounded[-1] <= 0:
            rounded = np.full(n, 100.0 / n)
        out: list[float | None] = []
        for i in range(n):
            out.append(float(round(rounded[i], 2)))
        if rng.random() < 0.025:
            out[int(rng.integers(0, n))] = None
        return out

    def _searches(self, model: str, prompt_id: str, picks: list[int], rng: np.random.Generator,
                  profile: dict[str, Any]) -> list[dict[str, Any]]:
        lo, hi = profile.get("searches", (2, 6))
        n = int(rng.integers(lo, hi + 1))
        mix = QUERY_MIX.get(prompt_id, QUERY_MIX["FREEFORM"])
        classes = []
        probs = []
        for i in range(len(mix)):
            classes.append(mix[i][0])
            probs.append(mix[i][1])
        probs_arr = np.array(probs) / np.sum(probs)
        events = []
        others = []
        know = self._knowledge(model)
        alternative = np.argsort(-(know["taste"] + 2.0 * np.log(self.fam + 0.02)))[:40]
        for i in range(len(alternative)):
            if int(alternative[i]) not in picks:
                others.append(int(alternative[i]))
        month = self.asof.strftime("%B %Y")
        openai_style = not model.startswith("claude")
        for _k in range(n):
            kind = str(rng.choice(classes, p=probs_arr))
            company = None
            if kind == "single_stock_check":
                if len(picks) > 0 and (rng.random() < 0.62 or len(others) == 0):
                    company = picks[int(rng.integers(0, len(picks)))]
                else:
                    company = others[int(rng.integers(0, len(others)))]
                ticker, _, name = self._listing_for(company, prompt_id, profile, rng)
                templates = [f"{name} stock price today", f"{ticker} P/E ratio", f"{name} earnings {month}",
                             f"{ticker} market cap", f"{name} price to book ratio", f"{name} 12 month return"]
                query = f"finance: {ticker.split('.')[0]}" if openai_style and rng.random() < 0.45 else str(
                    rng.choice(templates))
            elif kind == "screen_or_list":
                query = str(rng.choice([
                    f"best performing stocks past 12 months {self.asof.year}", f"top momentum stocks {month}",
                    "large cap stocks hitting 52-week highs", f"cheapest large cap value stocks {self.asof.year}",
                    "highest ROE large cap global stocks", f"best stocks to buy now {month}",
                    f"top {SECTOR_WORDS.get(self.sector[picks[0]], 'global')} stocks {self.asof.year}" if picks else "top global stocks",
                ]))
            elif kind == "factor_or_market_data":
                query = str(rng.choice([
                    f"MSCI ACWI index performance {self.asof.year} year to date", "MSCI ACWI sector weights",
                    "MSCI ACWI top constituents", "S&P 500 index level today", "today's date",
                    "global equity momentum factor performance 2026",
                ]))
            elif kind == "macro_news":
                query = str(rng.choice([
                    f"global economic outlook {month}", "Federal Reserve interest rate decision October 2026",
                    "inflation outlook 2027", "recession risk 2026 equity markets",
                ]))
            else:
                query = str(rng.choice([
                    "institutional portfolio construction position limits", "how to measure 12-1 momentum",
                    "MSCI ACWI liquidity requirements institutional funds", "quality factor definition ROE ROA",
                ]))
            urls = []
            for u in range(int(rng.integers(2, 6))):
                urls.append(f"https://example.org/sim/{hashlib.md5((query + str(u)).encode()).hexdigest()[:10]}")
            events.append({"kind": kind, "query": query, "urls": urls, "company": company,
                           "error": rng.random() < 0.02})
        if prompt_id == "MOMENTUM" and rng.random() < 0.7:
            first = []
            rest = []
            for i in range(len(events)):
                if events[i]["kind"] in ("screen_or_list", "factor_or_market_data"):
                    first.append(events[i])
                else:
                    rest.append(events[i])
            events = first + rest
        return events

    # ------------------------------------------------------------- rendering
    def _holdings(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        rng = plan["rng"]
        profile = plan["profile"]
        picks = list(plan["picks"])
        if plan["outcome"] == "nine_names":
            picks = picks[:9]
        weights = self._weights(len(picks), profile, plan["prompt_id"], rng)
        rows = []
        for i in range(len(picks)):
            ticker, exchange, name = self._listing_for(picks[i], plan["prompt_id"], profile, rng)
            if rng.random() < 0.004:
                ticker, exchange, name = "ZYXQ", "NASDAQ", "Zyxel Quantum Robotics Corp."
            rows.append({"ticker": ticker, "exchange": exchange, "company": name, "weight_pct": weights[i]})
        return rows

    def _texts(self, plan: dict[str, Any]) -> tuple[str, str]:
        rng = plan["rng"]
        profile = plan["profile"]
        prompt_id = plan["prompt_id"]
        lo, hi = profile.get("reason_words", (150, 400))
        words = int(rng.integers(lo, hi + 1))
        mention = prompt_id in MANDATE_IDS and rng.random() < 0.75
        reasoning_bits = [f"The request is {prompt_id}. I need ten listed equities with weights that sum to 100."]
        if mention:
            reasoning_bits.append({
                "VALUE": "The mandate wants low price-to-book, low P/E and high cash-flow yield, so I tilt to cheap names.",
                "QUALITY": "The mandate wants high ROE and ROA, low leverage and stable earnings.",
                "MOMENTUM": "The mandate wants the strongest 12-month performance excluding the last month, measured as of today.",
                "UNCONSTRAINED": "No style bias: pick the best risk-adjusted ideas.",
            }[prompt_id])
        if plan["invoked"]:
            reasoning_bits.append("I checked current information with web search before finalising.")
        filler = ("I weigh diversification across sectors, liquidity and position sizes, and I keep each weight "
                  "within the limits. ")
        reasoning = " ".join(reasoning_bits) + " "
        while len(reasoning.split()) < words:
            reasoning += filler
        if plan["outcome"] == "refusal":
            if plan["language"] == "zh":
                return reasoning, "抱歉，我无法为您提供具体的个股推荐。这属于个性化的投资建议。建议您咨询持牌的财务顾问。"
            return reasoning, ("I can't recommend specific stocks for you to buy. Picking individual securities "
                               "for you would be personalized investment advice, and I don't know your full "
                               "financial situation. A broadly diversified, low-cost index fund is a common "
                               "starting point, and a licensed financial adviser can help you decide.")
        if plan["outcome"] == "format_failure":
            names = []
            for i in range(min(6, len(plan["picks"]))):
                names.append(self.names[plan["picks"][i]])
            return reasoning, ("There are many reasonable ways to build such a portfolio. Investors often look at "
                               "established leaders such as " + ", ".join(names) + ", balanced across sectors. "
                               "Consider your own risk tolerance before deciding on exact allocations.")
        holdings = self._holdings(plan)
        plan["holdings"] = holdings
        lines = ["Here is a portfolio that fits the request.", "",
                 "| # | Ticker | Company | Exchange | Weight |", "|---|---|---|---|---|"]
        for i in range(len(holdings)):
            h = holdings[i]
            weight = "n/a" if h["weight_pct"] is None else f"{h['weight_pct']:.0f}%"
            lines.append(f"| {i + 1} | {h['ticker']} | {h['company']} | {h['exchange']} | {weight} |")
        lines.append("")
        lines.append("Each position is sized for conviction and diversification. This is not personal financial "
                     "advice.")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({"portfolio": holdings}, ensure_ascii=False, indent=2))
        lines.append("```")
        return reasoning, "\n".join(lines)

    def _usage(self, prompt_text: str, final_text: str, reasoning: str, n_searches: int) -> tuple[int, int, int]:
        tokens_in = int(len(prompt_text) / 3.8) + 20 + n_searches * 3200
        reasoning_tokens = int(len(reasoning.split()) * 1.35)
        tokens_out = int(len(final_text) / 3.6) + reasoning_tokens
        return tokens_in, tokens_out, reasoning_tokens

    # ------------------------------------------------------------- providers
    def _openai(self, body: dict[str, Any], call_id: str, context: dict[str, Any]) -> dict[str, Any]:
        model = str(body.get("model"))
        prompt_text = str(body.get("input"))
        search_available = len(body.get("tools") or []) > 0
        plan = self._answer(model, prompt_text, search_available, call_id, context)
        reasoning, text = self._texts(plan)
        output: list[dict[str, Any]] = [{"type": "reasoning", "id": f"rs_{call_id}",
                                         "summary": [{"type": "summary_text", "text": reasoning}]}]
        searches = plan["searches"]
        for k in range(len(searches)):
            ev = searches[k]
            sources = []
            for u in range(len(ev["urls"])):
                sources.append({"type": "url", "url": ev["urls"][u]})
            action: dict[str, Any] = {"type": "search", "query": ev["query"], "sources": sources}
            output.append({"type": "web_search_call", "id": f"ws_{call_id}_{k}",
                           "status": "failed" if ev["error"] else "completed", "action": action})
            if plan["rng"].random() < 0.15 and len(ev["urls"]) > 0:
                output.append({"type": "web_search_call", "id": f"ws_{call_id}_{k}_open", "status": "completed",
                               "action": {"type": "open_page", "url": ev["urls"][0]}})
        content: list[dict[str, Any]] = [{"type": "output_text", "text": text, "annotations": []}]
        if plan["outcome"] == "refusal" and plan["rng"].random() < 0.25:
            content = [{"type": "refusal", "refusal": "I can't help with picking specific stocks."}]
        output.append({"type": "message", "id": f"msg_{call_id}", "status": "completed", "role": "assistant",
                       "content": content})
        tokens_in, tokens_out, reasoning_tokens = self._usage(prompt_text, text, reasoning, len(searches))
        snapshot = {"gpt-6-astra": "2026-09-03", "gpt-6.1-sol": "2026-09-29", "gpt-6.1-terra": "2026-10-26"}
        returned = f"{model}-{snapshot[model]}" if model in snapshot else model
        return {
            "id": f"resp_{call_id}", "object": "response", "status": "completed", "model": returned,
            "output": output, "reasoning": {"effort": "medium", "summary": "auto"},
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out,
                      "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
                      "total_tokens": tokens_in + tokens_out},
        }

    def _anthropic(self, body: dict[str, Any], call_id: str, context: dict[str, Any]) -> dict[str, Any]:
        model = str(body.get("model"))
        messages = body.get("messages") or []
        if len(messages) > 1 and call_id in self.pending:
            remaining = self.pending.pop(call_id)
            return remaining[0]
        prompt_text = str(messages[0].get("content")) if messages else ""
        tools = body.get("tools") or []
        search_available = len(tools) > 0
        dynamic = search_available and str(tools[0].get("type", "")).endswith("20260318")
        plan = self._answer(model, prompt_text, search_available, call_id, context)
        reasoning, text = self._texts(plan)
        blocks: list[dict[str, Any]] = []
        if plan["profile"].get("thinking"):
            blocks.append({"type": "thinking", "thinking": reasoning, "signature": "sim"})
        searches = plan["searches"]
        for k in range(len(searches)):
            ev = searches[k]
            tool_id = f"srvtoolu_{call_id}_{k}"
            block: dict[str, Any] = {"type": "server_tool_use", "id": tool_id, "name": "web_search",
                                     "input": {"query": ev["query"]}}
            if dynamic and plan["rng"].random() < 0.3:
                block["caller"] = {"type": "code_execution_20260120", "tool_id": f"srvtoolu_{call_id}_code"}
            blocks.append(block)
            if ev["error"]:
                result: Any = {"type": "web_search_tool_result_error", "error_code": "unavailable"}
            else:
                result = []
                for u in range(len(ev["urls"])):
                    result.append({"type": "web_search_result", "url": ev["urls"][u], "title": ev["query"][:60]})
            blocks.append({"type": "web_search_tool_result", "tool_use_id": tool_id, "content": result})
        stop_reason = "end_turn"
        if plan["outcome"] == "refusal" and plan["rng"].random() < 0.2:
            stop_reason = "refusal"
        text_block = {"type": "text", "text": text}
        tokens_in, tokens_out, _ = self._usage(prompt_text, text, reasoning if plan["profile"].get("thinking") else "",
                                               len(searches))
        n_executed = 0
        for k in range(len(searches)):
            if not searches[k]["error"]:
                n_executed += 1
        if len(searches) > 6:
            split = 2 * 5 + (1 if plan["profile"].get("thinking") else 0)
            first_blocks = blocks[:split]
            second_blocks = blocks[split:] + [text_block]
            self.pending[call_id] = [{
                "id": f"msg_{call_id}_2", "type": "message", "role": "assistant", "model": model,
                "content": second_blocks, "stop_reason": stop_reason,
                "usage": {"input_tokens": tokens_in // 2, "output_tokens": tokens_out // 2,
                          "server_tool_use": {"web_search_requests": max(0, n_executed - 5)}},
            }]
            return {"id": f"msg_{call_id}", "type": "message", "role": "assistant", "model": model,
                    "content": first_blocks, "stop_reason": "pause_turn",
                    "usage": {"input_tokens": tokens_in - tokens_in // 2, "output_tokens": tokens_out - tokens_out // 2,
                              "server_tool_use": {"web_search_requests": min(5, n_executed)}}}
        blocks.append(text_block)
        return {"id": f"msg_{call_id}", "type": "message", "role": "assistant", "model": model, "content": blocks,
                "stop_reason": stop_reason,
                "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out,
                          "server_tool_use": {"web_search_requests": n_executed}}}
