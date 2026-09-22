from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


# 1) Browser probability: use the authoritative V99 PSA estimate as the center of
# a clearly labelled heuristic uncertainty distribution.  Keep the legacy p9+
# metric for compatibility, but exact 8/9/10 values come only from the helper.
name = "index.html"
text = read(name)
text = replace_once(
    text,
    '<script src="./grading_accuracy_v99.js"></script>',
    '<script src="./grading_accuracy_v99.js"></script>\n<script src="./grading_probability_v292.js?v=292"></script>',
    "index probability script",
)
pattern = re.compile(
    r''' let best=window\.TCGAccuracyV99\?TCGAccuracyV99\.estimateRawGrade\(FC\.worst,BC\.worst,r,edgeRisk,cornerRisk,"PSA"\):g\(FC\.worst,BC\.worst,defectRisk,"PSA"\);\n let centerPenalty=.*?\n let uncertaintyPenalty=.*?\n let p10=.*?\n let p9=.*?\n let p9only=.*?\n window\.tcgGradeProbabilities=\{8:p8,9:p9only,10:p10,below\};''',
    re.S,
)
replacement = ''' let best=window.TCGAccuracyV99?TCGAccuracyV99.estimateRawGrade(FC.worst,BC.worst,r,edgeRisk,cornerRisk,"PSA"):g(FC.worst,BC.worst,defectRisk,"PSA");
 const probability=window.TCGGradeProbabilityV292?TCGGradeProbabilityV292.estimate({
   psaGrade:Number(window.tcgLastGrades?.PSA??best),front:FC.worst,back:BC.worst,
   surfaceRisk:r,edgeRisk,cornerRisk,analysisConfidence
 }):{status:"insufficient_evidence",model:"unavailable",calibrated:false,exact:{8:0,9:0,10:0},p9plus:0,below8:100};
 let p8=Number(probability.exact?.[8]||0),p9only=Number(probability.exact?.[9]||0),p10=Number(probability.exact?.[10]||0);
 let p9=Number(probability.p9plus??(p9only+p10)),below=Number(probability.below8??Math.max(0,100-p8-p9only-p10));
 window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below};
 window.tcgGradeProbabilityMeta={status:probability.status,model:probability.model,calibrated:false,evidenceComplete:probability.status==="estimated",note:probability.note||""};'''
text2, n = pattern.subn(replacement, text, count=1)
if n != 1 and "window.tcgGradeProbabilityMeta" not in text:
    raise RuntimeError(f"index probability block: expected one match, found {n}")
text = text2 if n == 1 else text
write(name, text)

# 2) Result cockpit: exact PSA 9 must never fall back to the legacy cumulative
# PSA 9+ display.  Label the probability block as a heuristic, not a calibrated rate.
name = "ui_app_shell_v272.js"
text = read(name)
text = replace_once(text, 'probabilityTitle.textContent = "PSA 예상확률";',
                    'probabilityTitle.textContent = "PSA 예상확률(휴리스틱)";', "cockpit probability label")
text = replace_once(text,
                    'const fallback = nodeText(grade === 10 ? "p10prob" : grade === 9 ? "p9prob" : "");',
                    'const fallback = nodeText(grade === 10 ? "p10prob" : "");',
                    "exact nine fallback")
write(name, text)

# 3) Exact grade-price evidence travels with the exact price and is exposed by
# the valuation API.  User-entered exact prices remain allowed but are not
# silently promoted to verified market evidence.
name = "card_grading_valuation.py"
text = read(name)
anchor = '''def verified_card_valuation(
    card_name: str,
    card_values: Mapping[str, Any],
    grade_prices_krw: Mapping[str, Any] | None = None,
    *,'''
helper = '''def _clean_grade_price_evidence(value: Any) -> dict[str, str] | None:
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


def verified_card_valuation(
    card_name: str,
    card_values: Mapping[str, Any],
    grade_prices_krw: Mapping[str, Any] | None = None,
    grade_price_evidence: Mapping[str, Any] | None = None,
    *,'''
