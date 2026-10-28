"""Regression contract for tablet dock navigation; no runtime data or UI changes."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "feature_category_nav.js"


class DockNavigationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.dock = cls.source.split("function renderAppDock(items)", 1)[1].split("function applyAdaptiveDock(", 1)[0]

    def test_shortcut_does_not_report_success_when_screen_open_fails(self):
        shortcut = self.source.split("function navigateShortcut(link)", 1)[1].split("document.querySelectorAll(\".feature-shortcut\")", 1)[0]
        self.assertRegex(shortcut, r"if\s*\(\s*!showManagedTarget\(target\)\s*\)\s*return false",
                         "Shortcut must not show success or scroll after failed screen activation")

    def test_dock_requires_managed_target(self):
        self.assertRegex(self.dock, r"managedTargets\.has\(verifiedTarget\)",
                         "An existing DOM id is not necessarily a registered screen")

    def test_failed_navigation_does_not_activate_or_scroll(self):
        self.assertRegex(self.dock, r"if\s*\(\s*!showManagedTarget\(verifiedTarget\)\s*\)\s*return",
                         "Failed screen activation must not mark the dock active or scroll")

    def test_dock_does_not_force_home_active_after_rerender(self):
        self.assertNotRegex(self.dock, r"home\?\.setAttribute\(\s*[\"']aria-current[\"']",
                            "Rerender must reflect the actual active screen")


if __name__ == "__main__":
    unittest.main()
