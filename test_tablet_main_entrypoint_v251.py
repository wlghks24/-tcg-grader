from pathlib import Path
import unittest


class TabletMainEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent
        self.main = (self.root / 'main').read_text(encoding='utf-8')
        self.publisher = (self.root / 'tablet_collection_publish.py').read_text(encoding='utf-8')
        self.contextual = (self.root / 'tablet_collection_publish_contextual.py').read_text(encoding='utf-8')

    def test_main_routes_to_existing_safe_runtime(self):
        required = (
            'exec bash ANDROID_UPDATE_AND_START.sh',
            'exec python tablet_collection_publish_contextual.py',
            'exec python tablet_collection_publish_contextual.py --publish',
            'exec bash VERIFY_TABLET_FINAL.sh',
            'exec bash ANDROID_RECOVER_UPDATE.sh',
        )
        for token in required:
            self.assertIn(token, self.main)
        self.assertNotIn('exec python tablet_collection_publish.py\n', self.main)
        self.assertNotIn('exec python tablet_collection_publish.py --publish', self.main)

    def test_contextual_wrapper_preserves_fail_closed_publisher_and_same_cycle_freshness(self):
        self.assertIn('import tablet_collection_publish as core', self.contextual)
        self.assertIn('collection_verification_gate_contextual.py', self.contextual)
        self.assertIn("'--max-health-age-seconds', '900'", self.contextual)
        self.assertIn("'--fail-on-degraded'", self.contextual)
        self.assertIn('core.gates = gates', self.contextual)
        self.assertIn('return core.main()', self.contextual)

    def test_publish_requires_latest_main_and_pr_only_delivery(self):
        self.assertIn("git(root, 'fetch', 'origin', 'main')", self.publisher)
        self.assertIn("if publish and source != base", self.publisher)
        self.assertIn("gh', 'pr', 'create'", self.publisher)
        self.assertNotIn("push', 'origin', 'main'", self.publisher)
        self.assertNotIn("--force", self.publisher)

    def test_fail_closed_contract_is_not_weakened(self):
        self.assertIn("'--fail-on-degraded'", self.publisher)
        self.assertIn("공개 산출물 누락 또는 심볼릭 링크", self.publisher)
        self.assertIn("커밋 이후 변경", self.publisher)
        self.assertIn("수집 중 main 변경", self.publisher)


if __name__ == '__main__':
    unittest.main()
