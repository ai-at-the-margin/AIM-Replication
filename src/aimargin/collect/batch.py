"""Batch API collection for Stages A and B (about half price).

``submit`` sends every not-yet-completed call of a stage as provider batches and
records them in ``processed/batches.json``. ``poll`` checks each open batch and,
once it has ended, writes each result exactly like a live call (raw JSON first),
with ``via_batch = True`` and the batch's submission/completion times.
"""

from __future__ import annotations

import json
from typing import Any

from ..providers import api_key_for, make_adapter
from ..providers.base import Transport
from ..settings import Config, Workspace
from ..store.db import Store
from ..utils import get_logger, read_json, utc_now_iso, write_json
from .planner import CallSpec
from .runner import persist_call, raw_path_for

log = get_logger(__name__)
BATCH_PROVIDERS = {"openai", "anthropic"}


def _check_batch_providers(providers: set[str]) -> None:
    unsupported = providers - BATCH_PROVIDERS
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(f"Batch API is unavailable for {names}. Use direct collection or a baseline-only roster.")


def check_batch_plan(specs: list[CallSpec]) -> None:
    providers = set()
    for spec in specs:
        providers.add(spec.provider)
    _check_batch_providers(providers)


def _ledger_path(ws: Workspace):
    return ws.processed / "batches.json"


def load_ledger(ws: Workspace) -> list[dict[str, Any]]:
    return read_json(_ledger_path(ws), default=[])


def save_ledger(ws: Workspace, ledger: list[dict[str, Any]]) -> None:
    write_json(_ledger_path(ws), ledger)


async def submit(ws: Workspace, config: Config, store: Store, transport: Transport, specs: list[CallSpec],
                 run_id: str, max_per_batch: int = 5000) -> list[dict[str, Any]]:
    check_batch_plan(specs)
    done = store.query("SELECT call_id FROM calls WHERE status = 'completed'")
    done_ids = set()
    values = done["call_id"].tolist()
    for i in range(len(values)):
        done_ids.add(values[i])
    open_ids = set()
    ledger = load_ledger(ws)
    for i in range(len(ledger)):
        if ledger[i].get("state") != "collected":
            ids = ledger[i].get("call_ids", [])
            for j in range(len(ids)):
                open_ids.add(ids[j])

    by_provider: dict[str, list[CallSpec]] = {}
    for i in range(len(specs)):
        if specs[i].call_id in done_ids or specs[i].call_id in open_ids:
            continue
        if specs[i].search_enabled:
            continue  # Stage C is never batched
        by_provider.setdefault(specs[i].provider, []).append(specs[i])

    created: list[dict[str, Any]] = []
    providers = list(by_provider.keys())
    for p in range(len(providers)):
        provider = providers[p]
        adapter = make_adapter(provider, config, transport, api_key_for(provider, config))
        rows = by_provider[provider]
        for start in range(0, len(rows), max_per_batch):
            chunk = rows[start:start + max_per_batch]
            requests = []
            for i in range(len(chunk)):
                requests.append((chunk[i].call_id, adapter.build_request(
                    chunk[i].prompt_text, chunk[i].model_requested, False, {})))
            submitted = utc_now_iso()
            if provider == "openai":
                lines = []
                for i in range(len(requests)):
                    lines.append(json.dumps({"custom_id": requests[i][0], "method": "POST", "url": "/v1/responses",
                                             "body": requests[i][1]}))
                payload = ("\n".join(lines) + "\n").encode("utf-8")
                upload = await transport.request(
                    "POST", adapter.base_url + "/files", {"Authorization": adapter.headers()["Authorization"]},
                    files={"file": ("batch.jsonl", payload, "application/jsonl")}, data={"purpose": "batch"})
                file_id = (upload.json or {}).get("id")
                response = await transport.request("POST", adapter.base_url + "/batches", adapter.headers(), {
                    "input_file_id": file_id, "endpoint": "/v1/responses", "completion_window": "24h"})
                batch_id = (response.json or {}).get("id")
            else:
                items = []
                for i in range(len(requests)):
                    items.append({"custom_id": requests[i][0], "params": requests[i][1]})
                response = await transport.request("POST", adapter.base_url + "/messages/batches",
                                                   adapter.headers(), {"requests": items})
                batch_id = (response.json or {}).get("id")
            ids = []
            for i in range(len(chunk)):
                ids.append(chunk[i].call_id)
            entry = {"provider": provider, "batch_id": batch_id, "submitted_ts_utc": submitted,
                     "call_ids": ids, "state": "submitted", "run_id": run_id,
                     "requests": dict(requests)}
            ledger.append(entry)
            created.append(entry)
            log.info("submitted %s batch %s with %d calls", provider, batch_id, len(ids))
    save_ledger(ws, ledger)
    return created


