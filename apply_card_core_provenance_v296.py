from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "tablet_runtime_manifest.py",
    '"index.html","safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","ai_runtime_model_guard.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",\n'
    '"quality_review_policy.py","quality_review_policy_v2.json",',
    '"index.html","safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","ai_runtime_model_guard.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",\n'
    '"grading_accuracy_v99.py","card_grading_valuation.py","card_identity_recognition.py","server_security_guard.py",\n'
    '"quality_review_policy.py","quality_review_policy_v2.json",',
)
replace_once(
    "tablet_runtime_manifest.py",
    '"grading_vision_engine.js","grade_market_flow.js","grade_market_flow.css","grading_costs_live.js","grading_costs_live.css","inventory_lookup.js","inventory_lookup.css",',
    '"grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js","grade_market_flow.js","grade_market_flow.css","grading_costs_live.js","grading_costs_live.css","inventory_lookup.js","inventory_lookup.css",',
)

replace_once(
    "card_grading_valuation.py",
    """def _grade_key(grade: float) -> str:
    return str(int(grade)) if grade.is_integer() else str(grade)


def verified_card_valuation(
""",
    """def _grade_key(grade: float) -> str:
    return str(int(grade)) if grade.is_integer() else str(grade)


def _clean_grade_price_evidence(value: Any) -> dict[str, str] | None:
    # Validate provenance attached to one exact company+grade observation.
    if not isinstance(value, Mapping) or len(value) > 12:
        return None
    source = str(value.get("source") or "").strip()
    try:
        parsed = urllib.parse.urlsplit(source)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    price_type = str(value.get("price_type") or "").strip()
    if price_type not in {"sold", "auction_result", "official_example", "market_guide", "user_provided"}:
        return None
    observed_on = str(value.get("observed_on") or "").strip()
    observed_period = str(value.get("observed_period") or "").strip()
    if not observed_on and not observed_period:
        return None
    result = {"source": source[:500], "price_type": price_type}
    if observed_on:
        result["observed_on"] = observed_on[:32]
    if observed_period:
        result["observed_period"] = observed_period[:32]
    label = " ".join(str(value.get("label") or "").split())[:180]
    if label:
        result["label"] = label
    return result


def _validated_exchange_rate(value: Any) -> float | None:
    # Return a real bounded USD/KRW rate or None; never fabricate a fallback.
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str) and (not value.strip() or len(value.strip()) > 64):
            return None
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not 100.0 <= number <= 10_000.0:
        return None
    return number


def verified_card_valuation(
""",
)
replace_once(
    "card_grading_valuation.py",
    """    grade_prices_krw: Mapping[str, Any] | None = None,
    *,
    raw_krw: Any = 0,
    exchange_rate: Any = 1350.0,
""",
    """    grade_prices_krw: Mapping[str, Any] | None = None,
    grade_price_evidence: Mapping[str, Any] | None = None,
    *,
    raw_krw: Any = 0,
    exchange_rate: Any = None,
""",
)
replace_once(
    "card_grading_valuation.py",
    """    profiles = grade_prices_krw if isinstance(grade_prices_krw, Mapping) else {}
    source_kind = price_source if price_source in {
        "exact_company_grade_observation", "user_provided_exact_grade"
    } else "user_provided_exact_grade"
    rate = safe_float(exchange_rate, 1350.0, minimum=100.0, maximum=10_000.0)
    raw = safe_int(raw_krw, 0, minimum=0, maximum=MAX_PRICE_KRW)
    valuations = {}
    for company, grade in result["grades"].items():
        company_prices = profiles.get(company, {})
        exact = company_prices.get(_grade_key(float(grade)), 0) if isinstance(company_prices, Mapping) else 0
        krw = safe_int(exact, 0, minimum=0, maximum=MAX_PRICE_KRW)
        valuations[company] = {
            "grade": grade,
            "grade_key": _grade_key(float(grade)),
            "available": krw > 0,
            "krw": krw if krw else None,
            "usd": round(krw / rate, 2) if krw else None,
            "source": source_kind if krw else "unavailable",
            "reason": None if krw else "해당 업체·정확한 등급의 확인 거래가격 없음",
        }
    return {**result, "card_name": name, "raw_krw": raw or None, "exchange_rate": rate, "valuations": valuations}
""",
    """    profiles = grade_prices_krw if isinstance(grade_prices_krw, Mapping) else {}
    evidence_profiles = grade_price_evidence if isinstance(grade_price_evidence, Mapping) else {}
    source_kind = price_source if price_source in {
        "exact_company_grade_observation", "user_provided_exact_grade"
    } else "user_provided_exact_grade"
    # Public/static exact-grade observations must carry machine-readable provenance.
    # Direct caller/manual values remain user-provided and are never auto-promoted.
    enforce_public_evidence = source_kind == "exact_company_grade_observation" and grade_price_evidence is not None
    rate = _validated_exchange_rate(exchange_rate)
    raw = safe_int(raw_krw, 0, minimum=0, maximum=MAX_PRICE_KRW)
    valuations = {}
    for company, grade in result["grades"].items():
        grade_key = _grade_key(float(grade))
        company_prices = profiles.get(company, {})
        exact = company_prices.get(grade_key, 0) if isinstance(company_prices, Mapping) else 0
        krw = safe_int(exact, 0, minimum=0, maximum=MAX_PRICE_KRW)
        company_evidence = evidence_profiles.get(company, {})
        evidence = _clean_grade_price_evidence(company_evidence.get(grade_key)) if isinstance(company_evidence, Mapping) else None
        available = krw > 0 and (not enforce_public_evidence or evidence is not None)
        if krw > 0 and enforce_public_evidence and evidence is None:
            reason = "확인 거래가격의 출처·유형·관측시점 근거 부족"
        elif not krw:
            reason = "해당 업체·정확한 등급의 확인 거래가격 없음"
        else:
            reason = None
        valuations[company] = {
            "grade": grade,
            "grade_key": grade_key,
            "available": available,
            "krw": krw if available else None,
            "usd": round(krw / rate, 2) if available and rate is not None else None,
            "source": source_kind if available else "unavailable",
            "evidence": evidence if available else None,
            "evidence_verified": bool(evidence) if available else False,
            "reason": reason,
        }
    return {
        **result,
        "card_name": name,
        "raw_krw": raw or None,
        "exchange_rate": rate,
        "exchange_rate_available": rate is not None,
        "valuations": valuations,
    }
""",
)

