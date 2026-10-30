"""Prompt assembly and version hashes (BUILD_BRIEF §5, §10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .settings import Config
from .utils import stable_hash

FREEFORM_IDS = ["L1", "L2", "L3", "L4"]
MANDATE_IDS = ["VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"]
MANDATE_TARGET = {"VALUE": "value", "QUALITY": "quality", "MOMENTUM": "momentum", "UNCONSTRAINED": None}


@dataclass
class Prompt:
    prompt_id: str
    family: str          # freeform | mandate
    language: str
    label: str
    text: str            # full text sent to the model, suffix included


def prompt_family(prompt_id: str) -> str:
    if prompt_id in MANDATE_IDS:
        return "mandate"
    return "freeform"


def build_prompt(config: Config, prompt_id: str, language: str = "en") -> Prompt:
    """Return the exact text sent for one prompt id and language."""
    suffix = config.prompts["output_suffix"].get(language) or config.prompts["output_suffix"]["en"]
    family = prompt_family(prompt_id)
    if family == "freeform":
        source = config.prompts["freeform_zh"] if language == "zh" else config.prompts["freeform_en"]
        entry = source["prompts"][prompt_id]
        body = entry["text"].strip()
        label = entry.get("label", prompt_id)
    else:
        if language != "en":
            raise ValueError("mandates are English-only (BUILD_BRIEF §1.1)")
        mandates = config.prompts["mandates_en"]
        entry = mandates["mandates"][prompt_id]
        body = mandates["common_block"].replace("{style_block}", entry["style_block"].strip()).strip()
        label = entry.get("label", prompt_id)
    text = body + "\n\n" + suffix.strip()
    return Prompt(prompt_id=prompt_id, family=family, language=language, label=label, text=text)


def all_prompt_texts(config: Config) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(len(FREEFORM_IDS)):
        out["en:" + FREEFORM_IDS[i]] = build_prompt(config, FREEFORM_IDS[i], "en").text
        out["zh:" + FREEFORM_IDS[i]] = build_prompt(config, FREEFORM_IDS[i], "zh").text
    for i in range(len(MANDATE_IDS)):
        out["en:" + MANDATE_IDS[i]] = build_prompt(config, MANDATE_IDS[i], "en").text
    return out


def prompt_version(config: Config) -> str:
    """Hash of every prompt text: changes whenever any wording changes."""
    return stable_hash(all_prompt_texts(config), length=12)


def experiment_version(config: Config) -> str:
    """Hash of prompts, roster, call parameters and API versions (BUILD_BRIEF §10)."""
    models = config.model_list(include_optional=True)
    roster: list[dict[str, Any]] = []
    for i in range(len(models)):
        roster.append({
            "id": models[i]["id"],
            "stages": models[i].get("stages"),
            "request_extra": models[i].get("request_extra", {}),
        })
    payload = {
        "prompts": prompt_version(config),
        "roster": roster,
        "stages": config.experiment.get("stages"),
        "optional_arms": config.experiment.get("optional_arms"),
        "search_tools": config.experiment.get("search_tools"),
        "request": config.experiment.get("request"),
        "api_versions": {"anthropic": config.provider("anthropic").get("api_version")},
    }
    return stable_hash(payload, length=12)
