from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import tablet_runtime_manifest

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class UIAppShellV272Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = read("index.html")
        self.css = read("ui_app_shell_v272.css")
        self.js = read("ui_app_shell_v272.js")
        self.sw = read("sw.js")
        self.server = read("tcg_updater.py")

    def test_shell_assets_load_once_with_current_cache_buster(self):
        self.assertEqual(1, self.index.count('ui_app_shell_v272.css?v=272'))
        self.assertEqual(1, self.index.count('ui_app_shell_v272.js?v=272'))
        self.assertIn('<main class="app"', self.index)

    def test_accessibility_and_keyboard_contracts(self):
        self.assertIn('className = "ui-skip-link"', self.js)
        self.assertIn('skip.textContent = "본문 바로가기"', self.js)
        self.assertIn('host.setAttribute("role", "search")', self.js)
        self.assertIn('status.setAttribute("aria-live", "polite")', self.js)
        self.assertIn('event.key === "Escape"', self.js)
        self.assertIn('event.key !== "/"', self.js)
        self.assertIn('main.setAttribute("tabindex", "-1")', self.js)
        self.assertIn(':focus-visible', self.css)
        self.assertIn('@media(prefers-reduced-motion:reduce)', self.css)
        self.assertIn('@media(prefers-contrast:more)', self.css)
        self.assertIn('@media(forced-colors:active)', self.css)
        self.assertIn('env(safe-area-inset-top', self.css)

    def test_feature_search_is_local_only_and_dom_safe(self):
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("fetch(", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)
        self.assertNotIn("eval(", self.js)
        self.assertNotIn("new Function", self.js)
        self.assertIn('querySelectorAll(".feature-category")', self.js)
        self.assertIn('querySelectorAll(".feature-shortcut")', self.js)
        self.assertIn('toggleAttribute("data-ui-filter-hidden"', self.js)
        self.assertIn('Object.freeze({', self.js)

    def test_responsive_shell_contract(self):
        self.assertIn('--shell-content-max:1120px', self.css)
        self.assertIn('@media(min-width:1180px)', self.css)
        self.assertIn('--shell-content-max:1180px', self.css)
        self.assertIn('@media(max-width:350px)', self.css)
        self.assertIn('touch-action:manipulation', self.css)
        self.assertIn('overflow-wrap:anywhere', self.css)

    def test_pwa_runtime_delivery_and_manifest_contract(self):
        cache_match = re.search(r"const CACHE='tcg-v(\d+)-network-first-runtime';", self.sw)
        self.assertIsNotNone(cache_match)
        self.assertGreaterEqual(int(cache_match.group(1)), 272)
        for asset in ("./ui_app_shell_v272.css", "./ui_app_shell_v272.js"):
            self.assertIn(asset, self.sw)
        for asset in ("ui_app_shell_v272.css", "ui_app_shell_v272.js"):
            self.assertIn(repr(asset), self.server)
            self.assertIn(asset, tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)

        manifest = json.loads(read("manifest.webmanifest"))
        self.assertEqual("any", manifest.get("orientation"))
        self.assertEqual("109", str(manifest.get("version")))
        self.assertEqual("standalone", manifest.get("display"))

    def test_ci_and_tablet_guards_cover_new_ui_assets(self):
        final_workflow = read(".github/workflows/final-tablet-guard.yml")
        final_shell = read("VERIFY_TABLET_FINAL.sh")
        feature_matrix = read("verify_critical_feature_matrix_v25.py")
        current_runtime = read("verify_current_runtime.py")
        tablet_manifest_test = read("test_tablet_runtime_manifest_ui_assets_v254.py")
        for token in ("ui_app_shell_v272.css", "ui_app_shell_v272.js", "test_ui_app_shell_v272.py"):
            self.assertIn(token, final_workflow)
            self.assertIn(token, feature_matrix)
        for token in ("ui_app_shell_v272.css", "ui_app_shell_v272.js"):
            self.assertIn(token, final_shell)
            self.assertIn(token, tablet_manifest_test)
        self.assertIn('"ui_app_shell_v272"', current_runtime)
        self.assertIn('"test_ui_app_shell_v272.py"', current_runtime)


if __name__ == "__main__":
    unittest.main()
