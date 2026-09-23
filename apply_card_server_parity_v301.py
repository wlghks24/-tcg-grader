from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
VALUATION = ROOT / "card_grading_valuation.py"
CURRENT = ROOT / "verify_current_runtime.py"
DELIVERY = ROOT / ".github/workflows/runtime-delivery-guard.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_valuation() -> None:
    text = VALUATION.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from safe_runtime import env_int, safe_urlopen, validate_public_https_url\n",
        "from safe_runtime import env_int, safe_urlopen, validate_public_https_url\nimport grading_accuracy_v99 as grading_v99\n",
        "canonical grading import",
    )

    helper_anchor = "def _half_floor(value: float) -> float:\n    return max(1.0, min(10.0, math.floor(value * 2.0) / 2.0))\n\n\n"
    helper_block = """def _half_floor(value: float) -> float:\n    return max(1.0, min(10.0, math.floor(value * 2.0) / 2.0))\n\n\ndef _component_score_to_v99_risk(value: Any) -> float:\n    \"\"\"Invert the browser's score=max(1, 10-risk*0.09) mapping fail-closed.\"\"\"\n    score = safe_float(value, 1.0, minimum=1.0, maximum=10.0)\n    if score <= 1.0:\n        return 100.0\n    return max(0.0, min(100.0, (10.0 - score) / 0.09))\n\n\ndef _tag_advisory_from_grade(grade: float) -> dict[str, Any]:\n    \"\"\"Keep the legacy advisory TAG object aligned with the canonical numeric grade.\"\"\"\n    matches = [row for row in TAG_SCALE if math.isclose(float(row[1]), float(grade), abs_tol=1e-9)]\n    if not matches:\n        return {\"score\": 100, \"grade\": 1.0, \"condition\": \"POOR\"}\n    # Numeric TAG 10 can be Gem Mint or Pristine. Do not overclaim Pristine from a photo.\n    threshold, numeric, condition = min(matches, key=lambda row: row[0])\n    return {\"score\": int(threshold), \"grade\": float(numeric), \"condition\": condition}\n\n\n"""
    text = replace_once(text, helper_anchor, helper_block, "risk inversion helpers")

    pattern = re.compile(
        r"def estimate_grades\(values: Mapping\[str, Any\]\) -> dict\[str, Any\]:\n.*?\n\ndef _card_name",
        re.S,
    )
    replacement = '''def estimate_grades(values: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate five grades with the same canonical V99 core used by the browser.

    Browser snapshots store centering as the larger side of the ratio and
    corner/edge/surface quality as score=max(1, 10-risk*0.09).  Reconstruct the
    underlying V99 inputs here instead of running a second, divergent heuristic.
    A separate micro-flaw floor preserves the previous server's conservative
    behavior for direct/manual callers.
    """
    if not isinstance(values, Mapping):
        return {"ok": False, "status": "FAILED", "reason": "카드 분석자료 형식 오류", "grades": {}}
    required = ("centering_front", "centering_back", "corners", "edges", "surface", "micro_flaws", "is_authentic")
    missing = [name for name in required if name not in values or values.get(name) is None]
    if missing:
        return {"ok": False, "status": "FAILED", "reason": "카드 분석자료 부족: " + ", ".join(missing), "grades": {}}
    card = GradeInputs.from_mapping(values)
    if not card.authentic:
        return {"ok": False, "status": "FAILED", "reason": "가품 의심 또는 진위 확인 실패", "grades": {}}

    front_larger, back_larger = card.centering_front, card.centering_back
    front_worst = max(0.0, min(50.0, 100.0 - front_larger))
    back_worst = max(0.0, min(50.0, 100.0 - back_larger))
    corner_risk = _component_score_to_v99_risk(card.corners)
    edge_risk = _component_score_to_v99_risk(card.edges)
    surface_risk = _component_score_to_v99_risk(card.surface)
    # The legacy server subtracted 0.5 surface points per micro flaw. Express
    # the same conservative penalty on V99's 0..100 risk scale.
    micro_flaw_risk = min(100.0, card.micro_flaws * (0.5 / 0.09))
    surface_risk = max(surface_risk, micro_flaw_risk)

    grades = {
        company: grading_v99.estimate_raw_grade(
            front_worst, back_worst, surface_risk, edge_risk, corner_risk, company
        )
        for company in COMPANIES
    }
    tag = _tag_advisory_from_grade(float(grades["TAG"]))

    return {
        "ok": True,
        "status": "SUCCESS",
        "grades": grades,
        "tag": {**tag, "score_kind": "photo_advisory_not_official_DIG"},
        "components": {
            "centering_front_larger_side": front_larger,
            "centering_back_larger_side": back_larger,
            "centering_front_worst_side": round(front_worst, 4),
            "centering_back_worst_side": round(back_worst, 4),
            "corners": card.corners,
            "edges": card.edges,
            "surface": card.surface,
            "corner_risk": round(corner_risk, 4),
            "edge_risk": round(edge_risk, 4),
            "surface_risk": round(surface_risk, 4),
            "micro_flaws": card.micro_flaws,
        },
        "grading_engine": "v99-canonical-server",
        "official_grade": False,
        "notice": "사진 기반 사전 참고값이며 실제 업체 감정·정가품 판정을 대체하지 않습니다.",
    }


def _card_name'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"estimate_grades replacement failed: {count}")
    VALUATION.write_text(text, encoding="utf-8")


def patch_current_runtime() -> None:
    text = CURRENT.read_text(encoding="utf-8")
    old = '       "test_card_tablet_runtime_v300.py","test_multi_market_price_collector.py",\n'
    new = '       "test_card_tablet_runtime_v300.py","test_card_server_parity_v301.py","test_multi_market_price_collector.py",\n'
    text = replace_once(text, old, new, "current runtime v301 gate")
    CURRENT.write_text(text, encoding="utf-8")


def patch_delivery_workflow() -> None:
    text = DELIVERY.read_text(encoding="utf-8")
    path_anchor = "      - 'test_card_tablet_runtime_v300.py'\n"
    path_replacement = path_anchor + "      - 'test_card_server_parity_v301.py'\n"
    if "      - 'test_card_server_parity_v301.py'\n" not in text:
        count = text.count(path_anchor)
        if count != 2:
            raise SystemExit(f"delivery path anchors: expected 2, found {count}")
        text = text.replace(path_anchor, path_replacement)
    text = replace_once(
        text,
        "          python -m unittest -v test_card_tablet_runtime_v300.py test_multi_market_price_collector.py test_tablet_runtime_manifest_ui_assets_v254.py\n",
        "          python -m unittest -v test_card_tablet_runtime_v300.py test_card_server_parity_v301.py test_multi_market_price_collector.py test_tablet_runtime_manifest_ui_assets_v254.py\n",
        "delivery test execution",
    )
    text = replace_once(
        text,
        "verify_current_runtime.py test_card_regression_gate_v299.py test_card_tablet_runtime_v300.py multi_market_price_collector.py",
        "verify_current_runtime.py test_card_regression_gate_v299.py test_card_tablet_runtime_v300.py test_card_server_parity_v301.py multi_market_price_collector.py",
        "delivery py_compile",
    )
    DELIVERY.write_text(text, encoding="utf-8")


def main() -> None:
    patch_valuation()
    patch_current_runtime()
    patch_delivery_workflow()
    print("v301 canonical card server parity patch applied")


if __name__ == "__main__":
    main()
