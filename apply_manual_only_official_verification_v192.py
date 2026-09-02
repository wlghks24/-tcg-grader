#!/usr/bin/env python3
from pathlib import Path
import re


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing patch marker: {label}')
    if text.count(old) != 1:
        raise SystemExit(f'non-unique patch marker: {label} ({text.count(old)})')
    return text.replace(old, new, 1)


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')

# 1) Global hard guard: no environment override can turn automatic grader lookup back on.
p=Path('grading_cert_verifier.py'); text=p.read_text(encoding='utf-8')
text=replace_once(text,
'''def automatic_lookup_disabled() -> bool:\n    value = str(os.environ.get(DISABLE_AUTO_LOOKUP_ENV, "1") or "1").strip().lower()\n    return value not in {"0", "false", "no", "off"}\n''',
'''def automatic_lookup_disabled() -> bool:\n    """v192: official certification verification is always user-browser/manual.\n\n    The application may still build the official URL, but it must never request\n    PSA/BGS/CGC/TAG/BRG certification pages programmatically.  Keeping this as\n    a hard guard prevents a stale environment variable from silently re-enabling\n    the error-prone automatic path on Android/Termux.\n    """\n    return True\n''','global hard manual guard')
text=text.replace('Automatic official-site requests are disabled by default.', 'Automatic official-site requests are permanently disabled in normal application code.')
text=text.replace('Set TCG_DISABLE_AUTO_GRADER_LOOKUP=0 only for an explicitly supervised diagnostic\nsession; normal collection/registration must leave it disabled.', 'All certification confirmation uses the user-browser screenshot workflow; environment\nvariables cannot re-enable automatic certification requests.')
write(p,text)

# 2) Manual slab registration: resolve OCR identity locally, then always wait for manual official screenshot.
p=Path('manual_graded_photo_registration.py'); text=p.read_text(encoding='utf-8')
text=text.replace('from grading_cert_verifier import lookup_url, verify_cert', 'from grading_cert_verifier import lookup_url')
text=text.replace('from server_security_guard import OFFICIAL_LOOKUP_GUARD\n', '')
start='    allowed, guard = OFFICIAL_LOOKUP_GUARD.claim(resolved_company)\n'
end='    return {"ok": True, "deferred": provider_blocked, "registration": _public_row(current)}\n'
if start not in text or end not in text:
    raise SystemExit('manual registration automatic lookup block not found')
a=text.index(start); b=text.index(end,a)+len(end)
manual_block='''    # v192: company/certificate/grade identity is only a queue key.  Do not call\n    # the grading-company website from the server.  The user must open the\n    # official page in a browser, verify the cert, attach the result screenshot,\n    # and explicitly complete verification through manual_official_proof.py.\n    with LOCK:\n        registry = _registry()\n        index, current = _find_row(registry, registration_id)\n        current.update({\n            "updated_at": _now(),\n            "status": "pending_official_verification",\n            "verification_state": "manual_official_verification_required",\n            "official_result": False,\n            "official_grade": None,\n            "official_reference_url": lookup_url(resolved_company, resolved_cert),\n            "learning_eligibility": "manual_official_proof_required",\n            "training_eligible": False,\n            "raw_grade_calibration_eligible": False,\n            "retry_after_seconds": None,\n            "company": resolved_company,\n            "claimed_grade": resolved_grade,\n            "certification_id": resolved_cert,\n            "missing_identity_fields": [],\n            "ocr_label_text": text[:1800],\n            "ocr_error": ocr_error,\n            "ocr_diagnostics": diagnostics,\n            "ocr_cached_sha256": row.get("image_sha256"),\n            "ocr_cache_hit": ocr_cache_hit,\n            "ocr_company": ocr_company or None,\n            "ocr_grade": ocr_grade,\n            "ocr_certification_id": ocr_cert or None,\n            "manual_official_proof_required": True,\n            "automatic_official_lookup_used": False,\n        })\n        reasons = set(current.get("quarantine_reasons") or [])\n        reasons.discard("official_lookup_not_confirmed")\n        reasons.discard("official_provider_blocked")\n        reasons.add("manual_official_proof_required")\n        current["quarantine_reasons"] = sorted(reasons)\n        registry["registrations"][index] = current\n        _save_registry(registry)\n    _record_collection_gap(current)\n    return {\n        "ok": True, "deferred": True, "manual_official_proof_required": True,\n        "automatic_official_lookup_used": False,\n        "registration": _public_row(current),\n    }\n'''
text=text[:a]+manual_block+text[b:]
text=text.replace('"client_preview_training_eligible", "photo_revalidation",\n', '"client_preview_training_eligible", "photo_revalidation", "manual_official_proof_required",\n')
text=text.replace('"raw_and_slab_learning_isolated": True,\n', '"raw_and_slab_learning_isolated": True,\n            "automatic_official_lookup_enabled": False,\n            "manual_official_screenshot_required": True,\n')
write(p,text)

