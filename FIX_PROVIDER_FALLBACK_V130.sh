#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

python - <<'PY'
from pathlib import Path
import re

path = Path('graded_photo_multi_source.py')
if not path.exists():
    raise SystemExit('[ERROR] graded_photo_multi_source.py not found')

text = path.read_text(encoding='utf-8')
backup = Path('graded_photo_multi_source.py.before_v130_provider_guard')
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

state_block = """_SEARCHER=None

# v130: run-local search-provider circuit breaker.  Public search engines can
# temporarily time out or rate-limit Android/Tailscale clients.  Repeating the
# same dead route for every marketplace multiplies latency and diagnostic spam,
# so after two transient DuckDuckGo failures we cool that route down while Bing
# RSS and configured Google CSE continue independently.
_SEARCH_PROVIDER_STATE={
 'duckduckgo':{'failures':0,'blocked_until':0.0,'last_error':''},
}
DDG_FAIL_THRESHOLD=2
DDG_COOLDOWN_SECONDS=max(60,int(os.environ.get('TCG_DDG_COOLDOWN_SECONDS','900') or 900))

def _provider_transient_error(value:str)->bool:
 text=str(value or '').lower()
 return any(token in text for token in ('timeout','timed out','urlerror','429','502','503','connection','temporary','name resolution'))

def _provider_allowed(name:str)->bool:
 state=_SEARCH_PROVIDER_STATE.get(name)
 return not state or float(state.get('blocked_until') or 0.0)<=time.time()

def _provider_note(name:str,error:str|None):
 state=_SEARCH_PROVIDER_STATE.setdefault(name,{'failures':0,'blocked_until':0.0,'last_error':''})
 if not error:
  state.update({'failures':0,'blocked_until':0.0,'last_error':''})
  return
 state['last_error']=str(error)[:180]
 if _provider_transient_error(error):
  state['failures']=int(state.get('failures') or 0)+1
  if state['failures']>=DDG_FAIL_THRESHOLD:
   state['blocked_until']=time.time()+DDG_COOLDOWN_SECONDS
"""

if '_SEARCH_PROVIDER_STATE=' not in text:
    text = text.replace('_SEARCHER=None\n', state_block + '\n', 1)

new_query_rows = r'''def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:
 errors=[];merged=[];seen=set()
 def add(rows):
  for row in rows or []:
   if not isinstance(row,dict):continue
   url=str(row.get('url') or '').strip()
   key=url or (str(row.get('title') or ''),str(row.get('search_provider') or ''))
   if not key or key in seen:continue
   seen.add(key);merged.append(row)

 # v130: missing API keys are an optional configuration state, not a collection
 # error.  Bing RSS stays available without a key.  DuckDuckGo is attempted only
 # while its run-local circuit is healthy; repeated timeouts cool it down instead
 # of repeating the same failure for Amazon/eBay/every other marketplace.
 def google():
  key=(os.environ.get('GOOGLE_CSE_KEY') or os.environ.get('GOOGLE_CSE_API_KEY') or '').strip()
  cx=(os.environ.get('GOOGLE_CSE_CX') or os.environ.get('GOOGLE_CSE_ID') or '').strip()
  return (_google_cse(query,limit),None) if key and cx else ([],None)
 def bing():
  rows,err,_,_= _searcher()._search_bing_rss(query,limit);return rows,err
 def duck():
  rows,err,_,_= _searcher()._search_ddg(query,limit);return rows,err

 providers={'bing_rss':bing}
 if (os.environ.get('GOOGLE_CSE_KEY') or os.environ.get('GOOGLE_CSE_API_KEY')) and (os.environ.get('GOOGLE_CSE_CX') or os.environ.get('GOOGLE_CSE_ID')):
  providers['google_cse']=google
 if _provider_allowed('duckduckgo'):
  providers['duckduckgo']=duck

 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,len(providers)),thread_name_prefix='graded-photo-search') as pool:
  future_map={pool.submit(fn):name for name,fn in providers.items()}
  for future in concurrent.futures.as_completed(future_map):
   name=future_map[future]
   try:
    rows,err=future.result()
    if name=='duckduckgo':_provider_note(name,err)
    if err:
     # Only expose the first two DDG failures that caused the cooldown; do not
     # multiply identical timeout lines for every marketplace/query.
     if name!='duckduckgo' or int(_SEARCH_PROVIDER_STATE.get(name,{}).get('failures') or 0)<=DDG_FAIL_THRESHOLD:
      errors.append(name+':'+str(err)[:160])
    add(rows)
   except Exception as exc:
    err=type(exc).__name__+':'+str(exc)[:120]
    if name=='duckduckgo':_provider_note(name,err)
    errors.append(name+':'+err)
 return merged[:max(limit*3,limit)],errors
'''

pattern = re.compile(r"def _query_rows\(query:str,limit:int\)->tuple\[list\[dict\],list\[str\]\]:\n.*?\n\ndef _bing_image_rows", re.S)
match = pattern.search(text)
if not match:
    raise SystemExit('[ERROR] _query_rows block not found; source layout changed')
text = pattern.sub(new_query_rows + '\n\ndef _bing_image_rows', text, count=1)

path.write_text(text, encoding='utf-8')
print('[OK] v130 provider circuit breaker patched')
print('[OK] backup:', backup)
PY

python -m py_compile graded_photo_multi_source.py

echo "[OK] syntax check passed"
echo "[INFO] DuckDuckGo timeout: 2 failures -> 15 minute cooldown"
echo "[INFO] Bing RSS continues while DDG is cooling down"
echo "[INFO] Google CSE/eBay API remain optional; missing keys are not treated as hard failures"
echo "[NEXT] Restart the TCG server, then run '전체 안전 업데이트' once."
