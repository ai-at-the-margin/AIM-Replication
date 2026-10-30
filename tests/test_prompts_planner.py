"""Prompts (BUILD_BRIEF §5) and planning (Phase 1 acceptance)."""

from __future__ import annotations

from aimargin.collect.cost import estimate_plan
from aimargin.collect.planner import plan_stage
from aimargin.prompts import MANDATE_IDS, build_prompt, experiment_version, prompt_version


def test_mandates_are_300_to_400_words(config):
    for i in range(len(MANDATE_IDS)):
        mandate = config.prompts["mandates_en"]
        text = mandate["common_block"].replace("{style_block}", mandate["mandates"][MANDATE_IDS[i]]["style_block"])
        words = len(text.split())
        assert 300 <= words <= 400, (MANDATE_IDS[i], words)


def test_suffix_appended_and_versions_stable(config):
    prompt = build_prompt(config, "L1", "en")
    assert prompt.text.startswith("Pick 10 stocks for me to buy.")
    assert '"portfolio"' in prompt.text
    assert prompt_version(config) == prompt_version(config)
    assert len(experiment_version(config)) == 12


def test_planned_counts_match_the_design(config):
    assert len(plan_stage(config, "A")) == 1440
    assert len(plan_stage(config, "B")) == 720
    assert len(plan_stage(config, "C")) == 480
    pilot = plan_stage(config, "C", pilot=2)
    assert len(pilot) == 4 * 8 * 2


def test_call_ids_are_deterministic_and_unique(config):
    first = plan_stage(config, "A")
    second = plan_stage(config, "A")
    ids = set()
    for i in range(len(first)):
        assert first[i].call_id == second[i].call_id
        ids.add(first[i].call_id)
    assert len(ids) == len(first)


def test_stage_c_uses_search_and_only_four_models(config):
    specs = plan_stage(config, "C")
    models = set()
    for i in range(len(specs)):
        assert specs[i].search_enabled
        models.add(specs[i].model_requested)
    assert models == {"gpt-6-astra", "gpt-6.1-sol", "claude-fable-5-1", "claude-opus-5-5"}


def test_dry_run_estimate_is_positive(config):
    specs = plan_stage(config, "A")
    estimate = estimate_plan(config, specs)
    total = float(estimate["est_cost_usd"].sum())
    assert 20 < total < 1000
    batch = float(estimate_plan(config, specs, batch_stages=["A"])["est_cost_usd"].sum())
    assert abs(batch - total * 0.5) < 0.01
