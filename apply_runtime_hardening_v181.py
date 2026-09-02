#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def patch_index() -> None:
    text = read("index.html")
    text = re.sub(
        r'<script src="multi_market_prices\.js(?:\?v=\d+)?"></script>\s*'
        r'<script src="multi_market_prices\.js(?:\?v=\d+)?"></script>',
        '<script src="multi_market_prices.js?v=181"></script>',
        text,
        count=1,
    )
    text = re.sub(
        r'<script src="multi_market_prices\.js(?:\?v=\d+)?"></script>',
        '<script src="multi_market_prices.js?v=181"></script>',
        text,
        count=1,
    )
    text = re.sub(
        r'<script src="auto_validation_flow\.js(?:\?v=\d+)?"></script>',
        '<script src="auto_validation_flow.js?v=181"></script>',
        text,
        count=1,
    )
    text = re.sub(
        r'<script src="graded_photo_dashboard\.js(?:\?v=\d+)?"></script>',
        '<script src="graded_photo_dashboard.js?v=181"></script>',
        text,
        count=1,
    )
    text = re.sub(
        r'<script src="\./manual_dual_photo_bridge\.js(?:\?v=\d+)?"></script>',
        '<script src="./manual_dual_photo_bridge.js?v=181"></script>',
        text,
        count=1,
    )
    literal = '<script src="card_identity_recognition.js"></script>\\n<script src="inventory_lookup.js"></script>'
    if literal in text:
        text = text.replace(
            literal,
            '<script src="card_identity_recognition.js?v=181"></script>\n<script src="inventory_lookup.js"></script>',
            1,
        )
    else:
        text = re.sub(
            r'<script src="card_identity_recognition\.js(?:\?v=\d+)?"></script>',
            '<script src="card_identity_recognition.js?v=181"></script>',
            text,
            count=1,
        )
    if text.count("multi_market_prices.js") != 1:
        raise SystemExit("multi_market_prices.js duplicate loader remains")
    write("index.html", text)


def patch_multi_market() -> None:
    text = read("multi_market_prices.js")
    if "__TCG_MULTI_MARKET_PRICES__" not in text:
        needle = "'use strict';\n"
        if needle not in text:
            raise SystemExit("multi_market strict-mode anchor missing")
        text = text.replace(
            needle,
            "'use strict';\n"
            "const GLOBAL_KEY='__TCG_MULTI_MARKET_PRICES__';\n"
            "if(globalThis[GLOBAL_KEY]?.loaded)return;\n"
            "globalThis[GLOBAL_KEY]={loaded:true,version:181};\n",
            1,
        )
    write("multi_market_prices.js", text)


def patch_service_worker() -> None:
    text = read("sw.js")
    text = re.sub(
        r"const CACHE='[^']+';",
        "const CACHE='tcg-v181-network-first-runtime';",
        text,
        count=1,
    )
    old_install = """self.addEventListener('install',event=>event.waitUntil(\n  caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())\n));"""
    new_install = """self.addEventListener('install',event=>event.waitUntil((async()=>{\n  const cache=await caches.open(CACHE);\n  await Promise.allSettled(CORE.map(async asset=>{\n    try{\n      const response=await fetch(asset,{cache:'no-store'});\n      if(response&&response.ok)await cache.put(asset,response.clone());\n    }catch(_){/* one optional asset must never block a service-worker upgrade */}\n  }));\n  await self.skipWaiting();\n})()));"""
    if old_install in text:
        text = text.replace(old_install, new_install, 1)
    elif "Promise.allSettled(CORE.map" not in text:
        raise SystemExit("service-worker install anchor missing")

    text = text.replace(
        "const cached=await caches.match(request);",
        "const cached=await caches.match(request,{ignoreSearch:true});",
        1,
    )
    start = text.find("self.addEventListener('fetch',event=>{")
    if start < 0:
        raise SystemExit("service-worker fetch handler missing")
    text = text[:start] + """self.addEventListener('fetch',event=>{\n  if(event.request.method!=='GET')return;\n  const url=new URL(event.request.url);\n  if(url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;\n  const mutable=event.request.mode==='navigate'||/\\.(?:html|js|css|json|webmanifest)$/i.test(url.pathname);\n  if(mutable){\n    event.respondWith(fetch(event.request,{cache:'no-store'})\n      .then(response=>event.request.mode==='navigate'?enhanceNavigationResponse(response):response)\n      .then(response=>rememberSuccessfulResponse(event.request,response))\n      .catch(()=>unavailableResponse(event.request)));\n    return;\n  }\n  event.respondWith(caches.match(event.request,{ignoreSearch:true}).then(cached=>cached||fetch(event.request,{cache:'no-store'})\n    .then(response=>rememberSuccessfulResponse(event.request,response))\n    .catch(()=>unavailableResponse(event.request))));\n});\n"""
    write("sw.js", text)


