"""Read-only failure-injection tests for advisory image-model promotion writes.

Covers existing per-file atomicity; does NOT prove a two-file transaction.
No physical tablet, training, external API, or production model activation.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from execution import tablet_image_model_gate as gate


class ImageAdvisoryPromotionFailureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.path = root / "model.champion.json"
        self.backup = root / "model.last-good.json"
        self.old = {"id": "old", "production_enabled": False}
        self.earlier = {"id": "earlier", "production_enabled": False}
        self.new = {"id": "new", "production_enabled": False}
        gate.atomic_write_json(self.path, self.old)
        gate.atomic_write_json(self.backup, self.earlier)

    @staticmethod
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_success_copies_previous_champion_to_backup(self):
        gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.old, self.read(self.backup))
        self.assertEqual(self.new, self.read(self.path))

    def test_backup_write_failure_never_overwrites_champion(self):
        with patch.object(gate, "atomic_write_json",
                          side_effect=OSError("backup write denied")):
            with self.assertRaises(OSError):
                gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual(self.earlier, self.read(self.backup))

    def test_candidate_write_failure_keeps_prior_champion_and_backup(self):
        original = gate.atomic_write_json
        seen = []
        def fail_candidate(path, value):
            seen.append(Path(path))
            if Path(path) == self.path:
                raise OSError("candidate write denied")
            return original(path, value)
        with patch.object(gate, "atomic_write_json", side_effect=fail_candidate):
            with self.assertRaises(OSError):
                gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual([self.backup, self.path], seen)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual(self.old, self.read(self.backup))

    def test_json_nan_cannot_publish_candidate(self):
        with self.assertRaises((TypeError, ValueError)):
            gate.promote(self.path, self.backup,
                         dict(self.new, loss=float("nan")), self.old)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual(self.old, self.read(self.backup))

    def test_post_commit_exception_leaves_explicit_restore_possible(self):
        original = gate.atomic_write_json
        def commit_then_raise(path, value):
            result = original(path, value)
            if Path(path) == self.path:
                raise OSError("injected post-commit acknowledgement failure")
            return result
        with patch.object(gate, "atomic_write_json",
                          side_effect=commit_then_raise):
            with self.assertRaises(OSError):
                gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.new, self.read(self.path))
        self.assertEqual(self.old, self.read(self.backup))
        # Recovery is deliberately explicit, not a claim of auto-rollback.
        original(self.path, self.read(self.backup))
        self.assertEqual(self.old, self.read(self.path))

    def test_absent_champion_does_not_rewrite_existing_backup(self):
        self.path.unlink()  # A genuinely new model must not overwrite an existing one.
        gate.promote(self.path, self.backup, self.new, None)
        self.assertEqual(self.earlier, self.read(self.backup))
        self.assertEqual(self.new, self.read(self.path))

    def test_symlink_backup_rejected_before_champion_replacement(self):
        outside = Path(self.directory.name) / "outside"
        outside.write_text("unchanged", encoding="utf-8")
        self.backup.unlink()
        self.backup.symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual("unchanged", outside.read_text(encoding="utf-8"))

    def test_symlink_champion_rejected_without_target_write(self):
        outside = Path(self.directory.name) / "outside-champion"
        outside.write_text("unchanged", encoding="utf-8")
        self.path.unlink()
        self.path.symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            gate.promote(self.path, self.backup, self.new, self.old)
        self.assertTrue(self.path.is_symlink())
        self.assertEqual("unchanged", outside.read_text(encoding="utf-8"))
        self.assertEqual(self.earlier, self.read(self.backup))

    def test_equal_champion_and_last_good_paths_denied(self):
        with self.assertRaisesRegex(ValueError, 'COLLISION'):
            gate.promote(self.path, self.path, self.new, self.old)
        self.assertEqual(self.old, self.read(self.path))

    def test_normalized_backup_alias_denied(self):
        alias = self.path.parent / '.' / self.path.name
        with self.assertRaisesRegex(ValueError, 'COLLISION'):
            gate.promote(self.path, alias, self.new, self.old)
        self.assertEqual(self.old, self.read(self.path))

    def test_stale_champion_argument_denied_without_overwriting_backup(self):
        with self.assertRaisesRegex(ValueError, 'STALE'):
            gate.promote(self.path, self.backup, self.new, self.earlier)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual(self.earlier, self.read(self.backup))

    def test_missing_champion_snapshot_with_existing_file_denied(self):
        with self.assertRaisesRegex(ValueError, 'STALE'):
            gate.promote(self.path, self.backup, self.new, None)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual(self.earlier, self.read(self.backup))

    def test_deleted_champion_with_stale_snapshot_denied(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'DISAPPEARED'):
            gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.earlier, self.read(self.backup))

    def test_corrupted_live_model_denied_before_backup(self):
        self.path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.earlier, self.read(self.backup))

    def test_real_atomic_replace_failure_leaves_no_temp_files(self):
        original = os.replace
        def reject_model_replace(src, dst):
            if Path(dst) == self.path:
                raise OSError("injected atomic os.replace error")
            return original(src, dst)
        with patch("safe_runtime.os.replace", side_effect=reject_model_replace):
            with self.assertRaises(OSError):
                gate.promote(self.path, self.backup, self.new, self.old)
        self.assertEqual(self.old, self.read(self.path))
        self.assertEqual(self.old, self.read(self.backup))
        self.assertEqual([], list(Path(self.directory.name).glob("*.tmp")))
        self.assertEqual([], list(Path(self.directory.name).glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
