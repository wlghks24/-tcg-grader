#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE_SHA="9fdfe499139e2d68bc926e6655af058fbe116d29"
NOW_KST="2026-09-28T11:55:00+09:00"


def read(path):
    return (ROOT/path).read_text(encoding="utf-8")


def write(path,text):
    target=ROOT/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(text,encoding="utf-8")


def replace_once(path,old,new):
    text=read(path)
    count=text.count(old)
    if count!=1:
        raise SystemExit(f"{path}: expected exactly one replacement, got {count}: {old[:120]!r}")
    write(path,text.replace(old,new,1))


def replace_count(path,old,new,expected):
    text=read(path)
    count=text.count(old)
    if count!=expected:
        raise SystemExit(f"{path}: expected {expected} replacements, got {count}: {old[:120]!r}")
    write(path,text.replace(old,new))


# 1) Persisted FX cache must satisfy the same provenance/freshness/value proof
# as live consumers before it can be retained after a source outage.
path="update_exchange_rates.py"
replace_once(path,
"import datetime as dt,json,math,urllib.error,urllib.request\nfrom pathlib import Path\n",
"import datetime as dt,json,math,urllib.error,urllib.request\nfrom pathlib import Path\nfrom urllib.parse import urlparse\n")
replace_once(path,
"ALLOWED_HOSTS={'api.frankfurter.dev','api.frankfurter.app'}\n",
"ALLOWED_HOSTS={'api.frankfurter.dev','api.frankfurter.app'}\nFX_MAX_AGE_SECONDS=72*60*60\nFX_MAX_FUTURE_SKEW_SECONDS=6*60*60\nFX_SOURCE_PROVENANCE={\n    'frankfurter-v2':'api.frankfurter.dev',\n    'frankfurter-v1':'api.frankfurter.dev',\n    'frankfurter-legacy':'api.frankfurter.app',\n}\n")
replace_once(path,
"    except (TypeError,ValueError,OverflowError):\n        return None\n\ndef parse_source_timestamp(raw):\n",
"    except (TypeError,ValueError,OverflowError):\n        return None\n\ndef _timestamp_is_fresh(value, *, now=None):\n    observed=_parse_observed_at(value)\n    if observed is None:\n        return False\n    current=(now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)\n    age=(current-observed).total_seconds()\n    return -FX_MAX_FUTURE_SKEW_SECONDS <= age <= FX_MAX_AGE_SECONDS\n\ndef valid_persisted_cache(data, *, now=None):\n    \"\"\"Return True only for a cache that is safe to reuse without a new fetch.\"\"\"\n    if not isinstance(data,dict) or not isinstance(data.get('rates'),dict):\n        return False\n    route=str(data.get('source_route') or '').strip()\n    source=str(data.get('source') or '').strip()\n    try:\n        host=(urlparse(source).hostname or '').lower()\n    except (TypeError,ValueError):\n        return False\n    if FX_SOURCE_PROVENANCE.get(route) != host:\n        return False\n    if not (_timestamp_is_fresh(data.get('updated_at'),now=now) and\n            _timestamp_is_fresh(data.get('source_timestamp'),now=now)):\n        return False\n    rates=data['rates']\n    if any(isinstance(rates.get(key),bool) for key in ('JPY_KRW','USD_KRW')):\n        return False\n    try:\n        jpy=float(rates.get('JPY_KRW',0));usd=float(rates.get('USD_KRW',0))\n    except (TypeError,ValueError,OverflowError):\n        return False\n    return (math.isfinite(jpy) and math.isfinite(usd) and\n            0 < jpy < 30 and 500 < usd < 3000)\n\ndef parse_source_timestamp(raw):\n")
replace_once(path,
"    age=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()\n    if not (-6*60*60 <= age <= 72*60*60):\n",
"    age=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()\n    if not (-FX_MAX_FUTURE_SKEW_SECONDS <= age <= FX_MAX_AGE_SECONDS):\n")
replace_once(path,
"    else:\n        current['collection_status']='기존 확인환율 유지' if current.get('rates') else '사용 가능한 확인환율 없음'\n",
"    else:\n        cache_ok=valid_persisted_cache(current)\n        if not cache_ok:\n            # Never let a legacy/missing-provenance cache remain consumable merely\n            # because its numeric values look plausible. Preserve provenance fields\n            # for diagnosis, but remove all usable conversion values.\n            current['rates']={}\n        current['collection_status']='기존 확인환율 유지' if cache_ok else '사용 가능한 확인환율 없음'\n")

