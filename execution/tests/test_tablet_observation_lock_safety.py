"""Read-only lock-compatibility regression tests in disposable paths."""
import fcntl
import tempfile
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v382 as v382
import tablet_autonomous_evolution_v385 as v385


class ObservationLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_v382_lock_busy_refuses_second_writer(self):
        path = self.root / "v382.lock"
        fd, info = v382._acquire_lock(path)
        self.assertIsNotNone(fd, info)
        try:
            other, busy = v382._acquire_lock(path)
            self.assertIsNone(other)
            self.assertEqual("V382_CONCURRENT_AUTONOMY_HOLD", busy["status"])
        finally:
            v382._release_lock(fd)

    def test_v385_lock_busy_refuses_second_writer(self):
        path = self.root / "v385.lock"
        fd, info = v385._acquire_lock(path)
        self.assertIsNotNone(fd, info)
        try:
            other, busy = v385._acquire_lock(path)
            self.assertIsNone(other)
            self.assertEqual("V385_CONCURRENT_AUTONOMY_HOLD", busy["status"])
        finally:
            v385._release_lock(fd)

    def test_symlink_lock_is_rejected(self):
        target = self.root / "target"
        target.write_text("do not touch", encoding="utf-8")
        for name, controller in (("v382", v382), ("v385", v385)):
            with self.subTest(name=name):
                link = self.root / (name + ".lock")
                link.symlink_to(target)
                fd, info = controller._acquire_lock(link)
                self.assertIsNone(fd)
                self.assertIn("LOCK_UNAVAILABLE", info["status"])
                self.assertEqual("do not touch", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
