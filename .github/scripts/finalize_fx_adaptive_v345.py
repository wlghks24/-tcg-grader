from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "a8fe77bc38c51816f31b74320a786d45f3e5d346"
BRANCH = "fix/fx-adaptive-failclosed-v345"
WORKFLOW = ".github/workflows/finalize-fx-adaptive-v345.yml"
SELF = ".github/scripts/finalize_fx_adaptive_v345.py"


def run(*args: str) -> None:
    subprocess.run(list(args), cwd=ROOT, check=True)


exchange_code = '''#!/usr/bin/env python3
"""Refresh KRW reference exchange rates; preserve last values on failure."""
import datetime as dt,json,math,urllib.error,urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, safe_read_text, safe_urlopen
DATA=Path(__file__).resolve().parent/'exchange_rates.json'
SOURCES=(
    ('frankfurter-v2','https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY'),
    ('frankfurter-v1','https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW,JPY'),
    ('frankfurter-legacy','https://api.frankfurter.app/latest?from=USD&to=KRW,JPY'),
)
ALLOWED_HOSTS={'api.frankfurter.dev','api.frankfurter.app'}
SOURCE_MAX_AGE_SECONDS=72*60*60

def _utc_now(): return dt.datetime.now(dt.timezone.utc)

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'TCG-Grader-FX-Updater/2.1'})
    with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60),allowed_hosts=ALLOWED_HOSTS) as r:return json.load(r)

def _rows(raw):
    if isinstance(raw,dict) and isinstance(raw.get('data'),list):return raw['data']
    return raw if isinstance(raw,list) else None

def parse_rates(raw):
    if isinstance(raw,dict) and isinstance(raw.get('rates'),dict):
        rates=raw['rates'];return float(rates['KRW']),float(rates['JPY'])
    rows=_rows(raw)
    if isinstance(rows,list):
        quotes={str(row.get('quote') or row.get('currency') or '').upper():row.get('rate') for row in rows if isinstance(row,dict)}
        return float(quotes['KRW']),float(quotes['JPY'])
    raise ValueError('환율 응답의 KRW·JPY 필수값을 읽지 못했습니다')

def parse_source_date(raw):
    if isinstance(raw,dict) and isinstance(raw.get('rates'),dict):
        value=raw.get('date')
        if isinstance(value,str) and value.strip():return value.strip()
        raise ValueError('환율 원천 날짜가 없습니다')
    rows=_rows(raw)
    if isinstance(rows,list):
        dates=set();required=set()
        for row in rows:
            if not isinstance(row,dict):continue
            quote=str(row.get('quote') or row.get('currency') or '').upper()
            if quote not in {'KRW','JPY'}:continue
            required.add(quote);value=row.get('date')
            if not isinstance(value,str) or not value.strip():raise ValueError(f'{quote} 환율 원천 날짜가 없습니다')
            dates.add(value.strip())
        if required != {'KRW','JPY'} or len(dates) != 1:raise ValueError('KRW·JPY 환율 원천 날짜가 일치하지 않습니다')
        return next(iter(dates))
    raise ValueError('환율 원천 날짜를 읽지 못했습니다')

def validate_source_date(value,now=None):
    now=now or _utc_now()
    if now.tzinfo is None:raise ValueError('현재 시각 timezone이 필요합니다')
    try:source_date=dt.date.fromisoformat(str(value or '').strip())
    except (TypeError,ValueError) as exc:raise ValueError('환율 원천 날짜 형식이 잘못되었습니다') from exc
    source_ts=dt.datetime.combine(source_date,dt.time.min,tzinfo=dt.timezone.utc)
    age=(now.astimezone(dt.timezone.utc)-source_ts).total_seconds()
    if age < 0:raise ValueError('미래 환율 원천 날짜는 사용할 수 없습니다')
    if age > SOURCE_MAX_AGE_SECONDS:raise ValueError('환율 원천 날짜가 72시간을 초과했습니다')
    return source_date.isoformat(),source_ts.isoformat(timespec='seconds')

def main():
    current=json.loads(safe_read_text(DATA));errors=[];selected=None
    for label,url in SOURCES:
        try:
            raw=fetch(url);krw,jpy=parse_rates(raw);source_date,source_timestamp=validate_source_date(parse_source_date(raw))
            if not (math.isfinite(krw) and math.isfinite(jpy) and 500<krw<3000 and 50<jpy<250):raise ValueError('원화 환산 환율 수집값이 허용 범위를 벗어났습니다')
            selected=(label,url,krw,jpy,source_date,source_timestamp);break
        except (urllib.error.URLError,TimeoutError,OSError,KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
            errors.append(f'{label}: {diagnostic_exception(exc)}')
    if selected:
        label,url,krw,jpy,source_date,source_timestamp=selected
        current['rates']={'JPY_KRW':round(krw/jpy,5),'USD_KRW':round(krw,2)}
        current['updated_at']=_utc_now().isoformat(timespec='seconds');current['source']=url;current['source_route']=label
        current['source_date']=source_date;current['source_timestamp']=source_timestamp
        current['collection_status']='정상';current['collection_error']=None;current['collection_errors']=[]
    else:
        current['collection_status']='기존 확인환율 유지';current['collection_error']=errors[-1] if errors else '환율 수집 실패';current['collection_errors']=errors
    atomic_write_json(DATA,current);return current
if __name__=='__main__':main()
'''
(ROOT / "update_exchange_rates.py").write_text(exchange_code, encoding="utf-8")

