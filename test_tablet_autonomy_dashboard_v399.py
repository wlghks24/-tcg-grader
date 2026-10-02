import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class TabletAutonomyDashboardV399Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "tablet_autonomy_dashboard_v399.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "tablet_autonomy_dashboard_v399.css").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "main").read_text(encoding="utf-8")

    def test_dashboard_assets_are_mounted_and_cached(self):
        self.assertIn("tablet_autonomy_dashboard_v399.css?v=399", self.html)
        self.assertIn("tablet_autonomy_dashboard_v399.js?v=399", self.html)
        self.assertIn("tablet_autonomy_dashboard_v399.css", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v399.js", self.sw)

    def test_dashboard_reads_runtime_report_without_mutation_endpoint(self):
        self.assertIn('const REPORT_URL = "./tablet_autonomy_v399_report.json"', self.js)
        self.assertIn('headers: {"Accept": "application/json"}', self.js)
        self.assertNotIn("POST", self.js)
        self.assertNotIn("PUT", self.js)
        self.assertNotIn("DELETE", self.js)
        self.assertIn("aria-live", self.js)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_server_and_runtime_bundle_expose_required_assets(self):
        for name in (
            "tablet_autonomy_dashboard_v399.css",
            "tablet_autonomy_dashboard_v399.js",
            "tablet_autonomy_v399_report.json",
        ):
            self.assertIn(name, self.updater)
        for name in (
            "tablet_autonomous_evolution_v399.py",
            "tablet_autonomy_dashboard_v399.css",
            "tablet_autonomy_dashboard_v399.js",
        ):
            self.assertIn(name, self.manifest)
        self.assertIn(
            "tablet_autonomous_evolution_v399.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            self.main,
        )

    def test_dashboard_surfaces_full_autonomy_chain(self):
        for label in (
            "현재 목표",
            "검증학습 샘플",
            "기능 후보",
            "선택 기능",
            "Canary 상태",
            "Rollback",
            "UI/PWA 건강도",
            "UI 보완 후보",
            "안전 게이트",
            "실기기 확인",
        ):
            self.assertIn(label, self.js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
