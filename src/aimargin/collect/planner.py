"""Expand experiment.yaml into concrete, deterministically identified calls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..prompts import build_prompt, experiment_version, prompt_family, prompt_version
from ..providers.native_search import require_native_search
from ..settings import Config
from ..utils import stable_hash


@dataclass
class CallSpec:
    call_id: str
    stage: str
    provider: str
    model_requested: str
    role: str
    generation: str
    size_class: str
    prompt_family: str
    prompt_id: str
    language: str
    rep: int
    search_enabled: bool
    search_tool_version: str | None
    search_variant: str
    api_version: str | None
    prompt_version: str
    experiment_version: str
    prompt_text: str
    arm: str = "main"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_call_id(stage: str, model: str, prompt_id: str, language: str, rep: int, search_enabled: bool,
                 search_tool_version: str | None, prompt_ver: str) -> str:
    """Deterministic id: re-planning the same design yields the same ids (resumable)."""
    return stable_hash([stage, model, prompt_id, language, rep, search_enabled, search_tool_version, prompt_ver], 16)


def _search_tool_version(config: Config, provider: str, variant: str) -> str:
    tools = config.experiment.get("search_tools", {}).get(provider, {})
    if provider == "openai":
        return str(tools.get("default", {}).get("type", "web_search"))
    entry = tools.get(variant) or tools.get("default") or {}
    return str(entry.get("version", "web_search"))


def _models_for_stage(config: Config, stage: str) -> list[dict[str, Any]]:
    arms = config.experiment.get("optional_arms", {})
    include_consumer = bool(arms.get("consumer_proxy", {}).get("enabled"))
    rows = config.model_list(include_optional=True)
    out = []
    for i in range(len(rows)):
        if stage not in (rows[i].get("stages") or []):
            continue
        if rows[i].get("optional") and not (include_consumer and rows[i].get("role") == "consumer_proxy"):
            continue
        out.append(rows[i])
    return out


def plan_stage(config: Config, stage: str, pilot: int | None = None) -> list[CallSpec]:
    """All calls for one stage (``pilot`` caps repetitions per cell)."""
    stage_cfg = config.experiment["stages"][stage]
    prompts = stage_cfg["prompts"]
    reps = int(stage_cfg["reps"])
    search = bool(stage_cfg.get("search_enabled", False))
    pver = prompt_version(config)
    ever = experiment_version(config)
    api_version = config.provider("anthropic").get("api_version")
    models = _models_for_stage(config, stage)

    arms: list[dict[str, Any]] = [{"arm": "main", "language": "en", "reps": reps, "variant": "default",
                                   "providers": None, "prompts": prompts}]
    optional = config.experiment.get("optional_arms", {})
    zh = optional.get("mandarin", {})
    if zh.get("enabled") and zh.get("stage", "A") == stage:
        freeform_only = []
        for i in range(len(prompts)):
            if prompt_family(prompts[i]) == "freeform":
                freeform_only.append(prompts[i])
        arms.append({"arm": "mandarin", "language": "zh", "reps": int(zh.get("reps", reps)), "variant": "default",
                     "providers": None, "prompts": freeform_only})
    basic = optional.get("anthropic_basic_search", {})
    if stage == "C" and basic.get("enabled"):
        arms.append({"arm": "anthropic_basic_search", "language": "en", "reps": int(basic.get("reps", reps)),
                     "variant": "basic", "providers": ["anthropic"], "prompts": prompts})

    specs: list[CallSpec] = []
    for a in range(len(arms)):
        arm = arms[a]
        n_reps = arm["reps"] if pilot is None else min(int(pilot), arm["reps"])
        arm_prompts = arm["prompts"]
        for m in range(len(models)):
            model = models[m]
            provider = model["provider"]
            if arm["providers"] is not None and provider not in arm["providers"]:
                continue
            if search and provider not in ("openai", "anthropic"):
                require_native_search(provider, model["id"])
            tool_version = _search_tool_version(config, provider, arm["variant"]) if search else None
            for p in range(len(arm_prompts)):
                prompt = build_prompt(config, arm_prompts[p], arm["language"])
                for rep in range(n_reps):
                    call_id = make_call_id(stage, model["id"], prompt.prompt_id, prompt.language, rep, search,
                                           tool_version, pver)
                    specs.append(CallSpec(
                        call_id=call_id, stage=stage, provider=provider, model_requested=model["id"],
                        role=model.get("role", ""), generation=model.get("generation", ""),
                        size_class=model.get("size_class", ""), prompt_family=prompt.family,
                        prompt_id=prompt.prompt_id, language=prompt.language, rep=rep,
                        search_enabled=search, search_tool_version=tool_version, search_variant=arm["variant"],
                        api_version=api_version if provider == "anthropic" else None,
                        prompt_version=pver, experiment_version=ever, prompt_text=prompt.text, arm=arm["arm"],
                    ))
    return specs


def plan(config: Config, stages: list[str], pilot: int | None = None) -> list[CallSpec]:
    out: list[CallSpec] = []
    for i in range(len(stages)):
        rows = plan_stage(config, stages[i], pilot)
        for j in range(len(rows)):
            out.append(rows[j])
    return out
