"""Prompts (BUILD_BRIEF §5) and planning (Phase 1 acceptance)."""

from __future__ import annotations

from aimargin.collect.cost import estimate_plan
from aimargin.collect.planner import plan_stage
from aimargin.prompts import MANDATE_IDS, build_prompt, experiment_version, prompt_version
from aimargin.utils import stable_hash


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
    assert len(plan_stage(config, "A")) == 1920
    assert len(plan_stage(config, "B")) == 960
    assert len(plan_stage(config, "C")) == 840
    pilot = plan_stage(config, "C", pilot=2)
    assert len(pilot) == 7 * 8 * 2


def test_call_ids_are_deterministic_and_unique(config):
    first = plan_stage(config, "A")
    second = plan_stage(config, "A")
    ids = set()
    for i in range(len(first)):
        assert first[i].call_id == second[i].call_id
        ids.add(first[i].call_id)
    assert len(ids) == len(first)


def test_provider_extension_preserves_baseline_ids(config):
    expected = {"A": "ff3c76aff1213cb9", "B": "a725325f4e0f9261", "C": "255051300b25022d"}
    for stage, plan_hash in expected.items():
        specs = plan_stage(config, stage)
        baseline = [spec.call_id for spec in specs if spec.provider in {"openai", "anthropic"}]
        assert stable_hash(baseline) == plan_hash
        assert all(spec.prompt_version == "2ed04e116046" for spec in specs)
    specs = plan_stage(config, "A", pilot=1)
    assert len({spec.call_id for spec in specs}) == len(specs) == 64
    added = [spec for spec in specs if spec.provider in {"deepseek", "kimi"}]
    assert {spec.model_requested for spec in added} == {
        "deepseek-v4-pro", "deepseek-flash", "kimi-k3.1-pro", "kimi-k3",
    }
    assert len(added) == 16


def test_stage_c_uses_search_and_only_eligible_models(config):
    specs = plan_stage(config, "C")
    models = set()
    for i in range(len(specs)):
        assert specs[i].search_enabled
        models.add(specs[i].model_requested)
    assert models == {"gpt-6-astra", "gpt-6.1-sol", "claude-fable-5-1", "claude-opus-5-5",
                      "deepseek-v4-pro", "kimi-k3", "kimi-k3.1-pro"}
    pilot = plan_stage(config, "C", pilot=1)
    assert len({spec.call_id for spec in pilot}) == len(pilot) == 56
    assert {spec.search_tool_version for spec in pilot if spec.provider in {"deepseek", "kimi"}} == {
        "deepseek_responses_web_search", "kimi_responses_web_search",
    }


def test_dry_run_estimate_is_positive(config):
    specs = plan_stage(config, "A")
    estimate = estimate_plan(config, specs)
    total = float(estimate["est_cost_usd"].sum())
    assert 20 < total < 1000
    baseline = [spec for spec in specs if spec.provider in {"openai", "anthropic"}]
    batch = estimate_plan(config, baseline, batch_stages=["A"])
    direct = estimate_plan(config, baseline)
    assert abs(batch["est_cost_usd"].sum() - direct["est_cost_usd"].sum() * 0.5) < 0.01
