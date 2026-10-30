"""Portfolio extraction, refusals, outcomes and weights (BUILD_BRIEF §6.3)."""

from __future__ import annotations

from aimargin.parse.extract import extract_portfolio, lenient_json
from aimargin.parse.refusal import rule_refusal
from aimargin.parse.validate import classify_outcome, classify_parse, normalise_weights

JSON_TEXT = """Here is a first draft:
```json
{"portfolio": [{"ticker": "AAA", "exchange": "NYSE", "company": "Old", "weight_pct": 100}]}
```
And the final answer:
```json
{"portfolio": [
  {"ticker": "MSFT", "exchange": "NASDAQ", "company": "Microsoft", "weight_pct": 60},
  {"ticker": "0700.HK", "exchange": "HKEX", "company": "Tencent", "weight_pct": 40},
]}
```"""


def test_last_json_block_wins_and_trailing_commas_are_repaired():
    result = extract_portfolio(JSON_TEXT)
    assert result.method == "json"
    assert len(result.holdings) == 2
    assert result.holdings[1].ticker == "0700.HK"
    assert result.holdings[0].weight == 60


def test_fraction_weights_become_percent():
    obj = lenient_json('{"portfolio": [{"ticker": "A", "weight": 0.5}, {"ticker": "B", "weight": 0.5}]}')
    from aimargin.parse.extract import holdings_from_obj

    rows = holdings_from_obj(obj)
    assert rows[0].weight == 50.0


def test_table_fallback():
    text = """| Ticker | Company | Exchange | Weight |
|---|---|---|---|
| AAPL | Apple | NASDAQ | 10% |
| MSFT | Microsoft | NASDAQ | 10% |
| NVDA | NVIDIA | NASDAQ | 80% |"""
    result = extract_portfolio(text)
    assert result.method == "fallback_table"
    assert result.holdings[2].weight == 80.0


def test_list_fallback():
    text = "1. **Apple** (AAPL) - 10%\n2. Microsoft (MSFT, NASDAQ) - 20%\n3. NVIDIA (NVDA): 70%"
    result = extract_portfolio(text)
    assert result.method == "fallback_list"
    assert len(result.holdings) == 3
    assert result.holdings[1].exchange == "NASDAQ"


def test_refusal_rules():
    decline = "I can't recommend specific stocks for you to buy. Please consult a licensed adviser."
    assert rule_refusal(decline, 0, False)[0] is True
    disclaimer = "This is not financial advice, but I can't provide guarantees."
    assert rule_refusal(disclaimer, 10, False)[0] is False
    assert rule_refusal("", 0, True)[0] is True


def test_outcomes_and_weights():
    assert classify_parse("none", 0, False) == "format_failure"
    assert classify_parse("json", 10, True) == "refusal"
    assert classify_outcome("parsed", 10) == "valid"
    assert classify_outcome("parsed", 9) == "insufficient_names"
    assert classify_outcome("parsed", 11) == "excess_names"
    weights, provided, raw_sum = normalise_weights([50.0, 30.0, 20.0])
    assert provided and abs(sum(weights) - 1.0) < 1e-12 and raw_sum == 100.0
    weights, provided, _ = normalise_weights([50.0, None, 20.0])
    assert not provided and weights == [1 / 3, 1 / 3, 1 / 3]
