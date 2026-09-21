from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class TabletModernUIV274Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.css = (ROOT / "feature_category_nav.css").read_text(encoding="utf-8")
        self.index = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_existing_tablet_management_contract_is_preserved(self) -> None:
        self.assertEqual(self.index.count('class="tablet-manager-action"'), 6)
        for label in ("태블릿 상태", "서버 상태", "업데이트", "자동시작", "네트워크", "오류검사"):
            self.assertIn(label, self.index)
        for selector in (
            ".tablet-manager-hub",
            ".tablet-manager-grid",
            ".tablet-manager-action",
            ".tablet-manager-status",
        ):
            self.assertIn(selector, self.css)

    def test_tablet_first_visual_hierarchy_and_touch_layout(self) -> None:
        for token in (
            "--ui-surface:#ffffff",
            "--ui-shadow:0 14px 36px",
            "grid-template-columns:repeat(6,minmax(0,1fr))",
            "min-height:116px",
            ".tablet-manager-icon",
            ".feature-category-icon",
            "backdrop-filter:blur(12px)",
            "env(safe-area-inset-bottom",
        ):
            self.assertIn(token, self.css)

    def test_small_screen_and_accessibility_guards_remain(self) -> None:
        for token in (
            "@media(max-width:620px)",
            "@media(max-width:430px)",
            "@media(max-width:350px)",
            "@media(prefers-reduced-motion:reduce)",
            "@media(prefers-contrast:more)",
            "@media(prefers-color-scheme:dark)",
            ":focus-visible",
        ):
            self.assertIn(token, self.css)

    def test_navigation_information_is_not_hidden_by_default(self) -> None:
        self.assertIn(".feature-category-grid", self.css)
        self.assertIn(".feature-shortcut-grid", self.css)
        self.assertIn("아래 기능 중 하나를 선택하세요", self.css)
        # Only information-bearing containers must remain visible. Browser-native
        # decoration such as ::-webkit-details-marker may legitimately be hidden.
        for selector in (
            r"\.feature-category-grid",
            r"\.feature-shortcut-grid",
            r"\.tablet-manager-hub",
            r"\.tablet-manager-grid",
        ):
            self.assertNotRegex(
                self.css,
                selector + r"\s*\{[^}]*display\s*:\s*none",
                msg=f"navigation container is hidden by default: {selector}",
            )


if __name__ == "__main__":
    unittest.main()
