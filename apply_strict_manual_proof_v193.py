#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one exact match, got {count}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def regex_once(path: str, pattern: str, replacement: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{path}: expected one regex match, got {count}')
    p.write_text(new, encoding='utf-8')


replace_once(
    'manual_official_proof.py',
    '- grade may be recovered from the already OCR-confirmed slab when the official\n  page screenshot does not expose the grade in the current viewport;\n',
    '- grade must be visible or safely derivable from the official-page screenshot itself;\n- slab OCR never substitutes for a missing official-page grade;\n',
)

replace_once(
    'manual_official_proof.py',
    '            "manual_screenshot_grade_may_use_exact_slab_ocr_fallback": True,\n',
    '            "manual_screenshot_grade_may_use_exact_slab_ocr_fallback": False,\n',
)

regex_once(
    'manual_official_proof.py',
    r'\n\ndef _slab_identity_exact\(row: dict\[str, Any\], company: str, cert: str, expected_grade: float\) -> bool:\n.*?\n\ndef _tesseract_page_pass',
    '\n\ndef _tesseract_page_pass',
)

replace_once(
    'manual_official_proof.py',
    '''    slab_fallback = False\n    match_mode = None\n    if company_match and cert_match and grade_match and not explicit_conflicts:\n        match_mode = "official_page_company_cert_grade_ocr"\n    elif company_match and cert_match and not explicit_conflicts:\n        slab_fallback = _slab_identity_exact(row, company, cert, expected_grade)\n        if slab_fallback:\n            match_mode = "official_page_company_cert_plus_exact_slab_ocr_grade"\n\n    missing: list[str] = []\n    if not company_match:\n        missing.append("company")\n    if not cert_match:\n        missing.append("certification_id")\n    if not grade_match and not slab_fallback:\n        missing.append("grade")\n''',
    '''    slab_fallback = False\n    match_mode = None\n    if company_match and cert_match and grade_match and not explicit_conflicts:\n        match_mode = "official_page_company_cert_grade_ocr"\n\n    missing: list[str] = []\n    if not company_match:\n        missing.append("company")\n    if not cert_match:\n        missing.append("certification_id")\n    if not grade_match:\n        missing.append("grade")\n''',
)

replace_once(
    'manual_official_verify_bridge.js',
    " if(row.manual_official_proof_registered)return row.manual_official_proof_match_mode==='official_page_company_cert_plus_exact_slab_ocr_grade'?'공식페이지 인증번호 + 슬랩 등급 OCR 일치 · 공식검증 완료':'공식 페이지 캡처 일치 · 공식검증 완료';\n",
    " if(row.manual_official_proof_registered)return '공식페이지 등급사 + 인증번호 + 등급 일치 · 수동검증 완료';\n",
)

replace_once(
    'manual_official_verify_bridge.js',
    '공식사이트 일치가 확인된 앞면·뒷면은 공식검증 자료로 통합관리하며 card-only ROI 방식의 RAW 결함/등급 보정학습 후보에도 사용합니다.',
    '공식사이트 일치가 확인된 앞면·뒷면은 공식검증 참고자료로 통합관리합니다. 수동 공식검증 캡처는 RAW 등급 보정값에 직접 투입하지 않습니다.',
)

regex_once(
    'test_manual_official_proof.py',
    r'    def test_psa_page_cert_match_can_use_exact_slab_ocr_when_grade_not_in_viewport\(self\):\n.*?(?=    def test_missing_grade_without_exact_slab_ocr_does_not_quarantine)',
    '''    def test_psa_page_cert_match_without_official_grade_stays_pending(self):\n        registry = {"registrations": [row_template()]}\n        evidence = {"company": "PSA", "grade": None, "certification_id": "160600294"}\n        text = "PSA PSACARD.COM/CERT/160600294 #160600294 2026 ONE PIECE MONKEY D LUFFY"\n        with self._patch_common(registry, evidence, text), \\\n             mock.patch.object(proof.manual_photo, "_save_registry"), \\\n             mock.patch.object(proof, "_claim_proof_upload"), \\\n             mock.patch.object(proof, "atomic_write_bytes"), \\\n             mock.patch.object(proof, "_append_reference") as append_reference, \\\n             mock.patch.object(proof, "_remove_proof_file"):\n            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})\n        self.assertFalse(result["accepted"], result)\n        self.assertFalse(result["proof"]["slab_grade_fallback"], result)\n        self.assertIn("grade", result["proof"]["missing"], result)\n        self.assertFalse(registry["registrations"][0]["official_result"])\n        append_reference.assert_not_called()\n\n''',
)

regex_once(
    'test_manual_official_proof.py',
    r'    def test_card_number_or_cost_does_not_create_false_grade_conflict\(self\):\n.*?(?=    def test_conflicting_new_proof_does_not_downgrade_existing_valid_reference)',
    '''    def test_card_number_or_cost_does_not_create_false_grade_acceptance(self):\n        registry = {"registrations": [row_template()]}\n        evidence = {"company": "PSA", "grade": 4.0, "certification_id": "160600294"}\n        text = "PSA PSACARD.COM/CERT/160600294 #160600294 #055 4 ONE PIECE"\n        with self._patch_common(registry, evidence, text), \\\n             mock.patch.object(proof.manual_photo, "_save_registry"), \\\n             mock.patch.object(proof, "_claim_proof_upload"), \\\n             mock.patch.object(proof, "atomic_write_bytes"), \\\n             mock.patch.object(proof, "_append_reference") as append_reference, \\\n             mock.patch.object(proof, "_remove_proof_file"):\n            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})\n        self.assertFalse(result["accepted"], result)\n        self.assertFalse(result["proof"]["slab_grade_fallback"], result)\n        self.assertIn("grade", result["proof"]["missing"], result)\n        append_reference.assert_not_called()\n\n''',
)

replace_once(
    'test_manual_official_proof.py',
    '        self.assertTrue(policy["manual_screenshot_grade_may_use_exact_slab_ocr_fallback"])\n',
    '        self.assertFalse(policy["manual_screenshot_grade_may_use_exact_slab_ocr_fallback"])\n',
)

replace_once(
    'test_manual_only_official_verification_v192.py',
    "        self.assertIn('\"automatic_live_lookup_used\": False',source)\n",
    "        self.assertIn('\"automatic_live_lookup_used\": False',source)\n        self.assertIn('\"manual_screenshot_grade_may_use_exact_slab_ocr_fallback\": False',source)\n        self.assertNotIn('def _slab_identity_exact(',source)\n",
)

print('[OK] strict manual official proof v193 applied')