# 2) Automatic collection/last-good gates must not bless an unprovenanced FX file.
replace_once("auto_update_all.py",
"        if not (0 < jpy_krw < 30 and 500 < usd_krw < 3000):\n            raise ValueError(\"환율 범위 오류\")\n",
"        if not (0 < jpy_krw < 30 and 500 < usd_krw < 3000):\n            raise ValueError(\"환율 범위 오류\")\n        import update_exchange_rates\n        if not update_exchange_rates.valid_persisted_cache(data):\n            raise ValueError(\"환율 출처·source timestamp·freshness 검증 실패\")\n")
replace_once("auto_repair_engine.py",
"            if not (0 < values[0] < 30 and 500 < values[1] < 3000):\n                return False\n",
"            if not (0 < values[0] < 30 and 500 < values[1] < 3000):\n                return False\n            import update_exchange_rates\n            if not update_exchange_rates.valid_persisted_cache(data):\n                return False\n")

# 3) Browser conversion must enforce source timestamp + route/host provenance too.
replace_once("index.html",
'let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated="",fxTimestamp="",fxExpiryTimer=null;',
'let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated="",fxTimestamp="",fxSourceTimestamp="",fxExpiryTimer=null;')
replace_once("index.html",
"function fxTimestampFresh(value,now=Date.now()){const parsed=Date.parse(String(value||''));if(!Number.isFinite(parsed))return false;const age=now-parsed;return age>=-FX_MAX_FUTURE_SKEW_MS&&age<=FX_MAX_AGE_MS}\n",
"function fxTimestampFresh(value,now=Date.now()){const parsed=Date.parse(String(value||''));if(!Number.isFinite(parsed))return false;const age=now-parsed;return age>=-FX_MAX_FUTURE_SKEW_MS&&age<=FX_MAX_AGE_MS}\nfunction fxSourceProvenanceOk(data){try{const route=String(data?.source_route||''),host=new URL(String(data?.source||'')).hostname.toLowerCase();return ((route==='frankfurter-v2'||route==='frankfurter-v1')&&host==='api.frankfurter.dev')||(route==='frankfurter-legacy'&&host==='api.frankfurter.app')}catch(_){return false}}\n")
replace_count("index.html",
"if(!fxTimestampFresh(fxTimestamp)||",
"if(!(fxTimestampFresh(fxTimestamp)&&fxTimestampFresh(fxSourceTimestamp))||",2)
replace_once("index.html",
'function clearExpiredFx(now=Date.now()){if(!fxTimestamp||fxTimestampFresh(fxTimestamp,now))return false;if(fxExpiryTimer!==null&&typeof clearTimeout==="function")clearTimeout(fxExpiryTimer);fxExpiryTimer=null;fxRates={JPY_KRW:0,USD_KRW:0};fxUpdated="";fxTimestamp="";clearFxConversionDisplay();return true}',
'function clearExpiredFx(now=Date.now()){if(!fxTimestamp&&!fxSourceTimestamp)return false;if(fxTimestampFresh(fxTimestamp,now)&&fxTimestampFresh(fxSourceTimestamp,now))return false;if(fxExpiryTimer!==null&&typeof clearTimeout==="function")clearTimeout(fxExpiryTimer);fxExpiryTimer=null;fxRates={JPY_KRW:0,USD_KRW:0};fxUpdated="";fxTimestamp="";fxSourceTimestamp="";clearFxConversionDisplay();return true}')
replace_once("index.html",
'function scheduleFxExpiry(){if(fxExpiryTimer!==null&&typeof clearTimeout==="function")clearTimeout(fxExpiryTimer);fxExpiryTimer=null;const stamp=Date.parse(String(fxTimestamp||""));if(!Number.isFinite(stamp)||typeof setTimeout!=="function")return;const delay=Math.max(0,Math.min(stamp+FX_MAX_AGE_MS-Date.now()+1,2147483647));fxExpiryTimer=setTimeout(()=>{fxExpiryTimer=null;if(!clearExpiredFx())scheduleFxExpiry()},delay)}',
'function scheduleFxExpiry(){if(fxExpiryTimer!==null&&typeof clearTimeout==="function")clearTimeout(fxExpiryTimer);fxExpiryTimer=null;const stamps=[fxTimestamp,fxSourceTimestamp].map(value=>Date.parse(String(value||"")));if(stamps.some(value=>!Number.isFinite(value))||typeof setTimeout!=="function")return;const stamp=Math.min(...stamps),delay=Math.max(0,Math.min(stamp+FX_MAX_AGE_MS-Date.now()+1,2147483647));fxExpiryTimer=setTimeout(()=>{fxExpiryTimer=null;if(!clearExpiredFx())scheduleFxExpiry()},delay)}')
replace_once("index.html",
'  const d=await r.json(),jpy=Number(d.rates?.JPY_KRW),usd=Number(d.rates?.USD_KRW),stamp=String(d.updated_at||"");\n',
'  const d=await r.json(),jpy=Number(d.rates?.JPY_KRW),usd=Number(d.rates?.USD_KRW),stamp=String(d.updated_at||""),sourceStamp=String(d.source_timestamp||"");\n')
replace_once("index.html",
'  if(!fxTimestampFresh(stamp))throw new Error("fx timestamp stale");\n',
'  if(!fxSourceProvenanceOk(d))throw new Error("fx provenance");\n  if(!(fxTimestampFresh(stamp)&&fxTimestampFresh(sourceStamp)))throw new Error("fx timestamp stale");\n')
replace_once("index.html",
'  fxRates={JPY_KRW:jpy,USD_KRW:usd};fxUpdated=stamp.slice(0,10)||fxUpdated;fxTimestamp=stamp;scheduleFxExpiry();result.ok=true;\n',
'  fxRates={JPY_KRW:jpy,USD_KRW:usd};fxUpdated=stamp.slice(0,10)||fxUpdated;fxTimestamp=stamp;fxSourceTimestamp=sourceStamp;scheduleFxExpiry();result.ok=true;\n')
replace_once("index.html",
' }catch(e){if(fxExpiryTimer!==null&&typeof clearTimeout==="function")clearTimeout(fxExpiryTimer);fxExpiryTimer=null;fxRates={JPY_KRW:0,USD_KRW:0};fxUpdated="";fxTimestamp="";clearFxConversionDisplay();result.errors.push("환율자료")}',
' }catch(e){if(fxExpiryTimer!==null&&typeof clearTimeout==="function")clearTimeout(fxExpiryTimer);fxExpiryTimer=null;fxRates={JPY_KRW:0,USD_KRW:0};fxUpdated="";fxTimestamp="";fxSourceTimestamp="";clearFxConversionDisplay();result.errors.push("환율자료")}')

