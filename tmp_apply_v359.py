from pathlib import Path
import hashlib
import json


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one replacement, got {count}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# Market data: quarantine the historical KR<-international OP14-009 misjoin.
replace_once(
    'update_market_prices.py',
    "    return match.group(1) if match else None\ndef set_price(db,key,display,kind,market,transactions,source):\n",
    """    return match.group(1) if match else None

def quarantine_legacy_packmagik_misjoin(db):
    \"\"\"Remove only the known legacy KR key polluted by international/JP OP14-009 evidence.\"\"\"
    entries=db.get('entries') if isinstance(db,dict) else None
    if not isinstance(entries,dict): return False
    key='KR|창해의 칠걸|HIT'
    row=entries.get(key)
    if not isinstance(row,dict): return False
    source=str(row.get('source') or '').lower()
    evidence=' '.join(str(row.get(field) or '') for field in ('kind','transactions','card_number','language')).lower()
    if 'packmagik.com/' not in source or not ('op14-009' in evidence or '국제판' in evidence or '일본판' in evidence):
        return False
    quarantine=db.setdefault('invalid_entries_quarantine',{})
    quarantine[key]={
        'value':row,
        'reason':'legacy edition mismatch: international/JP OP14-009 evidence must not populate a KR market key',
    }
    entries.pop(key,None)
    return True


def market_error_is_warning(text:str)->bool:
    \"\"\"Optional provider degradation stays observable without invalidating other verified market rows.\"\"\"
    text=str(text)
    kream_transient=(
        re.search(r'^KREAM ',text,re.I) is not None and (
            re.search(r'HTTPError: status (?:403|429|5(?:00|02|03|04))\\b',text,re.I) is not None
            or re.search(r'(?:URLError|TimeoutError|timed out|temporary failure|connection reset|name resolution|DNS)',text,re.I) is not None
        )
    )
    packmagik_optional=(
        text.startswith('Pack Magik OP14-009 JP:') and (
            '가격 패턴 0건' in text
            or re.search(r'HTTPError: status (?:403|429|5(?:00|02|03|04))\\b',text,re.I) is not None
            or re.search(r'(?:URLError|TimeoutError|timed out|temporary failure|connection reset|name resolution|DNS)',text,re.I) is not None
        )
    )
    return bool(kream_transient or packmagik_optional)


def set_price(db,key,display,kind,market,transactions,source):
"""
)
replace_once(
    'update_market_prices.py',
    "    db=json.loads(safe_read_text(DATA)); errors=[]; initial_repairs=_sanitize_entries(db)\n    keep_verified_seeds(db)\n",
    "    db=json.loads(safe_read_text(DATA)); errors=[]; initial_repairs=_sanitize_entries(db)\n    if quarantine_legacy_packmagik_misjoin(db): initial_repairs+=1\n    keep_verified_seeds(db)\n"
)
old_classification = """    for item in errors:
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
"""
new_classification = """    for item in errors:
        text=str(item)
        if market_error_is_warning(text):
            transient_market_errors.append(text)
        else:
            hard_market_errors.append(text)
"""
replace_once('update_market_prices.py', old_classification, new_classification)
replace_once(
    'update_market_prices.py',
    "    db['collection_note']='KREAM 원출처 403/429/5xx/네트워크 지연 시 직전 검증자료 유지 · 다음 업데이트에서 재확인' if transient_market_errors else ''\n",
    "    db['collection_note']='선택적 가격 출처의 파싱/네트워크 실패는 해당 출처만 경고로 격리하며 검증된 다른 시장행과 판본을 결합하지 않음' if transient_market_errors else ''\n"
)

