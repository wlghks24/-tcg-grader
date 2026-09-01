from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label}: target not found')
    return text.replace(old, new, 1)


bridge = Path('manual_dual_photo_bridge.js')
text = bridge.read_text(encoding='utf-8')
if "__TCG_DUAL_PHOTO_BRIDGE_V158__" not in text:
    text = replace_once(text, "const GLOBAL_KEY='__TCG_DUAL_PHOTO_BRIDGE_V156__';", "const GLOBAL_KEY='__TCG_DUAL_PHOTO_BRIDGE_V158__';", 'bridge key')
    text = replace_once(text, 'version:156,enhanced:false', 'version:158,enhanced:false', 'bridge version')
    text = replace_once(text, "marker.content='inline-v156';", "marker.content='inline-v158';", 'bridge marker')
old = """function ensureRegistrationPanelPresentation(form){
 const details=form?.closest('details.gpd-manual');if(!details)return;
 details.open=true;
 const summary=details.querySelector(':scope > summary');
 if(summary&&summary.textContent!=='📷 등급사진 간편등록')summary.textContent='📷 등급사진 간편등록';
}"""
new = """function ensureRegistrationPanelPresentation(form){
 const details=form?.closest('details.gpd-manual');if(!details)return;
 details.open=true;
 const summary=details.querySelector(':scope > summary');
 const eightZoneReady=Boolean(document.getElementById('gpdZonePanel')&&document.getElementById('gpdRevalidateExisting'));
 const label=eightZoneReady?'📷 등급사진 8구역 정밀등록':'📷 등급사진 간편등록';
 if(summary&&summary.textContent!==label)summary.textContent=label;
 bridgeState.eightZoneCompatible=eightZoneReady;
}"""
if old in text:
    text = text.replace(old, new, 1)
if 'eightZoneCompatible=eightZoneReady' not in text:
    raise SystemExit('bridge eight-zone compatibility patch missing')
bridge.write_text(text, encoding='utf-8')

repair = Path('REPAIR_V135_SERVER.sh')
text = repair.read_text(encoding='utf-8')
old = """if ! printf '%s' \"$DASHBOARD\" | grep -q '앞면 + 뒷면 2장으로 수동등록'; then
  echo \"[오류] 앞면+뒷면 2장 등록 브리지가 실제 대시보드 응답에 포함되지 않았습니다.\"
  exit 1
fi"""
new = """if ! printf '%s' \"$DASHBOARD\" | grep -q '앞면 + 뒷면 8구역 등록하기'; then
  echo \"[오류] 앞면+뒷면 8구역 등록 UI가 실제 대시보드 응답에 포함되지 않았습니다.\"
  exit 1
fi
if ! printf '%s' \"$DASHBOARD\" | grep -q '총 8구역 정밀검사'; then
  echo \"[오류] 8구역 정밀검사 UI가 실제 대시보드 응답에 포함되지 않았습니다.\"
  exit 1
fi
if ! printf '%s' \"$DASHBOARD\" | grep -q '기존 등록사진 전체 재검증'; then
  echo \"[오류] 기존 등록사진 전체 재검증 버튼이 실제 대시보드 응답에 포함되지 않았습니다.\"
  exit 1
fi
if ! printf '%s' \"$DASHBOARD\" | grep -q '/api/run-existing-photo-revalidation'; then
  echo \"[오류] 기존 등록사진 재검증 API 호출 코드가 실제 대시보드 응답에 포함되지 않았습니다.\"
  exit 1
fi"""
if old in text:
    text = text.replace(old, new, 1)
if '기존 등록사진 전체 재검증' not in text or '/api/run-existing-photo-revalidation' not in text:
    raise SystemExit('repair eight-zone checks missing')
text = text.replace('echo "[OK] 앞면+뒷면 2장 UI + 공식검증 RAW학습 v155 실전달 확인"', 'echo "[OK] 앞면+뒷면 8구역 UI + 기존사진 전체 재검증 + 공식검증 RAW학습 실전달 확인"')
repair.write_text(text, encoding='utf-8')

wrapper = Path('tcg_updater_v135.py')
text = wrapper.read_text(encoding='utf-8')
text = text.replace('/* v150 dual-photo bridge: served inline by v135 */', '/* v158 dual-photo/eight-zone bridge: served inline by v135 */')
text = text.replace("self.send_header('X-TCG-Dual-Photo-UI', 'v150-inline')", "self.send_header('X-TCG-Dual-Photo-UI', 'v158-eight-zone-inline')")
text = text.replace("'manual_dual_photo_bridge_version': 150,", "'manual_dual_photo_bridge_version': 158,\n                'graded_photo_eight_zone_ui': True,\n                'existing_photo_revalidation': True,")
text = text.replace("print('수동등록 UI: 앞면+뒷면 2장 브리지를 대시보드 응답에 직접 포함 · 캐시 우회 v150', flush=True)", "print('수동등록 UI: 앞면+뒷면 8구역 정밀검사 + 기존 등록사진 전체 재검증 · 캐시 우회 v158', flush=True)")
if "'graded_photo_eight_zone_ui': True" not in text or "'existing_photo_revalidation': True" not in text:
    raise SystemExit('v135 health contract patch missing')
wrapper.write_text(text, encoding='utf-8')

print('eight-zone runtime fix v158 applied')