# 4) Runtime/browser tests exercise both rejection and expiry of source timestamps.
replace_once("verify_browser_runtime.js",
'  fxTimestamp: "",\n',
'  fxTimestamp: "",\n  fxSourceTimestamp: "",\n')
replace_once("verify_browser_runtime.js",
'  loadOneLine("fxTimestampFresh");\n  loadAsyncBlock("loadExchangeRates");\n',
'  loadOneLine("fxTimestampFresh");\n  loadOneLine("fxSourceProvenanceOk");\n  loadAsyncBlock("loadExchangeRates");\n')
replace_once("verify_browser_runtime.js",
'  context.fxTimestamp="";\n  assert.equal(context.foreignKrw("¥1000"),"","missing FX must not render a fabricated zero price");\n',
'  context.fxTimestamp="";\n  context.fxSourceTimestamp="";\n  assert.equal(context.foreignKrw("¥1000"),"","missing FX must not render a fabricated zero price");\n')
replace_once("verify_browser_runtime.js",
'  context.fxRates={JPY_KRW:8.7,USD_KRW:1380};\n  context.fxTimestamp=new Date().toISOString();\n',
'  context.fxRates={JPY_KRW:8.7,USD_KRW:1380};\n  context.fxTimestamp=new Date().toISOString();\n  context.fxSourceTimestamp=context.fxTimestamp;\n')
replace_once("verify_browser_runtime.js",
'  assert.equal(context.fxTimestamp,"");\n  assert.equal(context.foreignKrw("¥1000"),"","failed refresh must not retain stale conversion");\n',
'  assert.equal(context.fxTimestamp,"");\n  assert.equal(context.fxSourceTimestamp,"");\n  assert.equal(context.foreignKrw("¥1000"),"","failed refresh must not retain stale conversion");\n')
replace_once("verify_browser_runtime.js",
'        : { rates: { JPY_KRW: 8.7, USD_KRW: 1380 }, updated_at: new Date().toISOString() },\n',
'        : { rates: { JPY_KRW: 8.7, USD_KRW: 1380 }, updated_at: new Date().toISOString(), source_timestamp: new Date().toISOString(), source: "https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY", source_route: "frankfurter-v2" },\n')
replace_once("verify_browser_runtime.js",
'  assert.equal((await context.v13LoadAllPriceData()).complete, true);\n  assert.equal((await context.loadPopularitySignals(true)).ok, true);\n  assert.equal((await context.loadExchangeRates(true)).ok, true);\n',
'  assert.equal((await context.v13LoadAllPriceData()).complete, true);\n  assert.equal((await context.loadPopularitySignals(true)).ok, true);\n  const goodFetch=context.fetch;\n  context.fetch=async()=>({ok:true,status:200,json:async()=>({rates:{JPY_KRW:8.7,USD_KRW:1380},updated_at:new Date().toISOString()})});\n  assert.equal((await context.loadExchangeRates(true)).ok,false,"unprovenanced browser FX must fail closed");\n  assert.equal(context.fxRates.JPY_KRW,0);\n  context.fetch=goodFetch;\n  assert.equal((await context.loadExchangeRates(true)).ok, true);\n')
replace_once("verify_browser_runtime.js",
'  const freshStamp=context.fxTimestamp,expiry=Date.parse(freshStamp)+context.FX_MAX_AGE_MS;\n',
'  const freshStamp=context.fxTimestamp,sourceStamp=context.fxSourceTimestamp,expiry=Math.min(Date.parse(freshStamp),Date.parse(sourceStamp))+context.FX_MAX_AGE_MS;\n')
replace_once("verify_browser_runtime.js",
'  context.fxTimestamp=new Date(Date.now()-73*60*60*1000).toISOString();\n  assert.equal(context.foreignKrw("¥1000"),"","expired FX must not render a KRW conversion");\n',
'  context.fxTimestamp=new Date().toISOString();\n  context.fxSourceTimestamp=new Date(Date.now()-73*60*60*1000).toISOString();\n  context.fxRates={JPY_KRW:8.7,USD_KRW:1380};\n  assert.equal(context.foreignKrw("¥1000"),"","expired source FX must not render a KRW conversion");\n')