# Grading watcher: a bounded official bootstrap can seed last-good only.
replace_once(
    'grading_company_watch.py',
    'OUT = ROOT / "grading_company_updates.json"\nUA = "Mozilla/5.0 TCG-Grader-GradingCompanyWatch/1.0"\n',
    'OUT = ROOT / "grading_company_updates.json"\nBOOTSTRAP = ROOT / "grading_company_bootstrap.json"\nBOOTSTRAP_MAX_AGE_SECONDS = 30 * 24 * 3600\nUA = "Mozilla/5.0 TCG-Grader-GradingCompanyWatch/1.0"\n'
)
load_anchor = """def _load_previous(path: Path = OUT) -> dict:
    try:
        data = json.loads(safe_read_text(path, max_bytes=8_000_000))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return {}


"""
load_new = load_anchor + """def _load_bootstrap_sources(checked_at: str, path: Path = BOOTSTRAP) -> dict[str, dict]:
    try:
        data = json.loads(safe_read_text(path, max_bytes=2_000_000))
        now = datetime.fromisoformat(str(checked_at).replace('Z', '+00:00')).astimezone(timezone.utc)
        observed = datetime.fromisoformat(str(data.get('observed_at') or '').replace('Z', '+00:00')).astimezone(timezone.utc)
        expires = datetime.fromisoformat(str(data.get('expires_at') or '').replace('Z', '+00:00')).astimezone(timezone.utc)
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return {}
    age = (now - observed).total_seconds()
    if data.get('schema_version') != 1 or age < -300 or age > BOOTSTRAP_MAX_AGE_SECONDS or now > expires:
        return {}
    rows = data.get('sources')
    return rows if isinstance(rows, dict) else {}


def _valid_bootstrap_source(company: str, spec: dict, source_id: str, row: object) -> bool:
    if not isinstance(row, dict):
        return False
    return bool(
        row.get('company') == company
        and row.get('source_id') == source_id
        and row.get('kind') == spec.get('kind')
        and row.get('market') == spec.get('market')
        and row.get('currency') == spec.get('currency')
        and row.get('url') == spec.get('url')
        and row.get('verified_official_source') is True
        and row.get('parser_version') == PARSER_VERSION
        and row.get('signal_fingerprint')
        and isinstance(row.get('services'), list)
        and bool(row.get('services'))
        and row.get('last_verified_at')
    )


"""
replace_once('grading_company_watch.py', load_anchor, load_new)
replace_once(
    'grading_company_watch.py',
    "    prev_sources = previous.get(\"sources\", {}) if isinstance(previous.get(\"sources\"), dict) else {}\n    sources: dict[str, dict] = {}\n",
    "    prev_sources = previous.get(\"sources\", {}) if isinstance(previous.get(\"sources\"), dict) else {}\n    bootstrap_sources = _load_bootstrap_sources(checked_at)\n    sources: dict[str, dict] = {}\n"
)
replace_once(
    'grading_company_watch.py',
    '                    "services": services, "announcements": found, "verified_official_source": True,\n                    "parser_version": PARSER_VERSION,\n                }\n',
    '                    "services": services, "announcements": found, "verified_official_source": True,\n                    "parser_version": PARSER_VERSION, "last_verified_at": checked_at,\n                }\n'
)
exception_anchor = """            except Exception as exc:
                old_verified = bool(
                    old.get("verified_official_source") is True
                    and old.get("signal_fingerprint")
                )
                retained = dict(old) if old else {
"""
exception_new = """            except Exception as exc:
                old_verified = bool(
                    old.get("verified_official_source") is True
                    and old.get("signal_fingerprint")
                )
                bootstrap_row = bootstrap_sources.get(source_id, {})
                if not old_verified and _valid_bootstrap_source(company, spec, source_id, bootstrap_row):
                    old = dict(bootstrap_row)
                    old_verified = True
                retained = dict(old) if old else {
"""
replace_once('grading_company_watch.py', exception_anchor, exception_new)
replace_once(
    'grading_company_watch.py',
    '                sources[source_id] = retained\n                if old_verified and retained.get("services"):\n',
    '                if old_verified:\n                    retained["retained_last_good"] = True\n                sources[source_id] = retained\n                if old_verified and retained.get("services"):\n'
)

