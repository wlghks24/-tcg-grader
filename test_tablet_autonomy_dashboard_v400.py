import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class TabletAutonomyDashboardV400Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "tablet_autonomy_dashboard_v400.css").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "main").read_text(encoding="utf-8")

    def test_v400_dashboard_assets_are_mounted_cached_and_exposed(self):
        self.assertIn("tablet_autonomy_dashboard_v400.css?v=400", self.html)
        self.assertIn("tablet_autonomy_dashboard_v400.js?v=400", self.html)
        self.assertIn("tablet_autonomy_dashboard_v400.css", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v400.js", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v400.css", self.updater)
        self.assertIn("tablet_autonomy_dashboard_v400.js", self.updater)
        self.assertIn("tablet_autonomy_v400_report.json", self.updater)

    def test_dashboard_is_read_only_and_accessible(self):
        self.assertIn('const REPORT_URL = "./tablet_autonomy_v400_report.json"', self.js)
        self.assertIn('headers: {"Accept": "application/json"}', self.js)
        self.assertNotIn("POST", self.js)
        self.assertNotIn("PUT", self.js)
        self.assertNotIn("DELETE", self.js)
        self.assertIn("aria-live", self.js)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_five_requested_surfaces_are_visible(self):
        for label in (
            "UI · PWA",
            "카드 측정 · 등급",
            "카드 시세",
            "카드 발급 · 출시",
            "콜라보 · 이벤트",
            "현재 최우선 영역",
            "보완 긴급도",
            "V400 Canary",
            "Rollback",
            "보호 PR 후보",
            "안전 게이트",
        ):
            self.assertIn(label, self.js)

    def test_runtime_route_and_bundle_use_v400_while_preserving_v399_core(self):
        for name in (
            "tablet_autonomous_evolution_v399.py",
            "tablet_autonomous_evolution_v400.py",
            "tablet_autonomy_dashboard_v400.css",
            "tablet_autonomy_dashboard_v400.js",
        ):
            self.assertIn(name, self.manifest)
        self.assertIn(
            "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            self.main,
        )
        self.assertNotIn(
            "exec python tablet_autonomous_evolution_v399.py --domain tablet_gpt --execute-safe-learning",
            self.main,
        )

    def test_service_worker_cache_preserves_compatible_abi(self):
        self.assertIn("tcg-v276-network-first-runtime", self.sw)
        self.assertNotIn("tcg-v277-network-first-runtime", self.sw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
