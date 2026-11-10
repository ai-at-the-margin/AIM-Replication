"""Offline contract tests for DeepSeek and Kimi direct collection."""

import asyncio
from copy import deepcopy
from urllib.parse import urlsplit

import httpx
import pytest
from click.testing import CliRunner

from aimargin.cli import main
from aimargin.collect.batch import poll, submit
from aimargin.collect.planner import plan_stage
from aimargin.collect.runner import Runner
from aimargin.context import Context
from aimargin.phase0 import verify_providers
from aimargin.providers import api_key_for, make_adapter
from aimargin.providers.base import HttpTransport, Transport, TransportError, TransportResponse
from aimargin.settings import Workspace
from aimargin.store.db import Store
from aimargin.utils import stable_hash, write_json

PROVIDERS = ("deepseek", "kimi")


class FakeTransport(Transport):
    def __init__(self, config, errors=()):
        self.config = config
        self.errors = list(errors)
        self.posts = []
        self.gets = []

    async def request(self, method, url, headers, json_body=None, **kwargs):
        provider = next(name for name, cfg in self.config.models["providers"].items()
                        if urlsplit(cfg["base_url"]).netloc == urlsplit(url).netloc)
        if method == "GET":
            self.gets.append(provider)
            data = [{"id": model["id"]} for model in self.config.model_list(include_optional=True)
                    if model["provider"] == provider]
            return TransportResponse(200, {}, {"data": data}, "")
        self.posts.append(provider)
        assert url.endswith("/chat/completions")
        if self.errors:
            raise self.errors.pop(0)
        body = {"model": json_body["model"], "choices": [{
            "message": {"content": "portfolio answer", "reasoning_content": "private reasoning"},
            "finish_reason": "stop",
        }], "usage": {"prompt_tokens": 100, "completion_tokens": 250,
                      "completion_tokens_details": {"reasoning_tokens": 200}}}
        return TransportResponse(200, {}, body, "")


@pytest.mark.parametrize(("provider", "limit_field"), [
    ("deepseek", "max_tokens"), ("kimi", "max_completion_tokens"),
])
def test_chat_completions_contract(config, provider, limit_field):
    transport = FakeTransport(config)
    adapter = make_adapter(provider, config, transport, "test-key")
    spec = next(spec for spec in plan_stage(config, "A", 1) if spec.provider == provider)
    request = adapter.build_request(spec.prompt_text, spec.model_requested, False)
    assert request == {"model": spec.model_requested, "messages": [{"role": "user", "content": spec.prompt_text}],
                       "stream": False, limit_field: 8192, "reasoning_effort": "high"}
    assert adapter.headers()["Authorization"] == "Bearer test-key"
    raw = asyncio.run(adapter.send(request))
    assert raw["provider"] == provider
    answer = adapter.normalise(raw)
    assert (answer.final_text, answer.reasoning_text) == ("portfolio answer", "private reasoning")
    assert (answer.input_tokens, answer.output_tokens, answer.reasoning_tokens) == (100, 250, 200)
    assert answer.stop_reason == "stop" and answer.model_returned == spec.model_requested
    assert not answer.refusal_flag and answer.search_count == 0
    with pytest.raises(ValueError, match="search is unavailable"):
        adapter.build_request("hi", "unsupported-model", True)


def test_kimi_filter_is_a_refusal_and_quota_is_terminal(config):
    errors = [
        TransportError("filtered", status=400, body={"error": {"type": "content_filter"}}),
        TransportError("quota", status=429, body={"error": {"type": "exceeded_current_quota_error"}}),
    ]
    adapter = make_adapter("kimi", config, FakeTransport(config, errors), "key")
    request = adapter.build_request("hi", "kimi-k3", False)
    raw = asyncio.run(adapter.send(request))
    assert raw["http_status"] == 400
    assert adapter.normalise(raw).refusal_flag
    with pytest.raises(TransportError) as exc:
        asyncio.run(adapter.send(request))
    assert not exc.value.retryable


@pytest.mark.parametrize("provider", PROVIDERS)
def test_credentials_and_http_classification(config, provider, monkeypatch):
    env_key = f"AIM_{provider.upper()}_API_KEY"
    monkeypatch.delenv(env_key, raising=False)
    assert api_key_for(provider, config) is None
    monkeypatch.setenv(env_key, "fake-key")
    assert api_key_for(provider, config) == "fake-key"

    async def check():
        transport = HttpTransport()
        await transport.aclose()
        responses = iter((401, 429))
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(next(responses), json={"error": {"type": "mock", "message": "rejected fake-key"}},
                                           headers={"Retry-After": "1"})
        )) as client:
            transport.client = client
            adapter = make_adapter(provider, config, transport, api_key_for(provider, config))
            for expected, retryable in ((401, False), (429, True)):
                with pytest.raises(TransportError) as exc:
                    await adapter.send({})
                assert exc.value.status == expected and exc.value.retryable is retryable
                assert exc.value.retry_after == 1
                assert "fake-key" not in str(exc.value)
                assert "fake-key" not in str(exc.value.body)

    asyncio.run(check())


