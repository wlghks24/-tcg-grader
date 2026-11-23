"""Actual composed status must not turn frozen claims into device evidence."""
from pathlib import Path
import unittest
from execution.tablet_workspace_truth_20261123 import replace_legacy_status, STATUS_BODY
from execution.tablet_menu_shell_v903 import compose

ROOT = Path(__file__).resolve().parents[2]


class WorkspaceTruthTests(unittest.TestCase):
    def test_current_source_claims_are_removed_from_composed_status_only(self):
        source = (ROOT / 'index.html').read_text()
        self.assertIn('검증 스크립트 기준 PASS', source)
        rendered = replace_legacy_status(source)
        panel = rendered.split('id="v31testdashboard"', 1)[1].split('>', 1)[1].split('</section>', 1)[0]
        for claim in ('PASS', 'HTTP 200', '69개 이상', '13개 이상', '1분마다', '30분 전'):
            self.assertNotIn(claim, panel)
        self.assertIn('현재 기기 결과 미확인', panel)
        self.assertIn('현재 기기 검사 열기', panel)
        self.assertEqual(source.split('<section class="card" id="v31testdashboard">')[0],
                         rendered.split('<section class="card" id="v31testdashboard">')[0])

    def test_compose_uses_truthful_panel_without_changing_source_file(self):
        source = (ROOT / 'index.html').read_bytes()
        rendered = compose(ROOT)
        panel = rendered.split('id="v31testdashboard"', 1)[1].split('>', 1)[1].split('</section>', 1)[0]
        self.assertIn(STATUS_BODY, panel)
        self.assertNotIn('HTTP 200', panel)
        self.assertIn('id="gradingEconomics"', rendered)
        self.assertEqual(source, (ROOT / 'index.html').read_bytes())

    def test_missing_panel_keeps_partial_documents_unchanged(self):
        source = '<html><body><section id="other">PASS</section></body></html>'
        self.assertEqual(source, replace_legacy_status(source))

    def test_nested_sections_do_not_replace_unrelated_content(self):
        source = '<section id="v31testdashboard"><section>old</section></section><p>after</p>'
        self.assertEqual('<section id="v31testdashboard">'+STATUS_BODY+'</section><p>after</p>',
                         replace_legacy_status(source))

    def test_markup_inside_scripts_is_not_treated_as_a_status_panel(self):
        source = '<script>let s=\'<section id="v31testdashboard">old</section>\';</script>'
        self.assertEqual(source, replace_legacy_status(source))

    def test_duplicate_and_unclosed_panels_hold(self):
        for source in ('<section id="v31testdashboard">',
                       '<section id="v31testdashboard"></section><section id="v31testdashboard"></section>'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                replace_legacy_status(source)

    def test_status_replacement_is_idempotent(self):
        source = '<section id="v31testdashboard">old</section>'
        rendered = replace_legacy_status(source)
        self.assertEqual(rendered, replace_legacy_status(rendered))

    def test_quotes_attributes_and_line_offsets_are_preserved(self):
        source = "<p>앞</p>\n<section data-role='status' id='v31testdashboard' class='card'>old</section>\n<p>뒤</p>"
        self.assertEqual(source.replace('>old</section>', '>'+STATUS_BODY+'</section>'),
                         replace_legacy_status(source))


if __name__ == '__main__':
    unittest.main()
