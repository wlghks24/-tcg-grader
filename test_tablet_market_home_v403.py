import re
import unittest
from pathlib import Path

import tablet_runtime_manifest

ROOT = Path(__file__).resolve().parent


class TabletMarketHomeV403Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "tablet_market_home_v403.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "tablet_market_home_v403.css").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")

    def test_video_inspired_home_assets_are_mounted_and_delivered(self):
        self.assertIn("tablet_market_home_v403.css?v=403", self.html)
        self.assertIn("tablet_market_home_v403.js?v=403", self.html)
        self.assertIn("./tablet_market_home_v403.css", self.sw)
        self.assertIn("./tablet_market_home_v403.js", self.sw)
        self.assertIn("'tablet_market_home_v403.css'", self.updater)
        self.assertIn("'tablet_market_home_v403.js'", self.updater)
        self.assertIn("tablet_market_home_v403.css", tablet_runtime_manifest.TABLET_PWA_ENTRY_FILES)
        self.assertIn("tablet_market_home_v403.js", tablet_runtime_manifest.TABLET_PWA_ENTRY_FILES)

    def test_home_exposes_search_camera_quick_actions_games_and_market_modules(self):
        for token in (
            "태블릿 AI 카드 홈",
            "카드명 · 카드번호 · BOX · 세트명 검색",
            "카메라로 카드 촬영",
            "카드 등급 측정",
            "시세 확인",
            "출시·프로모",
            "구매처·거리",
            "최근 카드 시세",
            "BOX 시세",
            "시장 주목 TOP 10",
            "안산·경기 오프라인 구매처",
            "Pokémon",
            "ONE PIECE",
            "NARUTO",
        ):
            self.assertIn(token, self.js)

    def test_market_home_uses_only_verified_existing_data_surfaces(self):
        for token in (
            "./market_prices.json",
            "./market_watch.json",
            "./purchase_sources.json",
            "./tablet_autonomy_v400_report.json",
            "sourceDate",
            "sale_status",
            "link_status",
            "official_price",
        ):
            self.assertIn(token, self.js)
        self.assertIn("인기·상승을 임의 추정하지 않음", self.js)
        self.assertNotIn("market_direction = ", self.js)
        self.assertNotIn("pricePrediction", self.js)
        self.assertNotIn("stockConfirmed = true", self.js)

    def test_home_ai_reorders_only_known_home_modules_from_existing_v400_plan(self):
        for token in (
            'Object.freeze(["market","box","top","nearby"])',
            "screen_module_plan",
            "top_features",
            "data-tmh-module",
            "AI 홈 정렬",
            "tcgMarketHomeAiV403",
        ):
            self.assertIn(token, self.js)
        self.assertNotIn("eval(", self.js)
        self.assertNotIn("new Function(", self.js)
        self.assertNotIn("insertAdjacentHTML", self.js)
        self.assertNotIn("innerHTML =", self.js)

    def test_camera_entry_explains_permission_before_existing_camera_button(self):
        permission = self.js.index("카드 촬영을 위해 카메라 권한이 필요합니다")
        confirm = self.js.index("confirmCameraPermission")
        existing = self.js.index('byId("startAutoCamera")')
        self.assertGreaterEqual(permission, 0)
        self.assertGreaterEqual(confirm, 0)
        self.assertGreater(existing, confirm)
        self.assertIn("브라우저 권한창에서 카메라를 허용", self.js)
        self.assertNotIn("getUserMedia(", self.js)

    def test_purchase_region_picker_filters_offline_sources_and_preserves_inventory_warning(self):
        self.assertIn('id="purchaseAreaPreset"', self.html)
        for region in ("안산", "경기", "서울", "인천", "부산", "제주"):
            self.assertIn(f'<option value="{region}">{region}</option>', self.html)
        self.assertIn("areaMatches=x=>", self.html)
        self.assertIn('(x.channel||"online")!=="offline"', self.html)
        self.assertIn('purchaseChannel="offline"', self.html)
        self.assertIn("실제 도로거리와 재고는 지도·매장에서 확인하세요.", self.html)

    def test_responsive_accessible_and_service_worker_abi_is_preserved(self):
        for token in (
            "@media(max-width:820px)",
            "@media(max-width:520px)",
            "@media(prefers-color-scheme:dark)",
            "@media(prefers-reduced-motion:reduce)",
            "@media(forced-colors:active)",
        ):
            self.assertIn(token, self.css)
        self.assertIn('aria-live', self.js)
        self.assertIn('aria-modal', self.js)
        self.assertIn("tcg-v276-network-first-runtime", self.sw)
        self.assertNotIn("tcg-v277-network-first-runtime", self.sw)

    def test_no_user_behavior_telemetry_or_mutating_network_calls(self):
        for token in (
            'addEventListener("pointermove"',
            'addEventListener("mousemove"',
            "sendBeacon",
            '"POST"',
            '"PUT"',
            '"DELETE"',
        ):
            self.assertNotIn(token, self.js)
        self.assertNotIn("navigator.geolocation", self.js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