async def poll(ws: Workspace, config: Config, store: Store, transport: Transport,
               specs_by_id: dict[str, CallSpec]) -> dict[str, int]:
    ledger = load_ledger(ws)
    providers = set()
    for entry in ledger:
        if entry.get("state") != "collected":
            providers.add(entry["provider"])
    _check_batch_providers(providers)
    counts = {"open": 0, "collected": 0, "results_written": 0}
    for b in range(len(ledger)):
        entry = ledger[b]
        if entry.get("state") == "collected":
            continue
        provider = entry["provider"]
        adapter = make_adapter(provider, config, transport, api_key_for(provider, config))
        results: list[tuple[str, dict[str, Any] | None, str | None]] = []
        if provider == "openai":
            status = await transport.request("GET", adapter.base_url + f"/batches/{entry['batch_id']}",
                                             adapter.headers())
            body = status.json or {}
            if body.get("status") not in ("completed", "failed", "expired", "cancelled"):
                counts["open"] += 1
                continue
            for key in ("output_file_id", "error_file_id"):
                file_id = body.get(key)
                if not file_id:
                    continue
                content = await transport.request("GET", adapter.base_url + f"/files/{file_id}/content",
                                                  adapter.headers())
                lines = (content.text or "").splitlines()
                for i in range(len(lines)):
                    if not lines[i].strip():
                        continue
                    item = json.loads(lines[i])
                    response = item.get("response") or {}
                    if response.get("status_code") == 200:
                        results.append((item["custom_id"], {"provider": "openai", "responses": [response.get("body")],
                                                            "http_status": 200}, None))
                    else:
                        results.append((item["custom_id"], None, json.dumps(item.get("error") or response)[:1000]))
        else:
            status = await transport.request("GET", adapter.base_url + f"/messages/batches/{entry['batch_id']}",
                                             adapter.headers())
            body = status.json or {}
            if body.get("processing_status") != "ended":
                counts["open"] += 1
                continue
            url = body.get("results_url")
            content = await transport.request("GET", url, adapter.headers())
            lines = (content.text or "").splitlines()
            for i in range(len(lines)):
                if not lines[i].strip():
                    continue
                item = json.loads(lines[i])
                result = item.get("result") or {}
                if result.get("type") == "succeeded":
                    results.append((item["custom_id"], {"provider": "anthropic", "responses": [result.get("message")],
                                                        "http_status": 200}, None))
                else:
                    results.append((item["custom_id"], None, json.dumps(result)[:1000]))
        completed = utc_now_iso()
        for i in range(len(results)):
            call_id, raw, error = results[i]
            spec = specs_by_id.get(call_id)
            if spec is None:
                log.warning("batch result for unknown call_id %s (plan changed?) skipped", call_id)
                store.log_drop("batch", call_id, "unknown_call_id", entry.get("batch_id") or "")
                continue
            path = raw_path_for(ws, spec)
            write_json(path, {"call": spec.as_dict(), "request": entry.get("requests", {}).get(call_id),
                              "raw": raw, "error": error, "batch_id": entry.get("batch_id"),
                              "submitted_ts_utc": entry.get("submitted_ts_utc"), "completed_ts_utc": completed})
            normalised = adapter.normalise(raw) if raw is not None else None
            meta = {"submitted": entry.get("submitted_ts_utc"), "completed": completed, "latency_s": None,
                    "http_status": 200 if raw is not None else None, "error": error, "attempts": 1,
                    "status": "completed" if raw is not None else "error", "via_batch": True}
            persist_call(store, config, spec, entry.get("run_id", "batch"), path, normalised, meta)
            counts["results_written"] += 1
        entry["state"] = "collected"
        entry["completed_ts_utc"] = completed
        counts["collected"] += 1
    save_ledger(ws, ledger)
    return counts
