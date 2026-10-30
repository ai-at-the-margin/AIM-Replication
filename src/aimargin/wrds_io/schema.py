"""Logical -> physical column mapping (config/wrds_schema.yaml + the resolved copy)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..settings import CONFIG_DIR, load_yaml, write_yaml

RESOLVED_PATH = CONFIG_DIR / "wrds_schema.resolved.yaml"


@dataclass
class TableMap:
    key: str
    library: str
    table: str
    columns: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def fq(self) -> str:
        return f"{self.library}.{self.table}"

    def has(self, logical: str) -> bool:
        return logical in self.columns

    def c(self, logical: str) -> str:
        if logical not in self.columns:
            raise KeyError(f"{self.key}: no column mapped for {logical!r}")
        return self.columns[logical]

    def select(self, logicals: list[str], prefix: str = "") -> str:
        parts = []
        for i in range(len(logicals)):
            if self.has(logicals[i]):
                parts.append(f"{prefix}{self.c(logicals[i])} AS {logicals[i]}")
        return ", ".join(parts)


def default_map(key: str, spec: dict[str, Any]) -> TableMap:
    """First-candidate mapping, used before `aim verify` has run."""
    columns: dict[str, str] = {}
    fields = spec.get("fields") or {}
    names = list(fields.keys())
    for i in range(len(names)):
        candidates = fields[names[i]] or []
        if len(candidates) > 0:
            columns[names[i]] = str(candidates[0])
    extra = {}
    spec_keys = list(spec.keys())
    for i in range(len(spec_keys)):
        if spec_keys[i] not in ("library", "table", "fields", "optional"):
            extra[spec_keys[i]] = spec[spec_keys[i]]
    return TableMap(key=key, library=str(spec.get("library")), table=str(spec.get("table")),
                    columns=columns, extra=extra)


def load_maps(schema_cfg: dict[str, Any], resolved_path: Path = RESOLVED_PATH) -> dict[str, TableMap]:
    tables = schema_cfg.get("tables", {})
    resolved = load_yaml(resolved_path).get("resolved", {})
    out: dict[str, TableMap] = {}
    keys = list(tables.keys())
    for i in range(len(keys)):
        key = keys[i]
        spec = tables[key]
        mapping = default_map(key, spec)
        entry = resolved.get(key)
        if isinstance(entry, dict) and entry.get("ok"):
            mapping.columns = dict(entry.get("columns") or {})
            if entry.get("table"):
                mapping.table = str(entry["table"])
        out[key] = mapping
    return out


def write_resolved(probes: dict[str, dict[str, Any]], resolved_path: Path = RESOLVED_PATH) -> None:
    write_yaml(resolved_path, {"resolved": probes},
               header="# Written by `aim verify`: the physical column chosen for each logical field.\n"
                      "# Edit config/wrds_schema.yaml (candidates), not this file.")
