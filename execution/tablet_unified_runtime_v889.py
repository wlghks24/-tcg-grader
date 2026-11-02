"""Explicit local startup adapter: one existing scheduler, real repair, unified UI.

Run with python -m execution.tablet_unified_runtime_v889 after reviewed delivery.
No source rewriting, second scheduler, automatic installation or model training.
"""
from pathlib import Path
import time
import threading
from urllib.parse import urlsplit, parse_qs

import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library
from execution.tablet_image_unified_v888 import repair_existing, export_html
from execution.tablet_image_recheck_review_v887 import read_live

_ORIGINAL_COLLECT = auto.collect_once
_INSTALLED = False


def collect_once(repo, stop=None, sleeper=time.sleep):
    """Shared persisted quota/time window for metadata repair AND photo collection."""
    if getattr(auto._BUDGET_CONTEXT, 'current', None) is not None:
        raise ValueError('중첩 수집 실행 차단')
    stop = stop or threading.Event()
    root = library.storage_root()
    with auto._LOCK:
        state = auto._state(root)
    def save_budget():
        with auto._LOCK:
            state['enabled'] = auto._state(root)['enabled']
            auto._save(root, state)
    budget = auto.policy.Budget(state, save_budget)
    auto._BUDGET_CONTEXT.current = budget
    try:
        with library.LOCK:
            records = library._load(root)['items']
        repaired = repair_existing(auto, root, state, records, budget, stop)
        result = auto._collect_once(repo, stop=stop, sleeper=sleeper)
        result['metadata_enriched'] += repaired['enriched']
        result['metadata_repair_attempted'] += repaired['attempted']
        result['issues'].extend(repaired['issues'])
        result['errors'] += len(repaired['issues'])
        result['deferred'] = result['deferred'] or repaired['deferred']
        result['unified_metadata_repair'] = repaired
        with auto._LOCK:
            state['last_result'] = result
            save_budget()
        return result
    finally:
        del auto._BUDGET_CONTEXT.current


def feature_navigation(repo):
    """Derive links from existing feature shortcuts so new UI cannot drop a menu."""
    import html
    from html.parser import HTMLParser
    from urllib.parse import quote
    import tcg_updater as core
    class Features(HTMLParser):
        def __init__(self):
            super().__init__(); self.rows = []; self.current = None; self.small = 0
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'a' and 'feature-shortcut' in attrs.get('class', '').split():
                key = attrs.get('data-feature-key', '')
                if key and attrs.get('href', '').startswith('#'):
                    self.current = [key, []]
            if tag == 'small': self.small += 1
        def handle_data(self, data):
            if self.current is not None and not self.small: self.current[1].append(data)
        def handle_endtag(self, tag):
            if tag == 'small': self.small = max(0, self.small - 1)
            if tag == 'a' and self.current is not None:
                self.rows.append((self.current[0], ''.join(self.current[1]).strip()))
                self.current = None
    with core.open_safe_binary(Path(repo) / 'index.html', max_bytes=core.MAX_SAFE_FILE_BYTES) as source:
        parser = Features(); parser.feed(source.read().decode('utf-8'))
    links = ''.join('<a style="padding:10px;display:inline-block" href="/index.html?feature=' + quote(key, safe='') + '">' + html.escape(label) + '</a>' for key, label in parser.rows)
    return '<details><summary>기존 전체 기능 · 시세·행사·구매처·촬영·학습·관리</summary><nav aria-label="기존 전체 기능">' + links + '</nav></details>'


FEATURE_BOOT = """<script>window.addEventListener('load',()=>{const key=new URLSearchParams(location.search).get('feature');if(!key)return;const link=Array.from(document.querySelectorAll('.feature-shortcut[data-feature-key]')).find(x=>x.dataset.featureKey===key);if(link)link.click();});</script>"""


def make_handler(base):
    class UnifiedHandler(base):
        def do_GET(self):
            if not self._require_request_host():
                return
            path = urlsplit(self.path).path
            if path not in ('/tablet-unified', '/api/local-card-images/catalog-links', '/', '/index.html', '/tablet_market_hub_v881.html'):
                return super().do_GET()
            if not library._local_request(self):
                return self.json({'ok': False, 'error': '기기 내부 접속 전용'}, 403)
            try:
                if path == '/api/local-card-images/catalog-links':
                    return self.json(read_live(Path(self.directory)))
                options = parse_qs(urlsplit(self.path).query)
                unified_home = path in ('/', '/index.html') and not options.get('feature') and options.get('view') != ['classic']
                if path == '/tablet-unified' or unified_home:
                    page = export_html(read_live(Path(self.directory)), live=True)
                    controls = '''<nav><a href="/index.html?view=classic">기존 홈·이벤트</a> <button id="collect">사진·카드정보 보완 수집</button><button id="refresh-events">출시·행사·시세 자료 갱신</button><span id="job" role="status"></span></nav><script>document.getElementById('collect').onclick=async()=>{const b=document.getElementById('collect'),s=document.getElementById('job');b.disabled=true;try{const r=await fetch('/api/local-card-images/auto-start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();if(!r.ok||!d.ok)throw Error('수집 요청 실패');s.textContent='수집 중 · 완료 후 새로고침하여 확인';}catch(e){s.textContent=e.message;}finally{b.disabled=false;}};document.getElementById('refresh-events').onclick=async()=>{const b=document.getElementById('refresh-events'),s=document.getElementById('job');b.disabled=true;try{const r=await fetch('/api/run-auto-update',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();if(!r.ok||d.ok===false)throw Error('갱신 요청 실패');s.textContent='자료 갱신 요청 접수 · 완료 후 새로고침하여 확인';}catch(e){s.textContent=e.message;}finally{b.disabled=false;}};</script>'''
                    page = page.replace('<header>', '<header>' + feature_navigation(self.directory) + controls, 1)
                else:
                    import tcg_updater as core
                    target = Path(self.directory) / ('execution/tablet_market_hub_v881.html' if path == '/tablet_market_hub_v881.html' else 'index.html')
                    with core.open_safe_binary(target, max_bytes=core.MAX_SAFE_FILE_BYTES) as source:
                        page = source.read().decode('utf-8')
                    link = '<a href="/tablet-unified" style="display:block;padding:16px;background:#1749c9;color:white;font-weight:bold">통합 카드·사진 보관함 열기</a>'
                    import re
                    navigation = feature_navigation(self.directory)
                    page = re.sub(r'(<body\b[^>]*>)', lambda m: m.group(1) + link + navigation, page, count=1, flags=re.I)
                    if path != '/tablet_market_hub_v881.html':
                        page += FEATURE_BOOT
                content = page.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'private, no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(content)
            except (OSError, ValueError, TypeError, UnicodeError):
                return self.json({'ok': False, 'error': '통합 자료 확인 보류 · 원본 보존'}, 503)
    return UnifiedHandler


def install(runtime):
    """Install before main starts its existing scheduler; fail on active workers."""
    global _INSTALLED
    with auto._LOCK:
        if _INSTALLED:
            return
        if auto._THREAD is not None or auto._SCHEDULER is not None or auto.collect_once is not _ORIGINAL_COLLECT:
            raise RuntimeError('기존 서버/수집기 종료 후 시작해야 합니다')
        runtime.Handler = make_handler(runtime.Handler)
        auto.collect_once = collect_once
        _INSTALLED = True


def main():
    import tcg_updater_v135 as runtime
    import event_priority_watch
    from execution.tablet_event_freshness_v891 import install as install_event_freshness
    install_event_freshness(event_priority_watch)
    install(runtime)
    return runtime.main()


if __name__ == '__main__':
    raise SystemExit(main())