# 3) Manual official proof: exact official-page screenshot becomes the final official reference.
p=Path('manual_official_proof.py'); text=p.read_text(encoding='utf-8')
text=text.replace('The screenshot is reference-only evidence: it never sets\nofficial_result=True and never enters RAW grade calibration.', 'The screenshot is the authoritative official-reference evidence after exact\ncompany + certificate + grade matching. It sets official_result=True but never\nenters RAW grade calibration.')
text=replace_once(text,'"manual_screenshot_sets_official_result": False,','"manual_screenshot_sets_official_result": True,','manual proof policy official')
text=replace_once(text,'"later_live_official_lookup_can_promote": True,','"later_live_official_lookup_can_promote": False,\n            "automatic_live_lookup_used": False,\n            "verification_is_manual_only": True,','manual proof policy live lookup')
text=replace_once(text,'"official_result": False,\n        "manual_official_proof_matched": True,\n        "learning_eligibility": "reference_only_pending_live_official_verification",','"official_result": True,\n        "manual_official_proof_matched": True,\n        "learning_eligibility": "official_reference_manual_screenshot",','reference row official')
text=replace_once(text,'"manual_proof_is_live_official_truth": False,\n            "raw_calibration_allowed": False,\n            "later_live_lookup_required_for_official_result": True,','"manual_proof_is_live_official_truth": True,\n            "raw_calibration_allowed": False,\n            "later_live_lookup_required_for_official_result": False,\n            "automatic_live_lookup_used": False,','reference policy')
old='''            "official_reference_url": current.get("official_reference_url") or lookup_url(company, cert),\n            "official_result": False,\n            "training_eligible": False,\n            "raw_grade_calibration_eligible": False,\n'''
new='''            "official_reference_url": current.get("official_reference_url") or lookup_url(company, cert),\n            "official_result": bool(matched),\n            "official_grade": expected_grade if matched else None,\n            "official_verification_method": "user_browser_official_page_exact_screenshot" if matched else None,\n            "official_verified_at": now if matched else None,\n            "training_eligible": bool(matched),\n            "raw_grade_calibration_eligible": False,\n            "automatic_official_lookup_used": False,\n'''
text=replace_once(text,old,new,'manual proof row result')
old='''            reasons.discard("official_lookup_not_confirmed")\n            reasons.add("manual_official_page_proof_only")\n            reasons.add("live_official_lookup_pending")\n            current.update({\n                "status": "manual_official_reference",\n                "verification_state": "manual_official_proof_matched",\n                "learning_eligibility": "reference_only_pending_live_official_verification",\n            })\n'''
new='''            reasons.discard("official_lookup_not_confirmed")\n            reasons.discard("manual_official_proof_required")\n            reasons.discard("manual_official_page_proof_only")\n            reasons.discard("live_official_lookup_pending")\n            current.update({\n                "status": "verified_reference",\n                "verification_state": "manual_official_verified",\n                "learning_eligibility": "official_reference_manual_screenshot",\n                "manual_official_proof_required": False,\n            })\n'''
text=replace_once(text,old,new,'manual proof matched state')
write(p,text)

