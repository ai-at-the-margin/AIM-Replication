"""Asynchronous, resumable collection runner (BUILD_BRIEF §6.1).

* Idempotent through ``call_id``: a completed call is never sent again.
* Transport errors are retried with exponential backoff + jitter, honouring
  Retry-After (429 slow_down, 503 server_is_overloaded, 529, ...).
* Refusals and malformed outputs are observations: never retried.
* The raw response is written to disk before anything is parsed.
* A per-stage budget guard stops scheduling new calls once the cap would be crossed.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..providers import api_key_for, make_adapter
from ..providers.base import (
    CALL_CONTEXT,
    NormalisedResponse,
    ProviderAdapter,
    Transport,
    TransportError,
    word_count,
)
from ..providers.native_search import SEARCH_MODELS
from ..settings import Config, Workspace
from ..store.db import Store
from ..utils import get_logger, utc_now_iso, write_json
from .cost import call_cost, estimate_spec, measured_usage
from .planner import CallSpec
from .ratelimit import RateLimiter, backoff_delay

log = get_logger(__name__)


@dataclass
class RunSummary:
    planned: int = 0
    skipped_done: int = 0
    skipped_error: int = 0
    skipped_budget: int = 0
    completed: int = 0
    failed: int = 0
    spent_usd: float = 0.0
    messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "planned": self.planned, "skipped_done": self.skipped_done, "skipped_error": self.skipped_error,
            "skipped_budget": self.skipped_budget, "completed": self.completed, "failed": self.failed,
            "spent_usd": round(self.spent_usd, 4), "messages": self.messages,
        }


def raw_path_for(ws: Workspace, spec: CallSpec) -> Path:
    safe_model = spec.model_requested.replace("/", "_")
    return ws.raw_api / spec.stage / safe_model / f"{spec.call_id}.json"


def persist_call(store: Store, config: Config, spec: CallSpec, run_id: str, raw_path: Path,
                 normalised: NormalisedResponse | None, meta: dict[str, Any],
                 *, preserve_response: bool = False) -> float:
    """Write one call into calls/responses/search_events. Returns its cost."""
    model_cfg = config.model(spec.model_requested)
    provider_cfg = config.provider(spec.provider)
    cost = 0.0
    row: dict[str, Any] = {
        "call_id": spec.call_id, "run_id": run_id, "experiment_version": spec.experiment_version,
        "prompt_version": spec.prompt_version, "stage": spec.stage, "provider": spec.provider,
        "model_requested": spec.model_requested, "role": spec.role, "generation": spec.generation,
        "size_class": spec.size_class, "prompt_family": spec.prompt_family, "prompt_id": spec.prompt_id,
        "language": spec.language, "rep": spec.rep, "search_enabled": spec.search_enabled,
        "search_tool_version": spec.search_tool_version, "api_version": spec.api_version,
        "via_batch": bool(meta.get("via_batch", False)), "submitted_ts_utc": meta.get("submitted"),
        "completed_ts_utc": meta.get("completed"), "latency_s": meta.get("latency_s"),
        "http_status": meta.get("http_status"), "error": meta.get("error"), "attempts": meta.get("attempts"),
        "raw_path": str(raw_path), "status": meta.get("status", "completed"),
    }
    if normalised is not None:
        cost = call_cost(model_cfg, provider_cfg, normalised.input_tokens, normalised.output_tokens,
                         normalised.search_count, bool(meta.get("via_batch", False)), fetches=normalised.fetch_count)
        effort = normalised.reasoning_effort
        if effort is None:
            if spec.search_enabled and spec.provider in SEARCH_MODELS:
                tool = config.experiment["search_tools"][spec.provider]["default"]
                requested = tool.get("reasoning_effort")
                if requested is not None:
                    effort = f"requested:{requested}"
            elif model_cfg.get("reasoning_effort_default"):
                effort = f"default:{model_cfg['reasoning_effort_default']}"
        row.update({
            "model_returned": normalised.model_returned,
            "reasoning_effort_effective": effort,
            "input_tokens": normalised.input_tokens, "output_tokens": normalised.output_tokens,
            "reasoning_tokens": normalised.reasoning_tokens, "search_count": normalised.search_count,
            "search_invoked": normalised.search_invoked, "fetch_count": normalised.fetch_count,
            "est_cost_usd": cost, "stop_reason": normalised.stop_reason,
            "provider_refusal_flag": normalised.refusal_flag,
        })
        events = []
        for i in range(len(normalised.tool_events)):
            events.append(normalised.tool_events[i].as_dict())
        if not preserve_response:
            store.upsert("responses", [{
                "call_id": spec.call_id, "final_text": normalised.final_text,
                "reasoning_text": normalised.reasoning_text,
                "reasoning_word_count": word_count(normalised.reasoning_text),
                "tool_events_json": json.dumps(events, ensure_ascii=False),
            }])
        search_rows = []
        for i in range(len(normalised.tool_events)):
            event = normalised.tool_events[i]
            search_rows.append({
                "call_id": spec.call_id, "event_idx": event.event_idx,
                "provider_event_type": event.provider_event_type, "query_text": event.query_text,
                "query_visible": event.query_visible, "caller": event.caller,
                "result_urls_json": json.dumps(event.result_urls) if event.result_urls is not None else None,
                "error_code": event.error_code, "action_type": event.action_type,
                "tool_use_id": event.tool_use_id, "executed": event.executed,
            })
        store.replace_where("search_events", "call_id = ?", [spec.call_id], search_rows)
    store.upsert("calls", [row])
    return cost


class Runner:
    def __init__(self, ws: Workspace, config: Config, store: Store,
                 transport_factory: Callable[[], Transport], run_id: str, budget_cap_usd: float | None,
                 require_keys: bool = True, unthrottled: bool = False):
        self.ws = ws
        self.config = config
        self.store = store
        self.transport_factory = transport_factory
        self.run_id = run_id
        self.budget_cap = budget_cap_usd
        self.require_keys = require_keys
        settings = config.experiment.get("collection", {})
        self.max_attempts = int(settings.get("max_attempts", 6))
        self.base_delay = float(settings.get("base_delay_s", 2.0))
        self.max_delay = float(settings.get("max_delay_s", 120.0))
        self.concurrency = settings.get("concurrency", {})
        self.rpm = settings.get("requests_per_minute", {})
        if unthrottled:  # simulated transport only: no provider limits to respect
            self.concurrency = {"openai": 64, "anthropic": 64}
            self.rpm = {"openai": 1_000_000, "anthropic": 1_000_000}
            self.base_delay = 0.01
            self.max_delay = 0.05
        self.spent = 0.0
        self.reserved = 0.0
        self.budget_hit = False

    def _existing(self) -> dict[str, str]:
        frame = self.store.query("SELECT call_id, status FROM calls")
        out: dict[str, str] = {}
        ids = frame["call_id"].tolist()
        statuses = frame["status"].tolist()
        for i in range(len(ids)):
            out[str(ids[i])] = str(statuses[i])
        return out

    async def run(self, specs: list[CallSpec], resume: bool = False) -> RunSummary:
        summary = RunSummary(planned=len(specs))
        existing = self._existing()
        todo: list[CallSpec] = []
        for i in range(len(specs)):
            status = existing.get(specs[i].call_id)
            if status == "completed":
                summary.skipped_done += 1
            elif status == "error" and not resume:
                summary.skipped_error += 1
            else:
                todo.append(specs[i])
        if summary.skipped_error > 0:
            summary.messages.append(f"{summary.skipped_error} previously failed calls left alone (use --resume to retry)")
        if len(todo) == 0:
            return summary

        stage_spent = self.store.query(
            "SELECT stage, COALESCE(SUM(est_cost_usd), 0) AS spent FROM calls GROUP BY stage")
        already = 0.0
        stage_names = stage_spent["stage"].tolist()
        stage_values = stage_spent["spent"].tolist()
        for i in range(len(stage_names)):
            if stage_names[i] == todo[0].stage:
                already = float(stage_values[i])
        self.spent = already
        measured = measured_usage(self.store.query("SELECT * FROM calls"))

        transport = self.transport_factory()
        adapters: dict[str, ProviderAdapter] = {}
        limiters: dict[str, RateLimiter] = {}
        providers_needed: list[str] = []
        for i in range(len(todo)):
            if todo[i].provider not in providers_needed:
                providers_needed.append(todo[i].provider)
        for i in range(len(providers_needed)):
            name = providers_needed[i]
            key = api_key_for(name, self.config)
            if key is None and self.require_keys:
                raise RuntimeError(f"no API key for {name}: set {self.config.provider(name).get('env_key')}")
            adapters[name] = make_adapter(name, self.config, transport, key)
            limiters[name] = RateLimiter(int(self.concurrency.get(name, 4)), int(self.rpm.get(name, 60)))

        async def one(spec: CallSpec) -> None:
            estimate = estimate_spec(self.config, spec, measured)["est_cost_usd"]
            if self.budget_cap is not None and self.spent + self.reserved + estimate > self.budget_cap:
                summary.skipped_budget += 1
                if not self.budget_hit:
                    self.budget_hit = True
                    summary.messages.append(
                        f"budget guard: stage cap ${self.budget_cap:.2f} reached (spent ${self.spent:.2f}); "
                        "remaining calls not sent")
                return
            self.reserved += estimate
            try:
                async with limiters[spec.provider]:
                    outcome = await self._execute(adapters[spec.provider], spec)
            finally:
                self.reserved -= estimate
            self.spent += outcome
            summary.spent_usd += outcome

        tasks = []
        for i in range(len(todo)):
            tasks.append(one(todo[i]))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i in range(len(results)):
            if isinstance(results[i], Exception):
                summary.failed += 1
                summary.messages.append(f"unexpected error: {results[i]!r}")
        await transport.aclose()
        counts = self.store.query(
            "SELECT status, COUNT(*) AS n FROM calls WHERE run_id = ? GROUP BY status", [self.run_id])
        names = counts["status"].tolist()
        values = counts["n"].tolist()
        for i in range(len(names)):
            if names[i] == "completed":
                summary.completed = int(values[i])
            elif names[i] == "error":
                summary.failed += int(values[i])
        return summary

    async def _execute(self, adapter: ProviderAdapter, spec: CallSpec) -> float:
        request = adapter.build_request(spec.prompt_text, spec.model_requested, spec.search_enabled,
                                        {"search_variant": spec.search_variant})
        submitted = utc_now_iso()
        started = time.monotonic()
        raw: dict[str, Any] | None = None
        error: str | None = None
        http_status: int | None = None
        attempt = 0
        while attempt < self.max_attempts:
            attempt += 1
            token = CALL_CONTEXT.set({"call_id": spec.call_id, "rep": spec.rep, "attempt": attempt,
                                      "prompt_id": spec.prompt_id, "language": spec.language})
            try:
                raw = await adapter.send(request)
                http_status = int(raw.get("http_status") or 200)
                error = None
                break
            except TransportError as exc:
                http_status = exc.status
                error = str(exc)[:1000]
                if not exc.retryable or attempt >= self.max_attempts:
                    break
                delay = backoff_delay(attempt, self.base_delay, self.max_delay, exc.retry_after)
                log.warning("%s %s attempt %d failed (%s); retrying in %.1fs", spec.model_requested,
                            spec.call_id, attempt, exc.status, delay)
                await asyncio.sleep(delay)
            finally:
                CALL_CONTEXT.reset(token)
        completed = utc_now_iso()
        latency = round(time.monotonic() - started, 3)
        path = raw_path_for(self.ws, spec)
        envelope = {
            "call": spec.as_dict(), "request": request, "raw": raw, "error": error, "http_status": http_status,
            "submitted_ts_utc": submitted, "completed_ts_utc": completed, "attempts": attempt,
        }
        write_json(path, envelope)  # raw first, parse after (BUILD_BRIEF §6.1)
        normalised = None
        status = "error"
        if raw is not None:
            try:
                normalised = adapter.normalise(raw)
                status = "completed"
            except Exception as exc:  # malformed provider payload is an observation, kept on disk
                error = f"normalise failed: {exc!r}"
                status = "completed"
                normalised = NormalisedResponse(
                    final_text="", reasoning_text="", tool_events=[], search_count=None if spec.search_enabled else 0,
                    input_tokens=None,
                    output_tokens=None, reasoning_tokens=None, model_returned=None, stop_reason="malformed",
                    refusal_flag=False)
        meta = {
            "submitted": submitted, "completed": completed, "latency_s": latency, "http_status": http_status,
            "error": error, "attempts": attempt, "status": status, "via_batch": False,
        }
        return persist_call(self.store, self.config, spec, self.run_id, path, normalised, meta)


def summarise_calls(store: Store) -> pd.DataFrame:
    return store.query(
        "SELECT stage, model_requested, status, COUNT(*) AS n, ROUND(SUM(est_cost_usd), 4) AS cost_usd "
        "FROM calls GROUP BY 1, 2, 3 ORDER BY 1, 2, 3")
