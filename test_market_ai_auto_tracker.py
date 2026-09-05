#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import market_ai_auto_tracker as tracker


class MarketAIAutoTrackerTests(unittest.TestCase):
    def _repo(self, root: Path) -> None:
        (root / ".github/workflows").mkdir(parents=True)
        (root / "multi_market_price_collector.py").write_text(
            "def diagnostic_exception(x): return str(x)\n"
            "def search_multi_market(*a, **k): return {'ok': True}\n"
            "# Retry-After\n# cooldown\n",
            encoding="utf-8",
        )
        (root / "multi_market_prices.js").write_text("console.log('ok');\n", encoding="utf-8")
        (root / "multi_market_prices.css").write_text("body{}\n", encoding="utf-8")
        (root / "index.html").write_text(
            "<html><head><link rel=\"stylesheet\" href=\"multi_market_prices.css?v=181\"></head>"
            "<body><script src=\"auto_market_center.js\"></script>"
            "<script src=\"multi_market_prices.js?v=181\"></script></body></html>\n",
            encoding="utf-8",
        )
        (root / "tcg_updater.py").write_text(
            "def route(path, parsed, self, parse_qs):\n"
            "    allowed=('auto_market_center.js','auto_market_center.css','multi_market_prices.js','multi_market_prices.css')\n"
            "    if path=='/api/multi-market-prices':\n"
            "        return None\n"
            "    if path=='/api/grading-proxy-costs':\n"
            "        return None\n",
            encoding="utf-8",
        )
        (root / "market_prices.json").write_text("{}\n", encoding="utf-8")
        (root / "market_watch.json").write_text("{}\n", encoding="utf-8")
        (root / ".gitignore").write_text(
            "MARKET_AI_TRACKER_REPORT.json\nMARKET_AI_TRACKER_STATE.json\n",
            encoding="utf-8",
        )
        (root / tracker.TRACKER_WORKFLOW).write_text(
            "name: Market AI Auto Tracker\n"
            "on: workflow_dispatch\n"
            "permissions:\n  contents: write\n"
            "concurrency:\n  group: market-ai-${{ github.ref }}\n  cancel-in-progress: true\n"
            "jobs:\n  test:\n    steps:\n"
            "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
            encoding="utf-8",
        )

    def test_clean_minimal_market_integration_passes_static_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            self.assertEqual(tracker.scan_static(root), [])

    def test_versioned_duplicate_assets_are_detected_and_repaired_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            html = (root / "index.html").read_text(encoding="utf-8")
            html = html.replace(
                "</head>",
                '<link rel="stylesheet" href="multi_market_prices.css?duplicate=1"></head>',
            ).replace(
                "</body>",
                '<script src="multi_market_prices.js?duplicate=1"></script></body>',
            )
            (root / "index.html").write_text(html, encoding="utf-8")
            codes = {row["code"] for row in tracker.scan_static(root)}
            self.assertIn("MARKET_CSS_ASSET_DUPLICATE", codes)
            self.assertIn("MARKET_JS_ASSET_DUPLICATE", codes)

            result = tracker.repair_known_integration(root)
            self.assertTrue(result["attempted"])
            self.assertFalse(result["rolled_back"])
            repaired = (root / "index.html").read_text(encoding="utf-8")
            self.assertEqual(len(tracker.CSS_TAG_RE.findall(repaired)), 1)
            self.assertEqual(len(tracker.JS_TAG_RE.findall(repaired)), 1)
            self.assertEqual(tracker.scan_static(root), [])

    def test_missing_route_and_static_allowlist_are_repaired_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            updater = (
                "class H:\n"
                "    def route(self, path, parsed, parse_qs):\n"
                "        allowed=('auto_market_center.js','auto_market_center.css')\n"
                "        if path=='/api/grading-proxy-costs':\n"
                "            return None\n"
            )
            (root / "tcg_updater.py").write_text(updater, encoding="utf-8")
            codes = {row["code"] for row in tracker.scan_static(root)}
            self.assertIn("MARKET_STATIC_ALLOWLIST_MISSING", codes)
            self.assertIn("MARKET_API_ROUTE_MISSING", codes)

            result = tracker.repair_known_integration(root)
            self.assertTrue(result["attempted"])
            self.assertFalse(result["rolled_back"])
            text = (root / "tcg_updater.py").read_text(encoding="utf-8")
            self.assertIn("'multi_market_prices.js','multi_market_prices.css'", text)
            self.assertEqual(text.count(tracker.ROUTE_MARKER), 1)
            self.assertEqual(tracker.scan_static(root), [])

    def test_duplicate_api_route_fails_closed_and_is_not_auto_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            updater = (root / "tcg_updater.py").read_text(encoding="utf-8")
            updater += "\n# duplicate marker\n" + tracker.ROUTE_MARKER + "\n"
            (root / "tcg_updater.py").write_text(updater, encoding="utf-8")
            rows = tracker.scan_static(root)
            duplicate = [row for row in rows if row["code"] == "MARKET_API_ROUTE_DUPLICATE"]
            self.assertEqual(len(duplicate), 1)
            self.assertFalse(duplicate[0]["repairable"])
            before = (root / "tcg_updater.py").read_text(encoding="utf-8")
            result = tracker.repair_known_integration(root)
            self.assertFalse(result["attempted"])
            self.assertEqual(before, (root / "tcg_updater.py").read_text(encoding="utf-8"))

    def test_tracker_workflow_requires_sha_pinned_github_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            workflow = root / tracker.TRACKER_WORKFLOW
            text = workflow.read_text(encoding="utf-8").replace(
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/checkout@v6",
            )
            workflow.write_text(text, encoding="utf-8")
            codes = {row["code"] for row in tracker.scan_static(root)}
            self.assertIn("MARKET_TRACKER_ACTION_NOT_SHA_PINNED", codes)

    def test_design_references_are_official_github_docs(self):
        self.assertTrue(tracker.DESIGN_REFERENCES)
        self.assertTrue(all(
            value.startswith("https://docs.github.com/")
            for value in tracker.DESIGN_REFERENCES.values()
        ))


if __name__ == "__main__":
    unittest.main()
