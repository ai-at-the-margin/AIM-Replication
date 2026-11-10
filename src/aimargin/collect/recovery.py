"""Offline recovery of successful search-disabled calls from intact raw envelopes."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..providers import make_adapter
from ..providers.base import NormalisedResponse, word_count
from ..settings import Config, Workspace
from ..store.db import Store
from .planner import CallSpec
from .runner import persist_call, raw_path_for


@dataclass
class SavedCall:
    spec: CallSpec
    path: Path
    response: NormalisedResponse
    metadata: dict[str, Any]

    def response_fields(self) -> tuple[str, str, int, str]:
        events = []
        for event in self.response.tool_events:
            events.append(event.as_dict())
        return (self.response.final_text, self.response.reasoning_text,
                word_count(self.response.reasoning_text), json.dumps(events, ensure_ascii=False))


def _validate_saved_call(ws: Workspace, config: Config, spec: CallSpec) -> SavedCall:
    path = raw_path_for(ws, spec)
    try:
        if spec.search_enabled:
            raise ValueError("this recovery supports search-disabled direct calls only")
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope["call"] != spec.as_dict():
            raise ValueError("saved call metadata differs from the expected plan")
        adapter = make_adapter(spec.provider, config, None, None)
        expected_request = adapter.build_request(spec.prompt_text, spec.model_requested, spec.search_enabled,
                                                 {"search_variant": spec.search_variant})
        if envelope["request"] != expected_request:
            raise ValueError("saved request differs from the expected model request and prompt")
        raw = envelope["raw"]
        status = envelope["http_status"]
        if status != 200 or envelope["error"] is not None or raw["http_status"] != status:
            raise ValueError("expected a successful direct API response")
        if raw["provider"] != spec.provider:
            raise ValueError("saved response provider differs from the expected provider")
        bodies = raw["responses"]
        if not isinstance(bodies, list) or not bodies:
            raise ValueError("missing provider response bodies")
        model_id = re.compile(re.escape(spec.model_requested) + r"(?:-\d{4}-\d{2}-\d{2})?")
        content_field = {"openai": "output", "anthropic": "content"}.get(spec.provider, "choices")
        for body in bodies:
            if not model_id.fullmatch(body["model"]) or not isinstance(body[content_field], list):
                raise ValueError("unexpected provider response model or content envelope")
        submitted = dt.datetime.fromisoformat(envelope["submitted_ts_utc"])
        completed = dt.datetime.fromisoformat(envelope["completed_ts_utc"])
        if submitted.utcoffset() is None or completed.utcoffset() is None or completed < submitted:
            raise ValueError("invalid submission or completion timestamps")
        attempts = envelope["attempts"]
        if type(attempts) is not int or attempts < 1:
            raise ValueError("invalid attempt count")
        response = adapter.normalise(raw)
        if response.tool_events:
            raise ValueError("unexpected tool events in a search-disabled response")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError(f"{path.name}: {exc}") from exc
    return SavedCall(spec, path, response, {
        "submitted": envelope["submitted_ts_utc"], "completed": envelope["completed_ts_utc"],
        "http_status": status, "attempts": attempts, "status": "completed", "via_batch": False,
    })


def recover_direct_calls(ws: Workspace, config: Config, store: Store, specs: list[CallSpec],
                         run_id: str) -> dict[str, int]:
    """Validate the complete input set, then restore missing calls atomically."""
    saved = []
    seen = set()
    for spec in specs:
        if spec.call_id in seen:
            raise ValueError(f"duplicate planned call {spec.call_id}")
        seen.add(spec.call_id)
        saved.append(_validate_saved_call(ws, config, spec))

    recovered = 0
    skipped = 0
    store.con.execute("BEGIN TRANSACTION")
    try:
        for item in saved:
            call_id = item.spec.call_id
            existing = store.con.execute(
                "SELECT status, stage, provider, model_requested, prompt_id, rep FROM calls WHERE call_id = ?",
                [call_id]).fetchall()
            response = store.con.execute(
                "SELECT final_text, reasoning_text, reasoning_word_count, tool_events_json "
                "FROM responses WHERE call_id = ?", [call_id]).fetchall()
            if response and response[0] != item.response_fields():
                raise ValueError(f"{call_id}: existing response differs from saved response")
            if existing:
                spec = item.spec
                if existing[0] != ("completed", spec.stage, spec.provider, spec.model_requested, spec.prompt_id,
                                   spec.rep) or not response:
                    raise ValueError(f"{call_id}: conflicting existing call")
                skipped += 1
                continue
            orphan_events = store.con.execute("SELECT count(*) FROM search_events WHERE call_id = ?",
                                               [call_id]).fetchall()[0][0]
            if orphan_events:
                raise ValueError(f"{call_id}: unexpected existing search events")
            persist_call(store, config, item.spec, run_id, item.path, item.response, item.metadata,
                         preserve_response=bool(response))
            recovered += 1
        store.con.execute("COMMIT")
    except BaseException:
        store.con.execute("ROLLBACK")
        raise
    return {"validated": len(saved), "recovered": recovered, "skipped_completed": skipped}
