from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class CardMetadataMarketV328Tests(unittest.TestCase):
    def test_classifier_runtime_and_fail_closed_cases(self) -> None:
        proc = subprocess.run(
            ["node", "verify_card_metadata_classifier_v328.js"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("card metadata classifier v328: PASS", proc.stdout)

    def test_browser_load_order_and_quick_price_no_cross_game_fallback(self) -> None:
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        metadata_pos = page.find('card_metadata_classifier_v328.js?v=328')
        identity_pos = page.find('card_identity_recognition.js?v=207')
        self.assertGreaterEqual(metadata_pos, 0)
        self.assertGreater(identity_pos, metadata_pos)
        start = page.index("async function quickPrice(){")
        end = page.index("S('startAutoCamera').onclick=start", start)
        quick = page[start:end]
        self.assertIn("window.TCGCardMetadata", quick)
        self.assertIn("identity_safe", quick)
        self.assertIn("판본", quick)
        self.assertNotIn("if(!hits.length){for", quick)

    def test_grade_market_flow_requires_metadata_and_card_number(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("window.TCGCardMetadata", source)
        self.assertIn("bound.identity_safe", source)
        self.assertIn("if(!cn)return '';", source)

    def test_runtime_delivery_lists_classifier(self) -> None:
        for path in ("tcg_updater.py", "tablet_runtime_manifest.py", "feature_contract.py", "sw.js"):
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("card_metadata_classifier_v328.js", source, path)
        workflow = (ROOT / ".github/workflows/runtime-delivery-guard.yml").read_text(encoding="utf-8")
        self.assertIn("verify_card_metadata_classifier_v328.js", workflow)

    def test_market_key_regions_and_pending_coverage_are_explicit(self) -> None:
        data = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        entries = data.get("entries", {})
        self.assertIsInstance(entries, dict)
        for key in entries:
            self.assertIn(key.split("|", 1)[0], {"KR", "JP", "US"}, key)
        coverage = data.get("catalog_price_coverage", {})
        self.assertGreaterEqual(int(coverage.get("pending", 0)), 0)
        if int(coverage.get("pending", 0)):
            self.assertTrue(coverage.get("missing_keys"))


if __name__ == "__main__":
    unittest.main()
