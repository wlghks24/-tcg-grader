from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} marker not found')
    return text.replace(old, new, 1)

# 1) Dual-photo UI: official-page screenshots are reference verification only.
p = Path('manual_dual_photo_bridge.js')
s = p.read_text(encoding='utf-8')
s = replace_once(s, 'verifiedSlabRawLearning:true', 'verifiedSlabRawLearning:false', 'dual bridge raw flag')
old = """   const rawReady=row.raw_grade_calibration_eligible===true&&row.raw_defect_learning_eligible===true;\n   const rawActive=rawReady&&row.raw_proxy_learning_state==='active';\n   const label=rawActive?'공식검증 완료 · RAW학습 활성':rawReady?'공식검증 완료 · RAW학습 누적':'공식검증 완료 · 통합관리';\n   const badgeText=rawActive?'RAW학습 활성':rawReady?'RAW학습 누적':'공식검증 완료';\n"""
new = """   const label='공식검증 완료 · 통합관리';\n   const badgeText='공식검증 완료';\n"""
s = replace_once(s, old, new, 'dual bridge raw status')
old_policy = "카드게임을 선택하고 <b>등급 슬랩 앞면 + 뒷면 사진 2장</b>을 등록하세요. 앞면은 등급사·등급·인증번호 OCR에 사용하고 뒷면은 같은 카드의 증빙사진으로 저장합니다. <b>공식검증 완료 후에는 카드 영역만 추출해 RAW 결함·등급 보정학습에도 사용합니다.</b>"
new_policy = "카드게임을 선택하고 <b>등급 슬랩 앞면 + 뒷면 사진 2장</b>을 등록하세요. 앞면은 등급사·등급·인증번호 OCR에 사용하고 뒷면은 같은 카드의 증빙사진으로 저장합니다. 공식 홈페이지에서 직접 조회한 결과화면을 별도로 첨부해 검증하며, <b>수동 공식검증 캡처는 RAW 등급 보정값에 직접 투입하지 않습니다.</b>"
s = replace_once(s, old_policy, new_policy, 'dual bridge policy copy')
for forbidden in ('verifiedSlabRawLearning:true', 'RAW학습 활성', 'RAW학습 누적', 'RAW 결함·등급 보정학습에도 사용'):
    if forbidden in s:
        raise SystemExit(f'stale dual-photo policy remains: {forbidden}')
for required in ('verifiedSlabRawLearning:false', '공식검증 완료 · 통합관리', '수동 공식검증 캡처는 RAW 등급 보정값에 직접 투입하지 않습니다.'):
    if required not in s:
        raise SystemExit(f'dual-photo manual-only marker missing: {required}')
p.write_text(s, encoding='utf-8')

# 2) Dashboard copy: no suggestion that a manual proof becomes RAW calibration truth.
p = Path('graded_photo_dashboard.js')
s = p.read_text(encoding='utf-8')
old = "공식 업체 페이지에서 업체·인증번호·등급이 일치한 쌍만 서버가 카드 영역을 다시 측정하여 자가학습 후보로 사용하며, 미확인값과 브라우저 미리보기값은 학습 정답으로 사용하지 않습니다."
new = "공식 등급사 홈페이지에서 사용자가 직접 조회한 결과화면을 별도로 첨부하고 등급사·인증번호·등급이 모두 일치할 때만 공식검증 참고자료로 등록합니다. 수동 공식검증 캡처는 RAW 등급 보정값에 직접 투입하지 않습니다."
if old in s:
    s = s.replace(old, new, 1)
if '등급사 공식 인증조회로 교차검증합니다.' in s:
    s = s.replace('후보를 OCR과 등급사 공식 인증조회로 교차검증합니다.', '후보를 OCR로 정리하고, 등급사 공식사이트는 사용자가 직접 확인해 검증합니다.', 1)
if '수동 공식검증 캡처는 RAW 등급 보정값에 직접 투입하지 않습니다.' not in s:
    raise SystemExit('dashboard manual proof policy marker missing')
p.write_text(s, encoding='utf-8')

# 3) Tablet v135 wrapper: delete every legacy automatic grader lookup route/callback.
p = Path('tcg_updater_v135.py')
s = p.read_text(encoding='utf-8')
s, n = re.subn(r"\n    def _guarded_official_lookup\(self, company, cert, expected_grade=None\):.*?\n    def do_GET\(self\):", "\n    def do_GET(self):", s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('v135 guarded lookup method not removed')
start = s.find("        if path == '/api/verify-grading-cert':\n")
if start < 0:
    raise SystemExit('v135 verify endpoint marker not found')
end = s.find("        return super().do_GET()\n", start)
if end < 0:
    raise SystemExit('v135 do_GET return marker not found')
s = s[:start] + s[end:]
old = """            import verified_grade_learning_v135_safe as learning\n            registry = learning.registry_index()\n            key = learning._cert_key(company, cert) if cert else ''\n            already_verified = bool(key and key in registry)\n\n            def guarded_verifier(c, n, expected_grade):\n                return self._guarded_official_lookup(c, n, expected_grade)\n\n            with core.DATA_WRITE_LOCK:\n                result = learning.submit_verified_sample(\n                    incoming,\n                    verifier=None if already_verified else guarded_verifier,\n                )\n                core.clear_json_file_cache()\n            if result.get('accepted'):\n                return self.json(result, 200)\n            verification = result.get('verification') if isinstance(result, dict) else {}\n            if isinstance(verification, dict) and verification.get('error') == '공식 인증조회 안전 대기 중':\n                return self.json(result, 429)\n            return self.json(result, 409)\n"""
new = """            import verified_grade_learning_v135_safe as learning\n            with core.DATA_WRITE_LOCK:\n                result = learning.submit_verified_sample(\n                    incoming,\n                    verifier=None,\n                )\n                core.clear_json_file_cache()\n            if result.get('accepted'):\n                return self.json(result, 200)\n            return self.json(result, 409)\n"""
s = replace_once(s, old, new, 'v135 learning sample auto verifier')
for forbidden in ("_guarded_official_lookup", "if path == '/api/verify-grading-cert':", 'guarded_verifier'):
    if forbidden in s:
        raise SystemExit(f'v135 automatic cert path remains: {forbidden}')
if 'verifier=None' not in s:
    raise SystemExit('v135 manual-only verifier marker missing')
p.write_text(s, encoding='utf-8')

# 4) Cache-bust changed UI assets so Android Chrome/WebView cannot retain old controls/copy.
p = Path('index.html')
s = p.read_text(encoding='utf-8')
for asset in ('auto_validation_flow.js', 'graded_photo_dashboard.js', 'manual_dual_photo_bridge.js'):
    pattern = re.compile(re.escape(asset) + r'\?v=\d+')
    s, count = pattern.subn(asset + '?v=200', s)
    if count == 0:
        # If the asset is unversioned, version the first literal occurrence.
        if asset in s:
            s = s.replace(asset, asset + '?v=200', 1)
        else:
            raise SystemExit(f'index asset missing: {asset}')
for required in ('auto_validation_flow.js?v=200', 'graded_photo_dashboard.js?v=200', 'manual_dual_photo_bridge.js?v=200'):
    if required not in s:
        raise SystemExit(f'cache-bust marker missing: {required}')
p.write_text(s, encoding='utf-8')

print('v200 manual-only closure applied')
