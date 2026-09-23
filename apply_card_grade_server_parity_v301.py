from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VALUATION = ROOT / "card_grading_valuation.py"
VERIFY = ROOT / "verify_current_runtime.py"
DELIVERY = ROOT / ".github/workflows/runtime-delivery-guard.yml"
TEST = ROOT / "test_card_grade_server_parity_v301.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


valuation = VALUATION.read_text(encoding="utf-8")
if "canonical_estimate_raw_grade" not in valuation:
    valuation = replace_once(
        valuation,
        "from safe_runtime import env_int, safe_urlopen, validate_public_https_url\n",
        "from safe_runtime import env_int, safe_urlopen, validate_public_https_url\n"
        "from grading_accuracy_v99 import estimate_raw_grade as canonical_estimate_raw_grade\n",
        "canonical grading import",
    )

if "def _condition_score_to_risk" not in valuation:
    valuation = replace_once(
        valuation,
        "def _half_floor(value: float) -> float:\n"
        "    return max(1.0, min(10.0, math.floor(value * 2.0) / 2.0))\n\n\n",
        "def _half_floor(value: float) -> float:\n"
        "    return max(1.0, min(10.0, math.floor(value * 2.0) / 2.0))\n\n\n"
        "def _condition_score_to_risk(value: Any) -> float:\n"
        "    \"\"\"Invert the browser snapshot's 10 - risk*0.09 condition scale.\n\n"
        "    Rounding before the V99 threshold comparison is intentional: a browser\n"
        "    risk of exactly 5 becomes the decimal score 9.55, whose binary float\n"
        "    inverse can otherwise become 4.999999... and cross the PSA 10 boundary.\n"
        "    \"\"\"\n"
        "    score = safe_float(value, 1.0, minimum=1.0, maximum=10.0)\n"
        "    return max(0.0, min(100.0, round((10.0 - score) / 0.09, 6)))\n\n\n",
        "condition score inverse",
    )

pattern = re.compile(
    r"    front, back = card\.centering_front, card\.centering_back\n"
    r"    centering_score = .*?\n"
    r"    if card\.micro_flaws:\n"
    r"        brg = min\(9\.0, brg\)\n",
    re.S,
)
replacement = '''    front, back = card.centering_front, card.centering_back
    # Browser V99 consumes the smaller side of each centering split (0..50),
    # while this public API historically accepts the larger side (50..100).
    # Convert once and route every company through the same canonical V99 core.
    front_small = max(0.0, min(50.0, 100.0 - front))
    back_small = max(0.0, min(50.0, 100.0 - back))

    centering_score = max(1.0, 10.0 - max(front - 50.0, (back - 50.0) * 0.5) * 0.15)
    # Preserve the server's conservative micro-flaw penalty. A single explicit
    # flaw reduces the surface score by 0.5 before conversion to V99 defect risk.
    surface_adjusted = max(1.0, card.surface - card.micro_flaws * 0.5)
    components = (centering_score, card.corners, card.edges, surface_adjusted)
    surface_risk = _condition_score_to_risk(surface_adjusted)
    edge_risk = _condition_score_to_risk(card.edges)
    corner_risk = _condition_score_to_risk(card.corners)
    grades = {
        company: canonical_estimate_raw_grade(
            front_small, back_small, surface_risk, edge_risk, corner_risk, company
        )
        for company in COMPANIES
    }

    # TAG DIG remains an advisory photo-derived score shown as supporting detail.
    # The grade used for cross-checking/pricing is the canonical V99 TAG grade
    # above, so the server cannot silently select a different exact-grade price.
    advisory_score = max(100, min(1000, round(sum(components) * 25.0 - card.micro_flaws * 10.0)))
    tag = tag_score_to_grade(advisory_score)
'''
valuation, count = pattern.subn(replacement, valuation, count=1)
if count != 1:
    raise RuntimeError(f"canonical grading block: expected one replacement, got {count}")

valuation = replace_once(
    valuation,
    '        "grades": {"PSA": psa, "BGS": bgs, "CGC": cgc, "TAG": tag["grade"], "BRG": brg},\n'
    '        "tag": {**tag, "score_kind": "photo_advisory_not_official_DIG"},\n',
    '        "grades": grades,\n'
    '        "tag": {**tag, "canonical_grade": grades["TAG"], "score_kind": "photo_advisory_not_official_DIG"},\n',
    "canonical grade result",
)
valuation = replace_once(
    valuation,
    '            "centering_back_larger_side": back,\n'
    '            "centering": round(centering_score, 2),\n'
    '            "corners": card.corners,\n'
    '            "edges": card.edges,\n'
    '            "surface": card.surface,\n'
    '            "micro_flaws": card.micro_flaws,\n',
    '            "centering_back_larger_side": back,\n'
    '            "centering_front_smaller_side": round(front_small, 4),\n'
    '            "centering_back_smaller_side": round(back_small, 4),\n'
    '            "centering": round(centering_score, 2),\n'
    '            "corners": card.corners,\n'
    '            "edges": card.edges,\n'
    '            "surface": card.surface,\n'
    '            "micro_flaws": card.micro_flaws,\n'
    '            "corner_risk": round(corner_risk, 4),\n'
    '            "edge_risk": round(edge_risk, 4),\n'
    '            "surface_risk": round(surface_risk, 4),\n'
    '            "grading_engine": "grading_accuracy_v99",\n',
    "grade trace components",
)
valuation = replace_once(
    valuation,
    '        "notice": "사진 기반 사전 참고값이며 실제 업체 감정·정가품 판정을 대체하지 않습니다.",\n',
    '        "notice": "사진 기반 V99 공통 사전 참고값이며 실제 업체 감정·정가품 판정을 대체하지 않습니다.",\n',
    "grade notice",
)
VALUATION.write_text(valuation, encoding="utf-8")