replace_once(
    "tcg_updater.py",
    "                exchange_rate=exchange.get('rates',{}).get('USD_KRW',1350.0)\n",
    "                exchange_rate=exchange.get('rates',{}).get('USD_KRW') if isinstance(exchange.get('rates'),dict) else None\n",
)
replace_once(
    "tcg_updater.py",
    """                result=verified_card_valuation(
                    card_name,values,grade_prices,
                    raw_krw=profile.get('raw_krw',incoming.get('raw_krw',0)),
""",
    """                result=verified_card_valuation(
                    card_name,values,grade_prices,
                    grade_price_evidence=profile.get('grade_price_evidence',{}) if profile else None,
                    raw_krw=profile.get('raw_krw',incoming.get('raw_krw',0)),
""",
)

replace_once(
    "update_market_prices.py",
    """    profiles['JP|계승되는 의지 일본판 에이스 만화패러렐|HIT']['grade_prices_krw']['PSA']['10']=12_095_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['9']=450_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['10']=2_000_000
""",
    """    profiles['JP|계승되는 의지 일본판 에이스 만화패러렐|HIT']['grade_prices_krw']['PSA']['10']=12_095_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['9']=450_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['10']=2_000_000
    profiles['JP|계승되는 의지 일본판 에이스 만화패러렐|HIT']['grade_price_evidence']={
      'PSA':{'10':{'source':'https://kream.co.kr/products/911415','price_type':'sold',
                    'observed_on':'2026-09-22','label':'PSA 10 공개 체결가 범위 중앙값 · 페이지 확인일'}}
    }
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_price_evidence']={
      'BRG':{
        '9':{'source':'https://break.co.kr/','price_type':'official_example','observed_period':'2025-05','label':'BRG 공식 페이지 특정 카드 거래 예시'},
        '10':{'source':'https://break.co.kr/','price_type':'official_example','observed_period':'2025-05','label':'BRG 공식 페이지 특정 카드 거래 예시'},
      }
    }
""",
)
replace_once(
    "update_market_prices.py",
    "            if field in ('grade_prices_krw','note'):\n",
    "            if field in ('grade_prices_krw','grade_price_evidence','note'):\n",
)