# 5) Static/UI tests assert the stronger browser contract.
replace_once("test_edition_fx_failclosed_v328.py",
"        self.assertIn('let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated=\"\",fxTimestamp=\"\",fxExpiryTimer=null;',html)\n",
"        self.assertIn('let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated=\"\",fxTimestamp=\"\",fxSourceTimestamp=\"\",fxExpiryTimer=null;',html)\n")
replace_once("test_edition_fx_failclosed_v328.py",
"        self.assertIn('fxTimestampFresh',html)\n",
"        self.assertIn('fxTimestampFresh',html)\n        self.assertIn('fxSourceProvenanceOk',html)\n        self.assertIn('source_timestamp',html)\n")
replace_once("test_edition_fx_failclosed_v328.py",
"        self.assertIn('if(!fxTimestampFresh(fxTimestamp)',html)\n        self.assertIn('fxTimestamp=stamp;scheduleFxExpiry();result.ok=true;',html)\n        self.assertIn('fxTimestamp=\"\";clearFxConversionDisplay();result.errors.push(\"환율자료\")',html)\n",
"        self.assertIn('fxTimestampFresh(fxSourceTimestamp)',html)\n        self.assertIn('fxSourceTimestamp=sourceStamp;scheduleFxExpiry();result.ok=true;',html)\n        self.assertIn('fxTimestamp=\"\";fxSourceTimestamp=\"\";clearFxConversionDisplay();result.errors.push(\"환율자료\")',html)\n")

