(()=>{
'use strict';
const $=id=>document.getElementById(id);
const clean=s=>String(s||'').trim();
function ensureVerifiedLearningGuard(){
 if(Number(window.TCGVerifiedLearningV135?.uiVersion)>=174)return true;
 if(document.getElementById('v174GradeLearningGuardLoader'))return false;
 const script=document.createElement('script');
 script.id='v174GradeLearningGuardLoader';
 script.src='grade_learning_guard_v135.js?v=174';
 script.async=false;
 script.onload=()=>{try{window.TCGVerifiedLearningV135?.refresh?.();window.TCGVerifiedLearningV135?.refreshReferences?.()}catch(_){}};
 script.onerror=()=>{const status=$('autoValidationStatus');if(status)status.textContent='보정학습 UI 파일을 불러오지 못했습니다. 새로고침 후 다시 확인하세요.'};
 document.head.appendChild(script);
 return false;
}
function gameKey(){const g=String(window.tcgIdentityGame||'pokemon').toLowerCase();return ['pokemon','onepiece','naruto'].includes(g)?g:'pokemon'}
function predictedCompany(){return $('econCompany')?.value||$('actualCompany')?.value||'PSA'}
function predictedGrade(company){const v=Number(window.tcgLastGrades?.[company]);return Number.isFinite(v)?Math.max(1,Math.min(10,v)):null}
function identity(){return {name:clean($('identityCardName')?.value),number:clean($('identityCardNumber')?.value),region:clean($('identityRegion')?.value)||'UNKNOWN'}}
function makeKey(){const x=identity();return [gameKey(),x.region,x.name,x.number].filter(Boolean).join('|').slice(0,180)}
function syncIdentity(){const company=predictedCompany();if($('actualCompany'))$('actualCompany').value=company;const key=makeKey();if(key&&$('learningCardKey'))$('learningCardKey').value=key;const p=predictedGrade(company);const status=$('autoValidationStatus');if(status)status.textContent=p?`예상 ${company} ${p} · 카드 식별키 자동연결 완료`:'카드 분석 후 예상등급과 자동 연결됩니다.'}
const OFFICIAL_CERT_URL={
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
function boot(){ensureVerifiedLearningGuard();let n=0;const t=setInterval(()=>{n++;ensureVerifiedLearningGuard();if(mount()||n>20)clearInterval(t)},250);mount();setInterval(syncIdentity,1200)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
