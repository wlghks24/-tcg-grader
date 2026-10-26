#!/usr/bin/env python3
"""Opt-in, loopback-only V676 gallery preview; keep tcg_updater.py byte-identical.

This is a review server, NOT the production Termux boot entrypoint.
It does not schedule collection, train models, or promote results.
"""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcg_updater import Handler, PORT, QuietThreadingHTTPServer  # noqa: E402
from safe_runtime import MAX_SAFE_FILE_BYTES, open_safe_binary  # noqa: E402

# Values are literal local paths, never pieces split from an HTTP request.
PREVIEW_FILE_PARTS = {
    "/docs/tablet/v676/tablet_unified_dashboard_v676.html": ("docs", "tablet", "v676", "tablet_unified_dashboard_v676.html"),
    "/docs/tablet/v676/tablet_unified_dashboard_v676.css": ("docs", "tablet", "v676", "tablet_unified_dashboard_v676.css"),
    "/docs/tablet/v676/tablet_unified_dashboard_v676.js": ("docs", "tablet", "v676", "tablet_unified_dashboard_v676.js"),
    "/docs/tablet/v679/tablet_unified_dashboard_v679.html": ("docs", "tablet", "v679", "tablet_unified_dashboard_v679.html"),
    "/docs/tablet/v679/tablet_unified_dashboard_v679.js": ("docs", "tablet", "v679", "tablet_unified_dashboard_v679.js"),
}
PREVIEW_FILES = frozenset(PREVIEW_FILE_PARTS)
STATIC_FILE_PARTS = {
    **PREVIEW_FILE_PARTS,
    "/promo_events.json": ("promo_events.json",),
}
READ_ONLY_ROUTES = frozenset({
    "/",
    "/index.html",
    "/promo_events.json",
    "/api/local-card-images",
    "/api/local-card-images/catalog-links",
    "/api/verified-learning-gaps",
})


class PreviewHandler(Handler):
    """Inherit the audited API and safe descriptor-open; narrowly add V676 assets."""

    def _static_target(self, path):
        parts = STATIC_FILE_PARTS.get(path)
        if parts is None or self.path != path:
            return None
        cursor = Path(self.directory)
        try:
            if cursor.is_symlink():
                return None
            for segment in parts:
                cursor = cursor / segment
                if cursor.is_symlink():
                    return None
            return cursor if cursor.is_file() else None
        except (OSError, ValueError):
            return None

    def _safe_static(self, path):
        return self._static_target(path) is not None

    def send_head(self):
        """Open a literal allowlisted target; never use the legacy URL-to-path join."""
        target = self._static_target(self.path)
        if target is None:
            self.json({"ok": False, "error": "preview_route_denied"}, 404)
            return None
        try:
            handle = open_safe_binary(target, max_bytes=MAX_SAFE_FILE_BYTES)
            metadata = os.fstat(handle.fileno())
        except (OSError, ValueError):
            self.json({"ok": False, "error": "preview_asset_unavailable"}, 404)
            return None
        try:
            etag = f'"{metadata.st_mtime_ns:x}-{metadata.st_size:x}"'
            if self.headers.get("If-None-Match", "").strip() == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "private, no-cache, must-revalidate, max-age=0")
                self.end_headers()
                handle.close()
                return None
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(metadata.st_size))
            self.send_header("Last-Modified", self.date_time_string(metadata.st_mtime))
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "private, no-cache, must-revalidate, max-age=0")
            self.end_headers()
            return handle
        except BaseException:
            handle.close()
            raise

    def end_headers(self):
        # This opt-in preview serves only same-origin clients. Never reflect an
        # Origin value into a response header or enable production mutation CORS.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data: blob:; connect-src 'self'; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        SimpleHTTPRequestHandler.end_headers(self)

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

    def _redirect_gallery(self):
        self.send_response(302)
        self.send_header("Location", "/docs/tablet/v679/tablet_unified_dashboard_v679.html")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_OPTIONS(self):
        if not self._require_request_host():
            return None
        return self.json({"ok": False, "error": "preview_read_only"}, 405)

    def do_GET(self):
        if not self._require_request_host():
            return
        if not self._preview_path_allowed():
            return self.json({"ok": False, "error": "preview_route_denied"}, 404)
        if self.path in ("/", "/index.html"):
            return self._redirect_gallery()
        if self.path == "/api/verified-learning-gaps":
            from execution.tablet_learning_gap_advisor_v676 import snapshot
            return self.json(snapshot())
        if self.path.startswith("/api/local-card-images"):
            import tablet_image_library_v1
            return tablet_image_library_v1.handle_get(self, self.path)
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_HEAD(self):
        if not self._require_request_host():
            return
        if not self._preview_path_allowed():
            return self.json({"ok": False, "error": "preview_route_denied"}, 404)
        if self.path in ("/", "/index.html"):
            return self._redirect_gallery()
        if self.path.startswith("/api/"):
            return self.json({"ok": False, "error": "GET requests only"}, 405)
        return SimpleHTTPRequestHandler.do_HEAD(self)

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
        print("Read-only, local-only V679 preview: http://127.0.0.1:%d%s" %
              (port, "/docs/tablet/v679/tablet_unified_dashboard_v679.html"), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