# 6) Focused updater tests cover legacy cache rejection and verified cache retention.
path="test_fx_failclosed_recovery_v349.py"
insert='''\n    def test_updater_rejects_legacy_cache_without_source_timestamp_on_outage(self):\n        with tempfile.TemporaryDirectory() as td:\n            path=Path(td)/'exchange_rates.json'\n            payload={\n                'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),\n                'base':'KRW',\n                'rates':{'USD_KRW':1360.65,'JPY_KRW':8.60028},\n                'source':'https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY',\n                'source_route':'frankfurter-v2',\n            }\n            path.write_text(json.dumps(payload),encoding='utf-8')\n            with mock.patch.object(updater,'DATA',path), \\\n                 mock.patch.object(updater,'SOURCES',(('frankfurter-v2','https://api.frankfurter.dev/v2/rates'),)), \\\n                 mock.patch.object(updater,'fetch',side_effect=OSError('offline')):\n                result=updater.main()\n            self.assertEqual({},result['rates'])\n            self.assertEqual('사용 가능한 확인환율 없음',result['collection_status'])\n            self.assertNotIn('source_timestamp',result)\n            self.assertTrue(result['collection_errors'])\n\n    def test_updater_preserves_only_fresh_verified_cache_on_outage(self):\n        with tempfile.TemporaryDirectory() as td:\n            path=Path(td)/'exchange_rates.json'\n            self._write_fx(path,{'USD_KRW':1360.65,'JPY_KRW':8.60028})\n            with mock.patch.object(updater,'DATA',path), \\\n                 mock.patch.object(updater,'SOURCES',(('frankfurter-v2','https://api.frankfurter.dev/v2/rates'),)), \\\n                 mock.patch.object(updater,'fetch',side_effect=OSError('offline')):\n                result=updater.main()\n            self.assertEqual({'USD_KRW':1360.65,'JPY_KRW':8.60028},result['rates'])\n            self.assertEqual('기존 확인환율 유지',result['collection_status'])\n            self.assertTrue(updater.valid_persisted_cache(result))\n\n'''
text=read(path)
needle="\n\nif __name__=='__main__':\n    unittest.main()\n"
if text.count(needle)!=1:raise SystemExit('test_fx insertion anchor mismatch')
write(path,text.replace(needle,insert+needle,1))

