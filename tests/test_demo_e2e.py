"""End-to-end: the whole pipeline on a small synthetic world and simulated providers."""

from __future__ import annotations

import copy
import json

import pytest

from aimargin.analysis.run import run_all
from aimargin.context import Context
from aimargin.demo.run import run_demo
from aimargin.settings import Workspace


@pytest.mark.slow
def test_demo_pipeline_end_to_end(tmp_path, config):
    cfg = copy.deepcopy(config)
    cfg.experiment["stages"]["A"]["reps"] = 3
    cfg.experiment["stages"]["B"]["reps"] = 3
    cfg.experiment["stages"]["C"]["reps"] = 2
    ws = Workspace(name="demo", root=tmp_path, docs_dir=tmp_path / "docs")
    ctx = Context(ws=ws, config=cfg)
    ctx.extras["n_filler"] = 400
    try:
        summary = run_demo(ctx, draws=50)
        expanded = run_all(ws, cfg, ctx.store, ctx.default_asof().isoformat(), "acwi_proxy",
                           draws=20, cohort="expanded")
    finally:
        ctx.close()
    assert summary["collect_A"]["completed"] == 16 * 4 * 3
    assert summary["collect_C"]["completed"] == 7 * 8 * 2
    assert summary["resolve"]["resolution_rate"] >= 0.97
    check = summary["factors_acwi_proxy"]["capweighted_check"]
    for factor in ("size", "value", "quality", "momentum"):
        assert abs(check[factor]) < 1e-6
    assert summary["figures"] >= 7
    analysis = json.loads((tmp_path / "outputs" / "analysis.json").read_text())
    assert analysis["overlap"]["A"]["L1"]["b_cross_provider"]["mean"] > 0
    assert len(analysis["paper_comparison"]) > 15
    assert analysis["cohort"] == "baseline"
    assert len(analysis["overlap"]["A"]["L1"]["models"]) == 12
    assert len(expanded["overlap"]["A"]["L1"]["models"]) == 16
    assert expanded["paper_comparison"] == []
    assert set(analysis["search"]["invocation"]["models"]) == {
        "gpt-6-astra", "gpt-6.1-sol", "claude-fable-5-1", "claude-opus-5-5",
    }
    assert len(expanded["search"]["invocation"]["models"]) == 7
    assert (tmp_path / "outputs" / "expanded" / "analysis.json").exists()
    meta = json.loads((tmp_path / "dashboard" / "meta.json").read_text())
    assert meta["synthetic"] is True
    assert meta["cohort"] == "baseline"
    assert {row["provider"] for row in meta["roster"]} == {"openai", "anthropic"}
    assert (tmp_path / "docs" / "RESULTS.md").exists()
    assert (tmp_path / "docs" / "PHASE0_VERIFICATION.md").exists()
