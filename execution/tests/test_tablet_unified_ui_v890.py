"""Source preservation, live CSP and actual offline filter behavior."""
import json
import re
import shutil
import subprocess
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from execution.tablet_image_unified_v888 import export_html, unified_feed
from execution.tablet_unified_ui_v890 import render_document
from execution.tests.test_tablet_image_unified_v888 import paired_report


class UnifiedPresentationTests(unittest.TestCase):
    def test_live_only_permits_same_origin_collection(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('tablet_image_library_v1.storage_root', return_value=Path(directory)), \
             patch('tablet_image_library_v1.get_image', side_effect=ValueError('fixture')):
            standalone = export_html(paired_report())
            live = export_html(paired_report(), live=True)
            self.assertEqual([], list(Path(directory).iterdir()))
        self.assertIn("connect-src 'none'", standalone)
        self.assertIn("connect-src 'self'", live)
        self.assertNotIn("connect-src *", live)

    def test_unmatched_source_keeps_printing_source_and_observation_dates(self):
        report = paired_report()
        report['catalog_matches'] = []
        source = report['source_catalog'][0]
        source.update(source_url='https://official.example/card', source_checked_at='2026-11-02T00:00:00Z', observed_release_date='2026-11-01')
        row = next(r for r in unified_feed(report) if not r['image_id'])
        self.assertEqual('Normal', row['card_metadata']['printing'])
        self.assertEqual('ja', row['card_metadata']['language'])
        self.assertEqual(source['source_url'], row['source_url'])
        self.assertEqual('2026-11-01', row['observed_release_date'])
        self.assertEqual('NEEDS_IMAGE', row['link_status'])

    def test_malformed_source_is_never_an_active_link_or_inferred_sale(self):
        report = paired_report()
        report['source_catalog'][0]['source_url'] = 'javascript:alert(1)'
        with patch('tablet_image_library_v1.get_image', side_effect=ValueError('fixture')):
            page = export_html(report)
        self.assertNotIn('javascript:', page)
        self.assertIn('등급 측정 전', page)
        self.assertIn('정확한 판본의 거래자료 확인 필요', page)
        self.assertNotIn('₩', page)

    def test_missing_events_is_error_not_zero_and_archive_count_remains(self):
        page = render_document([], [], events={'ok': False})
        self.assertIn('자료를 읽지 못했습니다', page)
        page = render_document([], [], events={'ok': True, 'rows': [], 'summary': {'loaded_rows': 70, 'lifecycle_counts': {'ARCHIVED': 69}}})
        self.assertIn('지난 행사 69건 보존', page)
        self.assertIn('promo-event-info', page)

    @unittest.skipUnless(shutil.which('node'), 'Node is unavailable')
    def test_real_filter_script_country_game_search_and_kind(self):
        page = render_document([], [])
        script = re.findall(r'<script>(.*?)</script>', page, re.S)[-1]
        setup = """const assert=require('node:assert/strict');const inputs=Object.fromEntries(['region','game','kind','query','count'].map(k=>[k,{value:'',addEventListener(){}}]));const rows=[{dataset:{region:'CN-S',game:'pokemon',kind:'CARD'},textContent:'SV1S-001 Pokemon'},{dataset:{region:'CN-T',game:'pokemon',kind:'BOX'},textContent:'BOX'},{dataset:{region:'JP',game:'onepiece',kind:'CARD'},textContent:'OP01'}];const document={getElementById:k=>inputs[k],querySelectorAll:()=>rows};"""
        assertions = """inputs.region.value='CN';filter();assert.deepEqual(rows.map(x=>x.hidden),[false,false,true]);inputs.kind.value='CARD';filter();assert.deepEqual(rows.map(x=>x.hidden),[false,true,true]);inputs.query.value='not found';filter();assert(rows.every(x=>x.hidden));inputs.region.value='';inputs.kind.value='';inputs.query.value='op01';filter();assert.deepEqual(rows.map(x=>x.hidden),[true,true,false]);"""
        result = subprocess.run(['node', '-e', setup + script + assertions], capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_export_stops_work_after_view_byte_limit(self):
        import io
        from PIL import Image
        report = paired_report()
        image = report['local_catalog'][0]
        report['catalog_matches'] = []
        report['source_catalog'] = []
        report['local_catalog'] = [dict(image, id=f'{i:032x}') for i in range(100)]
        buf = io.BytesIO(); Image.new('RGB', (20, 30), 'white').save(buf, format='PNG')
        data = buf.getvalue() + b'0' * (4_000_000 - len(buf.getvalue()))
        with patch('execution.tablet_image_unified_v888.cached_display', return_value=(data, {'source_bytes': len(data), 'stored_bytes': len(data)})) as compress:
            page = export_html(report)
        self.assertEqual(4, compress.call_count)
        self.assertEqual(3, page.count('data:image/png;base64,'))
        self.assertIn('화면 용량 한도', page)