# 4) Candidate collector: existing verified registry may match, but never launch a live cert request.
p=Path('graded_photo_multi_source.py'); text=p.read_text(encoding='utf-8')
old='''def _official_verify_rows(rows:list[dict],registry:dict,max_live:int=10)->tuple[list[dict],dict]:\n cache=_load(OFFICIAL_CACHE,{})\n entries=cache.get('entries',{}) if isinstance(cache.get('entries'),dict) else {}\n now=time.time();live=0;stats={'''
new='''def _official_verify_rows(rows:list[dict],registry:dict,max_live:int=10)->tuple[list[dict],dict]:\n # v192: runtime candidate collection is manual-only.  Previously cached live\n # lookup responses are intentionally ignored so an old automatic response\n # cannot promote a new candidate after this policy change.\n cache={}\n entries={}\n max_live=0\n now=time.time();live=0;stats={'''
text=replace_once(text,old,new,'collector manual-only header')
text=text.replace(" live_targets=set(_balanced_official_verification_indices(rows,eligible,max_live))", " live_targets=set()  # v192 manual-only: no automatic official HTTP requests")
write(p,text)

# 5) Main manual UI: three explicit user actions; selecting a screenshot no longer submits automatically.
p=Path('manual_official_verify_bridge.js'); text=p.read_text(encoding='utf-8')
text=replace_once(text,'let summaryObserverInstalled=false;','let summaryObserverInstalled=false;\nconst proofDrafts=new Map();','proof draft map')
text=text.replace('.gpd-official-actions{display:grid;grid-template-columns:auto auto auto;', '.gpd-official-actions{display:grid;grid-template-columns:auto auto auto auto;')
text=text.replace('.gpd-official-open,.gpd-official-proof,.gpd-official-delete,.gpd-recent-delete{', '.gpd-official-open,.gpd-official-proof,.gpd-official-submit,.gpd-official-delete,.gpd-recent-delete{')
text=text.replace('.gpd-official-proof{background:#0f766e;color:#fff;margin:0;width:auto}', '.gpd-official-proof{background:#2563eb;color:#fff;margin:0;width:auto}.gpd-official-submit{background:#0f766e;color:#fff;margin:0;width:auto;cursor:pointer}.gpd-official-submit:disabled{opacity:.38;cursor:not-allowed}')
text=text.replace('.gpd-official-open,.gpd-official-proof,.gpd-official-delete{width:100%}', '.gpd-official-open,.gpd-official-proof,.gpd-official-submit,.gpd-official-delete{width:100%}')
old='<a class="gpd-official-open" href="${esc(row.official_reference_url)}" target="_blank" rel="noopener noreferrer">① 공식조회 열기</a><label class="gpd-official-proof">② 확인화면 등록<input class="gpd-official-file" type="file" accept="image/jpeg,image/png" data-proof="${esc(row.registration_id)}"></label><button type="button" class="gpd-official-delete" data-delete-registration="${esc(row.registration_id)}">🗑 잘못등록 삭제/취소</button>'
new='<a class="gpd-official-open" href="${esc(row.official_reference_url)}" target="_blank" rel="noopener noreferrer">① 공식조회 열기</a><label class="gpd-official-proof">② 확인화면 선택<input class="gpd-official-file" type="file" accept="image/jpeg,image/png" data-proof="${esc(row.registration_id)}"></label><button type="button" class="gpd-official-submit" data-submit-proof="${esc(row.registration_id)}" disabled>③ 검증완료 등록</button><button type="button" class="gpd-official-delete" data-delete-registration="${esc(row.registration_id)}">🗑 잘못등록 삭제/취소</button>'
text=replace_once(text,old,new,'manual UI three steps')
old="  box.querySelectorAll('[data-proof]').forEach(input=>input.addEventListener('change',submitProof));\n  box.querySelectorAll('[data-delete-registration]').forEach(button=>button.addEventListener('click',deleteRegistration));"
new="""  box.querySelectorAll('[data-proof]').forEach(input=>input.addEventListener('change',event=>{\n   const file=event.currentTarget.files?.[0]||null,id=event.currentTarget.dataset.proof,row=event.currentTarget.closest('.gpd-official-row'),button=row?.querySelector('[data-submit-proof]'),label=row?.querySelector('.gpd-official-id span');\n   if(file&&id){proofDrafts.set(id,file);if(button)button.disabled=false;if(label)label.textContent=`✓ 확인화면 선택 완료: ${file.name||'선택한 이미지'} · ③ 검증완료 등록을 누르세요.`}\n   else{proofDrafts.delete(id);if(button)button.disabled=true}\n  }));\n  box.querySelectorAll('[data-submit-proof]').forEach(button=>button.addEventListener('click',submitProof));\n  box.querySelectorAll('[data-delete-registration]').forEach(button=>button.addEventListener('click',deleteRegistration));"""
text=replace_once(text,old,new,'manual UI listeners')
pattern=re.compile(r'async function submitProof\(event\)\{.*?\n\}\n\nasync function install\(\)\{', re.S)
m=pattern.search(text)
if not m: raise SystemExit('submitProof function not found')
func='''async function submitProof(event){\n const button=event.currentTarget,registrationId=button.dataset.submitProof,row=button.closest('.gpd-official-row'),label=row?.querySelector('.gpd-official-id span'),file=proofDrafts.get(registrationId);\n if(!file||!registrationId){if(label)label.textContent='② 확인화면을 먼저 선택하세요.';return}\n const old=button.textContent;button.disabled=true;button.textContent='검증 중…';\n try{\n  if(label)label.textContent='공식 조회 화면 OCR 일치검사 중…';\n  const image=await normalize(file);\n  const response=await fetch('/api/manual-official-proof',{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',body:JSON.stringify({registration_id:registrationId,proof_image_data_url:image,filename:file.name||''})});\n  const data=await response.json().catch(()=>({}));\n  if(!response.ok)throw new Error(data.error||`등록 실패(${response.status})`);\n  if(!data.accepted){\n   const conflicts=data.proof?.conflicts||[],missing=data.proof?.missing||[];\n   if(data.reason==='official_page_screenshot_ocr_incomplete')throw new Error(`공식페이지 OCR 정보 부족(${missing.join(', ')||'일부 항목'}) · 주소창/인증번호/등급이 보이게 다시 캡처하세요.`);\n   throw new Error(`공식 조회 화면 일치검사 실패${conflicts.length?': '+conflicts.join(', '):''}`);\n  }\n  proofDrafts.delete(registrationId);\n  if(label)label.textContent='✓ 공식사이트 직접확인 + 첨부화면 일치 · 검증완료';\n  button.textContent='✓ 검증완료';\n  await sleep(500);await render();\n }catch(error){button.disabled=false;button.textContent=old;if(label)label.textContent=String(error?.message||'공식 확인화면 등록 실패')}\n}\n\nasync function install(){'''
text=text[:m.start()]+func+text[m.end():]
write(p,text)