# Verification gate: blocked provider + fresh verified retained last-good is medium, never healthy.
replace_once(
    'collection_verification_gate.py',
    'GRADING_MIN_OFFICIAL_SOURCES = 10\n',
    'GRADING_MIN_OFFICIAL_SOURCES = 10\nGRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS = 30 * 24 * 3600\n'
)
marker = 'def _audit_grading_companies(root: Path, now: dt.datetime, findings: list[dict[str, Any]]) -> dict[str, int]:\n'
helper = """def _grading_blocked_last_good_ok(company: str, sources: dict[str, Any], now: dt.datetime) -> bool:
    rows=[]
    for row in sources.values():
        if not isinstance(row, dict) or str(row.get('company') or '').upper() != company:
            continue
        raw_status=str(row.get('status') or '').lower()
        status='healthy' if raw_status in {'ok','healthy'} else raw_status
        if status == 'healthy' or status != 'degraded':
            return False
        error_text=str(row.get('error') or row.get('last_error') or '')
        if HTTP_BLOCK_RE.search(error_text) is None:
            return False
        rows.append(row)
    if not rows:
        return False
    for row in rows:
        if row.get('verified_official_source') is not True or row.get('retained_last_good') is not True:
            continue
        if not (row.get('services') or row.get('announcements')):
            continue
        verified_at=_parse_time(row.get('last_verified_at'))
        if verified_at is None:
            continue
        age=(now-verified_at).total_seconds()
        if -300 <= age <= GRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS:
            return True
    return False


"""
replace_once('collection_verification_gate.py', marker, helper + marker)
gate_path=Path('collection_verification_gate.py')
gate_text=gate_path.read_text(encoding='utf-8')
start=gate_text.index('    no_healthy = EXPECTED_GRADING_COMPANIES - healthy_companies\n')
end=gate_text.index('\n    changes = db.get("recent_changes")', start)
new_block="""    no_healthy = EXPECTED_GRADING_COMPANIES - healthy_companies
    blocked_with_last_good = {
        company for company in no_healthy
        if _grading_blocked_last_good_ok(company, sources, now)
    }
    hard_no_healthy = no_healthy - blocked_with_last_good
    if hard_no_healthy:
        ordered_companies = sorted(hard_no_healthy)
        samples_by_company = {
            company: degraded_errors_by_company.get(company, [])[:5]
            for company in ordered_companies
        }
        counts_by_company = {
            company: degraded_counts_by_company.get(company, 0)
            for company in ordered_companies
        }
        no_healthy_samples: list[dict[str, str]] = []
        for index in range(5):
            for company in ordered_companies:
                company_samples = samples_by_company[company]
                if index < len(company_samples):
                    no_healthy_samples.append(company_samples[index])
        findings.append({
            "severity": "high",
            "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",
            "target": path.name,
            "companies": ordered_companies,
            "degraded_samples": no_healthy_samples[:20],
            "degraded_samples_by_company": samples_by_company,
            "degraded_sample_counts_by_company": counts_by_company,
        })
    if blocked_with_last_good:
        findings.append({
            "severity": "medium",
            "code": "GRADING_COMPANY_BLOCKED_USING_FRESH_LAST_GOOD",
            "target": path.name,
            "companies": sorted(blocked_with_last_good),
            "max_last_good_age_seconds": GRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS,
            "bypass_attempted": False,
        })
    elif degraded and not hard_no_healthy:
        findings.append({"severity": "medium", "code": "DEGRADED_GRADING_SOURCE", "target": path.name,
                         "count": degraded, "samples": degraded_errors})
"""
gate_path.write_text(gate_text[:start] + new_block + gate_text[end:], encoding='utf-8')
replace_once(
    'collection_verification_gate.py',
    '    updated = db.get("updated_at") if isinstance(db, dict) else None\n    if updated:\n        _fresh("market_prices.json", updated, now, 24 * 3600, findings)\n    return {\n',
    '    warnings = db.get("collection_warnings") if isinstance(db, dict) else []\n    if isinstance(warnings, list) and warnings:\n        findings.append({"severity": "medium", "code": "DEGRADED_MARKET_SOURCE",\n                         "target": "market_prices.json", "count": len(warnings),\n                         "samples": [str(x)[:300] for x in warnings[:5]]})\n    updated = db.get("updated_at") if isinstance(db, dict) else None\n    if updated:\n        _fresh("market_prices.json", updated, now, 24 * 3600, findings)\n    return {\n'
)
replace_once(
    'collection_verification_gate.py',
    '        "invalid_graded_price_evidence": invalid_grade_evidence,\n    }\n',
    '        "invalid_graded_price_evidence": invalid_grade_evidence,\n        "market_source_warnings": len(warnings) if isinstance(warnings, list) else 0,\n    }\n'
)

