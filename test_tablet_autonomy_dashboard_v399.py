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

    def test_v399_dashboard_artifacts_remain_valid_historical_runtime_inputs(self):
        self.assertIn('const REPORT_URL = "./tablet_autonomy_v399_report.json"', self.js)
        self.assertIn('headers: {"Accept": "application/json"}', self.js)
        self.assertNotIn("POST", self.js)
        self.assertNotIn("PUT", self.js)
        self.assertNotIn("DELETE", self.js)
        self.assertIn("aria-live", self.js)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn("tablet_autonomous_evolution_v399.py", self.manifest)

    def test_v400_is_current_dashboard_successor(self):
        self.assertIn("tablet_autonomy_dashboard_v400.css?v=400", self.html)
        self.assertIn("tablet_autonomy_dashboard_v400.js?v=400", self.html)
        self.assertIn("tablet_autonomy_dashboard_v400.css", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v400.js", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v400.css", self.updater)
        self.assertIn("tablet_autonomy_dashboard_v400.js", self.updater)
        self.assertIn("tablet_autonomy_v400_report.json", self.updater)
        self.assertIn(
            "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            self.main,
        )

    def test_v399_dashboard_still_documents_full_predecessor_autonomy_chain(self):
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
