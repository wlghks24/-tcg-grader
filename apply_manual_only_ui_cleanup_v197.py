from pathlib import Path

# 1) Replace stale automatic-certification UI with manual browser-only flow.
p = Path('auto_validation_flow.js')
s = p.read_text(encoding='utf-8')

start = s.find('function mount(){')
end = s.find('function boot(){', start)
if start < 0 or end < 0:
    raise SystemExit('auto validation function block not found')

replacement = r'''const OFFICIAL_CERT_URL={
 PSA:cert=>`https://www.psacard.com/cert/${encodeURIComponent(cert)}/psa`,
 BGS:cert=>`https://www.beckett.com/grading/card-lookup?flag=1&item_id=${encodeURIComponent(cert)}&item_type=BGS`,
 CGC:cert=>`https://www.cgccards.com/certlookup/${encodeURIComponent(cert)}/`,
 TAG:cert=>`https://taggrading.com/pages/cert-search?cert=${encodeURIComponent(cert)}`,
 BRG:cert=>`https://break.co.kr/certification/${encodeURIComponent(cert)}`
};
function manualCertUrl(company,cert){
 const key=String(company||'').toUpperCase(),cleanCert=String(cert||'').replace(/[^A-Za-z0-9]/g,'').slice(0,24);
 return cleanCert&&OFFICIAL_CERT_URL[key]?OFFICIAL_CERT_URL[key](cleanCert):'';
}
function syncOfficialLink(){
 const company=$('actualCompany')?.value||'PSA',cert=clean($('certificationId')?.value),status=$('autoValidationStatus'),link=$('autoVerifyOfficialLink');
 if(!link||!status)return;
 const url=manualCertUrl(company,cert);
 if(!url){link.href='#';link.style.display='none';status.textContent='인증번호를 입력하면 공식 조회 링크가 준비됩니다.';return}
 link.href=url;link.style.display='inline-flex';
 status.textContent=`${company} 인증 ${cert} · 공식사이트에서 직접 확인 후 결과화면을 수동 등록하세요.`;
}
function mount(){
 if($('autoValidationPanel'))return true;const root=$('v30validation');if(!root)return false;
 const box=document.createElement('div');box.id='autoValidationPanel';box.className='auto-validation-panel';
 box.innerHTML=`<div class="av-head"><div><b>🔐 공식 인증 수동확인</b><small>자동 인증조회는 사용하지 않습니다. 인증번호를 입력하고 공식사이트를 직접 연 뒤 결과화면을 캡처해 수동 검증등록하세요.</small></div><span>MANUAL</span></div><div class="av-actions"><a id="autoVerifyOfficialLink" href="#" target="_blank" rel="noopener noreferrer" style="display:none">공식 조회 열기</a></div><div id="autoValidationStatus" class="av-status">인증번호 입력 대기</div>`;
 const first=root.querySelector('.workflow-part');(first||root).insertAdjacentElement(first?'afterbegin':'beforeend',box);
 ['identityCardName','identityCardNumber','identityRegion','actualCompany'].forEach(id=>$(id)?.addEventListener('change',()=>{syncIdentity();syncOfficialLink()}));
 $('certificationId')?.addEventListener('input',()=>{syncIdentity();syncOfficialLink()});
 $('certificationId')?.addEventListener('change',()=>{syncIdentity();syncOfficialLink()});
 syncOfficialLink();return true;
}
'''
s = s[:start] + replacement + s[end:]

for forbidden in ('인증번호 자동검증','인증번호 공식 자동확인','/api/verify-grading-cert','async function verify()'):
    if forbidden in s:
        raise SystemExit(f'stale auto verification path remains: {forbidden}')
for required in ('🔐 공식 인증 수동확인','자동 인증조회는 사용하지 않습니다.','공식 조회 열기','https://break.co.kr/certification/'):
    if required not in s:
        raise SystemExit(f'manual verification UI missing: {required}')
p.write_text(s,encoding='utf-8')

# 2) Align graded-photo dashboard wording with the same manual-only policy.
p = Path('graded_photo_dashboard.js')
s = p.read_text(encoding='utf-8')
old = 'eBay·Google 공개검색·Amazon·KREAM·당근 등 후보를 OCR과 등급사 공식 인증조회로 교차검증합니다.'
new = 'eBay·Google 공개검색·Amazon·KREAM·당근 등 후보를 OCR로 정리하고, 등급사 공식사이트는 사용자가 직접 확인해 검증합니다.'
if old not in s:
    raise SystemExit('graded-photo header wording marker not found')
s = s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

print('v197 manual-only UI cleanup applied')
