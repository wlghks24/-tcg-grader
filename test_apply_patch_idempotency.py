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

    def test_multi_market_patch_is_noop_with_versioned_assets(self):
        self._assert_noop(
            "apply_multi_market_prices_patch.py",
            ("index.html", "tcg_updater.py", ".gitignore"),
        )
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("multi_market_prices.css"), 1)
        self.assertEqual(html.count("multi_market_prices.js"), 1)

    def test_multi_route_patch_is_noop_on_newer_runtime(self):
        self._assert_noop(
            "apply_multi_route_event_patch.py",
            ("social_event_discovery.py",),
        )

    def test_multi_route_patch_rejects_unknown_or_partial_lineage(self):
        import apply_multi_route_event_patch as patcher
        current = (ROOT / 'social_event_discovery.py').read_text(encoding='utf-8')
        partial = current.replace(
            "winner['independent_source_count'] = min(9, sources)",
            "winner['independent_source_count'] = 99",
        )
        with self.assertRaises(RuntimeError):
            patcher.replace_once(partial, 'missing old anchor', 'missing new anchor',
                                 'independent-source counting')
        with self.assertRaises(RuntimeError):
            patcher.replace_once('unknown source', 'missing old anchor', 'missing new anchor',
                                 'independent-source counting')

    def test_collection_meta_patch_is_noop_on_newer_runtime(self):
        self._assert_noop(
            "apply_collection_meta_learning.py",
            ("adaptive_collection_learner.py", "auto_pipeline_runner.py", ".gitignore"),
        )


if __name__ == "__main__":
    unittest.main()