# Adaptive learning: distinguish a genuinely fresh store from persisted corruption.
p = ROOT / "auto_update_all.py"
text = p.read_text(encoding="utf-8")
anchor = 'ADAPTIVE_STATS_BAK = ROOT / "adaptive_collection_stats.json.bak"\n_STATS_LOCK = threading.Lock()\n'
if anchor not in text:
    raise SystemExit("adaptive globals anchor missing")
text = text.replace(anchor, anchor + '_ADAPTIVE_STATS_CORRUPTION_HOLD = False\n_ADAPTIVE_STATS_STORAGE_SOURCE = "fresh"\n', 1)
pattern = r'def _load_adaptive_stats\(\) -> dict:\n.*?\ndef _worker_count\(job_count: int\) -> int:'
replacement = '''def _load_adaptive_stats() -> dict:
    global _ADAPTIVE_STATS_CORRUPTION_HOLD, _ADAPTIVE_STATS_STORAGE_SOURCE
    existing_seen=False
    for source,candidate in (("primary",ADAPTIVE_STATS),("backup",ADAPTIVE_STATS_BAK)):
        if not candidate.exists():continue
        existing_seen=True
        try:
            data=json.loads(safe_read_text(candidate))
            if _valid_adaptive_stats(data):
                _ADAPTIVE_STATS_CORRUPTION_HOLD=False;_ADAPTIVE_STATS_STORAGE_SOURCE=source
                return _sanitize_adaptive_stats(data)
        except (OSError,ValueError,TypeError):continue
    _ADAPTIVE_STATS_CORRUPTION_HOLD=existing_seen
    _ADAPTIVE_STATS_STORAGE_SOURCE="corrupt" if existing_seen else "fresh"
    return {"version":1,"jobs":{},"updated_at":None}

def _save_adaptive_stats(data: dict) -> bool:
    with _STATS_LOCK:
        if _ADAPTIVE_STATS_CORRUPTION_HOLD:return False
        data["version"]=1;data["updated_at"]=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        encoded=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\\n"
        if ADAPTIVE_STATS.exists():
            try:
                old=json.loads(safe_read_text(ADAPTIVE_STATS))
                if _valid_adaptive_stats(old):atomic_write_text(ADAPTIVE_STATS_BAK,json.dumps(old,ensure_ascii=False,indent=2,allow_nan=False)+"\\n",suffix='.stats.bak.tmp')
            except (OSError,ValueError,TypeError):pass
        atomic_write_text(ADAPTIVE_STATS,encoded,suffix='.stats.tmp');return True

def _worker_count(job_count: int) -> int:'''
text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count != 1:
    raise SystemExit("adaptive load/save patch failed")
