"""Exercise migrations and direct response recovery without a live provider."""

import json

import duckdb
import pytest

from aimargin.collect.planner import plan_stage
from aimargin.collect.recovery import recover_direct_calls
from aimargin.collect.runner import raw_path_for
from aimargin.providers import make_adapter
from aimargin.settings import Workspace
from aimargin.store.db import Store
from aimargin.store.schemas import TABLES


def test_upsert_uses_names_after_migration(tmp_path):
    path = tmp_path / "old.duckdb"
    additions = {"search_invoked", "fetch_count"}
    old_columns = [f'"{name}" {kind}' for name, kind in TABLES["calls"]["columns"] if name not in additions]
    with duckdb.connect(str(path)) as db:
        db.execute(f"CREATE TABLE calls ({', '.join(old_columns)}, PRIMARY KEY(call_id))")
        db.execute("INSERT INTO calls (call_id, stage, status, http_status) VALUES ('old', 'A', 'completed', 200)")
    with Store(path) as store:
        assert store.query("PRAGMA table_info('calls')")["name"].tolist()[-2:] == ["search_invoked", "fetch_count"]
        row = {"call_id": "new", "stage": "B", "status": "completed", "http_status": 200,
               "stop_reason": "end_turn", "search_invoked": False, "fetch_count": 0}
        assert store.upsert("calls", [row]) == 1
        assert store.upsert("calls", [{**row, "search_invoked": True, "fetch_count": 3}]) == 1
        assert store.con.execute(
            "SELECT http_status, stop_reason, search_invoked, fetch_count FROM calls WHERE call_id='new'"
        ).fetchall() == [(200, "end_turn", True, 3)]
        assert store.con.execute("SELECT stage, status, http_status FROM calls WHERE call_id='old'").fetchall() == [
            ("A", "completed", 200)
        ]


def write_envelope(ws, config, spec):
    request = make_adapter(spec.provider, config, None, None).build_request(
        spec.prompt_text, spec.model_requested, spec.search_enabled, {"search_variant": spec.search_variant})
    response = {"model": spec.model_requested, "status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": "portfolio"}]},
    ], "usage": {"input_tokens": 100, "output_tokens": 200, "output_tokens_details": {"reasoning_tokens": 25}}}
    path = raw_path_for(ws, spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "call": spec.as_dict(), "request": request, "http_status": 200, "error": None, "attempts": 1,
        "submitted_ts_utc": "2026-11-10T00:00:00+00:00", "completed_ts_utc": "2026-11-10T00:00:01+00:00",
        "raw": {"provider": spec.provider, "responses": [response], "http_status": 200},
    }))
    return path


def test_recovery_preserves_orphan_response_and_skips_completed(config, tmp_path):
    ws = Workspace("test", tmp_path, tmp_path / "docs")
    spec = plan_stage(config, "B", 1)[0]
    write_envelope(ws, config, spec)
    with Store(ws.db_path) as store:
        store.upsert("calls", [{"call_id": "stage-a", "stage": "A", "status": "completed"}])
        response = {"call_id": spec.call_id, "final_text": "portfolio", "reasoning_text": "",
                    "reasoning_word_count": 0, "tool_events_json": "[]"}
        store.upsert("responses", [response])
        assert recover_direct_calls(ws, config, store, [spec], "recover") == {
            "validated": 1, "recovered": 1, "skipped_completed": 0,
        }
        assert recover_direct_calls(ws, config, store, [spec], "rerun") == {
            "validated": 1, "recovered": 0, "skipped_completed": 1,
        }
        assert store.table("responses").to_dict("records") == [response]
        assert store.con.execute("SELECT stage, status, run_id FROM calls ORDER BY stage").fetchall() == [
            ("A", "completed", None), ("B", "completed", "recover"),
        ]
        assert store.con.execute(
            "SELECT http_status, input_tokens, output_tokens, reasoning_tokens, est_cost_usd FROM calls WHERE stage='B'"
        ).fetchall() == [(200, 100, 200, 25, 0.011)]


def test_recovery_rejects_prompt_drift_and_rolls_back_conflicts(config, tmp_path):
    ws = Workspace("test", tmp_path, tmp_path / "docs")
    specs = plan_stage(config, "B", 1)[:2]
    write_envelope(ws, config, specs[0])
    path = write_envelope(ws, config, specs[1])
    envelope = json.loads(path.read_text())
    envelope["request"]["input"] = "wrong prompt"
    path.write_text(json.dumps(envelope))
    with Store(ws.db_path) as store:
        with pytest.raises(ValueError, match="expected model request and prompt"):
            recover_direct_calls(ws, config, store, specs, "recover")
        assert store.count("calls") == store.count("responses") == 0
        write_envelope(ws, config, specs[1])
        store.upsert("responses", [{"call_id": specs[1].call_id, "final_text": "conflict"}])
        with pytest.raises(ValueError, match="existing response differs"):
            recover_direct_calls(ws, config, store, specs, "recover")
        assert store.count("calls") == 0
        assert store.count("responses") == 1
