import re
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy

ROOT = Path(__file__).resolve().parent


class TabletVideoNeuralDockV407Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Scope historical dock security assertions to the dock module only.
        # V485 appends a separate read-only market-home data loader below it.
        cls.nav = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8").split(
            "/* V485: Screenshot-informed, evidence-only market home.", 1
        )[0]
        cls.dashboard = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")

    def test_video_informed_dock_has_five_slots_and_fixed_primary_capture(self):
        self.assertIn("repeat(5,minmax(0,1fr))", self.nav)
        self.assertIn('key: "scan", icon: "＋", label: "촬영", target: "simpleGradeV32", primary: true', self.nav)
        self.assertIn(
            "Object.freeze([FIXED_DOCK_MENU, chosen[0], FIXED_DOCK_PRIMARY, chosen[1], chosen[2]])",
            self.nav,
        )
        self.assertIn("app-bottom-dock-primary", self.nav)
        self.assertIn("v407-video-neural-dock", self.nav)

    def test_adaptive_dock_allowlist_exactly_matches_existing_eighteen_features(self):
        block = self.nav.split("const ADAPTIVE_DOCK_FEATURES = Object.freeze({", 1)[1].split("\n  });", 1)[0]
        keys = set(re.findall(r'^\s+"([^"]+)":Object\.freeze\(', block, flags=re.MULTILINE))
        expected = {
            key
            for category in autonomy.CATEGORY_ORDER
            for key in autonomy.FEATURE_SHORTCUT_ORDER[category]
        }
        self.assertEqual(expected, keys)
        self.assertEqual(18, len(keys))
        self.assertIn("usedTargets", self.nav)
        self.assertIn("chosen.length !== 3", self.nav)

    def test_screen_neural_rankings_drive_dock_without_behavior_tracking(self):
        self.assertIn("screen_module_plan.rankings.map", self.dashboard)
        self.assertIn("TCGFeatureCategoryNav?.applyAdaptiveDock", self.dashboard)
        self.assertIn("enabled ? dockFeatures : []", self.dashboard)
        self.assertIn("검증된 화면 신경망 순위의 허용 기능만 자동 재구성", self.dashboard)
        for source in (self.nav, self.dashboard):
            self.assertNotIn("navigator.sendBeacon", source)
            self.assertNotIn('addEventListener("pointermove"', source)
            self.assertNotIn('addEventListener("mousemove"', source)
            self.assertNotIn("eval(", source)

    def test_dock_cannot_invent_target_or_command(self):
        self.assertIn("const item = ADAPTIVE_DOCK_FEATURES[key]", self.nav)
        self.assertIn("!item || usedTargets.has(item.target) || !safeTarget(item.target)", self.nav)
        self.assertIn("const verifiedTarget = safeTarget(item.target)", self.nav)
        self.assertNotIn("localStorage", self.nav)
        self.assertNotIn("sessionStorage", self.nav)
        self.assertNotIn("fetch(", self.nav)


if __name__ == "__main__":
    unittest.main(verbosity=2)