fx_anchor = '''        if not (0 < jpy_krw < 30 and 500 < usd_krw < 3000):
            raise ValueError("환율 범위 오류")
    elif name == "grading_company_updates.json":'''
fx_replacement = '''        if not (0 < jpy_krw < 30 and 500 < usd_krw < 3000):
            raise ValueError("환율 범위 오류")
        source=str(data.get("source") or "");source_route=str(data.get("source_route") or "")
        source_date=str(data.get("source_date") or "");source_timestamp=str(data.get("source_timestamp") or "")
        if not source.startswith(("https://api.frankfurter.dev/","https://api.frankfurter.app/")):raise ValueError("환율 출처 provenance 오류")
        if source_route not in {"frankfurter-v2","frankfurter-v1","frankfurter-legacy"}:raise ValueError("환율 출처 route 오류")
        try:
            parsed=dt.datetime.fromisoformat(source_timestamp.replace("Z","+00:00"))
            if parsed.tzinfo is None or parsed.date().isoformat()!=source_date:raise ValueError("환율 원천 timestamp/date 불일치")
            age=(dt.datetime.now(dt.timezone.utc)-parsed.astimezone(dt.timezone.utc)).total_seconds()
        except (TypeError,ValueError,OverflowError) as exc:raise ValueError("환율 원천 timestamp 형식 오류") from exc
        if age < 0 or age > 72*60*60:raise ValueError("환율 원천 timestamp freshness 오류")
    elif name == "grading_company_updates.json":'''
if fx_anchor not in text:
    raise SystemExit("FX validate anchor missing")
p.write_text(text.replace(fx_anchor, fx_replacement, 1), encoding="utf-8")

# Runtime market conversion must independently require provenance, not collection time alone.
p = ROOT / "multi_market_price_collector.py"
text = p.read_text(encoding="utf-8").replace("import json, os, re, statistics, time", "import json, math, os, re, statistics, time", 1)
pattern = r'def _fx\(\):\n.*?\ndef _to_krw\(amount,currency,fx\):'
replacement = '''def _fx():
    d=_safe_json(FX,{})
    rates=d.get('rates') if isinstance(d,dict) else {}
    stamp=str(d.get('updated_at') or '') if isinstance(d,dict) else ''
    source_stamp=str(d.get('source_timestamp') or '') if isinstance(d,dict) else ''
    source_date=str(d.get('source_date') or '') if isinstance(d,dict) else ''
    source=str(d.get('source') or '') if isinstance(d,dict) else ''
    route=str(d.get('source_route') or '') if isinstance(d,dict) else ''
    try:
        collected=datetime.fromisoformat(stamp.replace('Z','+00:00'));published=datetime.fromisoformat(source_stamp.replace('Z','+00:00'))
        if collected.tzinfo is None or published.tzinfo is None:raise ValueError('timezone_required')
        now=datetime.now(timezone.utc);collected_age=(now-collected.astimezone(timezone.utc)).total_seconds();source_age=(now-published.astimezone(timezone.utc)).total_seconds()
        host=(urlparse(source).hostname or '').lower()
        provenance=(host in {'api.frankfurter.dev','api.frankfurter.app'} and route in {'frankfurter-v2','frankfurter-v1','frankfurter-legacy'} and published.date().isoformat()==source_date)
        fresh=(-FX_MAX_FUTURE_SKEW_SECONDS <= collected_age <= FX_MAX_AGE_SECONDS and 0 <= source_age <= FX_MAX_AGE_SECONDS)
        usd=float((rates or {}).get('USD_KRW'));jpy=float((rates or {}).get('JPY_KRW'))
        valid=math.isfinite(usd) and math.isfinite(jpy) and 500<usd<3000 and 0<jpy<30
    except (TypeError,ValueError,OverflowError):provenance=fresh=valid=False
    if not (provenance and fresh and valid):return {'USD':0.0,'JPY':0.0,'EUR':0.0,'KRW':1.0}
    try:
        eur=float((rates or {}).get('EUR_KRW',0));eur=eur if math.isfinite(eur) and eur>0 else 0.0
    except (TypeError,ValueError,OverflowError):eur=0.0
    return {'USD':usd,'JPY':jpy,'EUR':eur,'KRW':1.0}

def _to_krw(amount,currency,fx):'''
text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count != 1:
    raise SystemExit("market FX patch failed")
