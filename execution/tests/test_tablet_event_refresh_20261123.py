"""Stored-event freshness markup and actual bounded collection UI regressions."""
from pathlib import Path
import base64
import hashlib
import re
import shutil
import subprocess
import unittest
from execution.tablet_event_filters_20261122 import render

ROOT = Path(__file__).resolve().parents[2]


class EventRefreshTests(unittest.TestCase):
    def document(self, **changes):
        events = dict(ok=True, rows=[{'name': '이전 행사', 'evidence_state': 'STALE_OFFICIAL'},
                                     {'name': '시각 미상', 'evidence_state': 'UNKNOWN_FRESHNESS'},
                                     {'name': '최근 확인', 'evidence_state': 'FRESH_OFFICIAL'}],
                      source_updated_at='2026-11-23T01:00:00+00:00')
        events.update(changes)
        return render(events, {}, lambda data: 'STORED_LIST_RETAINED')

    def test_actual_javascript_collection_boundaries(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required; do not silently skip refresh checks')
        result = subprocess.run([node, 'execution/tests/test_tablet_event_refresh_20261123.js'],
                                cwd=ROOT, text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Event refresh DOM: 21 tests passed', result.stdout)

    def test_top_controls_are_unique_without_unservable_script_route(self):
        page = self.document()
        self.assertEqual(page.count('id="tcg-event-refresh"'), 1)
        self.assertEqual(page.count('id="tcg-event-refresh-status"'), 1)
        self.assertIn('type="button" id="tcg-event-refresh"', page)
        self.assertNotIn('<script', page)
        self.assertLess(page.index('id="tcg-event-refresh"'), page.index('<form'))
        self.assertNotIn('onclick=', page)
        self.assertIn('STORED_LIST_RETAINED', page)
        self.assertIn('선택 적용', page)
        self.assertIn('필터 초기화', page)

    def test_actual_compose_includes_refresh_in_exact_csp_hashed_boot(self):
        from execution.tablet_menu_shell_v903 import compose
        source = ('<html><head><meta http-equiv="Content-Security-Policy" '
                  'content="default-src \'self\'; script-src \'self\';"></head>'
                  '<body><main class="app"></main></body></html>')
        page = compose(ROOT, document=source)
        scripts = re.findall(r'<script>(.*?)</script>', page, re.S)
        refresh = (ROOT / 'execution/tablet_event_refresh_20261123.js').read_text()
        shell = (ROOT / 'execution/tablet_menu_shell_v903.js').read_text()
        matching = [script for script in scripts if refresh in script]
        self.assertEqual(len(matching), 1)
        self.assertIn(shell, matching[0])
        digest = base64.b64encode(hashlib.sha256(matching[0].encode()).digest()).decode()
        policy = re.search(r'script-src([^;\"]+)', page).group(1)
        self.assertIn("'sha256-" + digest + "'", policy)
        self.assertNotIn("'unsafe-inline'", policy)
        self.assertNotIn('src="/execution/tablet_event_refresh_20261123.js"', page)

    def test_saved_time_does_not_claim_all_sources_are_fresh(self):
        page = self.document()
        self.assertIn('목록 저장 시각: 2026-11-23T01:00:00+00:00', page)
        self.assertIn('출처 재확인 필요 1건', page)
        self.assertIn('출처·확인 시각 미확인 1건', page)
        self.assertIn('모든 공식 소식의 최신성 확인을 뜻하지 않습니다', page)

    def test_unknown_and_unsafe_timestamps_are_never_injected(self):
        for timestamp in (None, '2026-11-23T01:00:00', '<script>alert(1)</script>', True):
            with self.subTest(timestamp=timestamp):
                page = self.document(source_updated_at=timestamp)
                self.assertIn('목록 저장 시각: 확인 시각 미상', page)
                self.assertNotIn('alert(1)', page)

    def test_truncation_is_visible_before_filter_and_stored_results(self):
        page = self.document(summary={'rows_truncated': True})
        self.assertIn('표시 상한으로 저장 자료 일부가 생략', page)
        self.assertIn('현재 필터는 표시 대상 안에서만 검색', page)
        self.assertLess(page.index('일부가 생략'), page.index('<form'))

    def test_unavailable_and_empty_lists_still_allow_explicit_refresh(self):
        for changes, expected in [({'ok': False}, '행사 자료 읽기 보류'),
                                  ({'rows': []}, '선택 조건에 맞는 저장 자료가 없습니다')]:
            page = self.document(**changes)
            self.assertIn('id="tcg-event-refresh"', page)
            self.assertIn(expected, page)
            self.assertNotIn('STORED_LIST_RETAINED', page)


if __name__ == '__main__':
    unittest.main()
