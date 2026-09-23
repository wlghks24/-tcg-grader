from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise SystemExit(f'{path.name}: expected one match, found {text.count(old)}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


valuation = ROOT / 'card_grading_valuation.py'
replace_once(
    valuation,
    'import ast\nfrom dataclasses import dataclass\n',
    'import ast\nimport datetime as dt\nfrom dataclasses import dataclass\n',
)
replace_once(
    valuation,
'''def _clean_grade_price_evidence(value: Any) -> dict[str, str] | None:\n    # Validate provenance attached to one exact company+grade observation.\n    if not isinstance(value, Mapping) or len(value) > 12:\n        return None\n    source = str(value.get("source") or "").strip()\n    try:\n        parsed = urllib.parse.urlsplit(source)\n    except ValueError:\n        return None\n    if parsed.scheme != "https" or not parsed.hostname:\n        return None\n    price_type = str(value.get("price_type") or "").strip()\n    if price_type not in {"sold", "auction_result", "official_example", "market_guide", "user_provided"}:\n        return None\n    observed_on = str(value.get("observed_on") or "").strip()\n    observed_period = str(value.get("observed_period") or "").strip()\n    if not observed_on and not observed_period:\n        return None\n    result = {"source": source[:500], "price_type": price_type}\n    if observed_on:\n        result["observed_on"] = observed_on[:32]\n    if observed_period:\n        result["observed_period"] = observed_period[:32]\n    label = " ".join(str(value.get("label") or "").split())[:180]\n    if label:\n        result["label"] = label\n    return result\n''',
'''def _clean_grade_price_evidence(value: Any) -> dict[str, str] | None:\n    # Validate provenance attached to one exact public company+grade observation.\n    if not isinstance(value, Mapping) or len(value) > 12:\n        return None\n    source = str(value.get("source") or "").strip()\n    try:\n        validate_public_https_url(source)\n    except (TypeError, ValueError):\n        return None\n    price_type = str(value.get("price_type") or "").strip()\n    if price_type not in {"sold", "auction_result", "official_example", "market_guide"}:\n        return None\n    observed_on = str(value.get("observed_on") or "").strip()\n    observed_period = str(value.get("observed_period") or "").strip()\n    if observed_on:\n        try:\n            dt.date.fromisoformat(observed_on)\n        except ValueError:\n            return None\n    elif observed_period:\n        if not re.fullmatch(r"\\d{4}-\\d{2}", observed_period):\n            return None\n        try:\n            dt.date.fromisoformat(observed_period + "-01")\n        except ValueError:\n            return None\n    else:\n        return None\n    result = {"source": source[:500], "price_type": price_type}\n    if observed_on:\n        result["observed_on"] = observed_on[:32]\n    if observed_period:\n        result["observed_period"] = observed_period[:32]\n    label = " ".join(str(value.get("label") or "").split())[:180]\n    if label:\n        result["label"] = label\n    return result\n''',
)
replace_once(
    valuation,
    '    enforce_public_evidence = source_kind == "exact_company_grade_observation" and grade_price_evidence is not None\n',
    '    enforce_public_evidence = source_kind == "exact_company_grade_observation"\n',
)

gate = ROOT / 'collection_verification_gate.py'
replace_once(
    gate,
    'import multi_route_event_discovery\n',
    'import multi_route_event_discovery\nfrom safe_runtime import validate_public_https_url\n',
)
replace_once(
    gate,
'''def _valid_public_https(url: Any) -> bool:\n    try:\n        parsed = urlparse(str(url or ""))\n    except ValueError:\n        return False\n    host = (parsed.hostname or "").lower().rstrip(".")\n    if parsed.scheme != "https" or not host or host in {"localhost", "127.0.0.1", "::1"}:\n        return False\n    return True\n''',
'''def _valid_public_https(url: Any) -> bool:\n    try:\n        validate_public_https_url(str(url or ""))\n    except (TypeError, ValueError):\n        return False\n    return True\n''',
)

test = ROOT / 'test_card_core_provenance_v297.py'
test.write_text(r'''from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import card_grading_valuation as valuation
import collection_verification_gate as gate

ROOT = Path(__file__).resolve().parent


class CardCoreProvenanceV297Tests(unittest.TestCase):
    @staticmethod
    def pristine():
        return {
            "centering_front": 50, "centering_back": 50, "corners": 10,
            "edges": 10, "surface": 10, "micro_flaws": 0, "is_authentic": True,
        }

    def test_public_exact_price_without_evidence_object_fails_closed(self):
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence=None,
            price_source="exact_company_grade_observation",
            exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertFalse(row["available"])
        self.assertIsNone(row["krw"])
        self.assertFalse(row["evidence_verified"])
        self.assertIn("근거 부족", row["reason"])

    def test_public_evidence_rejects_private_or_local_urls(self):
        for source in (
            "https://localhost/sold/1",
            "https://127.0.0.1/sold/1",
            "https://10.0.0.1/sold/1",
            "https://192.168.1.5/sold/1",
            "https://user:pass@example.com/sold/1",
        ):
            with self.subTest(source=source):
                result = valuation.verified_card_valuation(
                    "test", self.pristine(), {"PSA": {"10": 123456}},
                    grade_price_evidence={"PSA": {"10": {
                        "source": source, "price_type": "sold", "observed_on": "2026-09-22"
                    }}},
                    price_source="exact_company_grade_observation",
                    exchange_rate=1400,
                )
                self.assertFalse(result["valuations"]["PSA"]["available"])
                self.assertFalse(result["valuations"]["PSA"]["evidence_verified"])
                self.assertFalse(gate._valid_public_https(source))

    def test_public_evidence_rejects_invalid_observation_time(self):
        bad_rows = (
            {"observed_on": "yesterday"},
            {"observed_on": "2026-02-31"},
            {"observed_period": "2026-13"},
            {"observed_period": "Sep-2026"},
        )
        for extra in bad_rows:
            with self.subTest(extra=extra):
                evidence = {"source": "https://example.com/sold/1", "price_type": "sold", **extra}
                result = valuation.verified_card_valuation(
                    "test", self.pristine(), {"PSA": {"10": 123456}},
                    grade_price_evidence={"PSA": {"10": evidence}},
                    price_source="exact_company_grade_observation",
                    exchange_rate=1400,
                )
                self.assertFalse(result["valuations"]["PSA"]["available"])

    def test_user_provided_price_type_cannot_be_promoted_to_public_verified(self):
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence={"PSA": {"10": {
                "source": "https://example.com/manual/1",
                "price_type": "user_provided",
                "observed_on": "2026-09-22",
            }}},
            price_source="exact_company_grade_observation",
            exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertFalse(row["available"])
        self.assertFalse(row["evidence_verified"])

    def test_valid_public_exact_grade_evidence_still_works(self):
        result = valuation.verified_card_valuation(
            "test", self.pristine(), {"PSA": {"10": 123456}},
            grade_price_evidence={"PSA": {"10": {
                "source": "https://example.com/sold/1",
                "price_type": "sold",
                "observed_on": "2026-09-22",
            }}},
            price_source="exact_company_grade_observation",
            exchange_rate=1400,
        )
        row = result["valuations"]["PSA"]
        self.assertTrue(row["available"])
        self.assertEqual(123456, row["krw"])
        self.assertTrue(row["evidence_verified"])

    def test_static_market_gate_remains_clean(self):
        findings = []
        summary = gate._audit_market(ROOT, dt.datetime.now(dt.timezone.utc), findings)
        self.assertEqual(0, summary["invalid_graded_price_evidence"])
        self.assertFalse(any(x.get("code") == "INVALID_GRADED_PRICE_EVIDENCE" for x in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
''', encoding='utf-8')

print('v297 patch prepared')
