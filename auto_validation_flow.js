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
function mount(){if($('autoValidationPanel'))return true;const root=$('v30validation');if(!root)return false;const box=document.createElement('div');box.id='autoValidationPanel';box.className='auto-validation-panel';box.innerHTML=`<div class="av-head"><div><b>🤖 인증번호 자동검증</b><small>카드명·번호·판본·식별키는 자동 연결합니다. 공식 사이트에서 실제 등급까지 확인된 경우에만 검증기록을 자동 저장합니다.</small></div><span>AUTO</span></div><div class="av-actions"><button type="button" id="autoVerifyCert">인증번호 공식 자동확인</button><a id="autoVerifyOfficialLink" href="#" target="_blank" rel="noopener noreferrer">공식 조회 열기</a></div><div id="autoValidationStatus" class="av-status">카드 분석/인증번호 입력 대기</div>`;const first=root.querySelector('.workflow-part');(first||root).insertAdjacentElement(first?'afterbegin':'beforeend',box);$('autoVerifyCert')?.addEventListener('click',verify);['identityCardName','identityCardNumber','identityRegion','actualCompany'].forEach(id=>$(id)?.addEventListener('change',syncIdentity));$('certificationId')?.addEventListener('change',()=>{syncIdentity();verify()});return true}
async function verify(){syncIdentity();const company=$('actualCompany')?.value||'PSA',cert=clean($('certificationId')?.value),status=$('autoValidationStatus'),link=$('autoVerifyOfficialLink');if(!cert){status.textContent='인증번호를 입력하세요.';return}status.textContent=`${company} 공식 인증번호 확인 중…`;try{const r=await fetch(`/api/verify-grading-cert?company=${encodeURIComponent(company)}&cert=${encodeURIComponent(cert)}&t=${Date.now()}`,{cache:'no-store'}),j=await r.json();if(j.official_url){link.href=j.official_url;link.style.display='inline-flex'}if(!r.ok||!j.ok){status.textContent=j.error||'공식 조회에 실패했습니다.';return}if(!j.verified){$('officialResult').checked=false;status.textContent=j.notice||'공식 페이지에서 직접 확인이 필요합니다.';return}const grade=Number(j.grade);if(!Number.isFinite(grade)){status.textContent='공식 등급값을 확인하지 못했습니다.';return}$('actualGrade').value=String(grade);$('officialResult').checked=true;syncIdentity();const predicted=predictedGrade(company);status.textContent=`✅ 공식 확인 ${company} ${grade}${predicted?` · 예상 ${predicted} · 오차 ${(grade-predicted).toFixed(1)}`:''} · 검증기록 자동 저장 중`;setTimeout(()=>$('saveValidation')?.click(),120)}catch(_){status.textContent='서버 연결 또는 공식 사이트 응답 제한으로 자동확인하지 못했습니다. 공식 조회를 이용하세요.'}}
function boot(){ensureVerifiedLearningGuard();let n=0;const t=setInterval(()=>{n++;ensureVerifiedLearningGuard();if(mount()||n>20)clearInterval(t)},250);mount();setInterval(syncIdentity,1200)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