def patch_server_cache_headers() -> None:
    text = read("tcg_updater.py")
    old = """            self.send_header('Last-Modified',self.date_time_string(metadata.st_mtime))\n            self.end_headers()"""
    new = """            self.send_header('Last-Modified',self.date_time_string(metadata.st_mtime))\n            if target.suffix.lower() in {'.html','.js','.css','.json','.webmanifest'}:\n                self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')\n                self.send_header('Pragma','no-cache')\n                self.send_header('Expires','0')\n            else:\n                self.send_header('Cache-Control','public, max-age=3600')\n            self.end_headers()"""
    if old in text:
        text = text.replace(old, new, 1)
    elif "target.suffix.lower() in {'.html','.js','.css','.json','.webmanifest'}" not in text:
        raise SystemExit("static cache header anchor missing")
    write("tcg_updater.py", text)


def patch_boot_supervisor() -> None:
    text = read("ANDROID_AUTO_START_INSTALL.sh")
    old = "  echo 'while true; do bash ANDROID_UPDATE_AND_START.sh >> TCG_ANDROID_STARTUP.log 2>&1; sleep 10; done'"
    new = """  echo 'LOG=TCG_ANDROID_STARTUP.log'\n  echo 'if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt 2097152 ]; then mv -f "$LOG" "$LOG.1"; fi'\n  echo 'delay=30'\n  echo 'while true; do'\n  echo '  bash ANDROID_UPDATE_AND_START.sh >> "$LOG" 2>&1'\n  echo '  rc=$?'\n  echo \"  if pgrep -f '[p]ython.*tcg_updater_v135.py' >/dev/null 2>&1; then exit 0; fi\"\n  echo '  echo "[WARN] TCG server stopped (rc=$rc); retrying in ${delay}s." >> "$LOG"'\n  echo '  sleep "$delay"'\n  echo '  if [ "$delay" -lt 300 ]; then delay=$((delay*2)); [ "$delay" -gt 300 ] && delay=300; fi'\n  echo 'done'"""
    if old in text:
        text = text.replace(old, new, 1)
    elif "retrying in ${delay}s" not in text:
        raise SystemExit("boot loop anchor missing")
    text = text.replace(
        "Android boot auto-start installed (v176 safe update + singleton launcher).",
        "Android boot auto-start installed (v181 safe update + singleton supervisor).",
    )
    write("ANDROID_AUTO_START_INSTALL.sh", text)


