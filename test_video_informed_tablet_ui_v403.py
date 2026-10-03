import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class VideoInformedTabletUiV403Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "video_informed_tablet_ui_v403.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "video_informed_tablet_ui_v403.css").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        cls.verify = (ROOT / "VERIFY_TABLET_FINAL.sh").read_text(encoding="utf-8")

    def test_assets_are_mounted_cached_served_and_delivered(self):
        self.assertIn("video_informed_tablet_ui_v403.css?v=403", self.html)
        self.assertIn("video_informed_tablet_ui_v403.js?v=403", self.html)
        for name in ("video_informed_tablet_ui_v403.css", "video_informed_tablet_ui_v403.js"):
            self.assertIn(name, self.sw)
            self.assertIn(name, self.updater)
            self.assertIn(name, self.manifest)
            self.assertIn(name, self.verify)

    def test_video_findings_are_implemented_as_real_ui_modules(self):
        for token in (
            "AI 시장·작업 홈",
            "시장 활동 TOP",
            "출시 · 프로모",
            "촬영 전 품질 확인",
            "purchase-split-v403",
            "등록 좌표 기반 미니맵",
            "내 카드 포트폴리오",
            "현재 분석 불러오기",
        ):
            self.assertIn(token, self.js + self.css)

    def test_market_home_is_driven_by_existing_neural_feature_plan(self):
        for token in (
            "tablet_autonomy_v400_report.json",
            "screen_module_plan",
            "top_features",
            "MODULE_FEATURES",
            "adaptiveLayoutEnabled",
            "tcgAdaptiveLayoutV400",
            "reorderHome",
        ):
            self.assertIn(token, self.js)
        self.assertIn("상승예측이 아니라", self.js)
        self.assertNotIn("predicted_price", self.js)
        self.assertNotIn("forecast_price", self.js)

    def test_capture_preflight_uses_existing_camera_runtime_status_not_fake_scores(self):
        for token in (
            'document.getElementById("cameraStatus")',
            "노출 양호",
            "초점 양호",
            "흔들림 안정",
            "자동촬영",
            "MutationObserver",
            "tcgCameraRuntime",
        ):
            self.assertIn(token, self.js)
        self.assertNotIn("Math.random", self.js)

    def test_purchase_workspace_requires_explicit_location_and_does_not_persist_coordinates(self):
        self.assertIn('current.addEventListener("click",useCurrentLocation)', self.js)
        self.assertIn("navigator.geolocation.getCurrentPosition", self.js)
        self.assertIn("precise_location_persisted:false", self.js)
        self.assertIn("위치 좌표는 저장하지 않습니다", self.js)
        self.assertNotRegex(self.js, r"saveJson\([^\n]*localLocation")
        self.assertNotRegex(self.js, r"localStorage\.setItem\([^\n]*(latitude|longitude|coords)")

    def test_region_picker_is_compact_and_recent_regions_are_local_only(self):
        self.assertIn("PROVINCES", self.js)
        self.assertIn("최근지역", self.js)
        self.assertIn("tcgVideoRecentRegionsV403", self.js)
        self.assertIn("시·군·구 또는 동 검색", self.js)
        self.assertNotIn("sendBeacon", self.js)

    def test_portfolio_only_uses_user_entered_prices_and_local_storage(self):
        self.assertIn("tcgVideoPortfolioV403", self.js)
        self.assertIn("1장 보유원가(원)", self.js)
        self.assertIn("1장 현재가(원)", self.js)
        self.assertIn("자동으로 지어내지 않고 직접 입력한 값만 합산", self.js)
        self.assertIn("portfolio_local_only:true", self.js)
        self.assertNotIn("/api/portfolio", self.js)

    def test_bottom_navigation_safe_area_is_preserved(self):
        self.assertIn("env(safe-area-inset-bottom,0px)", self.css)
        self.assertRegex(self.css, r"body\{padding-bottom:calc\(")

    def test_new_layer_avoids_arbitrary_html_execution(self):
        self.assertNotIn("innerHTML =", self.js)
        self.assertNotIn("eval(", self.js)
        self.assertNotIn("new Function", self.js)
        self.assertNotIn("document.write", self.js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
