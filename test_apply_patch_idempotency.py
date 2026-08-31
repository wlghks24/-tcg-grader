import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class PatchIdempotencyTests(unittest.TestCase):
    def _assert_noop(self, script: str, targets: tuple[str, ...]) -> None:
        before = {name: (ROOT / name).read_bytes() for name in targets}
        result = subprocess.run(
            [sys.executable, script], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        after = {name: (ROOT / name).read_bytes() for name in targets}
        self.assertEqual(before, after, result.stdout)

    def test_multi_route_patch_is_noop_on_newer_runtime(self):
        self._assert_noop(
            "apply_multi_route_event_patch.py",
            ("social_event_discovery.py",),
        )

    def test_collection_meta_patch_is_noop_on_newer_runtime(self):
        self._assert_noop(
            "apply_collection_meta_learning.py",
            ("adaptive_collection_learner.py", "auto_pipeline_runner.py", ".gitignore"),
        )


if __name__ == "__main__":
    unittest.main()
