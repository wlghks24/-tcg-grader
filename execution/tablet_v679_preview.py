#!/usr/bin/env python3
"""Opt-in V679 UI date-safety review, separate from all production Termux jobs."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from execution.tablet_v678_preview import PreviewHandler
from tcg_updater import PORT, QuietThreadingHTTPServer

V679_FILES = frozenset({
    "/docs/tablet/v679/tablet_unified_dashboard_v679.html",
    "/docs/tablet/v679/tablet_unified_dashboard_v679.css",
    "/docs/tablet/v679/tablet_unified_dashboard_v679.js",
})


class V679PreviewHandler(PreviewHandler):
    """Keep existing V678 routes and add only three audited V679 static assets."""

    def _safe_static(self, path):
        if path not in V679_FILES:
            return super()._safe_static(path)
        if self.path != path:
            return False
        root = Path(self.directory)
        cursor = root
        for segment in path[1:].split("/"):
            if not segment or segment in (".", ".."):
                return False
            cursor = cursor / segment
            if cursor.is_symlink():
                return False
        try:
            return cursor.is_file()
        except (OSError, ValueError):
            return False

    def _preview_path_allowed(self):
        path = urlparse(self.path).path
        if self.path != path:
            return False
        return path in V679_FILES or super()._preview_path_allowed()


def main():
    raw = os.environ.get("TCG_V679_PREVIEW_PORT", str(PORT + 2))
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise SystemExit("V679 preview port must be an integer")
    if not 1024 <= port <= 65535:
        raise SystemExit("V679 preview port must be 1024..65535")
    # Explicit opt-in; loopback only; never launches production updater or model jobs.
    with QuietThreadingHTTPServer(("127.0.0.1", port), V679PreviewHandler) as server:
        print("Read-only V679 preview: http://127.0.0.1:%d%s" %
              (port, sorted(V679_FILES)[1]), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