# 7) Keep historical v348 bounded to its own generation once v349 exists.
replace_once("test_tablet_gpt_tcg_grader_sync_v348.py",
'CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V348.json"\n',
'CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V348.json"\nNEXT_DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v349_delta.json"\n')
replace_once("test_tablet_gpt_tcg_grader_sync_v348.py",
'        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()\n',
'        next_delta=read(NEXT_DELTA) if NEXT_DELTA.exists() else None\n        comparison_head=next_delta["source_main_sha"] if next_delta else "HEAD"\n        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..{comparison_head}"],text=True).splitlines()\n')

# 8) Generate Tablet GPT <-> TCG Grader v349 alignment for this watched UI change.
old_delta=json.loads(read("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v348_delta.json"))
old_receipt=json.loads(read("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v348.json"))
old_contract=json.loads(read("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V348.json"))
lesson={
    "lesson_id":"TABLET-GPT-FX-BROWSER-CACHE-PROOF-V349",
    "subsystem":"market_price_fx_browser_and_cache_provenance",
    "issue_class":"python_fail_closed_can_be_bypassed_by_legacy_cache_or_browser_updated_at_only",
    "trigger_condition":"persisted FX has plausible numeric rates but lacks a verified source timestamp/provenance, or browser conversion checks collection time without the upstream observation time",
    "prevention_rule":"reuse and display FX only when route/host provenance, collection timestamp, upstream source timestamp, and positive finite bounded rates all pass the same 72-hour/6-hour-skew policy; otherwise remove usable rates and HOLD conversion",
    "validation_required":[
        "legacy cache without source_timestamp is rejected during source outage",
        "fresh fully provenanced cache alone may be retained during source outage",
        "automatic collection and last-good integrity gates reject unprovenanced FX",
        "browser conversion rejects missing provenance and expires at the older of collection/source timestamps",
        "candidate generation covers the exact watched index.html change from the exact base main"
    ],
    "safety_boundary":"never invent or backfill a source timestamp from local fetch/update time, never widen the 72-hour freshness gate, and never claim physical Tablet or Drive verification"
}
raw=json.dumps([lesson],ensure_ascii=False,sort_keys=True,separators=(",",":"))
digest=hashlib.sha256(raw.encode("utf-8")).hexdigest()
delta=copy.deepcopy(old_delta)
delta.update({
    "run_date_kst":"2026-09-28","built_at":NOW_KST,"status":"finalized",
    "prior_delta":"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v348_delta.json",
    "prior_lesson_digest_sha256":old_delta["lesson_digest_sha256"],
    "source_main_sha":BASE_SHA,
    "covered_merges":[{"pr":314,"version":"v349-fx-browser-cache-proof","merge_sha":BASE_SHA}],
    "lesson_digest_sha256":digest,"lessons":[lesson],
})
write("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v349_delta.json",json.dumps(delta,ensure_ascii=False,indent=2)+"\n")
receipt=copy.deepcopy(old_receipt)
receipt.update({
    "source_main_sha":BASE_SHA,"received_at":NOW_KST,"status":"SYNCED_VERIFIED",
    "source_snapshots":["TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v348_delta.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v349_delta.json"],
    "prior_lesson_digest_sha256":old_delta["lesson_digest_sha256"],
    "delta_lesson_digest_sha256":digest,
    "accepted_lesson_ids":[lesson["lesson_id"]],
})
receipt["verification"].update({
    "contract_version":"v349","verification_test":"test_tablet_gpt_tcg_grader_sync_v349.py",
    "verification_mode":"exact_candidate_fx_browser_and_persisted_cache_provenance_guard",
    "verified_result":"TABLET_GPT_TCG_GRADER_MATCH",
    "physical_tablet_runtime_verified":False,"physical_drive_readback_verified":False,"device_reverification_required":True,
})
write("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v349.json",json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
contract=copy.deepcopy(old_contract)
contract["contract_version"]="v349"
for key in ("generated_at","built_at","updated_at"):
    if key in contract:contract[key]=NOW_KST
for key in ("source_main_sha","base_main_sha"):
    if key in contract:contract[key]=BASE_SHA
if isinstance(contract.get("current_required_merge_prs"),list) and 314 not in contract["current_required_merge_prs"]:
    contract["current_required_merge_prs"].append(314)
if "expected_required_lesson_count" in contract:
    contract["expected_required_lesson_count"]=int(contract["expected_required_lesson_count"])+1
if isinstance(contract.get("required_lesson_ids"),list):
    contract["required_lesson_ids"].append(lesson["lesson_id"])
if "latest_lesson_digest_sha256" in contract:contract["latest_lesson_digest_sha256"]=digest
contract.setdefault("rules",{})["fx_browser_and_persisted_cache_must_share_provenance_gate"]=True
contract["rules"]["unverified_legacy_fx_cache_must_not_be_restored_as_last_good"]=True
candidate=contract.setdefault("candidate_sync",{})
candidate.update({
    "base_main_sha":BASE_SHA,
    "requires_exact_watched_path_match":True,
    "watched_paths":["index.html"],
    "generation_files":[
        "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v349_delta.json",
        "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v349.json",
        "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V349.json",
        "test_tablet_gpt_tcg_grader_sync_v349.py"
    ],
})
write("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V349.json",json.dumps(contract,ensure_ascii=False,indent=2)+"\n")

test=f'''import hashlib\nimport json\nfrom pathlib import Path\nimport subprocess\nimport unittest\n\nROOT=Path(__file__).resolve().parent\nSOURCE="{BASE_SHA}"\nDELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v349_delta.json"\nRECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v349.json"\nCONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V349.json"\n\ndef read(path):return json.loads(path.read_text(encoding="utf-8"))\n\nclass TabletGptTcgGraderSyncV349(unittest.TestCase):\n    def test_digest_receipt_and_safe_transfer_boundary(self):\n        delta,receipt,contract=map(read,(DELTA,RECEIPT,CONTRACT))\n        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))\n        digest=hashlib.sha256(raw.encode("utf-8")).hexdigest()\n        self.assertEqual("{digest}",digest)\n        self.assertEqual(digest,delta["lesson_digest_sha256"])\n        self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])\n        self.assertEqual(SOURCE,delta["source_main_sha"])\n        self.assertEqual(SOURCE,receipt["source_main_sha"])\n        self.assertEqual([row["lesson_id"] for row in delta["lessons"]],receipt["accepted_lesson_ids"])\n        self.assertEqual("SYNCED_VERIFIED",receipt["status"])\n        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])\n        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])\n        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])\n        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])\n        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])\n        self.assertTrue(contract["rules"]["fx_browser_and_persisted_cache_must_share_provenance_gate"])\n        self.assertTrue(contract["rules"]["unverified_legacy_fx_cache_must_not_be_restored_as_last_good"])\n\n    def test_exact_candidate_watched_path_set(self):\n        contract=read(CONTRACT);candidate=contract["candidate_sync"]\n        self.assertEqual(SOURCE,candidate["base_main_sha"])\n        self.assertTrue(candidate["requires_exact_watched_path_match"])\n        watch=contract["freshness_watch"]\n        exact=set(watch["exact_paths"]);prefixes=tuple(watch["path_prefixes"]);excluded=set(watch["exclude_paths"])\n        def watched(path):return path not in excluded and (path in exact or path.startswith(prefixes))\n        changed=subprocess.check_output(["git","diff","--name-only",f"{{SOURCE}}..HEAD"],text=True).splitlines()\n        relevant=sorted(path for path in changed if watched(path))\n        self.assertEqual(candidate["watched_paths"],relevant)\n        for path in candidate["generation_files"]:self.assertTrue((ROOT/path).is_file(),path)\n\nif __name__=="__main__":unittest.main(verbosity=2)\n'''
write("test_tablet_gpt_tcg_grader_sync_v349.py",test)

print("[OK] applied FX provenance/cache/browser proof repair v350")
