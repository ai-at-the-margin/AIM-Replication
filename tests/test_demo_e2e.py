"""End-to-end: the whole pipeline on a small synthetic world and simulated providers."""

from __future__ import annotations

import copy
import json

import pytest

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
    finally:
        ctx.close()
    assert summary["collect_A"]["completed"] == 12 * 4 * 3
    assert summary["collect_C"]["completed"] == 4 * 8 * 2
    assert summary["resolve"]["resolution_rate"] >= 0.97
    check = summary["factors_acwi_proxy"]["capweighted_check"]
    for factor in ("size", "value", "quality", "momentum"):
        assert abs(check[factor]) < 1e-6
    assert summary["figures"] >= 7
    analysis = json.loads((tmp_path / "outputs" / "analysis.json").read_text())
    assert analysis["overlap"]["A"]["L1"]["b_cross_provider"]["mean"] > 0
    assert len(analysis["paper_comparison"]) > 15
    meta = json.loads((tmp_path / "dashboard" / "meta.json").read_text())
    assert meta["synthetic"] is True
    assert (tmp_path / "docs" / "RESULTS.md").exists()
    assert (tmp_path / "docs" / "PHASE0_VERIFICATION.md").exists()