def test_expanded_runner_only_sends_new_calls(config, tmp_path):
    ws = Workspace("test", tmp_path, tmp_path / "docs")
    store = Store(ws.db_path)
    specs = plan_stage(config, "A", 1)
    store.upsert("calls", [{**s.as_dict(), "status": "completed"}
                           for s in specs if s.provider not in PROVIDERS])
    transport = FakeTransport(config, [TransportError("overloaded", status=503, retry_after=0)])
    try:
        runner = Runner(ws, config, store, lambda: transport, "pilot", None, require_keys=False, unthrottled=True)
        runner.max_delay = 0
        summary = asyncio.run(runner.run(specs))
        assert (summary.skipped_done, summary.completed, summary.failed) == (48, 16, 0)
        assert set(transport.posts) == set(PROVIDERS)
        assert len(transport.posts) == 17
        rows = store.query("SELECT * FROM calls WHERE run_id = 'pilot'")
        assert set(rows["output_tokens"]) == {250}
        assert set(rows["reasoning_tokens"]) == {200}
        assert rows.loc[rows["model_requested"] == "kimi-k3", "est_cost_usd"].tolist() == [0.00405] * 4
        assert len(list(ws.raw_api.rglob("*.json"))) == 16
        rerun = Runner(ws, config, store, lambda: pytest.fail("opened transport on rerun"),
                       "rerun", None, require_keys=False)
        assert asyncio.run(rerun.run(specs)).skipped_done == 64
    finally:
        store.close()


def test_model_verification_and_batch_fail_closed(config, tmp_path, monkeypatch):
    for model in config.model_list():
        monkeypatch.setenv(config.provider(model["provider"])["env_key"], "test")
    transport = FakeTransport(config)
    verified = asyncio.run(verify_providers(config, lambda: transport, search_test=False))
    assert set(transport.gets) == {"openai", "anthropic", *PROVIDERS}
    assert all(not row["models_missing"] and row["search_test"] is None for row in verified.values())
    assert transport.posts == []

    ws = Workspace("test", tmp_path, tmp_path / "docs")
    specs = plan_stage(config, "A", 1)
    with pytest.raises(ValueError, match="unavailable for deepseek, kimi"):
        asyncio.run(submit(ws, config, None, transport, specs, "batch"))
    assert transport.posts == []
    ws.processed.mkdir()
    (ws.processed / "batches.json").write_text('[{"provider":"kimi","state":"submitted"}]')
    with pytest.raises(ValueError, match="unavailable for kimi"):
        asyncio.run(poll(ws, config, None, transport, {}))
    assert transport.posts == []


def test_cli_batch_plan_rejects_expanded_roster(tmp_path):
    result = CliRunner().invoke(main, ["--data-dir", str(tmp_path), "plan", "--stage", "A", "--pilot", "1", "--batch"])
    assert result.exit_code == 1
    assert "Batch API is unavailable for deepseek, kimi" in result.output



def test_cli_pilot_requires_new_plan_and_uses_model_list_preflight(config, tmp_path, monkeypatch):
    config = deepcopy(config)
    config.experiment["collection"]["requests_per_minute"].update(kimi=100, deepseek=100)
    ws = Workspace("live", tmp_path / "data", tmp_path / "docs")
    monkeypatch.setattr("aimargin.cli.make_context", lambda demo, data_dir: Context(ws, config))
    transport = FakeTransport(config)
    monkeypatch.setattr(Context, "transport_factory", lambda self: lambda: transport)
    for provider in config.models["providers"]:
        monkeypatch.setenv(config.provider(provider)["env_key"], "test")
        monkeypatch.delenv(f"AIM_{provider.upper()}_BASE_URL", raising=False)

    baseline = [spec for spec in plan_stage(config, "A", 1) if spec.provider not in PROVIDERS]
    store = Store(ws.db_path)
    store.upsert("calls", [{**spec.as_dict(), "status": "completed"} for spec in baseline])
    store.close()
    write_json(ws.processed / "dryrun_A_pilot1.json",
               {"plan_hash": stable_hash([spec.call_id for spec in baseline]), "estimated_usd": 0})

    cli = CliRunner()
    collect = ["collect", "--stage", "A", "--pilot", "1"]
    result = cli.invoke(main, collect)
    assert result.exit_code == 1 and "--dry-run" in result.output
    assert not transport.posts and not transport.gets
    result = cli.invoke(main, ["plan", "--stage", "A", "--dry-run", "--pilot", "1"])
    assert result.exit_code == 0 and "64 planned calls" in result.output
    result = cli.invoke(main, collect, input="y\n")
    assert result.exit_code == 0, result.output
    assert '"skipped_done": 48' in result.output and '"completed": 16' in result.output
    assert set(transport.gets) == {"openai", "anthropic", *PROVIDERS}
    assert set(transport.posts) == set(PROVIDERS)
    assert len(transport.posts) == 16
