"""`aim dashboard serve`: serve the built frontend plus the exported JSON (stdlib only).

Routes:
  /api/datasets            which datasets exist (live, demo) with their meta
  /api/refresh?dataset=X   re-export dataset X from its database (POST or GET)
  /data/<dataset>/<file>   exported JSON
  everything else          frontend/dist (single-page app; unknown paths -> index.html)
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..settings import Workspace, get_workspace, load_config
from ..store.db import Store
from ..utils import get_logger, read_json
from .export import export, frontend_dist

log = get_logger(__name__)
LOCK = threading.Lock()


def datasets() -> dict[str, Workspace]:
    out = {}
    for name in ("live", "demo"):
        ws = get_workspace(name)
        if (ws.dashboard / "meta.json").exists() or ws.db_path.exists():
            out[name] = ws
    return out


def make_handler(dist: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quieter console
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: Any, status: int = 200) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

        def do_POST(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            path = url.path
            if path == "/api/datasets":
                found = datasets()
                rows = []
                names = list(found.keys())
                for i in range(len(names)):
                    meta = read_json(found[names[i]].dashboard / "meta.json", default=None)
                    rows.append({"name": names[i], "exported": meta is not None, "meta": meta})
                self._json({"datasets": rows})
                return
            if path == "/api/refresh":
                name = parse_qs(url.query).get("dataset", ["live"])[0]
                ws = get_workspace(name)
                if not ws.db_path.exists():
                    self._json({"ok": False, "error": f"no database for {name}"}, 404)
                    return
                with LOCK:
                    store = Store(ws.db_path)
                    try:
                        export(ws, load_config(), store)
                    finally:
                        store.close()
                self._json({"ok": True})
                return
            if path.startswith("/data/"):
                parts = path.split("/", 3)
                if len(parts) < 4 or parts[2] not in ("live", "demo"):
                    self._send(404, b"not found", "text/plain")
                    return
                base = get_workspace(parts[2]).dashboard.resolve()
                target = (base / parts[3]).resolve()
                if not str(target).startswith(str(base)) or not target.is_file():
                    self._send(404, b"not found", "text/plain")
                    return
                self._send(200, target.read_bytes(), "application/json")
                return
            root = dist.resolve()
            target = (root / path.lstrip("/")).resolve()
            if path in ("", "/") or not str(target).startswith(str(root)) or not target.is_file():
                target = root / "index.html"
            if not target.exists():
                self._send(500, b"frontend/dist missing: run `npm run build` in frontend/", "text/plain")
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), content_type)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    dist = frontend_dist()
    server = ThreadingHTTPServer((host, port), make_handler(dist))
    log.info("dashboard on http://%s:%d  (Ctrl+C to stop)", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
