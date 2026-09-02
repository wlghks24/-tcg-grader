from pathlib import Path

p = Path('manual_official_verify_bridge.js')
s = p.read_text(encoding='utf-8')

old_outer = ".gpd-official-fallback{display:block!important;margin-top:12px;border:1px solid #0f766e55;background:#f0fdfa;border-radius:13px;padding:11px;color:#134e4a}"
new_outer = ".gpd-official-fallback{margin-top:12px}"
if old_outer not in s:
    raise SystemExit('outer fallback style marker not found')
s = s.replace(old_outer, new_outer, 1)

old_row = ".gpd-official-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:10px 0;border-top:1px solid #99f6e4;align-items:center}.gpd-official-row:first-of-type{margin-top:8px}"
new_row = ".gpd-official-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:10px;border:1px solid #99f6e4;background:#f0fdfa;border-radius:13px;align-items:center;margin-top:8px}"
if old_row not in s:
    raise SystemExit('row style marker not found')
s = s.replace(old_row, new_row, 1)

old_load = "  const payload=await loadStatus();if(!payload){box.innerHTML='<h4>🔐 공식사이트 수동확인</h4><p>수동확인 상태를 불러오지 못했습니다.</p>';return}"
new_load = "  const payload=await loadStatus();if(!payload){box.hidden=true;box.innerHTML='';return}"
if old_load not in s:
    raise SystemExit('load-status marker not found')
s = s.replace(old_load, new_load, 1)

start_marker = "  box.innerHTML=`<h4>🔐 자동 인증조회 OFF · 공식사이트 직접확인</h4>"
start = s.find(start_marker)
if start < 0:
    raise SystemExit('large manual-only info panel marker not found')
end_marker = "  box.querySelectorAll('[data-proof]')"
end = s.find(end_marker, start)
if end < 0:
    raise SystemExit('proof handler marker not found')
segment = s[start:end]
row_start_marker = "${rows.length?rows.map(row=>`"
row_end_marker = "`).join(''):'"
rs = segment.find(row_start_marker)
re = segment.find(row_end_marker, rs + len(row_start_marker))
if rs < 0 or re < 0:
    raise SystemExit('row template markers not found')
row_template = segment[rs + len(row_start_marker):re]
replacement = (
    "  if(!rows.length){box.hidden=true;box.innerHTML='';return}\n"
    "  box.hidden=false;\n"
    "  box.innerHTML=rows.map(row=>`" + row_template + "`).join('');\n"
)
s = s[:start] + replacement + s[end:]

# Regression guards: the big explanatory copy must be gone, but core manual actions stay.
for forbidden in (
    '자동 인증조회 OFF · 공식사이트 직접확인',
    '현재 직접확인이 필요한 완성된 인증정보 항목이 없습니다.',
    '수동확인 통합관리:',
):
    if forbidden in s:
        raise SystemExit(f'large info copy still present: {forbidden}')
for required in (
    '① 공식조회 열기',
    '② 확인화면 선택',
    '③ 검증완료 등록',
    '잘못등록 삭제/취소',
    "if(!rows.length){box.hidden=true;box.innerHTML='';return}",
):
    if required not in s:
        raise SystemExit(f'core manual action missing: {required}')

p.write_text(s, encoding='utf-8')
print('v196 compact manual verification UI applied')
