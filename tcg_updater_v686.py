#!/usr/bin/env python3
"""Opt-in V686 gallery wrapper; keeps historically pinned updater modules immutable."""
from urllib.parse import urlparse
import threading

import tcg_updater_v135 as previous
from execution.tablet_production_gallery_v685 import ASSETS, serve_gallery_asset


class Handler(previous.Handler):
    def do_GET(self):
        if not self._require_request_host():
            return
        path = urlparse(self.path).path
        if path in ("/tablet-gallery", "/tablet-gallery/"):
            if self.path != path:
                return self.json({"ok": False, "error": "invalid_gallery_route"}, 404)
            self.send_response(302)
            self.send_header("Location", "/docs/tablet/v679/tablet_unified_dashboard_v679.html")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path in ASSETS:
            if self.path != path:
                return self.json({"ok": False, "error": "invalid_gallery_route"}, 404)
            return serve_gallery_asset(self, path)
        if path == "/api/verified-learning-gaps":
            if self.path != path:
                return self.json({"ok": False, "error": "invalid_gallery_route"}, 404)
            try:
                from execution.tablet_learning_gap_advisor_v676 import snapshot
                return self.json(snapshot())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({"ok": False, "error": "learning_gap_unavailable"}, 503)
        return previous.Handler.do_GET(self)


def main():
    # v135.main resolves Handler from its module. Patch only for this opt-in
    # startup, restoring it on exit; never modify the pinned source file.
    if threading.active_count() > 1:
        raise RuntimeError("V686 requires a dedicated process; use python tcg_updater_v686.py")
    original = previous.Handler
    try:
        previous.Handler = Handler
        return previous.main()
    finally:
        previous.Handler = original


if __name__ == "__main__":
    main()
