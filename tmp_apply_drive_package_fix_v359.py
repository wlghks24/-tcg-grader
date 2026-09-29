from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one patch target, got {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Remove the historical KR <- international/JP OP14-009 misjoin and keep Pack Magik optional.
replace_once(
    "update_market_prices.py",
    """    for key,value in list(entries.items()):\n        valid_key=isinstance(key,str) and key.count('|')==2\n        valid_value=isinstance(value,dict) and bool(value.get('display'))\n        if valid_key and valid_value:\n            continue\n""",
    """    for key,value in list(entries.items()):\n        legacy_packmagik_kr=(\n            key=='KR|창해의 칠걸|HIT'\n            and isinstance(value,dict)\n            and (\n                'Pack Magik' in str(value.get('market') or '')\n                or 'packmagik.com' in str(value.get('source') or '').lower()\n                or str(value.get('card_number') or '').upper()=='OP14-009'\n            )\n        )\n        if legacy_packmagik_kr:\n            quarantine[str(key)]={'value':value,'reason':'edition conflict: international/JP OP14-009 evidence stored under KR key'}\n            entries.pop(key,None);repaired+=1\n            continue\n        valid_key=isinstance(key,str) and key.count('|')==2\n        valid_value=isinstance(value,dict) and bool(value.get('display'))\n        if valid_key and valid_value:\n            continue\n""",
)
replace_once(
    "update_market_prices.py",
    """        else: errors.append('Pack Magik OP14-009 JP: 가격 패턴 0건')\n    except NETWORK_ERRORS as e: errors.append('Pack Magik OP14-009 JP: '+diagnostic_exception(e))\n""",
    """        else: errors.append('OPTIONAL Pack Magik OP14-009 JP: 가격 패턴 0건 · 값 생성 안 함')\n    except NETWORK_ERRORS as e: errors.append('OPTIONAL Pack Magik OP14-009 JP: '+diagnostic_exception(e))\n""",
)
replace_once(
    "update_market_prices.py",
    """        if kream_transient:\n            transient_market_errors.append(text)\n        else:\n            hard_market_errors.append(text)\n""",
    """        packmagik_optional=text.startswith('OPTIONAL Pack Magik OP14-009 JP:')\n        if kream_transient or packmagik_optional:\n            transient_market_errors.append(text)\n        else:\n            hard_market_errors.append(text)\n""",
)

# 2) Seed a short-lived, official PSA last-good snapshot. Runtime fetch remains degraded on 403.
(ROOT / "grading_company_psa_last_good.py").write_text(r'''#!/usr/bin/env python3
"""Short-lived verified PSA bootstrap used only when PSA blocks automated fetches.

The source remains marked degraded/SOURCE_BLOCKED by the live watcher. This module
never turns a 403 into healthy data. It only provides a bounded last-good baseline
from the official PSA trading-card grading page verified on 2026-09-29. Consumers
must honor the seven-day expiry and provenance fields.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from copy import deepcopy
from typing import Any

SOURCE_ID = "psa-us-pricing"
SOURCE_URL = "https://www.psacard.com/services/tradingcardgrading"
OBSERVED_ON = "2026-09-29"
MAX_AGE_DAYS = 7
PARSER_VERSION = 2

# Official PSA page values observed 2026-09-29. Value tiers were shown as paused;
# they are intentionally omitted from fee facts instead of inventing a price.
SERVICES = [
    {"name":"Standard","observed_label":"Standard","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":59.99,"turnaround_business_days":100,"turnaround_range_business_days":[90,100],"max_declared_or_insured_value":1000.0},
    {"name":"Priority","observed_label":"Priority","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":79.99,"turnaround_business_days":80,"turnaround_range_business_days":[70,80],"max_declared_or_insured_value":1500.0},
    {"name":"Express","observed_label":"Express","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":199.0,"turnaround_business_days":30,"turnaround_range_business_days":[20,30],"max_declared_or_insured_value":2500.0},
    {"name":"Super Express","observed_label":"Super Express","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":349.0,"turnaround_business_days":15,"turnaround_range_business_days":[10,15],"max_declared_or_insured_value":5000.0},
    {"name":"Premier","observed_label":"Premier","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":599.0,"turnaround_business_days":10,"turnaround_range_business_days":[7,10],"max_declared_or_insured_value":10000.0},
    {"name":"Premium 1","observed_label":"Premium 1","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":25000.0},
    {"name":"Premium 2","observed_label":"Premium 2","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":1999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":50000.0},
    {"name":"Premium 3","observed_label":"Premium 3","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":2999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":100000.0},
    {"name":"Premium 5","observed_label":"Premium 5","currency":"USD","availability":"open","source":SOURCE_URL,"verified_official_source":True,"parser_version":PARSER_VERSION,"fee":4999.0,"turnaround_business_days":7,"turnaround_range_business_days":[5,7],"max_declared_or_insured_value":250000.0},
]


def _fingerprint() -> str:
    raw = json.dumps(SERVICES, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _observed_date() -> dt.date:
    return dt.date.fromisoformat(OBSERVED_ON)


def bootstrap_is_current(today: dt.date | None = None) -> bool:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    age = (today - _observed_date()).days
    return 0 <= age <= MAX_AGE_DAYS


def inject_psa_verified_last_good(previous: dict[str, Any], today: dt.date | None = None) -> dict[str, Any]:
    out = deepcopy(previous) if isinstance(previous, dict) else {}
    sources = out.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        out["sources"] = sources
    existing = sources.get(SOURCE_ID)
    if isinstance(existing, dict) and existing.get("verified_official_source") is True and existing.get("services"):
        return out
    if not bootstrap_is_current(today):
        return out
    sources[SOURCE_ID] = {
        "company":"PSA","source_id":SOURCE_ID,"kind":"pricing","market":"US","currency":"USD",
        "url":SOURCE_URL,"status":"degraded","services":deepcopy(SERVICES),"announcements":[],
        "verified_official_source":True,"parser_version":PARSER_VERSION,"signal_fingerprint":_fingerprint(),
        "last_good_observed_on":OBSERVED_ON,"last_good_source":SOURCE_URL,"last_good_bootstrap":True,
        "last_good_max_age_days":MAX_AGE_DAYS,
    }
    return out
''', encoding="utf-8")

replace_once(
    "grading_company_watch_resilient.py",
    """import grading_company_watch as base\nfrom safe_runtime import atomic_write_json, safe_urlopen\n""",
    """import grading_company_watch as base\nfrom grading_company_psa_last_good import inject_psa_verified_last_good\nfrom safe_runtime import atomic_write_json, safe_urlopen\n""",
)
replace_once(
    "grading_company_watch_resilient.py",
    """def collect(previous: dict | None = None, fetcher=None, requester=None) -> dict:\n    previous = previous if isinstance(previous, dict) else base._load_previous(OUT)\n    requester = requester or _request\n""",
    """def collect(previous: dict | None = None, fetcher=None, requester=None) -> dict:\n    previous = previous if isinstance(previous, dict) else base._load_previous(OUT)\n    previous = inject_psa_verified_last_good(previous)\n    requester = requester or _request\n""",
)

# 3) Contextual gate: blocked PSA remains degraded but a recent verified last-good
# prevents a 403-only provider outage from blocking unrelated verified data delivery.
replace_once(
    "collection_verification_gate_contextual.py",
    """import json\nfrom pathlib import Path\nfrom typing import Any\n\nimport collection_verification_gate as base\n""",
    """import json\nimport re\nfrom pathlib import Path\nfrom typing import Any\nfrom urllib.parse import urlparse\n\nimport collection_verification_gate as base\n""",
)
replace_once(
    "collection_verification_gate_contextual.py",
    """BOUNDARY_SLOP_SECONDS = 5 * 60\n\n\ndef _load(path: Path) -> Any:\n""",
    """BOUNDARY_SLOP_SECONDS = 5 * 60\nBLOCKED_LAST_GOOD_MAX_AGE_DAYS = 7\n_BLOCKED_PROVIDER_RE = re.compile(r\"HTTPError:\\s*status\\s*(401|403|451)\\b\", re.I)\n\n\ndef _load(path: Path) -> Any:\n""",
)
insert_before = """def verify(root: Path | str = base.ROOT, *, max_health_age_seconds: int = 900,\n           now: dt.datetime | None = None) -> dict[str, Any]:\n"""
helper = r'''def _blocked_last_good_proof(root: Path, company: str, now: dt.datetime) -> dict[str, Any] | None:
    try:
        data = _load(root / "grading_company_updates.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, dict):
        return None
    company_rows = [row for row in sources.values() if isinstance(row, dict) and str(row.get("company") or "").upper() == company]
    if not company_rows:
        return None
    degraded = [row for row in company_rows if str(row.get("status") or "").lower() not in {"ok", "healthy"}]
    if not degraded or len(degraded) != len(company_rows):
        return None
    for row in degraded:
        error = str(row.get("last_error") or row.get("error") or "")
        if not _BLOCKED_PROVIDER_RE.search(error):
            return None
    candidates = []
    for row in degraded:
        if row.get("verified_official_source") is not True or not isinstance(row.get("services"), list) or not row.get("services"):
            continue
        source = str(row.get("last_good_source") or row.get("url") or "")
        if not base._valid_public_https(source):
            continue
        host = (urlparse(source).hostname or "").lower().rstrip(".")
        if host not in base.GRADING_ALLOWED_HOSTS:
            continue
        observed = str(row.get("last_good_observed_on") or "")
        try:
            observed_date = dt.date.fromisoformat(observed)
        except ValueError:
            continue
        age_days = (now.date() - observed_date).days
        max_age = int(row.get("last_good_max_age_days") or BLOCKED_LAST_GOOD_MAX_AGE_DAYS)
        max_age = min(max(1, max_age), BLOCKED_LAST_GOOD_MAX_AGE_DAYS)
        if 0 <= age_days <= max_age:
            candidates.append({"source_id": row.get("source_id"), "source": source, "observed_on": observed, "age_days": age_days, "service_count": len(row["services"])})
    if not candidates:
        return None
    return {"company": company, "failure_class": "SOURCE_BLOCKED", "bypass_attempted": False, "retained_last_good": candidates}


def _contextualize_blocked_last_good(root: Path, finding: dict[str, Any], now: dt.datetime) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if finding.get("severity") != "high" or finding.get("code") != "GRADING_COMPANY_NO_HEALTHY_SOURCE":
        return [finding], None
    companies = [str(x).upper() for x in (finding.get("companies") or []) if str(x).strip()]
    safe: list[dict[str, Any]] = []
    unsafe: list[str] = []
    for company in companies:
        proof = _blocked_last_good_proof(root, company, now)
        if proof is None:
            unsafe.append(company)
        else:
            safe.append(proof)
    rows: list[dict[str, Any]] = []
    if unsafe:
        kept = dict(finding)
        kept["companies"] = unsafe
        by_company = finding.get("degraded_samples_by_company") or {}
        counts = finding.get("degraded_sample_counts_by_company") or {}
        kept["degraded_samples_by_company"] = {k: by_company.get(k, []) for k in unsafe}
        kept["degraded_sample_counts_by_company"] = {k: counts.get(k, 0) for k in unsafe}
        kept["degraded_samples"] = [row for company in unsafe for row in by_company.get(company, [])][:20]
        rows.append(kept)
    if safe:
        rows.append({
            "severity":"medium","code":"GRADING_COMPANY_SOURCE_BLOCKED_WITH_VERIFIED_LAST_GOOD",
            "target":"grading_company_updates.json","companies":[row["company"] for row in safe],
            "proof":safe,"policy":"blocked source remains degraded; no bypass; bounded last-good only",
        })
    return rows, ({"companies":[row["company"] for row in safe],"proof":safe} if safe else None)


'''
replace_once("collection_verification_gate_contextual.py", insert_before, helper + insert_before)
replace_once(
    "collection_verification_gate_contextual.py",
    """    filtered: list[dict[str, Any]] = []\n    contextual: list[dict[str, Any]] = []\n\n    for finding in original:\n""",
    """    filtered: list[dict[str, Any]] = []\n    contextual: list[dict[str, Any]] = []\n    blocked_last_good: list[dict[str, Any]] = []\n\n    for finding in original:\n""",
)
replace_once(
    "collection_verification_gate_contextual.py",
    """                })\n                continue\n        filtered.append(finding)\n\n    filtered.extend(contextual)\n""",
    """                })\n                continue\n        contextual_rows, blocked_proof = _contextualize_blocked_last_good(root, finding, now)\n        filtered.extend(contextual_rows)\n        if blocked_proof is not None:\n            blocked_last_good.append(blocked_proof)\n\n    filtered.extend(contextual)\n""",
)
replace_once(
    "collection_verification_gate_contextual.py",
    """        \"max_completed_report_age_seconds\": MAX_REPORT_AGE_SECONDS,\n    }\n    return report\n""",
    """        \"max_completed_report_age_seconds\": MAX_REPORT_AGE_SECONDS,\n        \"blocked_last_good_proofs\": len(blocked_last_good),\n    }\n    report[\"blocked_provider_last_good\"] = blocked_last_good\n    return report\n""",
)

# Regression tests for both safety fixes.
(ROOT / "test_drive_package_blockers_v359.py").write_text(r'''import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate_contextual as contextual
import grading_company_psa_last_good as psa
import update_market_prices as market


class DrivePackageBlockersV359Tests(unittest.TestCase):
    def test_packmagik_legacy_kr_misjoin_is_quarantined(self):
        db={"entries":{"KR|창해의 칠걸|HIT":{"display":"$19.20","market":"Pack Magik 국제시장","source":"https://www.packmagik.com/cards/op-op14-op14-009-p1"}}}
        repaired=market._sanitize_entries(db)
        self.assertEqual(repaired,1)
        self.assertNotIn("KR|창해의 칠걸|HIT",db["entries"])
        self.assertIn("KR|창해의 칠걸|HIT",db["invalid_entries_quarantine"])

    def test_psa_bootstrap_is_bounded(self):
        seeded=psa.inject_psa_verified_last_good({},dt.date(2026,10,6))
        self.assertTrue(seeded["sources"][psa.SOURCE_ID]["services"])
        expired=psa.inject_psa_verified_last_good({},dt.date(2026,10,7))
        self.assertNotIn(psa.SOURCE_ID,expired.get("sources",{}))

    def test_blocked_psa_with_recent_verified_last_good_is_medium_not_high(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            seeded=psa.inject_psa_verified_last_good({},dt.date(2026,9,29))
            row=seeded["sources"][psa.SOURCE_ID]
            row.update({"status":"degraded","last_error":"HTTPError: status 403"})
            seeded["sources"]["psa-jp-pricing"]={"company":"PSA","status":"degraded","url":"https://www.psacard.com/ja-JP/services/tradingcardgrading/grading","last_error":"HTTPError: status 403"}
            seeded["sources"]["psa-jp-news"]={"company":"PSA","status":"degraded","url":"https://www.psacard.com/ja-JP/articles","last_error":"HTTPError: status 403"}
            (root/"grading_company_updates.json").write_text(json.dumps(seeded),encoding="utf-8")
            finding={"severity":"high","code":"GRADING_COMPANY_NO_HEALTHY_SOURCE","companies":["PSA"],"degraded_samples_by_company":{"PSA":[]},"degraded_sample_counts_by_company":{"PSA":3}}
            rows,proof=contextual._contextualize_blocked_last_good(root,finding,dt.datetime(2026,9,29,tzinfo=dt.timezone.utc))
            self.assertIsNotNone(proof)
            self.assertEqual(["medium"],[row["severity"] for row in rows])
            self.assertEqual("GRADING_COMPANY_SOURCE_BLOCKED_WITH_VERIFIED_LAST_GOOD",rows[0]["code"])

    def test_blocked_psa_expired_last_good_stays_high(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            seeded=psa.inject_psa_verified_last_good({},dt.date(2026,9,29))
            row=seeded["sources"][psa.SOURCE_ID]
            row.update({"status":"degraded","last_error":"HTTPError: status 403"})
            seeded["sources"]["psa-jp-pricing"]={"company":"PSA","status":"degraded","url":"https://www.psacard.com/ja-JP/services/tradingcardgrading/grading","last_error":"HTTPError: status 403"}
            seeded["sources"]["psa-jp-news"]={"company":"PSA","status":"degraded","url":"https://www.psacard.com/ja-JP/articles","last_error":"HTTPError: status 403"}
            (root/"grading_company_updates.json").write_text(json.dumps(seeded),encoding="utf-8")
            finding={"severity":"high","code":"GRADING_COMPANY_NO_HEALTHY_SOURCE","companies":["PSA"],"degraded_samples_by_company":{"PSA":[]},"degraded_sample_counts_by_company":{"PSA":3}}
            rows,proof=contextual._contextualize_blocked_last_good(root,finding,dt.datetime(2026,10,7,tzinfo=dt.timezone.utc))
            self.assertIsNone(proof)
            self.assertEqual("high",rows[0]["severity"])

    def test_non_blocked_failure_stays_high(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            seeded=psa.inject_psa_verified_last_good({},dt.date(2026,9,29))
            row=seeded["sources"][psa.SOURCE_ID]
            row.update({"status":"degraded","last_error":"ValueError: parser changed"})
            (root/"grading_company_updates.json").write_text(json.dumps(seeded),encoding="utf-8")
            finding={"severity":"high","code":"GRADING_COMPANY_NO_HEALTHY_SOURCE","companies":["PSA"],"degraded_samples_by_company":{"PSA":[]},"degraded_sample_counts_by_company":{"PSA":1}}
            rows,proof=contextual._contextualize_blocked_last_good(root,finding,dt.datetime(2026,9,29,tzinfo=dt.timezone.utc))
            self.assertIsNone(proof)
            self.assertEqual("high",rows[0]["severity"])


if __name__=="__main__":
    unittest.main()
''', encoding="utf-8")

print("v359 patch staged")