TEST.write_text(r'''from __future__ import annotations

import unittest
from pathlib import Path

import card_grading_valuation as valuation
import grading_accuracy_v99 as accuracy

ROOT = Path(__file__).resolve().parent


def score_from_risk(risk: float) -> float:
    return max(1.0, 10.0 - float(risk) * 0.09)


def snapshot(front_small: float, back_small: float, surface: float, edge: float, corner: float, *, micro: int = 0):
    return {
        "centering_front": 100.0 - front_small,
        "centering_back": 100.0 - back_small,
        "corners": score_from_risk(corner),
        "edges": score_from_risk(edge),
        "surface": score_from_risk(surface),
        "micro_flaws": micro,
        "is_authentic": True,
    }


class CardGradeServerParityV301Tests(unittest.TestCase):
    def assert_raw_parity(self, front: float, back: float, surface: float, edge: float, corner: float) -> None:
        result = valuation.estimate_grades(snapshot(front, back, surface, edge, corner))
        self.assertTrue(result["ok"])
        for company in accuracy.COMPANIES:
            expected = accuracy.estimate_raw_grade(front, back, surface, edge, corner, company)
            self.assertEqual(expected, result["grades"][company], (company, front, back, surface, edge, corner))
        self.assertEqual("grading_accuracy_v99", result["components"]["grading_engine"])

    def test_browser_snapshot_defect_boundaries_match_server_v99(self) -> None:
        # Exact threshold vectors catch float inversions such as 9.55 -> 4.999999...
        # that previously let the server return PSA 10 while the browser returned PSA 9.
        for risk in (0, 4.999, 5, 9.999, 10, 15.999, 16, 22.999, 23, 30.999, 31, 39.999, 40, 50, 60, 70, 80, 88, 94, 100):
            with self.subTest(risk=risk):
                self.assert_raw_parity(50, 50, risk, risk, risk)

    def test_centering_and_mixed_defect_vectors_match_server_v99(self) -> None:
        for vector in (
            (45, 25, 0, 0, 0),
            (44, 25, 4, 2, 3),
            (40, 30, 16, 10, 12),
            (35, 15, 23, 31, 16),
            (25, 10, 40, 22, 30),
        ):
            with self.subTest(vector=vector):
                self.assert_raw_parity(*vector)

    def test_explicit_micro_flaw_can_only_make_server_more_conservative(self) -> None:
        clean = valuation.estimate_grades(snapshot(50, 50, 0, 0, 0, micro=0))["grades"]
        flawed = valuation.estimate_grades(snapshot(50, 50, 0, 0, 0, micro=1))["grades"]
        for company in accuracy.COMPANIES:
            self.assertLessEqual(flawed[company], clean[company])
        self.assertLess(flawed["PSA"], 10)

    def test_exact_grade_valuation_uses_same_psa_bucket_as_browser(self) -> None:
        values = snapshot(50, 50, 5, 0, 0)
        result = valuation.verified_card_valuation(
            "boundary card",
            values,
            {"PSA": {"9": 900_000, "10": 1_000_000}},
            price_source="user_provided_exact_grade",
        )
        self.assertEqual(9.0, result["grades"]["PSA"])
        self.assertEqual("9", result["valuations"]["PSA"]["grade_key"])
        self.assertEqual(900_000, result["valuations"]["PSA"]["krw"])

    def test_v301_is_wired_into_current_runtime_and_delivery_gate(self) -> None:
        current = (ROOT / "verify_current_runtime.py").read_text(encoding="utf-8")
        delivery = (ROOT / ".github/workflows/runtime-delivery-guard.yml").read_text(encoding="utf-8")
        self.assertIn("test_card_grade_server_parity_v301.py", current)
        self.assertIn("test_card_grade_server_parity_v301.py", delivery)
        self.assertIn("current-main-v301-card-grade-parity-gated", current)


if __name__ == "__main__":
    unittest.main(verbosity=2)
''', encoding="utf-8")

verify = VERIFY.read_text(encoding="utf-8")
verify = replace_once(
    verify,
    '"test_card_tablet_runtime_v300.py","test_multi_market_price_collector.py",\n',
    '"test_card_tablet_runtime_v300.py","test_card_grade_server_parity_v301.py","test_multi_market_price_collector.py",\n',
    "current runtime card tests",
)
verify = replace_once(
    verify,
    '"engine":"current-main-v300-card-tablet-runtime-gated"',
    '"engine":"current-main-v301-card-grade-parity-gated"',
    "current runtime engine",
)
VERIFY.write_text(verify, encoding="utf-8")

delivery = DELIVERY.read_text(encoding="utf-8")
if "test_card_grade_server_parity_v301.py" not in delivery:
    delivery = delivery.replace(
        "      - 'test_card_tablet_runtime_v300.py'\n",
        "      - 'test_card_tablet_runtime_v300.py'\n      - 'test_card_grade_server_parity_v301.py'\n",
    )
    delivery = replace_once(
        delivery,
        "python -m unittest -v test_card_tablet_runtime_v300.py test_multi_market_price_collector.py test_tablet_runtime_manifest_ui_assets_v254.py",
        "python -m unittest -v test_card_tablet_runtime_v300.py test_card_grade_server_parity_v301.py test_multi_market_price_collector.py test_tablet_runtime_manifest_ui_assets_v254.py",
        "runtime delivery v301 unittest",
    )
    delivery = delivery.replace(
        "test_card_tablet_runtime_v300.py multi_market_price_collector.py",
        "test_card_tablet_runtime_v300.py test_card_grade_server_parity_v301.py multi_market_price_collector.py",
    )
DELIVERY.write_text(delivery, encoding="utf-8")

print("v301 canonical card grade server parity patch applied")
