from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OBSERVED_AT = "2026-09-29T08:11:00+00:00"
EXPIRES_AT = "2026-10-06T08:11:00+00:00"
PSA_URL = "https://www.psacard.com/services/tradingcardgrading"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def replace_once(name: str, old: str, new: str) -> None:
    text = read(name)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{name}: expected one normalization target, got {count}: {old!r}")
    write(name, text.replace(old, new, 1))


# The previous v359 attempt already added the edition-isolation and blocked-last-good
# mechanisms. Normalize those mechanisms instead of applying the same patch twice.
market = read("update_market_prices.py")
for marker in (
    "def quarantine_legacy_packmagik_misjoin(db):",
    "def market_error_is_warning(text:str)->bool:",
    "if quarantine_legacy_packmagik_misjoin(db): initial_repairs+=1",
):
    if marker not in market:
        raise SystemExit(f"update_market_prices.py missing required v359 marker: {marker}")

watch = read("grading_company_watch.py")
for marker in ("BOOTSTRAP = ROOT / \"grading_company_bootstrap.json\"", "def _load_bootstrap_sources(", "def _valid_bootstrap_source("):
    if marker not in watch:
        raise SystemExit(f"grading_company_watch.py missing required bootstrap marker: {marker}")
if "BOOTSTRAP_MAX_AGE_SECONDS = 30 * 24 * 3600" in watch:
    replace_once("grading_company_watch.py", "BOOTSTRAP_MAX_AGE_SECONDS = 30 * 24 * 3600", "BOOTSTRAP_MAX_AGE_SECONDS = 7 * 24 * 3600")
elif "BOOTSTRAP_MAX_AGE_SECONDS = 7 * 24 * 3600" not in watch:
    raise SystemExit("unexpected grading bootstrap TTL")

gate = read("collection_verification_gate.py")
if "def _grading_blocked_last_good_ok(" not in gate:
    raise SystemExit("collection gate missing bounded blocked-last-good helper")
if "GRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS = 30 * 24 * 3600" in gate:
    replace_once(
        "collection_verification_gate.py",
        "GRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS = 30 * 24 * 3600",
        "GRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS = 7 * 24 * 3600",
    )
elif "GRADING_BLOCKED_LAST_GOOD_MAX_AGE_SECONDS = 7 * 24 * 3600" not in gate:
    raise SystemExit("unexpected grading blocked-last-good TTL")

gate = read("collection_verification_gate.py")
if 'HTTP_BLOCK_RE = re.compile(r"HTTPError: status (403|429)\\b", re.I)' in gate:
    replace_once(
        "collection_verification_gate.py",
        'HTTP_BLOCK_RE = re.compile(r"HTTPError: status (403|429)\\b", re.I)',
        'HTTP_BLOCK_RE = re.compile(r"HTTPError: status (401|403|429|451)\\b", re.I)',
    )
elif 'HTTP_BLOCK_RE = re.compile(r"HTTPError: status (401|403|429|451)\\b", re.I)' not in gate:
    raise SystemExit("unexpected blocked HTTP classifier")

