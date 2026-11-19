"""Regression coverage for the tablet unified event-country selector."""
from html.parser import HTMLParser
import shutil
import subprocess
import unittest

from execution.tablet_unified_ui_v890 import render_document


class ScriptCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.in_script = True
            self.scripts.append('')

    def handle_data(self, data):
        if self.in_script:
            self.scripts[-1] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False


def event_fixture(region):
    return {
        'region': region, 'game': 'Pokemon', 'category': 'collaboration',
        'name': 'Event ' + region, 'lifecycle': 'UPCOMING',
        'evidence_state': 'UNVERIFIED', 'archived': False,
        'date_label': '일정 확인 필요', 'source_checked_at': '',
    }


class TabletUnifiedEventRegionTests(unittest.TestCase):
    def page(self):
        return render_document([], [], events={
            'ok': True,
            'rows': [event_fixture(r) for r in ('KR', 'JP', 'US', 'CN', 'GLOBAL', 'ASIA')],
            'summary': {'loaded_rows': 6, 'lifecycle_counts': {}},
        })

    def test_country_options_and_safe_event_attributes(self):
        page = self.page()
        self.assertIn('id="eventRegion"', page)
        self.assertIn('value="CN">중국', page)
        self.assertIn('value="ASIA">아시아', page)
        for region in ('KR', 'JP', 'US', 'CN', 'GLOBAL', 'ASIA'):
            self.assertIn('data-event-region="' + region + '"', page)

    def test_missing_event_data_does_not_claim_zero_or_show_filter(self):
        page = render_document([], [], events={'ok': False})
        self.assertIn('자료를 읽지 못했습니다', page)
        self.assertNotIn('id="eventRegion"', page)

    @unittest.skipUnless(shutil.which('node'), 'Node is unavailable')
    def test_country_selection_and_reset_hide_only_event_tiles(self):
        scripts = ScriptCollector()
        scripts.feed(self.page())
        script = next(x for x in scripts.scripts if 'eventRegionCount' in x)
        setup = """const assert=require('node:assert/strict');const rows=['KR','JP','US','CN','GLOBAL','ASIA'].map(r=>({dataset:{eventRegion:r},hidden:false}));const count={textContent:''};const control={value:'',addEventListener(type,cb){this.change=cb;}};const document={getElementById:id=>id==='eventRegion'?control:id==='eventRegionCount'?count:null,querySelectorAll:()=>rows};"""
        checks = """assert.equal(count.textContent,'6개 행사 표시');control.value='CN';control.change();assert.deepEqual(rows.map(r=>r.hidden),[true,true,true,false,true,true]);assert.equal(count.textContent,'1개 행사 표시');control.value='';control.change();assert(rows.every(r=>!r.hidden));"""
        result = subprocess.run(['node', '-e', setup + script + checks], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
