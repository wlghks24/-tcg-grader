"""Static regression checks for the five-item adaptive tablet dock.

These guard source-level invariants; they do not replace browser/device tests.
"""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "feature_category_nav.js"

class DockNavigationSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.dock = cls.source.split("function renderAppDock(items) {", 1)[1].split("\n  function applyAdaptiveDock(", 1)[0]

    def test_five_items_required(self):
        self.assertIn("items.length !== 5", self.dock)

    def test_all_destinations_checked_before_dom_mutation(self):
        guard = self.dock.index("items.some(")
        create = self.dock.index("document.createElement(\"nav\")")
        replace = self.dock.index("dock.replaceChildren()")
        self.assertLess(guard, create)
        self.assertLess(guard, replace)
        self.assertIn("!managedTargets.has(safeTarget(item.target))", self.dock)

    def test_repeat_render_signature_skips_rebuild(self):
        self.assertIn("dock.dataset.renderSignature === nextSignature", self.dock)
        self.assertLess(self.dock.index("return true;", self.dock.index("dock.dataset.renderSignature === nextSignature")), self.dock.index("dock.replaceChildren()"))

    def test_click_listener_registered_once_per_new_link(self):
        self.assertEqual(self.dock.count('link.addEventListener("click"'), 1)
        self.assertIn('event.preventDefault()', self.dock)

    def test_active_selection_is_resynchronized(self):
        self.assertIn('syncAppDockSelection();', self.dock)
        helper = self.source.split('function syncAppDockSelection(', 1)[1].split('function renderAppDock(', 1)[0]
        self.assertIn('link.setAttribute("aria-current", "location")', helper)
        self.assertIn('link.removeAttribute("aria-current")', helper)

if __name__ == "__main__":
    unittest.main()