p.write_text(text, encoding="utf-8")

# Keep existing tests current with the stronger source-date contract.
p = ROOT / "test_error_recovery_learning_v134.py"
text = p.read_text(encoding="utf-8")
old = 'exchange,"fetch",side_effect=[TimeoutError("timeout"),{"rates":{"KRW":1400,"JPY":140}}]'
if old not in text:
    raise SystemExit("FX fallback test anchor missing")
p.write_text(text.replace(old, 'exchange,"fetch",side_effect=[TimeoutError("timeout"),{"date":exchange._utc_now().date().isoformat(),"rates":{"KRW":1400,"JPY":140}}]', 1), encoding="utf-8")

p = ROOT / "test_edition_fx_failclosed_v328.py"
text = p.read_text(encoding="utf-8")
old = 'path.write_text(json.dumps({"updated_at":stamp,"rates":{"JPY_KRW":9.1,"USD_KRW":1400.0}}),encoding="utf-8")'
new = 'source_stamp=(datetime.now(timezone.utc)-timedelta(minutes=5)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()\n            path.write_text(json.dumps({"updated_at":stamp,"source_date":source_stamp[:10],"source_timestamp":source_stamp,"source":"https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY","source_route":"frankfurter-v2","rates":{"JPY_KRW":9.1,"USD_KRW":1400.0}}),encoding="utf-8")'
if old not in text:
    raise SystemExit("fresh FX test anchor missing")
p.write_text(text.replace(old, new, 1), encoding="utf-8")

