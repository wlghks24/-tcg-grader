#!/usr/bin/env python3
"""고장주입·무결성·제한적 자가복구의 독립 회귀검사."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import fault_injection_healing as healing


def tree_signature(root: Path) -> str:
    digest = hashlib.sha256()
    for path in healing.tracked_files(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class FaultHealingTests(unittest.TestCase):
    def test_all_faults_are_detected_and_repaired_only_in_lab(self):
        before = tree_signature(healing.ROOT)
        with tempfile.TemporaryDirectory(prefix="tcg-fault-learning-") as directory:
            output = Path(directory) / "learning.json"
            report = healing.run_fault_lab(healing.ROOT, output)
            learned = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["ok"], [row for row in report["results"] if not row["ok"]])
        self.assertEqual(report["scenario_count"], len(healing.SCENARIOS))
        self.assertEqual(report["successful_scenarios"], report["scenario_count"])
        self.assertTrue(all(row["fault_detected"] and row["repair_verified"] for row in report["results"]))
        self.assertFalse(report["production_files_modified"])
        self.assertTrue(learned["training_only"])
        self.assertFalse(learned["safety"]["production_files_modified"])
        self.assertEqual(tree_signature(healing.ROOT), before)

    def test_manifest_detects_change_without_auto_rewriting_code(self):
        with tempfile.TemporaryDirectory(prefix="tcg-integrity-") as directory:
            root = Path(directory)
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            self.assertTrue(healing.diagnose_integrity(root, manifest)["ok"])
            (root / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")
            result = healing.diagnose_integrity(root, manifest)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failed"], 1)
            self.assertEqual((root / "sample.py").read_text(encoding="utf-8"), "VALUE = 2\n")

    def test_only_invalid_json_uses_verified_backup(self):
        with tempfile.TemporaryDirectory(prefix="tcg-data-heal-") as directory:
            root = Path(directory)
            for name in healing.RECOVERABLE_DATA:
                (root / name).write_text('{"ok":true}\n', encoding="utf-8")
            target = root / "market_prices.json"
            backup = root / "market_prices.json.bak"
            target.write_text("{broken", encoding="utf-8")
            backup.write_text('{"ok":true,"restored":true}\n', encoding="utf-8")
            report = healing.restore_verified_data_backups(root)
            self.assertTrue(report["ok"])
            self.assertEqual(report["repaired"], 1)
            self.assertTrue(json.loads(target.read_text(encoding="utf-8"))["restored"])

    def test_invalid_backup_is_never_promoted(self):
        with tempfile.TemporaryDirectory(prefix="tcg-data-noheal-") as directory:
            root = Path(directory)
            for name in healing.RECOVERABLE_DATA:
                (root / name).write_text('{"ok":true}\n', encoding="utf-8")
            target = root / "promo_events.json"
            target.write_text("{broken", encoding="utf-8")
            (root / "promo_events.json.bak").write_text('{"x":NaN}', encoding="utf-8")
            report = healing.restore_verified_data_backups(root)
            self.assertFalse(report["ok"])
            self.assertEqual(target.read_text(encoding="utf-8"), "{broken")

    def test_path_escape_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="tcg-path-guard-") as directory:
            with self.assertRaises(ValueError):
                healing._safe_file(Path(directory), "../outside.py")

    def test_github_workflow_is_included_in_integrity_manifest(self):
        with tempfile.TemporaryDirectory(prefix="tcg-workflow-integrity-") as directory:
            root=Path(directory);workflow=root/".github"/"workflows"/"verify.yml"
            workflow.parent.mkdir(parents=True);workflow.write_text("name: verify\n",encoding="utf-8")
            payload=healing.build_integrity_manifest(root)
            self.assertIn(".github/workflows/verify.yml",payload["files"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FaultHealingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"ok": result.wasSuccessful(), "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors)}, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
