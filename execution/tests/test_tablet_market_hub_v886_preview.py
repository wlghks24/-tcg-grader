"""V886 unserved preview: structural navigation and real Node syntax/logic checks."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "execution/tablet_market_hub_v886_preview.html"
BASELINE = ROOT / "execution/tablet_market_hub_v881.html"
PAGES = {"home", "market", "scanner", "portfolio", "news"}


class PreviewStructure(HTMLParser):
    """Parse markup without evaluating untrusted or downloaded code."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.nav_targets = []
        self.select_options = {}
        self.active_select = None
        self.region_buttons_id = False
        self.page_sections = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        identifier = values.get("id")
        if identifier:
            self.ids.append(identifier)
        if values.get("data-page"):
            self.nav_targets.append((tag, values["data-page"]))
        if tag == "section" and (identifier or "").startswith("page-"):
            self.page_sections.append(identifier[5:])
        if tag == "select":
            self.active_select = identifier
            self.select_options.setdefault(identifier, [])
        if tag == "option" and self.active_select:
            self.select_options[self.active_select].append(values.get("value"))
        if identifier == "marketRegionTabs" and tag == "div":
            self.region_buttons_id = True

    def handle_endtag(self, tag):
        if tag == "select":
            self.active_select = None


class V886PreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = BASELINE.read_text(encoding="utf-8")
        cls.html = PREVIEW.read_text(encoding="utf-8")
        cls.markup = PreviewStructure()
        cls.markup.feed(cls.html)
        cls.markup.close()

    def test_preview_remains_separate_read_only_and_unserved(self):
        self.assertIn("TCG CARD HUB V881", self.before)
        self.assertIn("TCG CARD HUB V886", self.html)
        self.assertNotIn("method:'POST'", self.html)
        self.assertNotIn("innerHTML=", self.html)
        self.assertEqual(self.html.count("<script>"), 1)
        self.assertEqual(self.html.count("</script>"), 1)
        self.assertIn("V886", PREVIEW.name.upper())

    def test_every_navigation_button_targets_an_existing_unique_page(self):
        self.assertEqual(set(self.markup.page_sections), PAGES)
        self.assertEqual(len(self.markup.page_sections), len(PAGES))
        self.assertEqual(len(self.markup.ids), len(set(self.markup.ids)), "duplicate HTML ID")
        self.assertGreater(len(self.markup.nav_targets), 7, "missing navigation buttons")
        for tag, target in self.markup.nav_targets:
            with self.subTest(target=target):
                self.assertEqual(tag, "button")
                self.assertIn(target, PAGES)
                self.assertIn("page-" + target, self.markup.ids)

    def test_region_and_game_selections_have_valid_country_identity(self):
        self.assertTrue(self.markup.region_buttons_id)
        self.assertEqual(set(self.markup.select_options["marketRegion"]),
                         {"ALL", "KR", "JP", "US", "CN", "CN-S", "CN-T", "GLOBAL"})
        self.assertEqual(set(self.markup.select_options["marketGame"]),
                         {"ALL", "Pokémon", "ONE PIECE", "NARUTO"})
        self.assertEqual(set(self.markup.select_options["marketKind"]),
                         {"ALL", "BOX", "HIT"})

    @unittest.skipUnless(shutil.which("node"), "Node not installed: syntax NOT_VERIFIED")
    def test_embedded_javascript_parses_without_execution(self):
        code = self.html.split("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run(["node", "--check"], input=code, cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node not installed: search tests NOT_VERIFIED")
    def test_node_search_and_markup_binding_regressions(self):
        result = subprocess.run(
            ["node", "--test", "execution/tests/tablet_market_hub_v886_preview.test.cjs"],
            cwd=ROOT, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)


if __name__ == "__main__":
    unittest.main()
