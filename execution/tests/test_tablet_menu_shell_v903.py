"""Offline composition/preservation checks. No browser, server or collection."""
import base64
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution import tablet_menu_shell_v903 as shell

ROOT = Path(__file__).resolve().parents[2]


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.nodes, self.controls, self.scripts = {}, [], []
        self.ids, self.current, self.csp = [], None, ''
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
            self.nodes[attrs['id']] = attrs
        if tag in ('button','input','select','textarea'):
            self.controls.append((tag,tuple(sorted(attrs.items()))))
        if tag == 'script':
            self.current = [attrs,'']
        if tag == 'meta' and attrs.get('http-equiv','').lower() == 'content-security-policy':
            self.csp = attrs.get('content','')

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.scripts.append(self.current)
            self.current = None


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = (ROOT/'index.html').read_text(encoding='utf-8')
        (self.root/'index.html').write_text(self.source,encoding='utf-8')
        self.data = {'state':'COMPLETE','cards':'<article data-region="JP" data-game="pokemon" data-kind="CARD"><h2>Fixture card</h2></article>','options':'<option>pokemon</option>','count':1,'events':''}
        self.addCleanup(patch.stopall)
        self.gallery = patch.object(shell,'gallery',return_value=self.data).start()
        patch.object(shell,'event_fragment',return_value='<h1>행사 수집 현황</h1>').start()

    def test_original_ids_172_controls_and_scripts_remain_in_original_order(self):
        old, new = Document(self.source), Document(shell.compose(self.root))
        self.assertFalse(Counter(old.ids)-Counter(new.ids))
        self.assertFalse(Counter(old.controls)-Counter(new.controls))
        self.assertEqual(172,len(old.controls))
        self.assertEqual(len(new.ids),len(set(new.ids)))
        self.assertEqual(old.scripts,[s for s in new.scripts if s[0].get('id')!='tcg903-config'][:-1])

    def test_home_contains_search_country_filters_and_card_grid_without_secondary_library_panel(self):
        page = shell.compose(self.root)
        self.assertIn('id="tcg903-home"',page)
        self.assertNotIn('id="tcg903-library"',page)
        self.assertIn('id="tcg903-grid"',page)
        self.assertIn('Fixture card',page)
        for country in ('KR','JP','US','CN'):
            self.assertIn('data-tcg903-country="'+country+'"',page)
        self.assertIn('id="tcg903-query"',page)
        script = (ROOT/'execution/tablet_menu_shell_v903.js').read_text()
        self.assertIn('filter(); menu(false);',script)

    def test_18_shortcuts_and_40_advanced_targets_are_in_single_menu(self):
        menu, config = shell.navigation(self.source)
        self.assertEqual(18,len(config['features']))
        self.assertEqual(40,len(config['targets']))
        for key in config['features']:
            self.assertIn('feature='+key,menu)
        for target in config['targets']:
            self.assertIn('target='+target,menu)
        self.assertNotIn('target="_blank"',menu)
        self.assertNotIn('<iframe',shell.compose(self.root))

    def test_existing_csp_gains_only_exact_boot_hash_and_keeps_other_directives(self):
        old, new = Document(self.source), Document(shell.compose(self.root))
        digest = base64.b64encode(hashlib.sha256(new.scripts[-1][1].encode()).digest()).decode()
        policy = next(d for d in new.csp.split(';') if d.strip().startswith('script-src'))
        self.assertIn("'sha256-"+digest+"'",policy)
        self.assertNotIn("'unsafe-inline'",policy)
        for directive in old.csp.split(';'):
            if not directive.strip().startswith('script-src'):
                self.assertIn(directive,new.csp)

    def test_readback_markers_are_early_even_with_large_gallery(self):
        self.data['cards'] *= 6000
        page = shell.compose(self.root)
        for marker in ('TCG 카드·BOX 라이브러리','전체 TCG · 행사·콜라보·영화·프로모','data-tcg-view-state="COMPLETE"','/index.html?target='):
            self.assertIn(marker,page[:262144])

    def test_gated_results_keep_original_attributes_and_not_forced_visible(self):
        old, new = Document(self.source), Document(shell.compose(self.root))
        for target in ('out','simpleGradeResult'):
            for key,value in old.nodes[target].items():
                self.assertEqual(value,new.nodes[target][key])
        self.assertNotIn('parent.hidden = false',(ROOT/'execution/tablet_menu_shell_v903.js').read_text())

    def test_tag_strings_in_legacy_script_do_not_capture_html_boundary(self):
        source = '<html><head></head><body><script>const fake="</body>";</script><main>keep</main></body></html>'
        (self.root/'index.html').write_text(source)
        page = shell.compose(self.root)
        self.assertIn('<script>const fake="</body>";</script><main>keep</main>',page)
        self.assertGreater(page.index('id="tcg903-config"'),page.index('<main>keep'))

    def test_read_only_menu_does_not_change_repository_files(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        shell.compose(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_partial_and_unavailable_gallery_do_not_hide_legacy_functions(self):
        for state in ('PARTIAL_READ_ONLY','UNAVAILABLE'):
            self.data['state']=state
            page = shell.compose(self.root)
            self.assertIn('id="gradeStart"',page)
            self.assertIn('행사 수집 현황',page)
            self.assertIn('data-tcg-view-state="'+state+'"',page)
            self.assertIn('보류' if state=='UNAVAILABLE' else '일부 자료',page)

    def test_no_existing_unsafe_inline_policy_is_accidentally_disabled_by_one_hash(self):
        source = '''<html><head><meta http-equiv="Content-Security-Policy" content="script-src 'self' 'unsafe-inline'; object-src 'none'"></head><body><script>const legacy=1</script></body></html>'''
        new = Document(shell.compose(self.root,document=source,compatibility=True))
        self.assertNotIn('sha256-',new.csp)
        self.assertIn("object-src 'none'",new.csp)
        config = json.loads(next(s[1] for s in new.scripts if s[0].get('id')=='tcg903-config'))
        self.assertTrue(config['compatibility'])


if __name__ == '__main__':
    unittest.main()