# Current official PSA US grading-page bootstrap. It can only become retained/degraded last-good.
observed_at='2026-09-29T08:11:00+00:00'
expires_at='2026-10-29T08:11:00+00:00'
source='https://www.psacard.com/services/tradingcardgrading'
services=[
    {'name':'Value Bulk','observed_label':'Value Bulk','currency':'USD','availability':'paused','source':source,'verified_official_source':True,'parser_version':2,'max_declared_or_insured_value':500},
    {'name':'Value','observed_label':'Value','currency':'USD','availability':'paused','source':source,'verified_official_source':True,'parser_version':2,'max_declared_or_insured_value':500},
    {'name':'Value Plus','observed_label':'Value Plus','currency':'USD','availability':'paused','source':source,'verified_official_source':True,'parser_version':2,'max_declared_or_insured_value':500},
    {'name':'Value Max','observed_label':'Value Max','currency':'USD','availability':'paused','source':source,'verified_official_source':True,'parser_version':2,'max_declared_or_insured_value':1000},
    {'name':'Regular','observed_label':'Regular','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':79.99,'max_declared_or_insured_value':1500,'turnaround_business_days_range':[40,50]},
    {'name':'Express','observed_label':'Express','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':149.0,'max_declared_or_insured_value':2500,'turnaround_business_days_range':[20,30]},
    {'name':'Super Express','observed_label':'Super Express','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':349.0,'max_declared_or_insured_value':5000,'turnaround_business_days_range':[10,15]},
    {'name':'Walk-Through','observed_label':'Walk-Through','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':599.0,'max_declared_or_insured_value':10000,'turnaround_business_days_range':[7,10]},
    {'name':'Premium 1','observed_label':'Premium 1','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':999.0,'max_declared_or_insured_value':25000,'turnaround_business_days_range':[5,7]},
    {'name':'Premium 2','observed_label':'Premium 2','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':1999.0,'max_declared_or_insured_value':50000,'turnaround_business_days_range':[5,7]},
    {'name':'Premium 3','observed_label':'Premium 3','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':2999.0,'max_declared_or_insured_value':100000,'turnaround_business_days_range':[5,7]},
    {'name':'Premium 5','observed_label':'Premium 5','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':4999.0,'max_declared_or_insured_value':250000,'turnaround_business_days_range':[5,7]},
    {'name':'Premium 10','observed_label':'Premium 10','currency':'USD','availability':'open','source':source,'verified_official_source':True,'parser_version':2,'fee':9999.0,'max_declared_or_insured_value':250001,'turnaround_business_days_range':[5,7]},
]
fingerprint=hashlib.sha256(json.dumps(services,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
bootstrap={
    'schema_version':1,
    'observed_at':observed_at,
    'expires_at':expires_at,
    'policy':{
        'official_source_only':True,
        'runtime_block_does_not_become_healthy':True,
        'max_age_seconds':30*24*3600,
        'bypass_403_429':False,
    },
    'sources':{
        'psa-us-pricing':{
            'company':'PSA','source_id':'psa-us-pricing','kind':'pricing','market':'US','currency':'USD',
            'url':source,'status':'bootstrap_verified','services':services,'announcements':[],
            'signal_fingerprint':fingerprint,'verified_official_source':True,'parser_version':2,
            'last_verified_at':observed_at,'bootstrap_source':True,
        }
    }
}
Path('grading_company_bootstrap.json').write_text(json.dumps(bootstrap,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

Path('test_drive_package_blockers_v359.py').write_text(r'''import datetime as dt
import urllib.error
import unittest

import collection_verification_gate as gate
import grading_company_watch as grading
import update_market_prices as market


class DrivePackageBlockersV359Tests(unittest.TestCase):
    def test_legacy_packmagik_kr_row_is_quarantined(self):
        key='KR|창해의 칠걸|HIT'
        db={'entries':{key:{'source':'https://www.packmagik.com/cards/op-op14-op14-009-p1','kind':'OP14-009 패러렐 국제판 참고시세','transactions':'한국판 실거래 아님 · 국제판 시장가 참고'}}}
        self.assertTrue(market.quarantine_legacy_packmagik_misjoin(db))
        self.assertNotIn(key,db['entries'])
        self.assertIn(key,db['invalid_entries_quarantine'])

    def test_packmagik_parser_miss_is_optional_warning_but_arbitrary_error_is_hard(self):
        self.assertTrue(market.market_error_is_warning('Pack Magik OP14-009 JP: 가격 패턴 0건'))
        self.assertTrue(market.market_error_is_warning('Pack Magik OP14-009 JP: HTTPError: status 403'))
        self.assertFalse(market.market_error_is_warning('BOX/HIT 다중마켓 자동발견: ValueError'))

    def test_bootstrap_is_bounded_official_and_exact_source(self):
        rows=grading._load_bootstrap_sources('2026-09-29T08:12:00+00:00')
        row=rows['psa-us-pricing']
        spec=grading.WATCH_SOURCES['PSA'][0]
        self.assertTrue(grading._valid_bootstrap_source('PSA',spec,'psa-us-pricing',row))
        self.assertEqual(row['url'],'https://www.psacard.com/services/tradingcardgrading')
        self.assertTrue(row['services'])
        self.assertEqual({},grading._load_bootstrap_sources('2026-11-01T00:00:00+00:00'))

    def test_psa_403_retains_bootstrap_as_degraded_not_healthy(self):
        def blocked(url):
            raise urllib.error.HTTPError(url,403,'blocked',None,None)
        data=grading.collect(previous={},fetcher=blocked)
        row=data['sources']['psa-us-pricing']
        self.assertEqual('degraded',row['status'])
        self.assertTrue(row['verified_official_source'])
        self.assertTrue(row['retained_last_good'])
        self.assertTrue(row['services'])
        self.assertIn('403',row['last_error'])

    def test_gate_allows_only_fresh_verified_blocked_last_good(self):
        now=dt.datetime(2026,9,29,8,12,tzinfo=dt.timezone.utc)
        base={
            'company':'PSA','status':'degraded','last_error':'HTTPError: status 403',
            'verified_official_source':False,'services':[],'announcements':[]
        }
        sources={
            'psa-us-pricing':dict(base,verified_official_source=True,retained_last_good=True,
                                  last_verified_at='2026-09-29T08:11:00+00:00',services=[{'name':'Regular'}]),
            'psa-jp-pricing':dict(base),
            'psa-jp-news':dict(base),
        }
        self.assertTrue(gate._grading_blocked_last_good_ok('PSA',sources,now))
        stale={k:dict(v) for k,v in sources.items()}
        stale['psa-us-pricing']['last_verified_at']='2026-08-01T00:00:00+00:00'
        self.assertFalse(gate._grading_blocked_last_good_ok('PSA',stale,now))
        parser_failure={k:dict(v) for k,v in sources.items()}
        parser_failure['psa-jp-pricing']['last_error']='ValueError: pricing parser yielded zero verified services'
        self.assertFalse(gate._grading_blocked_last_good_ok('PSA',parser_failure,now))


if __name__ == '__main__':
    unittest.main()
''',encoding='utf-8')
