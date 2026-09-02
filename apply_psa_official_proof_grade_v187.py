#!/usr/bin/env python3
from pathlib import Path


def patch_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{label}: patch anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    patch_once(
        "manual_official_proof.py",
        '''def _company_in_text(text: Any, company: str) -> bool:\n    upper = _text_upper(text)\n    compact = re.sub(r"[^A-Z0-9.]", "", upper)\n    return any(hint in upper or hint in compact for hint in _COMPANY_HINTS.get(company, (company,)))\n\n\ndef _explicit_grade_candidates(text: Any, company: str) -> set[float]:\n''',
        '''def _company_in_text(text: Any, company: str) -> bool:\n    upper = _text_upper(text)\n    compact = re.sub(r"[^A-Z0-9.]", "", upper)\n    return any(hint in upper or hint in compact for hint in _COMPANY_HINTS.get(company, (company,)))\n\n\ndef _game_from_official_text(text: Any) -> str:\n    upper = _text_upper(text)\n    if any(token in upper for token in ("POKEMON", "POKÉMON", "ポケモン", "포켓몬")):\n        return "pokemon"\n    if any(token in upper for token in ("ONE PIECE", "ONEPIECE", "ワンピース", "원피스")):\n        return "onepiece"\n    if any(token in upper for token in ("NARUTO", "ナルト", "나루토")):\n        return "naruto"\n    return ""\n\n\ndef _explicit_grade_candidates(text: Any, company: str) -> set[float]:\n''',
        "official page game hint",
    )

    patch_once(
        "manual_official_proof.py",
        '''    return found\n\n\ndef _slab_identity_exact(row: dict[str, Any], company: str, cert: str, expected_grade: float) -> bool:\n''',
        '''    return found\n\n\ndef _contextual_grade_candidates(\n    text: Any, company: str, *, company_match: bool, cert_match: bool\n) -> set[float]:\n    """Recover a grader descriptor only after exact official-page identity matched.\n\n    Mobile OCR can read PSA's `GEM MT` and the certification number while\n    dropping or reordering the tiny numeric grade. PSA descriptors themselves\n    map to a single numeric grade, but we only trust that mapping when company\n    and certificate have already matched the same official-page screenshot.\n    Explicit numeric OCR always takes precedence and disables this fallback.\n    """\n    if company != "PSA" or not company_match or not cert_match:\n        return set()\n    upper = _text_upper(text)\n    # Order matters because MINT is a substring of GEM MINT / NEAR MINT.\n    if re.search(r"\\bGEM\\s*(?:MT|MINT)\\b", upper):\n        return {10.0}\n    if re.search(r"\\b(?:NM[\\s-]*MT|NEAR\\s+MINT)\\b", upper):\n        return {8.0}\n    if re.search(r"\\bEX[\\s-]*MT\\b", upper):\n        return {6.0}\n    if re.search(r"\\bMINT\\b", upper):\n        return {9.0}\n    if re.search(r"\\bNM\\b", upper):\n        return {7.0}\n    if re.search(r"\\bEX\\b", upper):\n        return {5.0}\n    return set()\n\n\ndef _slab_identity_exact(row: dict[str, Any], company: str, cert: str, expected_grade: float) -> bool:\n''',
        "PSA descriptor grade fallback",
    )

    patch_once(
        "manual_official_proof.py",
        '''    explicit_grades = _explicit_grade_candidates(text, company)\n    grade_match = (\n        proof_grade is not None and abs(proof_grade - expected_grade) < 1e-9\n    ) or any(abs(value - expected_grade) < 1e-9 for value in explicit_grades)\n''',
        '''    explicit_grades = _explicit_grade_candidates(text, company)\n    contextual_grades: set[float] = set()\n    if proof_grade is None and not explicit_grades:\n        contextual_grades = _contextual_grade_candidates(\n            text, company, company_match=company_match, cert_match=cert_match,\n        )\n    grade_match = (\n        proof_grade is not None and abs(proof_grade - expected_grade) < 1e-9\n    ) or any(abs(value - expected_grade) < 1e-9 for value in explicit_grades) \\\n      or any(abs(value - expected_grade) < 1e-9 for value in contextual_grades)\n''',
        "contextual grade matching",
    )

    patch_once(
        "manual_official_proof.py",
        '''        "slab_grade_fallback": slab_fallback,\n        "explicit_grade_candidates": sorted(explicit_grades),\n        "conflicts": explicit_conflicts,\n''',
        '''        "slab_grade_fallback": slab_fallback,\n        "explicit_grade_candidates": sorted(explicit_grades),\n        "contextual_grade_candidates": sorted(contextual_grades),\n        "conflicts": explicit_conflicts,\n''',
        "contextual grade diagnostics",
    )

    patch_once(
        "manual_official_proof.py",
        '''        "grade_match": match["grade_match"],\n        "slab_grade_fallback": match["slab_grade_fallback"],\n    }\n''',
        '''        "grade_match": match["grade_match"],\n        "slab_grade_fallback": match["slab_grade_fallback"],\n        "contextual_grade_candidates": match.get("contextual_grade_candidates", []),\n        "game_hint": _game_from_official_text(text) if matched else "",\n    }\n''',
        "proof diagnostics game hint",
    )

    patch_once(
        "manual_official_proof.py",
        '''        current.update({\n            "updated_at": now,\n            "manual_official_proof_state": proof_state,\n''',
        '''        official_game_hint = _game_from_official_text(text) if matched else ""\n        current.update({\n            "updated_at": now,\n            "manual_official_proof_state": proof_state,\n''',
        "prepare official game hint",
    )

    patch_once(
        "manual_official_proof.py",
        '''        reasons = _proof_reason_cleanup(set(current.get("quarantine_reasons") or []))\n        if matched:\n''',
        '''        if matched and str(current.get("game") or "").lower() not in manual_photo.GAMES and official_game_hint in manual_photo.GAMES:\n            current["game"] = official_game_hint\n            current["manual_official_proof_game_inferred"] = True\n            current["manual_official_proof_game_evidence"] = "official_page_text"\n        reasons = _proof_reason_cleanup(set(current.get("quarantine_reasons") or []))\n        if matched:\n''',
        "official game recovery",
    )

    patch_once(
        "manual_official_proof.py",
        '''                ("identity_band_psm11", _prepare_page_crop(source, 0.06, 0.72, 2200), 11, False),\n                ("lower_grade_psm11", _prepare_page_crop(source, 0.48, 1.0, 2000), 11, False),\n''',
        '''                ("identity_band_psm11", _prepare_page_crop(source, 0.06, 0.72, 2200), 11, False),\n                ("slab_descriptor_band_psm6", _prepare_page_crop(source, 0.34, 0.84, 2400), 6, False),\n                ("lower_grade_psm11", _prepare_page_crop(source, 0.48, 1.0, 2000), 11, False),\n''',
        "PSA mobile slab descriptor OCR pass",
    )

    print("[OK] v187 PSA official proof patch prepared")


if __name__ == "__main__":
    main()
