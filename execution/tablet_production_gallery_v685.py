"""Strict allowlisted read-only gallery assets on the existing updater server."""
from pathlib import Path
import os

from safe_runtime import MAX_SAFE_FILE_BYTES, open_safe_binary

ASSETS = {
    "/docs/tablet/v679/tablet_unified_dashboard_v679.html": ("docs","tablet","v679","tablet_unified_dashboard_v679.html"),
    "/docs/tablet/v679/tablet_unified_dashboard_v679.js": ("docs","tablet","v679","tablet_unified_dashboard_v679.js"),
    "/docs/tablet/v676/tablet_unified_dashboard_v676.css": ("docs","tablet","v676","tablet_unified_dashboard_v676.css"),
}
MIME = {".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8", ".css":"text/css; charset=utf-8"}

def asset_target(root, path):
    parts = ASSETS.get(path)
    if parts is None:
        return None
    cursor = Path(root)
    try:
        if cursor.is_symlink():
            return None
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return None
        return cursor if cursor.is_file() else None
    except (OSError, ValueError):
        return None

def serve_gallery_asset(handler, path):
    target = asset_target(handler.directory, path)
    if target is None:
        return handler.json({"ok":False,"error":"gallery_asset_unavailable"},404)
    try:
        stream = open_safe_binary(target,max_bytes=MAX_SAFE_FILE_BYTES)
        stat = os.fstat(stream.fileno())
    except (OSError,ValueError):
        return handler.json({"ok":False,"error":"gallery_asset_unavailable"},404)
    with stream:
        handler.send_response(200)
        handler.send_header("Content-Type", MIME[target.suffix])
        handler.send_header("Content-Length",str(stat.st_size))
        handler.send_header("Cache-Control","private, no-cache, must-revalidate, max-age=0")
        handler.end_headers()
        while True:
            block=stream.read(65536)
            if not block:
                break
            handler.wfile.write(block)
