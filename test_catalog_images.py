#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
MANIFEST = ROOT / "catalog_image_manifest.json"
START = "const COUNTRY_BOX_DATA=["
END = "];\nconst LEARNING_PRICE_DATA="


def catalog_rows(text: str) -> list[str]:
    start = text.find(START)
    end = text.find(END, start)
    if start < 0 or end < 0:
        raise AssertionError("COUNTRY_BOX_DATA markers missing")
    return [line for line in text[start:end].splitlines() if "{country:" in line]


def name_of(line: str) -> str:
    match = re.search(r'name:"([^"\r\n]+)"', line)
    if not match:
        raise AssertionError("catalog row name missing")
    return match.group(1)


class CatalogImageCoverageTests(unittest.TestCase):
    def test_every_box_row_has_https_image_after_sync(self):
        text = INDEX.read_text(encoding="utf-8")
        missing = []
        insecure = []
        for row in catalog_rows(text):
            name = name_of(row)
            match = re.search(r',boxImage:"([^"\r\n]+)"', row)
            if not match:
                missing.append(name)
            elif not match.group(1).startswith("https://"):
                insecure.append(name)
        self.assertEqual(missing, [], f"missing BOX images: {missing}")
        self.assertEqual(insecure, [], f"non-HTTPS BOX images: {insecure}")

    def test_manifest_urls_are_https_and_targets_exist(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        items = data.get("items", {})
        self.assertIsInstance(items, dict)
        self.assertGreaterEqual(len(items), 20)
        names = {name_of(row) for row in catalog_rows(INDEX.read_text(encoding="utf-8"))}
        for name, cfg in items.items():
            self.assertIn(name, names)
            self.assertTrue(str(cfg.get("url", "")).startswith("https://"), name)

    def test_placeholder_does_not_claim_third_party_image_is_official(self):
        text = INDEX.read_text(encoding="utf-8")
        self.assertNotIn("공식 BOX 이미지 준비 중", text)
        self.assertNotIn("공식 이미지를 불러오지 못했습니다.", text)

    def test_known_pack_art_regressions_are_forced_to_box_references(self):
        items = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]
        for name in ("블랙볼트", "포켓몬 카드 30주년 기념", "스톰 에메랄드"):
            self.assertTrue(items[name].get("force_replace"), name)


if __name__ == "__main__":
    unittest.main()
