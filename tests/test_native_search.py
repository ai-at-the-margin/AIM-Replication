"""Mocked Stage C search contracts and persisted telemetry."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pandas as pd
import pytest
from click.testing import CliRunner

from aimargin.analysis.query_classify import classify_all
from aimargin.analysis.search_usage import invocation
from aimargin.cli import main
from aimargin.collect.cost import estimate_spec
from aimargin.collect.planner import plan_stage
from aimargin.collect.runner import persist_call
from aimargin.context import Context
from aimargin.providers import make_adapter
from aimargin.providers.base import Transport, TransportResponse
from aimargin.settings import Workspace
from aimargin.store.db import Store

USAGE = {"input_tokens": 500, "output_tokens": 300, "output_tokens_details": {"reasoning_tokens": 200}}
ANSWER = {"type": "message", "content": [{"type": "output_text", "text": "portfolio"}]}


class ResponseTransport(Transport):
    def __init__(self, body, url):
        self.body = body
        self.url = url

    async def request(self, method, url, headers, json_body=None, **kwargs):
        assert (method, url) == ("POST", self.url)
        assert headers["Authorization"] == "Bearer test"
        return TransportResponse(200, {}, self.body, "")


@pytest.mark.parametrize(("provider", "model", "url", "include"), [
    ("deepseek", "deepseek-v4-pro", "https://api.deepseek.com/responses", None),
    ("kimi", "kimi-k3", "https://api.moonshot.ai/v1/responses", ["web_search_call.action.sources"]),
    ("kimi", "kimi-k3.1-pro", "https://api.moonshot.ai/v1/responses", ["web_search_call.action.sources"]),
])
def test_native_search_request(config, provider, model, url, include, monkeypatch):
    monkeypatch.delenv(f"AIM_{provider.upper()}_BASE_URL", raising=False)
    body = {"model": model, "status": "completed", "output": [ANSWER], "usage": USAGE}
    adapter = make_adapter(provider, config, ResponseTransport(body, url), "test")
    request = adapter.build_request("unchanged prompt", model, True)
    assert request["input"] == "unchanged prompt"
    assert request["tools"] == [{"type": "web_search"}] and request["tool_choice"] == "auto"
    assert request.get("reasoning") == ({"effort": "high"} if provider == "deepseek" else None)
    assert request["max_output_tokens"] == 8192
    assert request["stream"] is False and "messages" not in request
    assert request.get("include") == include
    result = adapter.normalise(asyncio.run(adapter.send(request)))
    assert result.final_text == "portfolio"
    assert result.search_invoked is False and result.search_count == 0
    assert result.fetch_count == (0 if provider == "deepseek" else None)


def test_deepseek_uses_aggregate_billable_counts_and_keeps_opaque_event(config, tmp_path):
    spec = next(spec for spec in plan_stage(config, "C", 1) if spec.provider == "deepseek")
    body = {"status": "completed", "model": spec.model_requested, "output": [
        {"type": "web_search_call", "id": "opaque", "status": "completed"},
        {"type": "tool_search_call", "id": "tool_discovery"},
        {"type": "web_search_call", "id": "failed", "status": "failed", "error": {"code": "timeout"}},
        ANSWER,
    ], "usage": {**USAGE, "server_tool_use": {"tool_search": 3, "tool_fetch": 2}}}
    adapter = make_adapter("deepseek", config, None, None)
    result = adapter.normalise({"native_search": True, "responses": [body]})
    assert (result.search_invoked, result.search_count, result.fetch_count) == (True, 3, 2)
    assert len(result.tool_events) == 2
    assert not result.tool_events[0].query_visible and result.tool_events[0].result_urls is None
    assert result.tool_events[1].error_code == "timeout" and result.tool_events[1].executed is False
    store = Store(tmp_path / "aim.duckdb")
    try:
        cost = persist_call(store, config, spec, "mock", tmp_path / "raw.json", result, {})
        assert cost == pytest.approx((500 * 1.32 + 300 * 3.96) / 1e6 + 5 * 0.00075)
        call = store.query("SELECT search_invoked, search_count, fetch_count FROM calls").iloc[0]
        assert tuple(call) == (True, 3, 2)
        event = store.query("SELECT * FROM search_events ORDER BY event_idx").iloc[0]
        assert event["tool_use_id"] == "opaque" and pd.isna(event["result_urls_json"])
        assert classify_all(store, None) == {"classified": 0}
        assert store.table("search_events")["query_class"].isna().all()
    finally:
        store.close()


def test_kimi_captures_query_sources_errors_and_charges_once_per_item(config):
    adapter = make_adapter("kimi", config, None, None)
    body = {"status": "completed", "output": [
        {"type": "web_search_call", "id": "search", "status": "completed",
         "action": {"type": "search", "query": "markets", "queries": ["markets", "rates"],
                    "sources": [{"url": "https://example.com/source"}]}},
        {"type": "web_search_call", "id": "empty", "status": "completed",
         "action": {"type": "search", "query": "empty", "sources": []}},
        {"type": "web_search_call", "id": "error", "status": "failed",
         "error": {"code": "rate_limit"}},
        ANSWER,
    ], "usage": USAGE}
    result = adapter.normalise({"native_search": True, "responses": [body]})
    assert (result.search_invoked, result.search_count, result.fetch_count) == (True, 1, None)
    assert [event.query_text for event in result.tool_events] == ["markets", "rates", "empty", None]
    assert result.tool_events[0].result_urls == ["https://example.com/source"]
    assert result.tool_events[2].result_urls == []
    assert result.tool_events[3].error_code == "rate_limit"


@pytest.mark.parametrize("provider", ["deepseek", "kimi"])
def test_unknown_telemetry_and_failed_search_are_distinct(config, provider):
    adapter = make_adapter(provider, config, None, None)
    unknown = adapter.normalise({"native_search": True, "responses": [{"status": "failed"}]})
    assert unknown.search_invoked is None and unknown.search_count is None and unknown.fetch_count is None
    result = adapter.normalise({"native_search": True, "responses": [{
        "status": "completed", "output": [{"type": "web_search_call", "status": "failed"}, ANSWER], "usage": USAGE,
    }]})
    assert result.search_invoked is True and result.search_count == 0


def test_unknown_invocation_is_excluded_from_share():
    calls = pd.DataFrame({"stage": ["C"] * 4, "status": ["completed"] * 4, "prompt_id": ["L1"] * 4,
                          "model_requested": ["model"] * 4, "search_invoked": pd.array(
                              [True, False, None, True], dtype="boolean"), "search_count": [0, 0, None, None]})
    row = invocation(SimpleNamespace(calls=calls, model_order=["model"]))["rows"][0]
    assert (row["n_observed"], row["n_unknown"]) == (3, 1)
    assert row["share_invoked"] == pytest.approx(2 / 3)
    assert row["mean_searches_when_invoked"] == 0


def test_measured_cost_does_not_add_tool_context_twice(config):
    spec = next(spec for spec in plan_stage(config, "C", 1) if spec.provider == "deepseek")
    estimate = estimate_spec(config, spec, {(spec.model_requested, True): {
        "n": 2, "input_tokens": 500, "output_tokens": 300, "search_count": 3, "fetch_count": 2,
    }})
    assert estimate["est_input_tokens"] == 500 and estimate["est_fetches"] == 2
    assert estimate["est_cost_usd"] == pytest.approx((500 * 1.32 + 300 * 3.96) / 1e6 + 5 * 0.00075)


def test_flash_fails_at_planning_and_adapter_before_transport(config, tmp_path, monkeypatch):
    config = deepcopy(config)
    config.model("deepseek-flash")["stages"].append("C")
    ws = Workspace("live", tmp_path, tmp_path / "docs")
    monkeypatch.setattr("aimargin.cli.make_context", lambda demo, data_dir: Context(ws, config))
    result = CliRunner().invoke(main, ["plan", "--stage", "C", "--pilot", "1"])
    assert result.exit_code == 1
    assert "deepseek search is unavailable for this experiment: deepseek-flash" in result.output
    with pytest.raises(ValueError, match="deepseek-flash"):
        make_adapter("deepseek", config, None, None).build_request("prompt", "deepseek-flash", True)
