"""Adapter normalisation, pause_turn continuation and the retrying runner (BUILD_BRIEF §6.1-6.2)."""

from __future__ import annotations

import asyncio
import json

from aimargin.collect.planner import plan_stage
from aimargin.collect.runner import Runner
from aimargin.providers.anthropic_adapter import AnthropicAdapter
from aimargin.providers.base import Transport, TransportError, TransportResponse
from aimargin.providers.openai_adapter import OpenAIAdapter
from aimargin.settings import Workspace
from aimargin.store.db import Store

OPENAI_RAW = {"responses": [{
    "model": "gpt-6-astra-2026-09-03", "status": "completed", "reasoning": {"effort": "medium"},
    "output": [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Thinking about momentum."}]},
        {"type": "web_search_call", "status": "completed",
         "action": {"type": "search", "query": "best performing stocks 2026", "sources": [{"url": "https://a"}]}},
        {"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": "https://b"}},
        {"type": "message", "content": [{"type": "output_text", "text": "Final answer"}]},
    ],
    "usage": {"input_tokens": 100, "output_tokens": 50, "output_tokens_details": {"reasoning_tokens": 20}},
}]}


def test_openai_normalise(config):
    adapter = OpenAIAdapter(config, None, "key")
    result = adapter.normalise(OPENAI_RAW)
    assert result.final_text == "Final answer"
    assert result.reasoning_text == "Thinking about momentum."
    assert result.search_count == 1 and len(result.tool_events) == 2
    assert result.tool_events[0].query_text == "best performing stocks 2026"
    assert result.reasoning_tokens == 20 and result.reasoning_effort == "medium"
    refusal = {"responses": [{"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]}]}
    assert adapter.normalise(refusal).refusal_flag is True


def test_openai_request_has_no_sampling_params(config):
    request = OpenAIAdapter(config, None, "k").build_request("hi", "gpt-6-astra", True)
    assert "temperature" not in request and "top_p" not in request
    assert request["store"] is False and request["tools"] == [{"type": "web_search"}]
    assert request["tool_choice"] == "auto"


class PauseTransport(Transport):
    """First reply pauses mid-search, second finishes the turn."""

    name = "test"

    def __init__(self):
        self.requests = []

    async def request(self, method, url, headers, json_body=None, content=None, files=None, data=None):
        self.requests.append(json.loads(json.dumps(json_body)))
        if len(self.requests) == 1:
            body = {"model": "claude-fable-5-1", "stop_reason": "pause_turn", "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": [{"type": "thinking", "thinking": "plan"},
                                {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "q1"}},
                                {"type": "web_search_tool_result", "tool_use_id": "s1",
                                 "content": [{"type": "web_search_result", "url": "https://x"}]}]}
        else:
            body = {"model": "claude-fable-5-1", "stop_reason": "end_turn",
                    "usage": {"input_tokens": 12, "output_tokens": 6, "server_tool_use": {"web_search_requests": 2}},
                    "content": [{"type": "server_tool_use", "id": "s2", "name": "web_search", "input": {"query": "q2"},
                                 "caller": {"type": "code_execution", "tool_id": "c1"}},
                                {"type": "web_search_tool_result", "tool_use_id": "s2",
                                 "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}},
                                {"type": "code_execution_tool_result", "content": [
                                    {"type": "server_tool_use", "id": "s3", "name": "web_search", "input": {"query": "q3"}}]},
                                {"type": "text", "text": "Done."}]}
        return TransportResponse(200, {}, body, "")


def test_anthropic_pause_turn_and_nested_callers(config):
    transport = PauseTransport()
    adapter = AnthropicAdapter(config, transport, "key")
    request = adapter.build_request("prompt", "claude-fable-5-1", True)
    assert request["tools"][0]["type"] == "web_search_20260318"
    raw = asyncio.run(adapter.send(request))
    assert len(transport.requests) == 2
    assert transport.requests[1]["messages"][1]["role"] == "assistant"
    result = adapter.normalise(raw)
    queries = []
    for i in range(len(result.tool_events)):
        queries.append(result.tool_events[i].query_text)
    assert queries == ["q1", "q2", "q3"]
    assert result.tool_events[1].caller is not None and result.tool_events[1].error_code == "max_uses_exceeded"
    assert result.tool_events[2].caller is not None
    assert result.final_text == "Done." and result.reasoning_text == "plan"
    assert result.input_tokens == 22 and result.stop_reason == "end_turn"
    refusal = {"responses": [{"stop_reason": "refusal", "content": []}]}
    assert adapter.normalise(refusal).refusal_flag is True


class FlakyTransport(Transport):
    """429 on the first attempt of every call, then a valid OpenAI-shaped answer."""

    name = "test"

    def __init__(self):
        self.calls = {}

    async def request(self, method, url, headers, json_body=None, content=None, files=None, data=None):
        key = json.dumps(json_body, sort_keys=True)
        self.calls[key] = self.calls.get(key, 0) + 1
        if self.calls[key] == 1:
            raise TransportError("HTTP 429 slow_down", status=429, retry_after=0.0)
        text = "I can't recommend specific stocks for you."
        body = {"model": json_body["model"], "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
                "usage": {"input_tokens": 10, "output_tokens": 10}}
        return TransportResponse(200, {}, body, "")


def test_runner_retries_transport_errors_but_not_refusals(config, tmp_path, monkeypatch):
    monkeypatch.setenv("AIM_OPENAI_API_KEY", "test")
    ws = Workspace(name="test", root=tmp_path, docs_dir=tmp_path / "docs")
    ws.ensure()
    store = Store(ws.db_path)
    specs = plan_stage(config, "A", pilot=1)
    openai_specs = []
    for i in range(len(specs)):
        if specs[i].provider == "openai":
            openai_specs.append(specs[i])
    transport = FlakyTransport()
    runner = Runner(ws, config, store, lambda: transport, "run1", None, unthrottled=True)
    summary = asyncio.run(runner.run(openai_specs[:4]))
    assert summary.completed == 4
    attempts = store.query("SELECT attempts FROM calls")["attempts"].tolist()
    assert attempts == [2, 2, 2, 2]  # one retry for the 429, none for the refusal text
    again = asyncio.run(Runner(ws, config, store, lambda: transport, "run2", None, unthrottled=True).run(openai_specs[:4]))
    assert again.skipped_done == 4
    assert len(list((tmp_path / "raw" / "api").rglob("*.json"))) == 4


def test_budget_guard_stops_sending(config, tmp_path, monkeypatch):
    monkeypatch.setenv("AIM_OPENAI_API_KEY", "test")
    ws = Workspace(name="test", root=tmp_path, docs_dir=tmp_path / "docs")
    ws.ensure()
    store = Store(ws.db_path)
    specs = plan_stage(config, "A", pilot=1)
    transport = FlakyTransport()
    runner = Runner(ws, config, store, lambda: transport, "run1", 0.0001, unthrottled=True,
                    require_keys=False)
    summary = asyncio.run(runner.run(specs[:5]))
    assert summary.skipped_budget == 5 and summary.completed == 0