text = replace_once(text, anchor, helper, "valuation evidence signature")
text = replace_once(text,
                    '    profiles = grade_prices_krw if isinstance(grade_prices_krw, Mapping) else {}\n',
                    '    profiles = grade_prices_krw if isinstance(grade_prices_krw, Mapping) else {}\n    evidence_profiles = grade_price_evidence if isinstance(grade_price_evidence, Mapping) else {}\n',
                    "valuation evidence profiles")
old_loop = '''        company_prices = profiles.get(company, {})
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
        }'''
new_loop = '''        grade_key = _grade_key(float(grade))
        company_prices = profiles.get(company, {})
        exact = company_prices.get(grade_key, 0) if isinstance(company_prices, Mapping) else 0
        krw = safe_int(exact, 0, minimum=0, maximum=MAX_PRICE_KRW)
        company_evidence = evidence_profiles.get(company, {})
        evidence = _clean_grade_price_evidence(company_evidence.get(grade_key)) if isinstance(company_evidence, Mapping) else None
        valuations[company] = {
            "grade": grade,
            "grade_key": grade_key,
            "available": krw > 0,
            "krw": krw if krw else None,
            "usd": round(krw / rate, 2) if krw else None,
            "source": source_kind if krw else "unavailable",
            "evidence": evidence if krw else None,
            "evidence_verified": bool(evidence) if krw else False,
            "reason": None if krw else "해당 업체·정확한 등급의 확인 거래가격 없음",
        }'''
text = replace_once(text, old_loop, new_loop, "valuation loop")
write(name, text)

# 4) The server forwards structured evidence with the static exact-grade profile.
name = "tcg_updater.py"
text = read(name)
text = replace_once(text,
                    "'grading_vision_engine.js','grading_accuracy_v99.js','card_identity_recognition.js'",
                    "'grading_vision_engine.js','grading_accuracy_v99.js','grading_probability_v292.js','card_identity_recognition.js'",
                    "public probability asset")
text = replace_once(text,
                    '''                result=verified_card_valuation(
                    card_name,values,grade_prices,
                    raw_krw=profile.get('raw_krw',incoming.get('raw_krw',0)),''',
                    '''                result=verified_card_valuation(
                    card_name,values,grade_prices,
                    grade_price_evidence=profile.get('grade_price_evidence',{}) if profile else None,
                    raw_krw=profile.get('raw_krw',incoming.get('raw_krw',0)),''',
                    "server valuation evidence")
write(name, text)

# 5) Seeded positive exact-grade values get machine-readable provenance.  This
# does not manufacture any new price; it only attaches evidence to existing facts.
name = "update_market_prices.py"
text = read(name)
anchor = '''    profiles['JP|계승되는 의지 일본판 에이스 만화패러렐|HIT']['grade_prices_krw']['PSA']['10']=12_095_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['9']=450_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['10']=2_000_000
'''
replacement = anchor + '''    profiles['JP|계승되는 의지 일본판 에이스 만화패러렐|HIT']['grade_price_evidence']={
      'PSA':{'10':{'source':'https://kream.co.kr/products/911415','price_type':'sold',
                    'observed_on':'2026-09-22','label':'PSA 10 공개 체결가 범위 중앙값 · 페이지 확인일'}}
    }
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_price_evidence']={
      'BRG':{
        '9':{'source':'https://break.co.kr/','price_type':'official_example','observed_period':'2025-05','label':'BRG 공식 페이지 특정 카드 거래 예시'},
        '10':{'source':'https://break.co.kr/','price_type':'official_example','observed_period':'2025-05','label':'BRG 공식 페이지 특정 카드 거래 예시'},
      }
    }
'''
text = replace_once(text, anchor, replacement, "seed grade evidence")
text = replace_once(text,
                    "            if field in ('grade_prices_krw','note'):\n",
                    "            if field in ('grade_prices_krw','grade_price_evidence','note'):\n",
                    "seed evidence overwrite")