services = [
    {"name":"Value Bulk","observed_label":"Value Bulk","currency":"USD","availability":"paused","source":PSA_URL,"verified_official_source":True,"parser_version":2,"max_declared_or_insured_value":500.0},
    {"name":"Value","observed_label":"Value","currency":"USD","availability":"paused","source":PSA_URL,"verified_official_source":True,"parser_version":2,"max_declared_or_insured_value":500.0},
    {"name":"Standard","observed_label":"Standard","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":59.99,"turnaround_business_days":100,"turnaround_range_business_days":[90,100],"max_declared_or_insured_value":1000.0},
    {"name":"Priority","observed_label":"Priority","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":79.99,"turnaround_business_days":80,"turnaround_range_business_days":[70,80],"max_declared_or_insured_value":1500.0},
    {"name":"Express","observed_label":"Express","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":199.0,"turnaround_business_days":30,"turnaround_range_business_days":[20,30],"max_declared_or_insured_value":2500.0},
    {"name":"Super Express","observed_label":"Super Express","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":349.0,"turnaround_business_days":15,"turnaround_range_business_days":[10,15],"max_declared_or_insured_value":5000.0},
    {"name":"Premier","observed_label":"Premier","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":599.0,"turnaround_business_days":10,"turnaround_range_business_days":[7,10],"max_declared_or_insured_value":10000.0},
    {"name":"Premium 1","observed_label":"Premium 1","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":25000.0},
    {"name":"Premium 2","observed_label":"Premium 2","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":1999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":50000.0},
    {"name":"Premium 3","observed_label":"Premium 3","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":2999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":100000.0},
    {"name":"Premium 5","observed_label":"Premium 5","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee":4999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":250000.0},
    {"name":"Premium 10","observed_label":"Premium 10","currency":"USD","availability":"open","source":PSA_URL,"verified_official_source":True,"parser_version":2,"fee_floor":9999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"min_declared_or_insured_value":250001.0,"pricing_note":"starts at $9,999 for insured value $350,000 or less; higher values add $399 per $10,000 or fraction"},
]
bootstrap = {
    "schema_version": 1,
    "observed_at": OBSERVED_AT,
    "expires_at": EXPIRES_AT,
    "policy": {
        "official_source_only": True,
        "runtime_block_does_not_become_healthy": True,
        "max_age_seconds": 7 * 24 * 3600,
        "bypass_403_429": False,
    },
    "sources": {
        "psa-us-pricing": {
            "company":"PSA","source_id":"psa-us-pricing","kind":"pricing","market":"US","currency":"USD",
            "url":PSA_URL,"status":"bootstrap_verified","services":services,"announcements":[],
            "signal_fingerprint":"2c6b4145b4ea462ecf1bf2ae0143c64207f3e6471d71cb3c3673edf7678a6cf1",
            "verified_official_source":True,"parser_version":2,"last_verified_at":OBSERVED_AT,"bootstrap_source":True,
        }
    },
}
write("grading_company_bootstrap.json", json.dumps(bootstrap, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

write("test_drive_package_blockers_v359.py", r'''import datetime as dt
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

    def test_bootstrap_matches_current_official_values_and_expires_after_seven_days(self):
        rows=grading._load_bootstrap_sources('2026-10-06T08:11:00+00:00')
        row=rows['psa-us-pricing']
        spec=grading.WATCH_SOURCES['PSA'][0]
        self.assertTrue(grading._valid_bootstrap_source('PSA',spec,'psa-us-pricing',row))
        by_name={item['name']:item for item in row['services']}
        self.assertEqual(59.99,by_name['Standard']['fee'])
        self.assertEqual(79.99,by_name['Priority']['fee'])
        self.assertEqual(199.0,by_name['Express']['fee'])
        self.assertEqual(599.0,by_name['Premier']['fee'])
        self.assertEqual('paused',by_name['Value Bulk']['availability'])
        self.assertNotIn('fee',by_name['Value Bulk'])
        self.assertEqual({},grading._load_bootstrap_sources('2026-10-06T08:11:01+00:00'))

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
        self.assertNotIn('PSA',{c for c,v in data['companies'].items() if any(x.get('status')=='ok' for x in v['source_health'])})

    def test_gate_allows_only_fresh_verified_blocked_last_good(self):
        now=dt.datetime(2026,9,29,8,12,tzinfo=dt.timezone.utc)
        base={'company':'PSA','status':'degraded','last_error':'HTTPError: status 403','verified_official_source':False,'services':[],'announcements':[]}
        sources={
            'psa-us-pricing':dict(base,verified_official_source=True,retained_last_good=True,last_verified_at='2026-09-29T08:11:00+00:00',services=[{'name':'Standard'}]),
            'psa-jp-pricing':dict(base,last_error='HTTPError: status 451'),
            'psa-jp-news':dict(base,last_error='HTTPError: status 401'),
        }
        self.assertTrue(gate._grading_blocked_last_good_ok('PSA',sources,now))
        stale={k:dict(v) for k,v in sources.items()}
        stale['psa-us-pricing']['last_verified_at']='2026-09-22T08:11:00+00:00'
        self.assertFalse(gate._grading_blocked_last_good_ok('PSA',stale,now))
        parser_failure={k:dict(v) for k,v in sources.items()}
        parser_failure['psa-jp-pricing']['last_error']='ValueError: pricing parser yielded zero verified services'
        self.assertFalse(gate._grading_blocked_last_good_ok('PSA',parser_failure,now))


if __name__ == '__main__':
    unittest.main()
''')

print("v359 current-state normalization staged")
