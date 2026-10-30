"""Workspace paths and configuration loading.

Two workspaces share one code path:

* ``live``  -- ``./data`` (or ``$AIM_DATA_DIR``): real API calls and WRDS pulls.
* ``demo``  -- ``./data/demo``: simulated LLM transport and a synthetic WRDS world,
  used by ``aim demo`` and the end-to-end tests. Everything it produces is labelled
  synthetic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("AIM_CONFIG_DIR", str(REPO_ROOT / "config")))


@dataclass
class Workspace:
    """All filesystem locations used by one workspace."""

    name: str
    root: Path
    docs_dir: Path

    @property
    def is_demo(self) -> bool:
        return self.name == "demo"

    @property
    def raw_api(self) -> Path:
        return self.root / "raw" / "api"

    @property
    def raw_wrds(self) -> Path:
        return self.root / "raw" / "wrds"

    @property
    def interim(self) -> Path:
        return self.root / "interim"

    @property
    def processed(self) -> Path:
        return self.root / "processed"

    @property
    def manual(self) -> Path:
        return self.root / "manual"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def figures(self) -> Path:
        return self.outputs / "figures"

    @property
    def tables(self) -> Path:
        return self.outputs / "tables"

    @property
    def dashboard(self) -> Path:
        return self.root / "dashboard"

    @property
    def db_path(self) -> Path:
        return self.processed / "aim.duckdb"

    @property
    def state_path(self) -> Path:
        return self.processed / "state.json"

    def ensure(self) -> None:
        """Create every directory the pipeline writes to."""
        folders = [
            self.raw_api, self.raw_wrds, self.interim, self.processed, self.manual,
            self.figures, self.tables, self.dashboard, self.docs_dir,
        ]
        for i in range(len(folders)):
            folders[i].mkdir(parents=True, exist_ok=True)


def get_workspace(name: str = "live", data_dir: str | None = None) -> Workspace:
    """Return the live or demo workspace (``data_dir`` overrides the live root)."""
    if name == "demo":
        root = REPO_ROOT / "data" / "demo"
        return Workspace(name="demo", root=root, docs_dir=root / "docs")
    if data_dir is None:
        data_dir = os.environ.get("AIM_DATA_DIR") or None
    root = Path(data_dir) if data_dir else REPO_ROOT / "data"
    return Workspace(name="live", root=root, docs_dir=REPO_ROOT / "docs")


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file; a missing or empty file returns an empty dict."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    return data


def write_yaml(path: Path, data: dict[str, Any], header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        if header:
            handle.write(header.rstrip() + "\n")
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


@dataclass
class Config:
    """Everything under config/, loaded once per command."""

    models: dict[str, Any]
    experiment: dict[str, Any]
    universe: dict[str, Any]
    factors: dict[str, Any]
    sources: dict[str, Any]
    schema: dict[str, Any]
    prompts: dict[str, Any]

    def model_list(self, include_optional: bool = False) -> list[dict[str, Any]]:
        rows = self.models.get("models", [])
        out = []
        for i in range(len(rows)):
            if rows[i].get("optional") and not include_optional:
                continue
            out.append(rows[i])
        return out

    def model(self, model_id: str) -> dict[str, Any]:
        rows = self.models.get("models", [])
        for i in range(len(rows)):
            if rows[i]["id"] == model_id:
                return rows[i]
        raise KeyError(f"unknown model id {model_id!r}")

    def provider(self, name: str) -> dict[str, Any]:
        return self.models.get("providers", {}).get(name, {})


def load_config(config_dir: Path | None = None) -> Config:
    folder = config_dir or CONFIG_DIR
    prompt_dir = folder / "prompts"
    prompts = {
        "freeform_en": load_yaml(prompt_dir / "freeform_en.yaml"),
        "freeform_zh": load_yaml(prompt_dir / "freeform_zh.yaml"),
        "mandates_en": load_yaml(prompt_dir / "mandates_en.yaml"),
        "output_suffix": load_yaml(prompt_dir / "output_suffix.yaml"),
    }
    return Config(
        models=load_yaml(folder / "models.yaml"),
        experiment=load_yaml(folder / "experiment.yaml"),
        universe=load_yaml(folder / "universe.yaml"),
        factors=load_yaml(folder / "factors.yaml"),
        sources=load_yaml(folder / "sources.yaml"),
        schema=load_yaml(folder / "wrds_schema.yaml"),
        prompts=prompts,
    )