write(name, text)

# Patch the current static snapshot with the same provenance so runtime and
# producer contract are coherent before the next live data refresh.
path = ROOT / "market_prices.json"
db = json.loads(path.read_text(encoding="utf-8"))
profiles = db.setdefault("graded_prices", {})
ace = profiles.get("JP|계승되는 의지 일본판 에이스 만화패러렐|HIT")
if isinstance(ace, dict):
    ace["grade_price_evidence"] = {"PSA": {"10": {
        "source": "https://kream.co.kr/products/911415", "price_type": "sold",
        "observed_on": "2026-09-22", "label": "PSA 10 공개 체결가 범위 중앙값 · 페이지 확인일",
    }}}
lillie = profiles.get("KR|릴리에 SM1M 065/060|HIT")
if isinstance(lillie, dict):
    lillie["grade_price_evidence"] = {"BRG": {
        "9": {"source": "https://break.co.kr/", "price_type": "official_example", "observed_period": "2025-05", "label": "BRG 공식 페이지 특정 카드 거래 예시"},
        "10": {"source": "https://break.co.kr/", "price_type": "official_example", "observed_period": "2025-05", "label": "BRG 공식 페이지 특정 카드 거래 예시"},
    }}
path.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# 6) Collection verification now fails closed when a positive exact-grade
# static price lacks source/type/time provenance.
name = "collection_verification_gate.py"
text = read(name)
anchor = '''    if bad > 20:
        findings.append({"severity": "high", "code": "INVALID_MARKET_ENTRY_OVERFLOW", "count": bad - 20})
    updated = db.get("updated_at") if isinstance(db, dict) else None
'''
replacement = '''    if bad > 20:
        findings.append({"severity": "high", "code": "INVALID_MARKET_ENTRY_OVERFLOW", "count": bad - 20})

    graded_profiles = db.get("graded_prices") if isinstance(db, dict) else {}
    invalid_grade_evidence = 0
    positive_grade_prices = 0
    allowed_companies = {"PSA", "BGS", "CGC", "TAG", "BRG"}
    allowed_price_types = {"sold", "auction_result", "official_example", "market_guide"}
    if graded_profiles is not None and not isinstance(graded_profiles, dict):
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
                if not (0.0 <= amount <= 1_000_000_000_000.0):
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
                    if not _valid_public_https(row.get("source")): reasons.append("invalid_source")
                    if row.get("price_type") not in allowed_price_types: reasons.append("invalid_price_type")
                    observed_on = str(row.get("observed_on") or "").strip()
                    observed_period = str(row.get("observed_period") or "").strip()
                    if observed_on:
                        try: dt.date.fromisoformat(observed_on)
                        except ValueError: reasons.append("invalid_observed_on")
                    elif observed_period:
                        if not re.fullmatch(r"\\d{4}-\\d{2}", observed_period): reasons.append("invalid_observed_period")
                    else:
                        reasons.append("missing_observed_time")
                if reasons:
                    invalid_grade_evidence += 1
                    if invalid_grade_evidence <= 20:
                        findings.append({"severity": "high", "code": "INVALID_GRADED_PRICE_EVIDENCE",
                                         "target": f"{market_key}|{company}|{grade_key}"[:220], "reasons": reasons})
    if invalid_grade_evidence > 20:
        findings.append({"severity": "high", "code": "INVALID_GRADED_PRICE_EVIDENCE_OVERFLOW",
                         "count": invalid_grade_evidence - 20})
    updated = db.get("updated_at") if isinstance(db, dict) else None
'''
text = replace_once(text, anchor, replacement, "market provenance audit")
text = replace_once(text,
                    '    return {"market_entries": len(entries), "invalid_market_entries": bad}\n',
                    '    return {"market_entries": len(entries), "invalid_market_entries": bad,\n            "graded_price_profiles": len(graded_profiles), "positive_grade_prices": positive_grade_prices,\n            "invalid_graded_price_evidence": invalid_grade_evidence}\n',
                    "market audit metrics")
