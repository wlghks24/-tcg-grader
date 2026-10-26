"""Exact V682 source/ancestry proof; preserves old generation evidence without suppression."""
from pathlib import Path
import hashlib
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BASE = '2f30e8cbe790c9e4c1d7eed1ad6443b3c3271f3f'
CANDIDATE = 'dafdd3a07d2f6e960eb5ebaef8708321d3a72798'
REVIEWED = {'.github/workflows/v678-immutable-preview-guard.yml': 'ed98e585454af749240b7c09d7bfe9cd43d499dead13d4fc56e4fa2fe713a76f', 'docs/tablet/V682_CROSS_REVIEW_20261026.md': '1b000618e5acf961663b6e8702ccab5b160fda4b736992261eebe5c9973fba91', 'docs/tablet/v679/tablet_unified_dashboard_v679.html': '11a1e98a990dfa99462d2312fb83e2b7e0a8e85fe96183ab46d6d8e9a22fd682', 'docs/tablet/v679/tablet_unified_dashboard_v679.js': '2f4131217557e9f43352371c402bdb9621bd7943c1041fa9b33e393dafed13f5', 'execution/tablet_learning_gap_advisor_v676.py': '4ad3f19654489934db33202449388fa09b7199f2897821a7ba81c2db38959f73', 'execution/tablet_v678_preview.py': '89b27501cb2aff9f1fee4cab64522ce302f2342e084b1ab994ad1e10852b2c59', 'execution/tests/test_market_collector_security_v682.py': 'f065e1beabc98908c3bd35c62234e6207eeb597bd3df23c0cd2903e29024acb2', 'execution/tests/test_tablet_learning_gap_advisor_v676.py': 'e6ef6db44664d78827f1bd9e7bc17144a2eaea01f94f39dec32f494e4c7b5113', 'execution/tests/test_tablet_unified_dashboard_v679.cjs': '27bbb7e00f117c19327beb307acc01dd611f602f58f4a276cdadb8670b3e1fa5', 'execution/tests/test_v678_preview_route.py': '54b784218660e2528dc82ad899017e8effdcfd732cd3d78fed0ebc2425174d59', 'multi_market_price_collector.py': 'ac8b1239f5840d445c8f986740e5b083edea41db6ba3acfcd5824ddc3fcf1348'}
BASELINE = {'.github/workflows/v678-immutable-preview-guard.yml': 'ea189e5fb700cf2c494b9f3a7d0e89cec93212d6c655ce4b317b94d03adc62ab', 'docs/tablet/V682_CROSS_REVIEW_20261026.md': None, 'docs/tablet/v679/tablet_unified_dashboard_v679.html': '9ee08d08ec1fe82261f99e83751d984059e761514652dad3d1e64556c959006b', 'docs/tablet/v679/tablet_unified_dashboard_v679.js': 'bbdcf7568d410469d7f36f35c3dd192e2f4be907212925f9de6b52dc1e683d58', 'execution/tablet_learning_gap_advisor_v676.py': 'cd27fb5872e42099ac1c7899bd7b5b605c90e7748c92f859b987a800c0fc81e2', 'execution/tablet_v678_preview.py': 'b9b526ac105ad8d1550841feff97199ab96ce5ad2d475312311171c7d69caa5b', 'execution/tests/test_market_collector_security_v682.py': None, 'execution/tests/test_tablet_learning_gap_advisor_v676.py': 'f0b9863fe7429865ca6a616650330c77582945ff3d73a7d944e59e44d1ab49f0', 'execution/tests/test_tablet_unified_dashboard_v679.cjs': 'ed5969940cfeb2a3f42a1b7903949cadfe6daf5240f969b4e08d466571c8bcf7', 'execution/tests/test_v678_preview_route.py': 'b4599db932a222e9e281463d5fb5e627c459f8d76cdac18b473bfe3b5226e9e1', 'multi_market_price_collector.py': '6ceb07258e958d37b84a4d5295b0fbc32013ebcb1f85ffd7f1c57298f9892939'}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False, timeout=20)


def verify_current():
    for name, digest in REVIEWED.items():
        target = ROOT / name
        if target.is_symlink() or not target.is_file():
            raise ValueError("unsafe reviewed source: " + name)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("changed reviewed source: " + name)
    updater = ROOT / "tcg_updater.py"
    if updater.is_symlink() or hashlib.sha256(updater.read_bytes()).hexdigest() != \
            "a7d930aca8afbc37497256ae0c0b60ff77a1aa75dc4704f6d9d12e349ae0bfa5":
        raise ValueError("immutable production updater changed")


class V682SourceSuccessorTests(unittest.TestCase):
    def test_exact_candidate_scope_ancestry_and_baseline_bytes(self):
        self.assertEqual(git("merge-base", "--is-ancestor", BASE, CANDIDATE).returncode, 0)
        self.assertEqual(git("merge-base", "--is-ancestor", CANDIDATE, "HEAD").returncode, 0)
        diff = git("diff", "--name-only", BASE, CANDIDATE)
        self.assertEqual(diff.returncode, 0)
        self.assertEqual(set(diff.stdout.decode().splitlines()), set(REVIEWED) | {"integrity_manifest.json"})
        for name, digest in REVIEWED.items():
            with self.subTest(path=name):
                before = git("show", BASE + ":" + name)
                baseline = hashlib.sha256(before.stdout).hexdigest() if before.returncode == 0 else None
                self.assertEqual(baseline, BASELINE[name])
                after = git("show", CANDIDATE + ":" + name)
                self.assertEqual(after.returncode, 0)
                self.assertEqual(hashlib.sha256(after.stdout).hexdigest(), digest)
        verify_current()

    def test_post_review_tampering_is_not_hidden_by_historical_boundaries(self):
        original = Path.read_bytes
        for name in ("multi_market_price_collector.py", "execution/tablet_v678_preview.py",
                     "execution/tablet_learning_gap_advisor_v676.py",
                     "docs/tablet/v679/tablet_unified_dashboard_v679.js"):
            def changed(path):
                raw = original(path)
                return raw + b"unreviewed" if path == ROOT / name else raw
            with self.subTest(path=name), patch.object(Path, "read_bytes", changed):
                with self.assertRaisesRegex(ValueError, "changed reviewed source"):
                    verify_current()

    def test_symlink_and_immutable_updater_mutation_are_rejected(self):
        original_link, original_read = Path.is_symlink, Path.read_bytes
        target = ROOT / "multi_market_price_collector.py"
        with patch.object(Path, "is_symlink", lambda p: p == target or original_link(p)):
            with self.assertRaisesRegex(ValueError, "unsafe reviewed source"):
                verify_current()
        updater = ROOT / "tcg_updater.py"
        with patch.object(Path, "read_bytes", lambda p: b"modified" if p == updater else original_read(p)):
            with self.assertRaisesRegex(ValueError, "immutable production updater"):
                verify_current()


if __name__ == "__main__":
    unittest.main()
