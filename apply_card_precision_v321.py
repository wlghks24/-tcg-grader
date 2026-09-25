#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def patch(path, old, new, label):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')

# Explicit EN must be treated as English-edition evidence, just like normalizeRegion already does.
patch('card_identity_recognition.py',
'''        ("US", r"(?:\\b(?:US|USA|ENGLISH)\\b|영문판|미국판)"),''',
'''        ("US", r"(?:\\b(?:US|USA|EN|ENGLISH)\\b|영문판|미국판)"),''',
'python EN edition label')

# Stage consensus must never merge the same name/number across KR/JP/US.
patch('card_identity_recognition.py',
'''    candidate_votes: Counter[tuple[str, str, str]] = Counter()\n    candidate_confidence: dict[tuple[str, str, str], float] = {}''',
'''    candidate_votes: Counter[tuple[str, str, str, str]] = Counter()\n    candidate_confidence: dict[tuple[str, str, str, str], float] = {}''',
'consensus tuple types')
patch('card_identity_recognition.py',
'''            key = (\n                str(best.get("card_name") or ""),\n                str(best.get("card_number") or ""),\n                str(best.get("market_key") or ""),\n            )''',
'''            key = (\n                str(best.get("card_name") or ""),\n                str(best.get("card_number") or ""),\n                str(best.get("market_key") or ""),\n                normalize_region(best.get("region")),\n            )''',
'consensus region key')
patch('card_identity_recognition.py',
'''    best_identity: tuple[str, str, str] | None = None''',
'''    best_identity: tuple[str, str, str, str] | None = None''',
'consensus best identity type')
patch('card_identity_recognition.py',
'''                "market_key": best_identity[2],\n                "stage_votes": best_identity_votes,''',
'''                "market_key": best_identity[2],\n                "region": best_identity[3],\n                "stage_votes": best_identity_votes,''',
'consensus region output')

patch('card_identity_recognition.js',
''' if(/(?:\\b(?:US|USA|ENGLISH)\\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);''',
''' if(/(?:\\b(?:US|USA|EN|ENGLISH)\\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);''',
'browser EN edition label')

# Public/static exact-grade prices must always carry provenance, even when the evidence mapping is omitted.
patch('card_grading_valuation.py',
'''    enforce_public_evidence = source_kind == "exact_company_grade_observation" and grade_price_evidence is not None''',
'''    enforce_public_evidence = source_kind == "exact_company_grade_observation"''',
'exact-grade provenance fail-closed')
patch('card_grading_valuation.py',
'''        raw_krw=300_000,\n    )''',
'''        raw_krw=300_000,\n        price_source="user_provided_exact_grade",\n    )''',
'manual example source')
patch('verify_all_legacy_v99.py',
'''        valued=engine.verified_card_valuation('LILLIE SM1M 065/060',pristine,profile,raw_krw=300000)''',
'''        valued=engine.verified_card_valuation('LILLIE SM1M 065/060',pristine,profile,raw_krw=300000,\n                                               price_source='user_provided_exact_grade')''',
'legacy manual valuation source')

# Current runtime gate must execute the new regressions.
patch('verify_current_runtime.py',
'''       "test_card_identity_ambiguity_v320.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),''',
'''       "test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),''',
'current runtime v321 test')
patch('verify_current_runtime.py',
'''payload={"schema_version":1,"engine":"current-main-v320-card-identity-market-failclosed"''',
'''payload={"schema_version":1,"engine":"current-main-v321-edition-consensus-valuation-provenance"''',
'current runtime engine')

print('v321 patch applied')
