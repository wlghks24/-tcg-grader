"""V887 locally executed real-Chromium smoke for UNDEPLOYED V886 preview.

Optional manual invocation on a user-owned workstation with installed Playwright and
Chromium: python execution/v887_local_browser_smoke.py
This is not a tablet test, GitHub Actions step, installer, or cloud browser farm.
Every network request is intercepted; the local server binds to loopback only.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "execution" / "tablet_market_hub_v886_preview.html"
PREVIEW_ROUTE = "/tablet_market_hub_v886_preview.html"

WATCH = {"items": [
    {"region": "KR", "game": "ONE PIECE", "asset": "BOX",
     "name": "계승되는 의지", "product_code": "OPK-13"},
    {"region": "JP", "game": "ONE PIECE", "asset": "BOX",
     "name": "受け継がれる意志", "product_code": "OP-13"},
    {"region": "CN-S", "game": "Pokémon", "asset": "BOX",
     "name": "英雄", "product_code": "CN001"},
    {"region": "CN-T", "game": "Pokémon", "asset": "BOX",
     "name": "英雄", "product_code": "TW001"},
]}
PRICES = {"entries": {
    "KR|계승되는 의지|BOX": {"game": "ONE PIECE", "source_date": "2026-10-31", "display": "₩50,000"},
    "JP|受け継がれる意志|BOX": {"game": "ONE PIECE", "source_date": "2026-10-31", "display": "¥9,000"},
    "CN-S|英雄|BOX": {"game": "Pokémon", "source_date": "2026-10-31", "display": "¥100"},
    "CN-T|英雄|BOX": {"game": "Pokémon", "source_date": "2026-10-31", "display": "NT$200"},
}}
FIXTURES = {
    "/market_prices.json": PRICES,
    "/market_watch.json": WATCH,
    "/catalog_image_manifest.json": {"items": {}},
    "/releases.json": {"items": []},
    "/api/local-card-images/cross-status":
        {"summary": {"auto_linked": 0, "local_all_photos": 0, "catalog_records_scanned": 4}},
}


class QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != PREVIEW_ROUTE:
            self.send_error(404, "Only the V886 preview is served")
            return
        payload = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


def assert_count(page, count: int, message: str) -> None:
    found = page.locator("#marketItems > article.product").count()
    if found != count:
        raise AssertionError(f"{message}: expected {count} card rows, got {found}")


def run() -> dict:
    if not HTML_PATH.is_file() or HTML_PATH.is_symlink():
        raise RuntimeError("V886 preview HTML missing or linked")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("NOT_VERIFIED: Python Playwright not installed locally") from exc
    binary = os.environ.get("TCG_LOCAL_CHROMIUM") or next(
        (shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome")
         if shutil.which(name)), None)
    if not binary or not Path(binary).is_file():
        raise RuntimeError("NOT_VERIFIED: local Chromium not installed; no cloud fallback")
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    errors: list[str] = []
    actions: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=str(binary),
                args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width": 800, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))

                def route_request(route):
                    url = urlsplit(route.request.url)
                    if url.hostname != "127.0.0.1" or url.port != server.server_port:
                        route.abort()
                    elif url.path in FIXTURES:
                        route.fulfill(status=200, content_type="application/json",
                                      body=json.dumps(FIXTURES[url.path], ensure_ascii=False))
                    elif url.path == PREVIEW_ROUTE and url.query == "":
                        route.continue_()
                    else:
                        route.abort()

                page.route("**/*", route_request)
                response = page.goto(
                    f"http://127.0.0.1:{server.server_port}{PREVIEW_ROUTE}",
                    wait_until="domcontentloaded", timeout=15000)
                if response is None or response.status != 200:
                    raise AssertionError("V886 static page did not load locally")
                page.wait_for_function(
                    "document.getElementById('marketState').textContent.includes('실제 자료 기준')",
                    timeout=15000)
                actions.append("load-local-only")

                page.locator('#homeGames button[data-game="ONE PIECE"]').click()
                if page.locator("#marketGame").input_value() != "ONE PIECE":
                    raise AssertionError("home game selection not synchronized")
                page.locator('.dock button[data-page="market"]').click()
                assert_count(page, 2, "One Piece home to market")
                actions.append("home-game-to-market")

                page.locator("#marketQuery").fill("원피스 한국판 OPK-13")
                page.locator("#marketSearch button").click()
                assert_count(page, 1, "multi-language and product code")
                actions.append("mixed-language-product-code")

                page.locator("#marketQuery").fill("")
                page.locator("#marketGame").select_option("Pokémon")
                page.locator('#marketRegionTabs button[data-region="CN"]').click()
                assert_count(page, 2, "unified Chinese edition")
                page.locator("#marketRegion").select_option("CN-S")
                assert_count(page, 1, "simplified only")
                page.locator("#marketRegion").select_option("CN-T")
                assert_count(page, 1, "traditional only")
                actions.append("china-unified-and-specific")

                page.locator('.dock button[data-page="home"]').click()
                page.locator(".tile.orange").click()
                if not page.locator("#page-market").evaluate(
                    "element => element.classList.contains('active')"):
                    raise AssertionError("price tile navigates to wrong page")
                actions.append("price-button-target")

                for width, height in ((360, 800), (800, 1100)):
                    page.set_viewport_size({"width": width, "height": height})
                    scroll_width = page.evaluate("document.documentElement.scrollWidth")
                    if scroll_width > width + 2:
                        raise AssertionError(f"horizontal overflow at {width}px: {scroll_width}px")
                actions.append("narrow-and-tablet-layout")

                if errors:
                    raise AssertionError("JavaScript page errors: " + "; ".join(errors[:5]))
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    return {"status": "PASS", "environment": "local-Chromium-synthetic-data",
            "device_verified": False, "live_market_verified": False,
            "network_external": False, "actions": actions}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "NOT_VERIFIED_OR_FAIL", "error": str(error),
                          "device_verified": False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