# 6) Pending-candidate UI: remove retired BRG form special-case and make wording identical for all five graders.
p=Path('pending_official_candidate_bridge_v161.js'); text=p.read_text(encoding='utf-8')
text=replace_once(text,"function officialOpenUrl(url,cert,company){const c=String(company||'').toUpperCase();if(c==='BRG')return 'https://www.brgcard.com/certification';if(c!=='BGS')return url;", "function officialOpenUrl(url,cert,company){const c=String(company||'').toUpperCase();if(c!=='BGS')return url;", 'BRG stale URL')
old='<b>BRG 안내:</b> 인증번호가 포함된 직접 URL에서 서버 오류가 날 수 있어 BRG는 조회 폼만 열고 인증번호를 자동복사합니다. 붙여넣어 조회하세요. <b>Application error / server-side exception / Digest 화면은 조회결과 없음이 아니므로 ④로 삭제하지 마세요.</b>'
new='<b>PSA/BGS/CGC/TAG/BRG 공통:</b> 자동 인증조회는 사용하지 않습니다. ① 공식사이트에서 인증번호를 직접 확인하고 ② 실제 결과화면을 첨부한 뒤 ③ 검증완료 등록을 누르세요. <b>서버 오류·차단·Application error 화면은 조회결과 없음이 아니므로 ④로 삭제하지 마세요.</b>'
text=replace_once(text,old,new,'pending generic manual help')
write(p,text)