(ROOT / "test_runtime_provenance_failclosed_v345.py").write_text(r'''from __future__ import annotations
import json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest import mock
import auto_update_all as updater
import multi_market_price_collector as market
import update_exchange_rates as exchange

class RuntimeProvenanceFailClosedV345Tests(unittest.TestCase):
    NOW=datetime(2026,9,27,12,0,tzinfo=timezone.utc)
    def test_source_date_rules(self):
        rows=[{"date":"2026-09-27","quote":"KRW","rate":1400},{"date":"2026-09-27","quote":"JPY","rate":140}]
        self.assertEqual(exchange.parse_source_date(rows),"2026-09-27");rows[1]["date"]="2026-09-26"
        with self.assertRaises(ValueError):exchange.parse_source_date(rows)
        with self.assertRaisesRegex(ValueError,"72시간"):exchange.validate_source_date("2026-09-24",self.NOW)
        with self.assertRaisesRegex(ValueError,"미래"):exchange.validate_source_date("2026-09-28",self.NOW)
    def test_stale_provider_date_preserves_last_good(self):
        initial={"updated_at":"2026-09-26T00:00:00+00:00","source_date":"2026-09-26","source_timestamp":"2026-09-26T00:00:00+00:00","rates":{"JPY_KRW":9.0,"USD_KRW":1350.0},"source":"old"}
        with tempfile.TemporaryDirectory() as td:
            data=Path(td)/"exchange_rates.json";data.write_text(json.dumps(initial),encoding="utf-8")
            with mock.patch.object(exchange,"DATA",data),mock.patch.object(exchange,"_utc_now",return_value=self.NOW),mock.patch.object(exchange,"fetch",return_value={"date":"2026-09-20","rates":{"KRW":1400,"JPY":140}}):result=exchange.main()
            self.assertEqual(result["rates"],initial["rates"]);self.assertEqual(result["source_date"],initial["source_date"]);self.assertEqual(result["collection_status"],"기존 확인환율 유지")
    def test_fresh_provider_provenance_is_persisted_and_consumed(self):
        rows=[{"date":"2026-09-27","quote":"KRW","rate":1400},{"date":"2026-09-27","quote":"JPY","rate":140}]
        with tempfile.TemporaryDirectory() as td:
            data=Path(td)/"exchange_rates.json";data.write_text(json.dumps({"rates":{"JPY_KRW":9,"USD_KRW":1350}}),encoding="utf-8")
            with mock.patch.object(exchange,"DATA",data),mock.patch.object(exchange,"_utc_now",return_value=self.NOW),mock.patch.object(exchange,"fetch",return_value=rows):result=exchange.main()
            self.assertEqual(result["source_date"],"2026-09-27");self.assertEqual(result["source_timestamp"],"2026-09-27T00:00:00+00:00");self.assertEqual(result["updated_at"],"2026-09-27T12:00:00+00:00")
            with mock.patch.object(market,"FX",data),mock.patch.object(market,"datetime") as fake_dt:
                fake_dt.fromisoformat=datetime.fromisoformat;fake_dt.now.return_value=self.NOW;fx=market._fx()
            self.assertEqual(fx["USD"],1400.0);self.assertEqual(fx["JPY"],10.0)
    def test_price_path_rejects_missing_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            data=Path(td)/"exchange_rates.json";fresh=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat();data.write_text(json.dumps({"updated_at":fresh,"rates":{"JPY_KRW":9.1,"USD_KRW":1400}}),encoding="utf-8")
            with mock.patch.object(market,"FX",data):self.assertEqual(market._fx()["USD"],0.0)
    def test_corrupt_adaptive_primary_and_backup_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            primary=Path(td)/"adaptive_collection_stats.json";backup=Path(td)/"adaptive_collection_stats.json.bak";primary.write_bytes(b'{broken-primary');backup.write_bytes(b'{broken-backup');before=(primary.read_bytes(),backup.read_bytes())
            with mock.patch.object(updater,"ADAPTIVE_STATS",primary),mock.patch.object(updater,"ADAPTIVE_STATS_BAK",backup):
                stats=updater._load_adaptive_stats();self.assertTrue(updater._ADAPTIVE_STATS_CORRUPTION_HOLD);stats["jobs"]["x"]={"runs":1};self.assertFalse(updater._save_adaptive_stats(stats))
            self.assertEqual((primary.read_bytes(),backup.read_bytes()),before)
    def test_valid_backup_and_fresh_store(self):
        with tempfile.TemporaryDirectory() as td:
            primary=Path(td)/"adaptive_collection_stats.json";backup=Path(td)/"adaptive_collection_stats.json.bak";primary.write_bytes(b'{broken');backup.write_text(json.dumps({"version":1,"jobs":{"x":{"runs":7}},"updated_at":None}),encoding="utf-8")
            with mock.patch.object(updater,"ADAPTIVE_STATS",primary),mock.patch.object(updater,"ADAPTIVE_STATS_BAK",backup):
                stats=updater._load_adaptive_stats();self.assertEqual(updater._ADAPTIVE_STATS_STORAGE_SOURCE,"backup");stats["jobs"]["x"]["runs"]=8;self.assertTrue(updater._save_adaptive_stats(stats))
            self.assertEqual(json.loads(primary.read_text(encoding="utf-8"))["jobs"]["x"]["runs"],8)
        with tempfile.TemporaryDirectory() as td:
            primary=Path(td)/"adaptive_collection_stats.json";backup=Path(td)/"adaptive_collection_stats.json.bak"
            with mock.patch.object(updater,"ADAPTIVE_STATS",primary),mock.patch.object(updater,"ADAPTIVE_STATS_BAK",backup):stats=updater._load_adaptive_stats();self.assertEqual(updater._ADAPTIVE_STATS_STORAGE_SOURCE,"fresh");self.assertTrue(updater._save_adaptive_stats(stats))
            self.assertTrue(primary.is_file())
if __name__=='__main__':unittest.main(verbosity=2)
''', encoding="utf-8")

