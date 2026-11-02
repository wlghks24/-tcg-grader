"""Explicit local startup adapter: one existing scheduler, real repair, unified UI.

Run with python -m execution.tablet_unified_runtime_v889 after reviewed delivery.
No source rewriting, second scheduler, automatic installation or model training.
"""
from pathlib import Path
import time
import threading
from urllib.parse import urlsplit

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


def make_handler(base):
    class UnifiedHandler(base):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path not in ('/tablet-unified', '/api/local-card-images/catalog-links', '/', '/index.html'):
                return super().do_GET()
            if not library._local_request(self):
                return self.json({'ok': False, 'error': '기기 내부 접속 전용'}, 403)
            try:
                if path == '/api/local-card-images/catalog-links':
                    return self.json(read_live(Path(self.directory)))
                if path == '/tablet-unified':
                    page = export_html(read_live(Path(self.directory)))
                    controls = '''<nav><a href="/index.html">기존 홈·이벤트</a> <button id="collect">사진·카드정보 보완 수집</button><span id="job" role="status"></span></nav><script>document.getElementById('collect').onclick=async()=>{const b=document.getElementById('collect'),s=document.getElementById('job');b.disabled=true;try{const r=await fetch('/api/local-card-images/auto-start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();if(!r.ok||!d.ok)throw Error('수집 요청 실패');s.textContent='수집 중 · 완료 후 새로고침하여 확인';}catch(e){s.textContent=e.message;}finally{b.disabled=false;}};</script>'''
                    page = page.replace('<header>', '<header>' + controls, 1)
                else:
                    import tcg_updater as core
                    with core.open_safe_binary(Path(self.directory) / 'index.html', max_bytes=core.MAX_SAFE_FILE_BYTES) as source:
                        page = source.read().decode('utf-8')
                    link = '<a href="/tablet-unified" style="display:block;padding:16px;background:#1749c9;color:white;font-weight:bold">통합 카드·사진 보관함 열기</a>'
                    import re
                    page = re.sub(r'(<body\b[^>]*>)', lambda m: m.group(1) + link, page, count=1, flags=re.I)
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
    install(runtime)
    return runtime.main()


if __name__ == '__main__':
    raise SystemExit(main())