write(name, text)

# 7) Tablet bundle fail-closed coverage: these are actual card-core imports/assets,
# not optional documentation.  A partial checkout must not pass tablet startup.
name = "tablet_runtime_manifest.py"
text = read(name)
text = replace_once(text,
                    '"index.html","safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","ai_runtime_model_guard.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",',
                    '"index.html","safe_runtime.py","runtime_sre_metrics.py","collection_runtime_health.py","ai_runtime_model_guard.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",\n"grading_accuracy_v99.py","card_grading_valuation.py","card_identity_recognition.py","server_security_guard.py",',
                    "tablet card python dependencies")
text = replace_once(text,
                    '"grading_vision_engine.js","grade_market_flow.js","grade_market_flow.css"',
                    '"grading_vision_engine.js","grading_accuracy_v99.js","grading_probability_v292.js","card_identity_recognition.js","grade_market_flow.js","grade_market_flow.css"',
                    "tablet card browser dependencies")
write(name, text)

# 8) PWA offline/runtime bundle and feature contract know the new executable.
name = "sw.js"
text = read(name)
text = text.replace('// v276 rotates the tablet/PWA runtime cache so the latest navigation UI is pre-cached after upgrade.',
                    '// v292 rotates the tablet/PWA runtime cache so the hardened card-core probability asset is pre-cached after upgrade.', 1)
text = replace_once(text, "const CACHE='tcg-v276-network-first-runtime';", "const CACHE='tcg-v292-card-core-runtime';", "service worker cache")
text = replace_once(text, "'./grading_vision_engine.js','./grading_accuracy_v99.js','./card_identity_recognition.js'",
                    "'./grading_vision_engine.js','./grading_accuracy_v99.js','./grading_probability_v292.js','./card_identity_recognition.js'",
                    "service worker probability asset")
write(name, text)

name = "feature_contract.py"
text = read(name)
text = replace_once(text,
                    '"grading_vision_engine.js", "grading_accuracy_v99.js", "verify_vision_runtime.js",',
                    '"grading_vision_engine.js", "grading_accuracy_v99.js", "grading_probability_v292.js", "verify_vision_runtime.js",',
                    "feature probability requirement")
write(name, text)

# Historical UI tests intentionally assert the current cache token; update them
# with the cache rotation rather than weakening the assertion.
for name in ("test_ui_version_coherence_v276.py", "test_tablet_app_dock_v275.py"):
    text = read(name)
    text = text.replace("const CACHE='tcg-v276-network-first-runtime';", "const CACHE='tcg-v292-card-core-runtime';")
    write(name, text)

# Strengthen this round's tablet check with the previously omitted critical assets.
name = "test_card_core_crosscheck_v292.py"
text = read(name)
old = '''    def test_probability_asset_is_in_tablet_server_and_pwa_runtime(self):
        self.assertIn("grading_probability_v292.js", tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("grading_probability_v292.js", tcg_updater.PUBLIC_STATIC_FILES)
'''
new = '''    def test_probability_asset_is_in_tablet_server_and_pwa_runtime(self):
        for dependency in (
            "grading_accuracy_v99.py", "card_grading_valuation.py", "card_identity_recognition.py", "server_security_guard.py",
            "grading_vision_engine.js", "grading_accuracy_v99.js", "grading_probability_v292.js", "card_identity_recognition.js",
        ):
            self.assertIn(dependency, tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("grading_probability_v292.js", tcg_updater.PUBLIC_STATIC_FILES)
'''
text = replace_once(text, old, new, "tablet regression dependencies")
write(name, text)

print("v292 bounded card-core patch applied")