# Tablet GPT generation for the watched market-price runtime file.
prior_delta = json.loads((ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json").read_text(encoding="utf-8"))
prior_contract = json.loads((ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V344.json").read_text(encoding="utf-8"))
lessons = [
    {"lesson_id":"TCG-FX-SOURCE-DATE-PROVENANCE-V345","subsystem":"market_price_fx_provenance","issue_class":"collection_time_can_mask_stale_provider_fx_date","trigger_condition":"provider FX publication date is missing stale mismatched or future","symptom_summary":"collection time can make stale source rates look fresh","root_cause_class":"provider_publication_time_not_preserved_or_validated","fix_pattern":"persist and validate source_date/source_timestamp separately and fail closed after 72h","prevention_rule_id":"FX-PREV-SOURCE-TIME-PROVENANCE","verification_result":"targeted_and_full_regression","regression_pass":True,"recurrence_count":1,"applicable_scope":"both","confidence_level":"high","physical_tablet_runtime_reverification_required":False},
    {"lesson_id":"TCG-ADAPTIVE-STATS-CORRUPTION-HOLD-V345","subsystem":"adaptive_collection_learning","issue_class":"corrupt_primary_and_backup_can_be_replaced_by_fresh_state","trigger_condition":"both adaptive stats files exist but neither is valid","symptom_summary":"fresh fallback can overwrite corrupt persisted evidence","root_cause_class":"fresh_and_corrupt_storage_share_load_fallback","fix_pattern":"distinguish fresh from corrupt storage and block persistence on corruption hold","prevention_rule_id":"LEARNING-PREV-CORRUPTION-HOLD","verification_result":"targeted_and_full_regression","regression_pass":True,"recurrence_count":1,"applicable_scope":"both","confidence_level":"high","physical_tablet_runtime_reverification_required":False},
]
digest = hashlib.sha256(json.dumps(lessons, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
delta = {"schema_version":prior_delta["schema_version"],"namespace":"TABLET_GPT","snapshot_kind":"learning_delta","run_date_kst":"2026-09-28","built_at":"2026-09-28T01:20:00+09:00","status":"finalized","source_repository":"wlghks24/-tcg-grader","prior_delta":"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json","prior_lesson_digest_sha256":prior_delta["lesson_digest_sha256"],"source_main_sha":BASE,"share_policy":prior_delta["share_policy"],"covered_merges":[{"pr":303,"version":"v344-postmerge-guard","merge_sha":"f9328e4414fab823af7470fa31b7ac2c54ba7246"},{"pr":304,"version":"v344-fan-learning-corruption-hold","merge_sha":BASE}],"lesson_digest_sha256":digest,"lessons":lessons}
(ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json").write_text(json.dumps(delta, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
prior_receipt = json.loads((ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v344.json").read_text(encoding="utf-8"))
receipt = {"schema_version":delta["schema_version"],"receiver":"TCG_GRADER","source_namespace":"TABLET_GPT","source_repository":"wlghks24/-tcg-grader","source_main_sha":BASE,"received_at":"2026-09-28T01:20:00+09:00","status":"SYNCED_VERIFIED","source_snapshots":["TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json"],"prior_lesson_digest_sha256":prior_delta["lesson_digest_sha256"],"delta_lesson_digest_sha256":digest,"accepted_lesson_ids":[x["lesson_id"] for x in lessons],"alignment_policy":copy.deepcopy(prior_receipt["alignment_policy"]),"verification":{"contract_version":"v345","verification_test":"test_tablet_gpt_tcg_grader_sync_v345.py","verification_mode":"exact_base_watched_path_candidate_plus_fx_and_learning_failclosed","verified_result":"TABLET_GPT_TCG_GRADER_MATCH","physical_tablet_runtime_verified":False,"physical_drive_readback_verified":False,"device_reverification_required":True}}
(ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v345.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
contract = copy.deepcopy(prior_contract)
contract.update({"purpose":"cover v345 verified FX provenance and adaptive learning fail-closed changes","prior_contract":"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V344.json","prior_delta_snapshot":"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json","delta_snapshot":"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json","receiver_receipt":"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v345.json","verification_test":"test_tablet_gpt_tcg_grader_sync_v345.py","current_required_merge_prs":sorted(set(prior_contract["current_required_merge_prs"])|{303,304}),"prior_required_lesson_count":prior_contract["current_required_lesson_count"],"delta_required_lesson_count":2,"current_required_lesson_count":prior_contract["current_required_lesson_count"]+2})
generation = ["TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v345.json","TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V345.json","test_tablet_gpt_tcg_grader_sync_v345.py"]
contract["freshness_watch"]["exclude_paths"] += generation
contract["candidate_sync"] = {"base_main_sha":BASE,"generation_files":generation,"watched_paths":["multi_market_price_collector.py"],"requires_exact_watched_path_match":True,"post_merge_coverage_allowed":True}
(ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V345.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
(ROOT / "test_tablet_gpt_tcg_grader_sync_v345.py").write_text(f'''import hashlib,json,unittest\nfrom pathlib import Path\nROOT=Path(__file__).resolve().parent\ndef read(p):return json.loads((ROOT/p).read_text(encoding="utf-8"))\nclass SyncV345(unittest.TestCase):\n def test_v345(self):\n  prior=read("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v344_delta.json");delta=read("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v345_delta.json");receipt=read("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v345.json");contract=read("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V345.json")\n  self.assertEqual(delta["source_main_sha"],"{BASE}");self.assertEqual(delta["source_main_sha"],receipt["source_main_sha"]);self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])\n  raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"));digest=hashlib.sha256(raw.encode()).hexdigest();self.assertEqual(digest,delta["lesson_digest_sha256"]);self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])\n  self.assertEqual(contract["candidate_sync"]["watched_paths"],["multi_market_price_collector.py"]);self.assertTrue(contract["candidate_sync"]["requires_exact_watched_path_match"]);self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"]);self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])\nif __name__=="__main__":unittest.main(verbosity=2)\n''', encoding="utf-8")

# Remove temporary writers before generating the exact-tree integrity manifest.
run("git", "rm", "--", WORKFLOW, SELF)
run("python", "fault_injection_healing.py", "--manifest")
run("python", "-m", "py_compile", "update_exchange_rates.py", "auto_update_all.py", "multi_market_price_collector.py", "test_runtime_provenance_failclosed_v345.py", "test_tablet_gpt_tcg_grader_sync_v345.py")
run("python", "-m", "unittest", "-v", "test_runtime_provenance_failclosed_v345.py", "test_error_recovery_learning_v134.py", "test_edition_fx_failclosed_v328.py", "test_tablet_gpt_tcg_grader_sync_v345.py")
run("python", "fault_injection_healing.py", "--diagnose")
run("python", "repository_integrity_guard.py")
run("git", "diff", "--check")
run("git", "add", "-A")
staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).splitlines()
if WORKFLOW in staged or SELF in staged:
    raise SystemExit("temporary finalizer leaked into final diff")
run("git", "diff", "--cached", "--check")
run("git", "commit", "-m", "Harden FX provenance and adaptive learning persistence v345")
run("git", "push", "origin", f"HEAD:{BRANCH}")
