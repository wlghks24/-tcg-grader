from __future__ import annotations

import hashlib
import json
import subprocess
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
        raise SystemExit(f"{name}: expected one patch target, got {count}: {old!r}")
    write(name, text.replace(old, new, 1))


# Revert the earlier watched grading_* experiment. The runtime grading snapshot must
# remain truthful: PSA stays degraded/empty when GitHub Actions receives HTTP 403.
subprocess.run([
    "git", "checkout", "origin/main", "--",
    "grading_company_watch.py", "collection_verification_gate.py",
], cwd=ROOT, check=True)
bootstrap = ROOT / "grading_company_bootstrap.json"
if bootstrap.exists():
    bootstrap.unlink()

# Keep the already-tested market fix: quarantine the historical KR <- JP/international
# OP14-009 misjoin and treat a Pack Magik dynamic-page miss as an optional warning only.
market = read("update_market_prices.py")
for marker in (
    "def quarantine_legacy_packmagik_misjoin(db):",
    "def market_error_is_warning(text:str)->bool:",
    "if quarantine_legacy_packmagik_misjoin(db): initial_repairs+=1",
):
    if marker not in market:
        raise SystemExit(f"update_market_prices.py missing required v359 marker: {marker}")

services = [
    {"name":"Value Bulk","availability":"paused","max_insured_value_usd":500.0},
    {"name":"Value","availability":"paused","max_insured_value_usd":500.0},
    {"name":"Standard","availability":"open","fee_usd":59.99,"turnaround_business_days":[90,100],"max_insured_value_usd":1000.0},
    {"name":"Priority","availability":"open","fee_usd":79.99,"turnaround_business_days":[70,80],"max_insured_value_usd":1500.0},
    {"name":"Express","availability":"open","fee_usd":199.0,"turnaround_business_days":[20,30],"max_insured_value_usd":2500.0},
    {"name":"Super Express","availability":"open","fee_usd":349.0,"turnaround_business_days":[10,15],"max_insured_value_usd":5000.0},
    {"name":"Premier","availability":"open","fee_usd":599.0,"turnaround_business_days":[7,10],"max_insured_value_usd":10000.0},
    {"name":"Premium 1","availability":"open","fee_usd":999.0,"turnaround_business_days":[5,7],"max_insured_value_usd":25000.0},
    {"name":"Premium 2","availability":"open","fee_usd":1999.0,"turnaround_business_days":[5,7],"max_insured_value_usd":50000.0},
    {"name":"Premium 3","availability":"open","fee_usd":2999.0,"turnaround_business_days":[5,7],"max_insured_value_usd":100000.0},
    {"name":"Premium 5","availability":"open","fee_usd":4999.0,"turnaround_business_days":[5,7],"max_insured_value_usd":250000.0},
    {"name":"Premium 10","availability":"open","fee_floor_usd":9999.0,"turnaround_business_days":[5,7],"min_insured_value_usd":250001.0},
]
services_raw = json.dumps(services, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
proof = {
    "schema_version": 1,
    "provider": "PSA",
    "source_id": "psa-us-pricing",
    "source_url": PSA_URL,
    "observed_at": OBSERVED_AT,
    "expires_at": EXPIRES_AT,
    "facts_sha256": hashlib.sha256(services_raw.encode("utf-8")).hexdigest(),
    "services": services,
    "policy": {
        "official_source_only": True,
        "runtime_block_stays_degraded": True,
        "bypass_blocked_source": False,
        "max_age_seconds": 7 * 24 * 3600,
        "not_injected_into_grading_company_updates": True,
    },
}
write("provider_last_good_official.json", json.dumps(proof, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

# Extend only the contextual delivery gate. The base collection gate remains strict.
contextual = read("collection_verification_gate_contextual.py")
if "def _blocked_provider_last_good_proof(" not in contextual:
    replace_once(
        "collection_verification_gate_contextual.py",
        "import argparse\nimport datetime as dt\nimport json\nfrom pathlib import Path\nfrom typing import Any\n",
        "import argparse\nimport datetime as dt\nimport hashlib\nimport json\nimport re\nfrom pathlib import Path\nfrom typing import Any\nfrom urllib.parse import urlparse\n",
    )
    replace_once(
        "collection_verification_gate_contextual.py",
        "BOUNDARY_SLOP_SECONDS = 5 * 60\n",
        "BOUNDARY_SLOP_SECONDS = 5 * 60\nPROVIDER_PROOF_FILE = 'provider_last_good_official.json'\nMAX_PROVIDER_PROOF_AGE_SECONDS = 7 * 24 * 3600\n_BLOCKED_PROVIDER_RE = re.compile(r'HTTPError:\\s*status\\s*(401|403|451)\\b', re.I)\n",
    )
    anchor = "\ndef verify(root: Path | str = base.ROOT, *, max_health_age_seconds: int = 900,\n           now: dt.datetime | None = None) -> dict[str, Any]:\n"
    helper = r'''
def _blocked_provider_last_good_proof(root: Path, company: str, now: dt.datetime) -> dict[str, Any] | None:
    try:
        proof = _load(root / PROVIDER_PROOF_FILE)
        snapshot = _load(root / "grading_company_updates.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(proof, dict) or proof.get("schema_version") != 1:
        return None
    company = str(company or "").upper()
    if str(proof.get("provider") or "").upper() != company:
        return None
    policy = proof.get("policy") if isinstance(proof.get("policy"), dict) else {}
    required_policy = {
        "official_source_only": True,
        "runtime_block_stays_degraded": True,
        "bypass_blocked_source": False,
        "not_injected_into_grading_company_updates": True,
    }
    if any(policy.get(k) is not v for k, v in required_policy.items()):
        return None
    try:
        max_age = int(policy.get("max_age_seconds"))
    except (TypeError, ValueError):
        return None
    if max_age <= 0 or max_age > MAX_PROVIDER_PROOF_AGE_SECONDS:
        return None
    observed = _timestamp(proof.get("observed_at"))
    expires = _timestamp(proof.get("expires_at"))
    if observed is None or expires is None or expires < observed:
        return None
    age = (now - observed).total_seconds()
    if age < -BOUNDARY_SLOP_SECONDS or age > max_age or now > expires:
        return None
    source = str(proof.get("source_url") or "")
    if not base._valid_public_https(source):
        return None
    host = (urlparse(source).hostname or "").lower().rstrip(".")
    if host not in base.GRADING_ALLOWED_HOSTS:
        return None
    services = proof.get("services")
    if not isinstance(services, list) or not services:
        return None
    canonical = json.dumps(services, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != proof.get("facts_sha256"):
        return None

    sources = snapshot.get("sources") if isinstance(snapshot, dict) else None
    if not isinstance(sources, dict):
        return None
    rows = [row for row in sources.values() if isinstance(row, dict) and str(row.get("company") or "").upper() == company]
    if not rows:
        return None
    # Every current provider row must still be degraded because of an explicit hard block.
    # Any healthy row, parser failure, timeout, rate limit, or unknown error invalidates this proof.
    for row in rows:
        if str(row.get("status") or "").lower() in {"ok", "healthy"}:
            return None
        if str(row.get("status") or "").lower() != "degraded":
            return None
        error = str(row.get("last_error") or row.get("error") or "")
        if _BLOCKED_PROVIDER_RE.search(error) is None:
            return None
    return {
        "provider": company,
        "source": source,
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "age_seconds": round(age, 1),
        "facts_sha256": proof["facts_sha256"],
        "service_fact_count": len(services),
        "runtime_status": "degraded",
        "failure_class": "SOURCE_BLOCKED",
        "bypass_attempted": False,
    }


def _contextualize_blocked_provider(root: Path, finding: dict[str, Any], now: dt.datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if finding.get("severity") != "high" or finding.get("code") != "GRADING_COMPANY_NO_HEALTHY_SOURCE":
        return [finding], []
    companies = [str(item).upper() for item in (finding.get("companies") or []) if str(item).strip()]
    safe: list[dict[str, Any]] = []
    unsafe: list[str] = []
    for company in companies:
        proof = _blocked_provider_last_good_proof(root, company, now)
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
        kept["degraded_samples_by_company"] = {name: by_company.get(name, []) for name in unsafe}
        kept["degraded_sample_counts_by_company"] = {name: counts.get(name, 0) for name in unsafe}
        kept["degraded_samples"] = [sample for name in unsafe for sample in by_company.get(name, [])][:20]
        rows.append(kept)
    if safe:
        rows.append({
            "severity": "medium",
            "code": "GRADING_COMPANY_SOURCE_BLOCKED_WITH_EXTERNAL_LAST_GOOD",
            "target": "grading_company_updates.json",
            "companies": [item["provider"] for item in safe],
            "proof": safe,
            "policy": "runtime snapshot remains degraded/empty; no source bypass; proof only permits unrelated verified outputs to publish",
        })
    return rows, safe

'''
    replace_once("collection_verification_gate_contextual.py", anchor, helper + anchor)
    replace_once(
        "collection_verification_gate_contextual.py",
        "    filtered: list[dict[str, Any]] = []\n    contextual: list[dict[str, Any]] = []\n",
        "    filtered: list[dict[str, Any]] = []\n    contextual: list[dict[str, Any]] = []\n    blocked_provider_proofs: list[dict[str, Any]] = []\n",
    )
    replace_once(
        "collection_verification_gate_contextual.py",
        "                })\n                continue\n        filtered.append(finding)\n\n    filtered.extend(contextual)\n",
        "                })\n                continue\n        if isinstance(finding, dict):\n            provider_rows, provider_proofs = _contextualize_blocked_provider(root, finding, now)\n            if provider_proofs:\n                filtered.extend(provider_rows)\n                blocked_provider_proofs.extend(provider_proofs)\n                continue\n        filtered.append(finding)\n\n    filtered.extend(contextual)\n",
    )
    replace_once(
        "collection_verification_gate_contextual.py",
        "        \"max_completed_report_age_seconds\": MAX_REPORT_AGE_SECONDS,\n    }\n    return report\n",
        "        \"max_completed_report_age_seconds\": MAX_REPORT_AGE_SECONDS,\n        \"blocked_provider_proofs\": len(blocked_provider_proofs),\n    }\n    report[\"blocked_provider_last_good\"] = blocked_provider_proofs\n    return report\n",
    )

write("test_drive_package_blockers_v359.py", r'''import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate_contextual as contextual
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

    def _write_fixture(self, root: Path, *, observed='2026-09-29T08:11:00+00:00', expires='2026-10-06T08:11:00+00:00', errors=None):
        services=[{'name':'Standard','fee_usd':59.99,'availability':'open'}]
        canonical=json.dumps(services,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        proof={
            'schema_version':1,'provider':'PSA','source_id':'psa-us-pricing',
            'source_url':'https://www.psacard.com/services/tradingcardgrading',
            'observed_at':observed,'expires_at':expires,
            'facts_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'services':services,
            'policy':{'official_source_only':True,'runtime_block_stays_degraded':True,'bypass_blocked_source':False,'max_age_seconds':604800,'not_injected_into_grading_company_updates':True},
        }
        (root/'provider_last_good_official.json').write_text(json.dumps(proof),encoding='utf-8')
        errs=errors or ['HTTPError: status 403','HTTPError: status 403','HTTPError: status 403']
        sources={}
        for source_id,error in zip(('psa-us-pricing','psa-jp-pricing','psa-jp-news'),errs):
            sources[source_id]={'company':'PSA','status':'degraded','url':'https://www.psacard.com/services/tradingcardgrading','last_error':error,'services':[],'verified_official_source':False}
        (root/'grading_company_updates.json').write_text(json.dumps({'sources':sources}),encoding='utf-8')

    def test_recent_external_proof_downgrades_only_hard_block_to_medium(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root)
            finding={'severity':'high','code':'GRADING_COMPANY_NO_HEALTHY_SOURCE','companies':['PSA'],'degraded_samples_by_company':{'PSA':[]},'degraded_sample_counts_by_company':{'PSA':3}}
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,9,29,9,tzinfo=dt.timezone.utc))
            self.assertEqual(1,len(proofs)); self.assertEqual('medium',rows[0]['severity'])
            self.assertEqual('degraded',proofs[0]['runtime_status']); self.assertFalse(proofs[0]['bypass_attempted'])

    def test_expired_or_nonblocked_provider_stays_high(self):
        finding={'severity':'high','code':'GRADING_COMPANY_NO_HEALTHY_SOURCE','companies':['PSA'],'degraded_samples_by_company':{'PSA':[]},'degraded_sample_counts_by_company':{'PSA':3}}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root)
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,10,6,8,11,1,tzinfo=dt.timezone.utc))
            self.assertFalse(proofs); self.assertEqual('high',rows[0]['severity'])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root,errors=['HTTPError: status 403','ValueError: parser changed','HTTPError: status 403'])
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,9,29,9,tzinfo=dt.timezone.utc))
            self.assertFalse(proofs); self.assertEqual('high',rows[0]['severity'])

    def test_tampered_proof_stays_high(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root)
            proof=json.loads((root/'provider_last_good_official.json').read_text())
            proof['services'][0]['fee_usd']=1.0
            (root/'provider_last_good_official.json').write_text(json.dumps(proof))
            finding={'severity':'high','code':'GRADING_COMPANY_NO_HEALTHY_SOURCE','companies':['PSA'],'degraded_samples_by_company':{'PSA':[]},'degraded_sample_counts_by_company':{'PSA':3}}
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,9,29,9,tzinfo=dt.timezone.utc))
            self.assertFalse(proofs); self.assertEqual('high',rows[0]['severity'])


if __name__ == '__main__':
    unittest.main()
''')

print("v359 isolated provider proof staged")
