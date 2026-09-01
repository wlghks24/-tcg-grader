#!/usr/bin/env python3
from pathlib import Path

py = Path('pending_official_candidate_v161.py')
text = py.read_text(encoding='utf-8')
text = text.replace(
    'ENGINE = "v162-pending-official-candidate-manual-verification"',
    'ENGINE = "v163-pending-official-candidate-manual-verification"',
)

negative_tail = '    re.compile(r"(?:certificate|certification|cert(?:ificate)?\\s*number)\\s+(?:was\\s+)?not\\s+found", re.I),\n)\n'
site_block = '''    re.compile(r"(?:certificate|certification|cert(?:ificate)?\\s*number)\\s+(?:was\\s+)?not\\s+found", re.I),
    re.compile(r"(?:検索|照会).*?(?:結果|記録).*?(?:ありません|見つかりません)", re.I),
    re.compile(r"(?:查無|找不到|沒有).*?(?:紀錄|記錄|結果|認證|认证)", re.I),
)
_SITE_ERROR_PATTERNS = (
    re.compile(r"application\\s+error", re.I),
    re.compile(r"server[-\\s]*side\\s+exception", re.I),
    re.compile(r"internal\\s+server\\s+error", re.I),
    re.compile(r"service\\s+unavailable", re.I),
    re.compile(r"\\bdigest\\s*:\\s*\\d+", re.I),
    re.compile(r"서버\\s*(?:오류|에러)", re.I),
)
'''
if '_SITE_ERROR_PATTERNS' not in text:
    if negative_tail not in text:
        raise SystemExit('negative pattern marker not found')
    text = text.replace(negative_tail, site_block, 1)

old = '    negative = any(pattern.search(raw) for pattern in _NEGATIVE_PATTERNS)\n    upper = raw.upper()\n'
new = '    negative = any(pattern.search(raw) for pattern in _NEGATIVE_PATTERNS)\n    site_error = any(pattern.search(raw) for pattern in _SITE_ERROR_PATTERNS)\n    upper = raw.upper()\n'
if 'site_error = any(pattern.search(raw)' not in text:
    if old not in text:
        raise SystemExit('negative OCR marker not found')
    text = text.replace(old, new, 1)

old = '        "negative_text_detected": negative,\n        "company_brand_detected": brand,\n        "ocr_text": raw[:1800],\n'
new = '        "negative_text_detected": negative,\n        "company_brand_detected": brand,\n        "site_error_detected": site_error,\n        "ocr_text": raw[:1800],\n'
if '"site_error_detected": site_error' not in text:
    if old not in text:
        raise SystemExit('negative OCR return marker not found')
    text = text.replace(old, new, 1)

gate_marker = '    signal = _negative_ocr(text, evidence, company)\n\n    rejected_at = _now()\n'
gate = '''    signal = _negative_ocr(text, evidence, company)
    if signal.get("site_error_detected"):
        proof_path.unlink(missing_ok=True)
        raise ValueError("공식사이트 서버 오류 화면은 '조회결과 없음' 증거가 아닙니다. 후보는 유지됩니다. 잠시 후 공식사이트에서 다시 확인하세요.")
    if not signal.get("negative_text_detected"):
        proof_path.unlink(missing_ok=True)
        raise ValueError("공식사이트에 '조회 결과 없음/인증번호 없음' 문구가 확인된 화면만 후보삭제에 사용할 수 있습니다.")
    if not signal.get("company_brand_detected"):
        proof_path.unlink(missing_ok=True)
        raise ValueError("공식 등급사 화면임을 확인할 수 없습니다. 등급사 로고/명칭과 조회결과 없음 문구가 함께 보이도록 캡처하세요.")

    rejected_at = _now()
'''
if '공식사이트 서버 오류 화면은' not in text:
    if gate_marker not in text:
        raise SystemExit('negative proof gate marker not found')
    text = text.replace(gate_marker, gate, 1)

py.write_text(text, encoding='utf-8')

js = Path('pending_official_candidate_bridge_v161.js')
text = js.read_text(encoding='utf-8')
old = "function bgsDirect(url,cert,company){if(String(company||'').toUpperCase()!=='BGS')return url;try{const u=new URL(url,location.href);u.searchParams.set('flag','1');u.searchParams.set('item_id',cert);u.searchParams.set('item_type','BGS');return u.toString()}catch(_){return url}}"
new = "function officialOpenUrl(url,cert,company){const c=String(company||'').toUpperCase();if(c==='BRG')return 'https://www.brgcard.com/certification';if(c!=='BGS')return url;try{const u=new URL(url,location.href);u.searchParams.set('flag','1');u.searchParams.set('item_id',cert);u.searchParams.set('item_type','BGS');return u.toString()}catch(_){return url}}"
if 'function officialOpenUrl(' not in text:
    if old not in text:
        raise SystemExit('BGS direct helper marker not found')
    text = text.replace(old, new, 1)
text = text.replace(
    "const url=bgsDirect(String(row.official_reference_url||''),cert,row.company);",
    "const url=officialOpenUrl(String(row.official_reference_url||''),cert,row.company);",
)
old_note = '공식 등급사 사이트에서 확인한 뒤 <b>② 갤러리에서 확인화면 선택</b>으로 저장된 캡처를 고르세요. 선택한 캡처는 화면 자동갱신 중에도 유지되며 <b>③ 검증완료 등록</b>과 <b>④ 조회결과 없음 → 후보삭제</b>가 활성화됩니다.'
new_note = old_note + ' <b>BRG 안내:</b> 인증번호가 포함된 직접 URL에서 서버 오류가 날 수 있어 BRG는 조회 폼만 열고 인증번호를 자동복사합니다. 붙여넣어 조회하세요. <b>Application error / server-side exception / Digest 화면은 조회결과 없음이 아니므로 ④로 삭제하지 마세요.</b>'
if 'Application error / server-side exception / Digest' not in text:
    if old_note not in text:
        raise SystemExit('UI note marker not found')
    text = text.replace(old_note, new_note, 1)
js.write_text(text, encoding='utf-8')

Path('test_brg_manual_server_error_v163.py').write_text('''import unittest\nfrom pathlib import Path\nimport pending_official_candidate_v161 as pending\n\nclass Tests(unittest.TestCase):\n    def test_server_error_not_no_record(self):\n        s=pending._negative_ocr("Application error: a server-side exception has occurred. Digest: 3089131211",{},"BRG")\n        self.assertTrue(s["site_error_detected"])\n        self.assertFalse(s["negative_text_detected"])\n    def test_no_record(self):\n        s=pending._negative_ocr("BRG no records found",{},"BRG")\n        self.assertFalse(s["site_error_detected"])\n        self.assertTrue(s["negative_text_detected"])\n        self.assertTrue(s["company_brand_detected"])\n    def test_brg_form_url(self):\n        src=Path("pending_official_candidate_bridge_v161.js").read_text(encoding="utf-8")\n        self.assertIn("if(c==='BRG')return 'https://www.brgcard.com/certification'",src)\n        self.assertIn("Application error / server-side exception / Digest",src)\n        self.assertNotIn("const url=bgsDirect(",src)\n\nif __name__=='__main__': unittest.main()\n''', encoding='utf-8')

print('[OK] BRG manual verification server-error patch v163 applied')
