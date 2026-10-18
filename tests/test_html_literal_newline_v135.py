"""Regression: naked backslash-n at HTML level displayed literally in tablet recording."""
from pathlib import Path
import unittest

INDEX = Path(__file__).resolve().parents[1] / "index.html"


class HtmlLiteralNewlineV135(unittest.TestCase):
    def setUp(self):
        self.html = INDEX.read_text(encoding="utf-8")

    def test_no_visible_backslash_n_in_html(self):
        self.assertNotIn(r"\n", self.html)

    def test_stylesheet_newline(self):
        self.assertIn(
            'href="ui_app_shell_v272.css?v=272">\n<link rel="stylesheet" '
            'href="tablet_autonomy_dashboard_v400.css?v=400">',
            self.html,
        )

    def test_main_and_grading_script_newline(self):
        self.assertIn('</main>\n\n<script id="simple-grade-v32-script">', self.html)

    def test_widget_script_newline(self):
        self.assertIn(
            '<script src="ui_app_shell_v272.js?v=272"></script>\n'
            '<script src="tablet_autonomy_dashboard_v400.js?v=400"></script>',
            self.html,
        )


if __name__ == "__main__":
    unittest.main()