def patch_launcher_lifecycle() -> None:
    text = read("START_TCG_UPDATER_ANDROID.sh")
    if 'PAIR_QUEUE_PID=""' not in text:
        text = text.replace('WAKE_LOCKED=0\n', 'WAKE_LOCKED=0\nPAIR_QUEUE_PID=""\n', 1)
    if 'kill "$PAIR_QUEUE_PID"' not in text:
        anchor = 'cleanup_android_start() {\n'
        if anchor not in text:
            raise SystemExit("launcher cleanup anchor missing")
        text = text.replace(
            anchor,
            """cleanup_android_start() {\n  if [ -n "${PAIR_QUEUE_PID:-}" ] && kill -0 "$PAIR_QUEUE_PID" 2>/dev/null; then\n    kill "$PAIR_QUEUE_PID" 2>/dev/null || true\n    wait "$PAIR_QUEUE_PID" 2>/dev/null || true\n  fi\n""",
            1,
        )
    text = text.replace(
        'echo "[안전] 혼합 업데이트 상태로 서버를 시작하지 않습니다. INSTALL_MANUAL_OFFICIAL_FALLBACK.sh를 다시 실행하세요."',
        'echo "[안전] 혼합 업데이트 상태로 서버를 시작하지 않습니다. bash ANDROID_UPDATE_AND_START.sh 로 GitHub main을 다시 확인하세요."',
    )
    if "PAIR_QUEUE_PID=$!" not in text:
        pattern = re.compile(
            r"(nohup python graded_photo_manual_pair_queue\.py --watch --interval 60 \\\n  > TCG_MANUAL_PAIR_QUEUE\.log 2>&1 &\n)"
        )
        text, count = pattern.subn(r"\1PAIR_QUEUE_PID=$!\n", text, count=1)
        if count != 1:
            raise SystemExit("queue pid anchor missing")
    write("START_TCG_UPDATER_ANDROID.sh", text)


def patch_safe_updater() -> None:
    text = read("ANDROID_UPDATE_AND_START.sh")
    start = text.find("if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree")
    end = text.find('\nif [ "$updated" = "1" ]; then', start)
    if start < 0 or end < 0:
        raise SystemExit("android updater git block missing")
    new_git = r'''if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  before="$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)"
  branch="$(git branch --show-current 2>/dev/null || true)"
  can_update=1
  if [ "$branch" != "main" ]; then
    echo "[안내] 현재 브랜치가 main이 아닙니다(${branch:-detached}). 자동 업데이트는 건너뜁니다."
    can_update=0
  elif ! git diff --cached --quiet --ignore-submodules --; then
    echo "[안전] staged 변경이 있어 자동 업데이트를 건너뜁니다. 사용자가 준비한 변경은 자동으로 건드리지 않습니다."
    can_update=0
  else
    dirty_paths="$(git diff --name-only --ignore-submodules --)"
    unsafe_paths=""
    if [ -n "$dirty_paths" ]; then
      while IFS= read -r changed; do
        [ -z "$changed" ] && continue
        case "$changed" in
          tcg_live_data.json|releases.json|market_watch.json|market_prices.json|promo_events.json|purchase_sources.json|purchase_signals.json|social_stock_signals.json|exchange_rates.json|graded_photo_candidates.json|supplementary_candidates.json|social_event_candidates.json|web_discovery_candidates.json|link_health_report.json|auto_update_report.json|auto_update_issues.json|auto_repair_memory.json|adaptive_collection_stats.json|adaptive_collection_stats.json.bak|verified_certifications.json|learning_store.json|vision_self_learning_report.json|ebay_grader_candidates.json|card_identity_learning.json|source_collection_stats.json|source_collection_stats.json.bak|precollect_status.json)
            ;;
          *) unsafe_paths="${unsafe_paths}${unsafe_paths:+, }$changed" ;;
        esac
      done <<EOF
$dirty_paths
EOF
    fi
    if [ -n "$unsafe_paths" ]; then
      echo "[안전] 코드/설정 추적파일에 로컬 수정이 있어 자동 업데이트를 건너뜁니다: $unsafe_paths"
      can_update=0
    elif [ -n "$dirty_paths" ]; then
      echo "[OK] 정상 수집으로 변경된 런타임 JSON만 감지했습니다. Git이 덮어쓰지 않는 범위에서 fast-forward를 시도합니다."
    fi
  fi

  if [ "$can_update" = "1" ]; then
    echo "[업데이트] GitHub main 최신 상태를 확인합니다..."
    if git fetch origin main --prune; then
      local_head="$(git rev-parse HEAD 2>/dev/null || true)"
      remote_head="$(git rev-parse origin/main 2>/dev/null || true)"
      if [ -n "$remote_head" ] && [ "$local_head" != "$remote_head" ]; then
        if git merge --ff-only origin/main; then
          updated=1
        else
          echo "[안전] 원격 변경과 로컬 런타임 자료가 같은 파일을 건드려 자동 병합을 중단했습니다. 로컬 자료는 그대로 보존합니다."
        fi
      else
        echo "[OK] 이미 최신 main입니다."
      fi
    else
      echo "[안내] 네트워크/GitHub 연결 문제로 업데이트 확인을 건너뜁니다. 현재 버전으로 시작합니다."
    fi
  fi
  after="$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)"
fi
'''
    text = text[:start] + new_git + text[end:]
    write("ANDROID_UPDATE_AND_START.sh", text)


