"""Regression checks for V1013 second-pass fail-closed comparison."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from execution import offdevice_verify_v1013 as target


class DoublePassTests(unittest.TestCase):
    def test_matching_pair_remains_unverified_for_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "file").write_bytes(b"same")
            (b / "file").write_bytes(b"same")
            result = target.compare(a, b)
            self.assertTrue(result["comparison_pass"])
            self.assertFalse(result["offdevice_copy_verified"])
            self.assertFalse(result["physical_tablet_verified"])
            self.assertFalse(result["ready_for_migration"])

    def test_mutation_between_passes_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "file").write_bytes(b"same")
            (b / "file").write_bytes(b"same")
            original = target.inventory
            calls = [0]

            def changing_inventory(root):
                calls[0] += 1
                if calls[0] == 3:
                    (a / "file").write_bytes(b"changed")
                return original(root)

            with patch.object(target, "inventory", side_effect=changing_inventory):
                result = target.compare(a, b)
            self.assertFalse(result["comparison_pass"])
            self.assertEqual(result["reason"], "changed_between_passes")
            self.assertFalse(result["ready_for_migration"])


if __name__ == "__main__":
    unittest.main()
