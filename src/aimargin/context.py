"""Per-command context: workspace, config, store, transport and data source (live or demo)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .providers.base import HttpTransport, Transport
from .settings import Config, Workspace, get_workspace, load_config
from .store.db import Store

DEMO_ASOF = dt.date(2026, 10, 29)


@dataclass
class Context:
    ws: Workspace
    config: Config
    _store: Store | None = None
    _world: Any = None
    _transport: Any = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def demo(self) -> bool:
        return self.ws.is_demo

    @property
    def store(self) -> Store:
        if self._store is None:
            self.ws.ensure()
            self._store = Store(self.ws.db_path)
        return self._store

    def world(self) -> Any:
        if self._world is None:
            from .demo.world import ensure_world

            self.ws.ensure()
            n_filler = int(self.extras.get("n_filler", 2600))
            self._world = ensure_world(self.ws.root, DEMO_ASOF, n_filler)
        return self._world

    def transport_factory(self) -> Any:
        if self.demo:
            if self._transport is None:
                from .demo.simulator import SimulatedTransport

                self._transport = SimulatedTransport(self.config, self.world(), DEMO_ASOF)
            transport = self._transport

            def factory() -> Transport:
                return transport

            return factory
        timeout = float(self.config.experiment.get("collection", {}).get("timeout_s", 600))

        def live_factory() -> Transport:
            return HttpTransport(timeout)

        return live_factory

    def source(self) -> Any:
        if self.demo:
            from .demo.world import SyntheticSource

            return SyntheticSource(self.world())
        from .wrds_io.source import WrdsSource

        return WrdsSource(self.ws, self.config)

    def default_asof(self) -> dt.date:
        if self.demo:
            return DEMO_ASOF
        value = self.config.experiment.get("asof_date")
        if value:
            return dt.date.fromisoformat(str(value))
        end = (self.config.experiment.get("collection_window") or {}).get("end")
        if end:
            return dt.date.fromisoformat(str(end))
        return dt.date.today() - dt.timedelta(days=1)

    def close(self) -> None:
        if self._store is not None:
            self._store.close()


def make_context(demo: bool, data_dir: str | None = None) -> Context:
    ws = get_workspace("demo" if demo else "live", data_dir)
    ws.ensure()
    return Context(ws=ws, config=load_config())