def patch_market_collector() -> None:
    text = read("update_market_prices.py")
    start = text.find("def coverage(db):")
    end = text.find("\ndef main():", start)
    if start < 0 or end < 0:
        raise SystemExit("market coverage function missing")
    new_cov = '''def coverage(db):
    raw=safe_read_text(APP)
    start='const COUNTRY_BOX_DATA='; end='const LEARNING_PRICE_DATA='
    if start not in raw or end not in raw:
        return {'total':0,'verified':0,'pending':0,'missing_keys':[],
                'warning':'catalog_marker_missing · 가격자료는 유지하고 UI 카탈로그 커버리지 계산만 보류'}
    try:
        block=raw.split(start,1)[1].split(end,1)[0]
        products=re.findall(r'\\{country:"(KR|JP|US)",game:"[^"]+",name:"([^"]+)"',block)
    except (IndexError,TypeError,ValueError):
        return {'total':0,'verified':0,'pending':0,'missing_keys':[],
                'warning':'catalog_parse_failed · 가격자료는 유지하고 UI 카탈로그 커버리지 계산만 보류'}
    required={f'{region}|{name}|{asset}' for region,name in products for asset in ('BOX','HIT')}
    verified=required & set(db.get('entries',{}));missing=sorted(required-verified)
    return {'total':len(required),'verified':len(verified),'pending':len(missing),'missing_keys':missing}
'''
    text = text[:start] + new_cov + text[end:]

    class_start = text.find("    transient_market_errors=[]")
    class_end = text.find("    db['updated_at']=", class_start)
    if class_start < 0 or class_end < 0:
        raise SystemExit("KREAM classification block missing")
    new_class = '''    transient_market_errors=[]
    hard_market_errors=[]
    for item in errors:
        text=str(item)
        kream_transient=(
            re.search(r'^KREAM ',text,re.I) is not None and (
                re.search(r'HTTPError: status (?:403|429|5(?:00|02|03|04))\\b',text,re.I) is not None
                or re.search(r'(?:URLError|TimeoutError|timed out|temporary failure|connection reset|name resolution|DNS)',text,re.I) is not None
            )
        )
        if kream_transient:
            transient_market_errors.append(text)
        else:
            hard_market_errors.append(text)
'''
    text = text[:class_start] + new_class + text[class_end:]
    text = text.replace(
        "db['collection_note']='KREAM 원출처 5xx 시 직전 검증자료 유지 · 다음 업데이트에서 재확인' if transient_market_errors else ''",
        "db['collection_note']='KREAM 원출처 403/429/5xx/네트워크 지연 시 직전 검증자료 유지 · 다음 업데이트에서 재확인' if transient_market_errors else ''",
    )
    write("update_market_prices.py", text)


