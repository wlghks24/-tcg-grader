import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v377 as v377


class TabletAutonomousEvolutionV377Tests(unittest.TestCase):
    def test_plan_only_delegates_without_lock(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v377.v376, "run_cycle", return_value={"controller_version": "v376", "v376_status": "PLAN_ONLY"}
        ) as core:
            result = v377.run_cycle(root=Path(td), persist_outputs=False)
            self.assertEqual("v377", result["controller_version"])
            self.assertEqual("v376", result["core_controller_version"])
            self.assertEqual("PLAN_ONLY", result["v377_status"])
            self.assertEqual("LOCK_NOT_REQUIRED", result["single_run_lock"]["status"])
            core.assert_called_once()

    def test_mutating_cycle_holds_when_lock_is_busy_without_delegating(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lock_path = root / v377.LOCK_PATH.name
            fd = lock_path.open("a+")
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with mock.patch.object(v377.v376, "run_cycle") as core:
                    result = v377.run_cycle(
                        execute=True,
                        apply_capabilities=True,
                        train_meta=True,
                        apply_skills=True,
                        root=root,
                        lock_path=lock_path,
                        persist_outputs=False,
                    )
                    core.assert_not_called()
                self.assertEqual("CONCURRENT_AUTONOMY_HOLD", result["v377_status"])
                self.assertFalse(result["execution"]["executed"])
                self.assertEqual("LOCK_BUSY", result["single_run_lock"]["error_code"])
                self.assertFalse((root / v377.v376.EXECUTION_JOURNAL_PATH.name).exists())
            finally:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                fd.close()

    def test_mutating_cycle_delegates_under_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v377.v376,
            "run_cycle",
            return_value={"controller_version": "v376", "v376_status": "V376_EXECUTED", "execution": {"executed": True}},
        ) as core:
            result = v377.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                persist_outputs=False,
            )
            self.assertEqual("V376_EXECUTED", result["v377_status"])
            self.assertEqual("LOCK_ACQUIRED", result["single_run_lock"]["status"])
            self.assertTrue(result["safety"]["single_mutating_cycle_lock_required"])
            core.assert_called_once()

    def test_symlink_lock_fails_closed_when_nofollow_is_available(self):
        if not hasattr(v377.os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as td, mock.patch.object(v377.v376, "run_cycle") as core:
            root = Path(td)
            target = root / "target"
            target.write_text("x", encoding="utf-8")
            link = root / v377.LOCK_PATH.name
            link.symlink_to(target)
            result = v377.run_cycle(
                apply_skills=True,
                root=root,
                lock_path=link,
                persist_outputs=False,
            )
            core.assert_not_called()
            self.assertEqual("AUTONOMY_LOCK_UNAVAILABLE", result["v377_status"])
            self.assertFalse(result["execution"]["executed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