market_path = ROOT / "market_prices.json"
market = json.loads(market_path.read_text(encoding="utf-8"))
profiles = market.setdefault("graded_prices", {})
ace = profiles.setdefault("JP|계승되는 의지 일본판 에이스 만화패러렐|HIT", {})
ace["grade_price_evidence"] = {
    "PSA": {"10": {
        "source": "https://kream.co.kr/products/911415",
        "price_type": "sold",
        "observed_on": "2026-09-22",
        "label": "PSA 10 공개 체결가 범위 중앙값 · 페이지 확인일",
    }}
}
lillie = profiles.setdefault("KR|릴리에 SM1M 065/060|HIT", {})
lillie["grade_price_evidence"] = {
    "BRG": {
        "9": {
            "source": "https://break.co.kr/",
            "price_type": "official_example",
            "observed_period": "2025-05",
            "label": "BRG 공식 페이지 특정 카드 거래 예시",
        },
        "10": {
            "source": "https://break.co.kr/",
            "price_type": "official_example",
            "observed_period": "2025-05",
            "label": "BRG 공식 페이지 특정 카드 거래 예시",
        },
    }
}
market_path.write_text(json.dumps(market, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

replace_once(
    "collection_verification_gate.py",
    """    if bad > 20:
        findings.append({"severity": "high", "code": "INVALID_MARKET_ENTRY_OVERFLOW", "count": bad - 20})
    updated = db.get("updated_at") if isinstance(db, dict) else None
    if updated:
        _fresh("market_prices.json", updated, now, 24 * 3600, findings)
    return {"market_entries": len(entries), "invalid_market_entries": bad}
""",
    """    if bad > 20:
        findings.append({"severity": "high", "code": "INVALID_MARKET_ENTRY_OVERFLOW", "count": bad - 20})

    graded_profiles = db.get("graded_prices") if isinstance(db, dict) else {}
    invalid_grade_evidence = 0
    positive_grade_prices = 0
    allowed_companies = {"PSA", "BGS", "CGC", "TAG", "BRG"}
    allowed_price_types = {"sold", "auction_result", "official_example", "market_guide"}
    if graded_profiles is None:
        graded_profiles = {}
    elif not isinstance(graded_profiles, dict):
        findings.append({"severity": "high", "code": "INVALID_GRADED_PRICE_PROFILES", "target": "market_prices.json"})
        graded_profiles = {}
    for market_key, profile in graded_profiles.items():
        if not isinstance(profile, dict):
            invalid_grade_evidence += 1
            continue
        grade_prices = profile.get("grade_prices_krw") if isinstance(profile.get("grade_prices_krw"), dict) else {}
        evidence = profile.get("grade_price_evidence") if isinstance(profile.get("grade_price_evidence"), dict) else {}
        for company, grade_rows in grade_prices.items():
            if company not in allowed_companies or not isinstance(grade_rows, dict):
                invalid_grade_evidence += 1
                continue
            for grade_key, raw_price in grade_rows.items():
                try:
                    amount = float(raw_price)
                except (TypeError, ValueError, OverflowError):
                    amount = -1.0
                if not (amount == amount and amount not in (float("inf"), float("-inf")) and 0.0 <= amount <= 1_000_000_000_000.0):
                    invalid_grade_evidence += 1
                    continue
                if amount == 0:
                    continue
                positive_grade_prices += 1
                company_evidence = evidence.get(company) if isinstance(evidence.get(company), dict) else {}
                row = company_evidence.get(str(grade_key)) if isinstance(company_evidence, dict) else None
                reasons = []
                if not isinstance(row, dict):
                    reasons.append("missing_evidence")
                else:
                    if not _valid_public_https(row.get("source")):
                        reasons.append("invalid_source")
                    if row.get("price_type") not in allowed_price_types:
                        reasons.append("invalid_price_type")
                    observed_on = str(row.get("observed_on") or "").strip()
                    observed_period = str(row.get("observed_period") or "").strip()
                    if observed_on:
                        try:
                            dt.date.fromisoformat(observed_on)
                        except ValueError:
                            reasons.append("invalid_observed_on")
                    elif observed_period:
                        if not re.fullmatch(r"\\d{4}-\\d{2}", observed_period):
                            reasons.append("invalid_observed_period")
                    else:
                        reasons.append("missing_observed_time")
                if reasons:
                    invalid_grade_evidence += 1
                    if invalid_grade_evidence <= 20:
                        findings.append({
                            "severity": "high",
                            "code": "INVALID_GRADED_PRICE_EVIDENCE",
                            "target": f"{market_key}|{company}|{grade_key}"[:220],
                            "reasons": reasons,
                        })
    if invalid_grade_evidence > 20:
        findings.append({
            "severity": "high",
            "code": "INVALID_GRADED_PRICE_EVIDENCE_OVERFLOW",
            "count": invalid_grade_evidence - 20,
        })
    updated = db.get("updated_at") if isinstance(db, dict) else None
    if updated:
        _fresh("market_prices.json", updated, now, 24 * 3600, findings)
    return {
        "market_entries": len(entries),
        "invalid_market_entries": bad,
        "graded_price_profiles": len(graded_profiles),
        "positive_grade_prices": positive_grade_prices,
        "invalid_graded_price_evidence": invalid_grade_evidence,
    }
""",
)

test = r"""from __future__ import annotations

import json
from pathlib import Path
import datetime as dt
import unittest

import card_grading_valuation as valuation
import collection_verification_gate as gate
import tablet_runtime_manifest as manifest

ROOT = Path(__file__).resolve().parent


class CardCoreProvenanceV296Tests(unittest.TestCase):
    def pristine(self):
        return {
            "centering_front": 50, "centering_back": 50, "corners": 10,
            "edges": 10, "surface": 10, "micro_flaws": 0, "is_authentic": True,
        }

    def test_positive_static_exact_grade_prices_have_structured_provenance(self):
        db = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        allowed = {"sold", "auction_result", "official_example", "market_guide"}
        positives = 0
        for market_key, profile in (db.get("graded_prices") or {}).items():
            if not isinstance(profile, dict):
                continue
            evidence = profile.get("grade_price_evidence") or {}
            for company, grades in (profile.get("grade_prices_krw") or {}).items():
                if not isinstance(grades, dict):
                    continue
                for grade, price in grades.items():
                    if float(price or 0) <= 0:
                        continue
                    positives += 1
                    row = ((evidence.get(company) or {}).get(str(grade)) or {})
                    self.assertTrue(str(row.get("source") or "").startswith("https://"), (market_key, company, grade))
                    self.assertIn(row.get("price_type"), allowed, (market_key, company, grade))
                    self.assertTrue(row.get("observed_on") or row.get("observed_period"), (market_key, company, grade))
        self.assertGreaterEqual(positives, 3)

    def test_public_exact_price_without_provenance_is_suppressed(self):
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence={}, price_source="exact_company_grade_observation", exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertFalse(row["available"])
        self.assertIsNone(row["krw"])
        self.assertFalse(row["evidence_verified"])
        self.assertIn("근거 부족", row["reason"])

    def test_public_exact_price_with_provenance_is_available(self):
        evidence = {"PSA": {"10": {
            "source": "https://example.com/sold/1", "price_type": "sold",
            "observed_on": "2026-09-22", "label": "exact sold",
        }}}
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence=evidence, price_source="exact_company_grade_observation", exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertTrue(row["available"])
        self.assertEqual(123456, row["krw"])
        self.assertTrue(row["evidence_verified"])
        self.assertEqual("sold", row["evidence"]["price_type"])

    def test_missing_or_invalid_fx_never_fabricates_usd_value(self):
        evidence = {"PSA": {"10": {
            "source": "https://example.com/sold/1", "price_type": "sold", "observed_on": "2026-09-22",
        }}}
        for bad in (None, "", False, "nan", float("inf"), 0, 99, 10001):
            with self.subTest(rate=bad):
                result = valuation.verified_card_valuation(
                    "test", self.pristine(), {"PSA": {"10": 140000}},
                    grade_price_evidence=evidence, exchange_rate=bad,
                )
                self.assertEqual(140000, result["valuations"]["PSA"]["krw"])
                self.assertIsNone(result["valuations"]["PSA"]["usd"])
                self.assertIsNone(result["exchange_rate"])
                self.assertFalse(result["exchange_rate_available"])

    def test_manual_exact_price_stays_user_provided_not_publicly_verified(self):
        result = valuation.verified_card_valuation(
            "manual", self.pristine(), {"PSA": {"10": 100000}},
            price_source="user_provided_exact_grade", exchange_rate=None,
        )
        row = result["valuations"]["PSA"]
        self.assertTrue(row["available"])
        self.assertEqual("user_provided_exact_grade", row["source"])
        self.assertFalse(row["evidence_verified"])

    def test_runtime_manifest_fail_closes_card_core_dependencies(self):
        required = {
            "grading_accuracy_v99.py", "card_grading_valuation.py", "card_identity_recognition.py",
            "server_security_guard.py", "grading_vision_engine.js", "grading_accuracy_v99.js",
            "card_identity_recognition.js",
        }
        self.assertTrue(required.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))

    def test_collection_gate_accepts_current_static_grade_provenance(self):
        findings = []
        summary = gate._audit_market(ROOT, dt.datetime.now(dt.timezone.utc), findings)
        self.assertGreaterEqual(summary["positive_grade_prices"], 3)
        self.assertEqual(0, summary["invalid_graded_price_evidence"])
        self.assertFalse(any(row.get("code") == "INVALID_GRADED_PRICE_EVIDENCE" for row in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
"""
(ROOT / "test_card_core_provenance_v296.py").write_text(test, encoding="utf-8")

print("v296 card-core provenance/runtime patch applied")