# 7) Cache-bust the two manual-verification bridges when index has direct references.
p=Path('index.html'); text=p.read_text(encoding='utf-8')
text=re.sub(r'(manual_official_verify_bridge\.js)(?:\?v=[^"\']*)?', r'\1?v=192', text)
text=re.sub(r'(pending_official_candidate_bridge_v161\.js)(?:\?v=[^"\']*)?', r'\1?v=192', text)
write(p,text)

# 8) Regression contract.
test=Path('test_manual_only_official_verification_v192.py')
test.write_text(r'''#!/usr/bin/env python3
import inspect
import unittest
from unittest import mock

import grading_cert_verifier as verifier
import graded_photo_multi_source as gp
import manual_official_proof as proof


class ManualOnlyOfficialVerificationV192Tests(unittest.TestCase):
    def test_global_verifier_is_hard_disabled(self):
        self.assertTrue(verifier.automatic_lookup_disabled())
        with mock.patch.object(verifier, '_fetch') as fetch:
            result=verifier.verify_cert('BRG','0346643',expected_grade=10)
        fetch.assert_not_called()
        self.assertTrue(result.get('manual_verification_required'))
        self.assertFalse(result.get('verified'))
        self.assertEqual(result.get('official_url'),'https://break.co.kr/certification/0346643')

    def test_candidate_collection_makes_zero_live_cert_requests(self):
        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643'}]
        with mock.patch.object(gp,'verify_cert') as live, \
             mock.patch.object(gp,'_load',return_value={}), \
             mock.patch.object(gp,'atomic_write_json'):
            _rows,stats=gp._official_verify_rows(rows,{},max_live=10)
        live.assert_not_called()
        self.assertEqual(int(stats.get('live_attempts') or 0),0)

    def test_manual_proof_is_final_official_reference_but_not_raw(self):
        source=inspect.getsource(proof)
        self.assertIn('"manual_screenshot_sets_official_result": True',source)
        self.assertIn('"official_result": bool(matched)',source)
        self.assertIn('"verification_state": "manual_official_verified"',source)
        self.assertIn('"raw_grade_calibration_eligible": False',source)
        self.assertIn('"automatic_live_lookup_used": False',source)

    def test_ui_requires_explicit_third_step(self):
        bridge=open('manual_official_verify_bridge.js',encoding='utf-8').read()
        pending=open('pending_official_candidate_bridge_v161.js',encoding='utf-8').read()
        self.assertIn('③ 검증완료 등록',bridge)
        self.assertIn('proofDrafts',bridge)
        self.assertIn('③ 검증완료 등록',pending)
        self.assertNotIn('brgcard.com/certification',pending)
        self.assertIn('break.co.kr/certification/{cert}',open('grading_cert_verifier.py',encoding='utf-8').read())


if __name__=='__main__':
    unittest.main()
''',encoding='utf-8')

print('v192 manual-only official verification patch applied')