def write_regression_test() -> None:
    write(
        "test_runtime_delivery_guards.py",
        r'''from pathlib import Path

ROOT=Path(__file__).resolve().parent


def text(name):
    return (ROOT/name).read_text(encoding='utf-8')


def main():
    index=text('index.html')
    assert index.count('multi_market_prices.js') == 1, 'multi-market script must load exactly once'
    assert 'multi_market_prices.js?v=181' in index
    assert 'auto_validation_flow.js?v=181' in index
    assert 'graded_photo_dashboard.js?v=181' in index
    assert 'manual_dual_photo_bridge.js?v=181' in index
    assert '__TCG_MULTI_MARKET_PRICES__' in text('multi_market_prices.js')

    sw=text('sw.js')
    assert 'tcg-v181-network-first-runtime' in sw
    assert "cache:'no-store'" in sw
    assert 'Promise.allSettled(CORE.map' in sw
    assert '(?:html|js|css|json|webmanifest)' in sw

    server=text('tcg_updater.py')
    assert "target.suffix.lower() in {'.html','.js','.css','.json','.webmanifest'}" in server
    assert 'no-store, no-cache, must-revalidate, max-age=0' in server

    updater=text('ANDROID_UPDATE_AND_START.sh')
    assert '정상 수집으로 변경된 런타임 JSON만 감지했습니다' in updater
    assert 'market_prices.json' in updater and 'graded_photo_candidates.json' in updater

    boot=text('ANDROID_AUTO_START_INSTALL.sh')
    assert 'retrying in ${delay}s' in boot
    assert 'sleep 10; done' not in boot

    launcher=text('START_TCG_UPDATER_ANDROID.sh')
    assert 'PAIR_QUEUE_PID=$!' in launcher
    assert 'kill "$PAIR_QUEUE_PID"' in launcher
    assert '혼합 업데이트 상태로 서버를 시작하지 않습니다. INSTALL_MANUAL_OFFICIAL_FALLBACK.sh' not in launcher

    market=text('update_market_prices.py')
    assert 'catalog_marker_missing' in market
    assert 'kream_transient=(' in market
    print('[OK] runtime delivery guards v181')


if __name__=='__main__':
    main()
''',
    )


def write_guard_workflow() -> None:
    write(
        ".github/workflows/runtime-delivery-guard.yml",
        '''name: Runtime delivery guard

on:
  push:
    branches: [main]
    paths:
      - 'index.html'
      - 'sw.js'
      - 'multi_market_prices.js'
      - 'tcg_updater.py'
      - 'ANDROID_UPDATE_AND_START.sh'
      - 'ANDROID_AUTO_START_INSTALL.sh'
      - 'START_TCG_UPDATER_ANDROID.sh'
      - 'update_market_prices.py'
      - 'test_runtime_delivery_guards.py'
      - '.github/workflows/runtime-delivery-guard.yml'
  pull_request:
    paths:
      - 'index.html'
      - 'sw.js'
      - 'multi_market_prices.js'
      - 'tcg_updater.py'
      - 'ANDROID_UPDATE_AND_START.sh'
      - 'ANDROID_AUTO_START_INSTALL.sh'
      - 'START_TCG_UPDATER_ANDROID.sh'
      - 'update_market_prices.py'
      - 'test_runtime_delivery_guards.py'

permissions:
  contents: read

concurrency:
  group: runtime-delivery-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Verify runtime delivery invariants
        run: |
          python test_runtime_delivery_guards.py
          python -m py_compile tcg_updater.py update_market_prices.py
          bash -n ANDROID_UPDATE_AND_START.sh
          bash -n ANDROID_AUTO_START_INSTALL.sh
          bash -n START_TCG_UPDATER_ANDROID.sh
          node --check multi_market_prices.js
          node --check sw.js
''',
    )


def main() -> None:
    patch_index()
    patch_multi_market()
    patch_service_worker()
    patch_server_cache_headers()
    patch_boot_supervisor()
    patch_launcher_lifecycle()
    patch_safe_updater()
    patch_market_collector()
    write_regression_test()
    write_guard_workflow()
    print("[OK] veteran runtime hardening v181 prepared")


if __name__ == "__main__":
    main()
