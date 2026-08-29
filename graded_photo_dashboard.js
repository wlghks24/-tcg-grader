(()=>{
'use strict';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[m]));
const n=v=>Number.isFinite(Number(v))?Number(v):0;
function companyOf(r){return String(r.company||r.grader||r.grading_company||r.provider||'').toUpperCase()}
function sourceOf(r){return String(r.source||r.market||r.search_provider||r.source_name||'기타')}
function statusOf(r){return String(r.status||r.verification_status||r.learning_status||'').toLowerCase()}
function isVerified(r){const s=statusOf(r);return r.verified===true||r.official_verified===true||s==='verified_reference'||s.includes('공식검증')}
function isEligible(r){const s=statusOf(r);return r.training_eligible===true||r.calibration_eligible===true||r.learning_eligible===true||s.includes('training_eligible')||s.includes('보정학습가능')}
function isQuarantine(r){const s=statusOf(r);return r.quarantined===true||s.includes('quarantine')||s.includes('격리')||(!isVerified(r)&&!isEligible(r))}
function latestOf(rows,payload){const vals=rows.map(r=>r.collected_at||r.updated_at||r.verified_at||r.created_at).filter(Boolean).sort();return vals.at(-1)||payload.created_at||payload.updated_at||payload.collected_at||payload.generated_at||'-'}
function insertPanel(){
 if(document.getElementById('gradedPhotoDashboard')) return document.getElementById('gradedPhotoDashboard');
 const anchor=document.getElementById('v11')||document.querySelector('[id*="validation"]')||document.querySelector('.card');
 const box=document.createElement('section'); box.id='gradedPhotoDashboard'; box.className='graded-photo-dashboard card';
 box.innerHTML=`<div class="gpd-head"><div><h2>📊 등급사진 학습 현황</h2><p>7단계 자동수집의 등급카드 사진을 등급사·출처·검증상태별로 표시합니다.</p></div><button id="gpdRefresh" type="button">새로고침</button></div><div id="gpdBody" class="gpd-body"><div class="gpd-loading">학습 현황을 불러오는 중…</div></div>`;
 if(anchor&&anchor.parentNode) anchor.parentNode.insertBefore(box,anchor.nextSibling); else document.querySelector('.app')?.appendChild(box);
 box.querySelector('#gpdRefresh')?.addEventListener('click',()=>load(true)); return box;
}
function diagnosticHtml(payload,total){
 if(total>0)return '';
 const errs=Array.isArray(payload.errors)?payload.errors.filter(Boolean).slice(0,6):[];
 const stats=payload.source_stats&&typeof payload.source_stats==='object'?Object.entries(payload.source_stats):[];
 const attempted=stats.filter(([,v])=>v&&Number(v.errors||0)>=0).length;
 const state=String(payload.collection_status||'대기');
 return `<div class="gpd-section"><h3>수집 진단</h3><div class="gpd-empty">상태: <b>${esc(state)}</b> · 확인한 출처 ${attempted}곳${errs.length?`<br>최근 오류: ${errs.map(esc).join(' · ')}`:'<br>오류 기록 없음 — 시작 수집 또는 공개검색 결과를 기다리는 중입니다.'}</div></div>`;
}
function render(payload){
 const body=document.getElementById('gpdBody'); if(!body)return;
 const rows=Array.isArray(payload.records)?payload.records:Array.isArray(payload.items)?payload.items:[];
 const verified=rows.filter(isVerified).length,eligible=rows.filter(isEligible).length,quarantine=rows.filter(isQuarantine).length;
 const total=rows.length||n(payload.summary?.total_candidates)||n(payload.summary?.total);
 const byCompany=Object.fromEntries(COMPANIES.map(c=>[c,rows.filter(r=>companyOf(r)===c).length]));
 const sourceMap={};rows.forEach(r=>{const s=sourceOf(r);sourceMap[s]=(sourceMap[s]||0)+1});
 const sources=Object.entries(sourceMap).sort((a,b)=>b[1]-a[1]).slice(0,12);
 body.innerHTML=`<div class="gpd-summary"><div><span>전체 후보</span><b>${total.toLocaleString()}건</b></div><div><span>공식검증</span><b>${verified.toLocaleString()}건</b></div><div><span>격리 후보</span><b>${quarantine.toLocaleString()}건</b></div><div><span>보정학습 가능</span><b>${eligible.toLocaleString()}건</b></div></div>
 <div class="gpd-section"><h3>등급사별 확보량</h3><div class="gpd-companies">${COMPANIES.map(c=>`<div class="gpd-company"><b>${c}</b><strong>${byCompany[c].toLocaleString()}</strong><span>장</span></div>`).join('')}</div></div>
 <div class="gpd-section"><h3>출처별 수집량</h3>${sources.length?`<div class="gpd-sources">${sources.map(([s,c])=>`<div><span>${esc(s)}</span><b>${c.toLocaleString()}건</b></div>`).join('')}</div>`:'<div class="gpd-empty">아직 출처별 수집기록이 없습니다.</div>'}</div>
 ${diagnosticHtml(payload,total)}
 <div class="gpd-foot"><span>최근 수집: ${esc(latestOf(rows,payload))}</span><span class="gpd-safe">미검증 사진은 보정학습에 사용하지 않음</span></div>`;
}
async function load(force=false){insertPanel();const body=document.getElementById('gpdBody');if(body&&force)body.innerHTML='<div class="gpd-loading">다시 확인하는 중…</div>';try{const res=await fetch('/api/graded-photo-learning?_='+(force?Date.now():'1'),{cache:'no-store'});if(!res.ok)throw new Error('HTTP '+res.status);render(await res.json())}catch(e){if(body)body.innerHTML='<div class="gpd-error">현황을 불러오지 못했습니다. 서버가 켜져 있는지 확인하세요.</div>'}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>load(false));else load(false);setInterval(()=>load(false),60000);
})();
