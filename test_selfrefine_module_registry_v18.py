#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from selfrefine_modules.registry import MODULES, validate_registry

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))


class SelfrefineModuleRegistryTests(unittest.TestCase):
    def test_four_subsystems_are_explicit(self):
        expected = {"grading_vision", "collection", "repair_security", "orchestration"}
        self.assertEqual(set(MODULES), expected)
        self.assertEqual(set(POLICY["module_management"]["modules"]), expected)

    def test_registry_is_complete_and_collision_free(self):
        report = validate_registry()
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["missing"], report)
        self.assertFalse(report["collisions"], report)
        self.assertFalse(report["state_collisions"], report)

    def test_policy_state_ownership_matches_registry(self):
        configured = POLICY["module_management"]["modules"]
        for name, spec in MODULES.items():
            self.assertEqual(
                set(configured[name]["state_files"]),
                set(spec.state_files),
                name,
            )
        self.assertTrue(POLICY["module_management"]["exclusive_source_ownership"])
        self.assertTrue(POLICY["module_management"]["exclusive_state_ownership"])
        self.assertTrue(POLICY["module_management"]["legacy_root_entrypoints_preserved"])
        self.assertTrue(POLICY["rules"]["module_source_ownership_exclusive"])
        self.assertTrue(POLICY["rules"]["module_state_ownership_exclusive"])

    def test_grading_and_collection_state_are_not_shared(self):
        grading = set(MODULES["grading_vision"].state_files)
        collection = set(MODULES["collection"].state_files)
        repair = set(MODULES["repair_security"].state_files)
        orchestration = set(MODULES["orchestration"].state_files)
        self.assertFalse(grading & collection)
        self.assertFalse(grading & repair)
        self.assertFalse(grading & orchestration)
        self.assertFalse(collection & repair)
        self.assertFalse(collection & orchestration)
        self.assertFalse(repair & orchestration)

    def test_orchestrator_does_not_own_grading_collection_or_repair_engine(self):
        owned = set(MODULES["orchestration"].source_files)
        self.assertNotIn("grading_vision_engine.js", owned)
        self.assertNotIn("detailed_collection_intelligence.py", owned)
        self.assertNotIn("verified_code_repair_rules.py", owned)


if __name__ == "__main__":
    unittest.main()
