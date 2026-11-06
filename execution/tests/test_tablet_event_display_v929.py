"""V929 offline visible-output regressions, with no collection or file mutation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution import tablet_event_display_v929 as ui
from execution import tablet_menu_shell_v903 as shell

ROOT = Path(__file__).resolve().parents[2]


class EventDisplayV929Tests(unittest.TestCase):
    def test_status_table_uses_korean_labels_and_preserves_machine_state(self):
        raw = (
            ui.OLD_LEGEND + '<table>' +
            ''.join('<tr><td>' + registry + '</td><td>' + state + '</td></tr>'
                    for registry, state in zip(
                        ('core', 'promoted', 'watch', 'core', 'promoted'),
                        ui.SEARCH_LABELS
                    )) + '</table>'
        )
        rendered = ui.localize_event_fragment(raw)
        self.assertIn('검색 상태는 행사 존재 여부나 공식 확인을 뜻하지 않습니다', rendered)
        for code, label in ui.SEARCH_LABELS.items():
            self.assertIn('data-tcg929-search-state="' + code + '"', rendered)
            self.assertIn('>' + label + '</td>', rendered)
            self.assertNotIn('<td>' + code + '</td>', rendered)
        for code, label in ui.REGISTRY_LABELS.items():
            self.assertIn('data-tcg929-registry-state="' + code + '"', rendered)
            self.assertIn('>' + label + '</td>', rendered)
            self.assertNotIn('<td>' + code + '</td>', rendered)
        self.assertNotIn(ui.OLD_LEGEND, rendered)

    def test_unknown_states_remain_explicitly_unknown_and_no_fact_promotion(self):
        fragment = (
            '<table><tr><td>NEW_UNREVIEWED_STATE</td><td>watch</td></tr></table>'
            '<article><h2>&lt;script&gt;untrusted&lt;/script&gt;</h2>'
            '<a href="https://example.org/reference">출처 확인</a></article>'
        )
        actual = ui.localize_event_fragment(fragment)
        self.assertIn('>NEW_UNREVIEWED_STATE</td>', actual)
        self.assertIn('data-tcg929-registry-state="watch"', actual)
        self.assertNotIn('<script>untrusted</script>', actual)
        self.assertIn('&lt;script&gt;untrusted&lt;/script&gt;', actual)
        self.assertIn('https://example.org/reference', actual)
        self.assertNotIn('공식 인증 완료', actual)
        self.assertEqual(actual, ui.localize_event_fragment(actual))

    def test_only_two_known_visible_legacy_separator_shapes_are_removed(self):
        test_page = (
            '<main>card</main>\n\\n<script id="grade">const s="\\\\n";</script>'
            '\\n<script id="next">const t="\\\\n";</script>'
        )
        original = test_page[:]
        cleaned = ui.clean_legacy_script_separators(test_page)
        self.assertNotIn('</main>\n\\n<script', cleaned)
        self.assertNotIn('</script>\\n<script', cleaned)
        self.assertIn('</main>\n<script', cleaned)
        self.assertIn('</script>\n<script', cleaned)
        self.assertIn('const s="\\\\n";', cleaned)
        self.assertIn('const t="\\\\n";', cleaned)
        self.assertEqual(test_page, original)
        self.assertEqual(cleaned, ui.clean_legacy_script_separators(cleaned))

    def test_actual_legacy_index_stays_bytewise_unchanged(self):
        page = ROOT.joinpath('index.html').read_text(encoding='utf-8')
        self.assertIn('</main>\n\\n<script', page)
        self.assertIn('</script>\\n<script', page)
        clean = ui.clean_legacy_script_separators(page)
        self.assertEqual(len(page) - 2, len(clean))
        self.assertNotIn('</main>\n\\n<script', clean)
        self.assertNotIn('</script>\\n<script', clean)
        self.assertIn('</main>\n\\n<script', ROOT.joinpath('index.html').read_text(encoding='utf-8'))

    def test_event_fragment_integration_retains_filters_and_link_source(self):
        rendered = (
            '<!doctype html><html><style>body{color:navy}</style>'
            '<p>기존 행사 목록은 기존 홈에서 계속 볼 수 있습니다.</p>'
            + ui.OLD_LEGEND +
            '<table><tr><td>promoted</td><td>SEARCHED_UNCONFIRMED</td></tr></table>'
            '<article><a href="https://example.org/film">출처 확인</a></article></html>'
        )
        with patch('execution.tablet_event_coverage_v896.render', return_value=rendered) as read:
            fragment = shell.event_fragment(Path('.'), {'game': ['onepiece'], 'region': ['KR']})
        read.assert_called_once_with(Path('.'), game_id='onepiece', region='KR')
        self.assertIn('확인합니다', fragment)
        self.assertIn('data-tcg929-search-state="SEARCHED_UNCONFIRMED"', fragment)
        self.assertNotIn('<td>SEARCHED_UNCONFIRMED</td>', fragment)
        self.assertIn('https://example.org/film', fragment)

    def test_current_shell_output_has_no_two_visible_separator_literals(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            (root / 'index.html').write_bytes((ROOT / 'index.html').read_bytes())
            fake = {
                'state': 'COMPLETE',
                'cards': '<article data-game="pokemon" data-region="KR" data-kind="CARD">fixture</article>',
                'options': '<option value="pokemon">포켓몬</option>',
                'count': 1,
                'events': '',
            }
            with patch.object(shell, 'gallery', return_value=fake):
                with patch.object(shell, 'event_fragment', return_value='<p>fixture event</p>'):
                    page = shell.compose(root)
            self.assertNotIn('</main>\n\\n<script', page)
            self.assertNotIn('</script>\\n<script', page)
            self.assertIn('<script id="simple-grade-v32-script">', page)
            self.assertIn('TCG 카드·BOX 라이브러리', page)
            self.assertIn('</main>\n\\n<script', (root / 'index.html').read_text(encoding='utf-8'))

    def test_type_and_size_guards(self):
        with self.assertRaises(TypeError):
            ui.localize_event_fragment(None)
        with self.assertRaises(TypeError):
            ui.clean_legacy_script_separators(b'html')
        with self.assertRaises(ValueError):
            ui.localize_event_fragment('x' * 1_000_001)


if __name__ == '__main__':
    unittest.main()
