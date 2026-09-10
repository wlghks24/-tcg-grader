#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from instagram_tcg_content.automation_state_guard import CANONICAL_ID

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ai_reliability_v8"
CODE_MAP_PATH = PACKAGE / "CODE_MAP.json"
BINDING_PATH = PACKAGE / "binding.json"

class AiReliabilityV8CodeMapContractTests(unittest.TestCase):
    def load_map(self) -> dict:
        return json.loads(CODE_MAP_PATH.read_text(encoding="utf-8"))

    def test_aliases_resolve_to_declared_features(self):
        data = self.load_map()
        features = data["features"]
        for alias, target in data["aliases"].items():
            with self.subTest(alias=alias):
                self.assertIn(target, features)

    def test_entry_and_impact_files_exist(self):
        data = self.load_map()
        for feature, item in data["features"].items():
            for relative in [item["entry_file"], *(item.get("impact") or [])]:
                with self.subTest(feature=feature, path=relative):
                    self.assertTrue((PACKAGE / relative).is_file(), relative)

    def test_targeted_test_references_exist(self):
        data = self.load_map()
        for feature, item in data["features"].items():
            for node in item.get("tests") or []:
                path_text = str(node).split("::", 1)[0]
                with self.subTest(feature=feature, node=node):
                    self.assertTrue(path_text.endswith(".py"), node)
                    self.assertTrue((ROOT / path_text).is_file(), node)

    def test_binding_hashes_match_installed_files(self):
        binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
        self.assertEqual(binding.get("schema_version"), 8)
        self.assertEqual(binding.get("project"), "instagram_card")
        self.assertEqual(binding.get("task_id"), CANONICAL_ID)
        files = binding.get("files")
        self.assertIsInstance(files, dict)
        for relative, expected in files.items():
            with self.subTest(path=relative):
                path = PACKAGE / relative
                self.assertTrue(path.is_file(), relative)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

if __name__ == "__main__":
    unittest.main()
