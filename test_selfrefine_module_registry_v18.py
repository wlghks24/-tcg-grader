#!/usr/bin/env python3
from __future__ import annotations

import unittest

from selfrefine_modules.registry import MODULES, validate_registry


class SelfrefineModuleRegistryTests(unittest.TestCase):
    def test_four_subsystems_are_explicit(self):
        self.assertEqual(
            set(MODULES),
            {"grading_vision", "collection", "repair_security", "orchestration"},
        )

    def test_registry_is_complete_and_collision_free(self):
        report = validate_registry()
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["missing"], report)
        self.assertFalse(report["collisions"], report)
        self.assertFalse(report["state_collisions"], report)

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

    def test_orchestrator_does_not_own_grading_or_collection_engine(self):
        owned = set(MODULES["orchestration"].source_files)
        self.assertNotIn("grading_vision_engine.js", owned)
        self.assertNotIn("detailed_collection_intelligence.py", owned)
        self.assertNotIn("verified_code_repair_rules.py", owned)


if __name__ == "__main__":
    unittest.main()
