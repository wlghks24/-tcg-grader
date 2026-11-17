"""V1028: preserve phone/tablet navigation and touch-safe UI contracts.

Static regression checks; they do not claim physical device or browser rendering.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CrossDeviceUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / 'index.html').read_text(encoding='utf-8')
        cls.shell = (ROOT / 'execution/tablet_menu_shell_v903.py').read_text(encoding='utf-8')
        cls.runtime = (ROOT / 'execution/tablet_menu_shell_v903.js').read_text(encoding='utf-8')

    def test_mobile_viewport_and_one_app_shell(self):
        self.assertRegex(self.page, r'<meta\s+name="viewport"\s+content="width=device-width,initial-scale=1')
        self.assertIn('id="tcg903-top"', self.shell)
        self.assertIn('id="tcg903-drawer"', self.shell)
        self.assertIn('id="tcg903-home"', self.shell)
        self.assertIn('id="tcg903-events"', self.shell)
        self.assertIn('기존 통합 도구', self.runtime)

    def test_phone_has_compact_grid_and_touch_targets(self):
        self.assertIn('@media(max-width:600px)', self.shell)
        self.assertIn('.tcg903-quick{grid-template-columns:repeat(2,minmax(0,1fr))', self.shell)
        self.assertIn('width:min(86vw,320px)', self.shell)
        self.assertIn('min-height:46px', self.shell)
        self.assertIn('font:16px/1.5 system-ui', self.shell)
        self.assertIn('repeat(auto-fill,minmax(min(100%,245px),1fr))', self.shell)

    def test_tablet_wide_layout_and_compact_drawer_are_distinct(self):
        self.assertIn('@media(min-width:1100px)', self.shell)
        self.assertIn('padding-left:280px!important', self.shell)
        self.assertIn('window.matchMedia("(min-width:1100px)")', self.runtime)
        self.assertIn('drawer.inert = !open && !desktop();', self.runtime)
        self.assertIn('drawer.setAttribute("aria-modal", "true")', self.runtime)
        self.assertIn('node("close").focus()', self.runtime)
        self.assertIn('returnFocus.focus()', self.runtime)
        self.assertIn('window.addEventListener("resize"', self.runtime)

    def test_switching_out_of_camera_view_stops_stream(self):
        self.assertIn('window.tcgCameraRuntime?.stop?.();', self.runtime)
        self.assertIn('setView("home",', self.runtime)
        self.assertIn('clearCardContext();', self.runtime)
        self.assertIn('card.dataset.cardGradeBlocked === "true"', self.runtime)


if __name__ == '__main__':
    unittest.main()
