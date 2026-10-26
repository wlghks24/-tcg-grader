#!/usr/bin/env python3
"""Opt-in, loopback-only V676 gallery preview; keep tcg_updater.py byte-identical.

This is a review server, NOT the production Termux boot entrypoint.
It does not schedule collection, train models, or promote results.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcg_updater import BASE, Handler, PORT, QuietThreadingHTTPServer  # noqa: E402

PREVIEW_FILES = frozenset({
    "/docs/tablet/v676/tablet_unified_dashboard_v676.html",
    "/docs/tablet/v676/tablet_unified_dashboard_v676.css",
    "/docs/tablet/v676/tablet_unified_dashboard_v676.js",
})
READ_ONLY_ROUTES = frozenset({
    "/",
    "/index.html",
    "/promo_events.json",
    "/api/local-card-images",
    "/api/local-card-images/catalog-links",
})


class PreviewHandler(Handler):
    """Inherit the audited API and safe descriptor-open; narrowly add V676 assets."""

    def _safe_static(self, path):
        if path not in PREVIEW_FILES:
            return super()._safe_static(path)
        if self.path != path:
            return False  # Reject queries, encodings, fragments and other aliases.
        root = Path(self.directory)
        relative = path[1:].split("/")
        cursor = root
        for segment in relative:
            if segment in ("", ".", ".."):
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
        # No query strings or noncanonical spellings on preview endpoints.
        if self.path != path:
            return False
        return (
            path in PREVIEW_FILES
            or path in READ_ONLY_ROUTES
            or path.startswith("/api/local-card-images/file/")
        )

    def do_GET(self):
        if not self._require_request_host():
            return
        if not self._preview_path_allowed():
            return self.json({"ok": False, "error": "preview_route_denied"}, 404)
        return super().do_GET()

    def do_HEAD(self):
        if not self._require_request_host():
            return
        if not self._preview_path_allowed():
            return self.json({"ok": False, "error": "preview_route_denied"}, 404)
        return super().do_HEAD()

    def do_POST(self):
        if not self._require_request_host():
            return
        return self.json({"ok": False, "error": "preview_read_only"}, 405)


def main():
    raw = os.environ.get("TCG_V678_PREVIEW_PORT", str(PORT + 1))
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise SystemExit("Preview port must be an integer")
    if not 1024 <= port <= 65535:
        raise SystemExit("Preview port must be 1024..65535")
    # A second process on localhost only; original 0.0.0.0 production port is untouched.
    with QuietThreadingHTTPServer(("127.0.0.1", port), PreviewHandler) as server:
        print("Read-only, local-only V676 preview: http://127.0.0.1:%d%s" %
              (port, sorted(PREVIEW_FILES)[1]), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
