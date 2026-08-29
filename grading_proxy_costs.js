(()=>{
'use strict';
const $=id=>document.getElementById(id);
const krw=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'-';
function priceSummary(p){
 if((p.services||[]).length)return p.services.map(s=>`${s.name} ${krw(s.price_krw)}`).join(' · ');
 if(p.proxy_fee_from_krw)return `대행수수료 ${krw(p.proxy_fee_from_krw)}~ + 실비`;
 return '실시간 견적/문의';
}
function typeText(t){return ({total_service_price:'공개 대행가격',proxy_fee_plus_actual:'대행수수료 + 실비',dynamic_quote:'동적 견적'}[t]||'가격 확인')}
function mount(){
 if($('gradingProxyPanel'))return;
 const anchor=$('gradingCostPanel')||$('autoGradeMarketFlow');if(!anchor)return;
 const s=document.createElement('section');s.id='gradingProxyPanel';s.className='card grading-proxy-panel';
 s.innerHTML=`<div class="gpp-head"><div><h3>📦 국내 등급대행 비용 비교</h3><p>PSA·BGS·CGC·TAG·BRG 대행처의 공개가격/수수료를 비교합니다.</p></div><button id="gradingProxyRefresh" type="button">대행비 새로고침</button></div>
 <div class="gpp-filter">${['ALL','PSA','BGS','CGC','TAG','BRG'].map((x,i)=>`<button class="gpp-chip${i?'':' active'}" data-grader="${x}" type="button">${x==='ALL'?'전체':x}</button>`).join('')}</div>
 <div id="gradingProxyRows" class="gpp-rows">불러오는 중…</div><div id="gradingProxyNote" class="gpp-note"></div>`;
 anchor.insertAdjacentElement('afterend',s);
 s.querySelectorAll('.gpp-chip').forEach(b=>b.addEventListener('click',()=>{s.querySelectorAll('.gpp-chip').forEach(x=>x.classList.remove('active'));b.classList.add('active');render(window.__gradingProxyData||{},b.dataset.grader)}));
 $('gradingProxyRefresh')?.addEventListener('click',()=>load(true));load(false);
}
function render(j,filter='ALL'){
 const box=$('gradingProxyRows');if(!box)return;
 let rows=(j.providers||[]).filter(x=>filter==='ALL'||x.grader===filter);
 const graders=['PSA','BGS','CGC','TAG','BRG'];
 if(filter!=='ALL'&&!rows.length)rows=[{provider:'공개 대행가격 미확인',grader:filter,pricing_type:'dynamic_quote',source:'#',note:'현재 공개 웹에서 확인 가능한 한국 대행가격을 찾지 못했습니다. 임의 가격을 표시하지 않습니다.'}];
 if(filter==='ALL'){
   for(const g of graders)if(!(j.providers||[]).some(x=>x.grader===g))rows.push({provider:'공개 대행가격 미확인',grader:g,pricing_type:'dynamic_quote',source:'#',note:'공개가격 확인 전'});
 }
 box.innerHTML=rows.map(p=>`<article class="gpp-row"><div class="gpp-main"><div class="gpp-line"><b>${p.grader}</b><strong>${p.provider}</strong>${p.official_dealer?'<span class="gpp-official">공식딜러</span>':''}</div><div class="gpp-price">${priceSummary(p)}</div><small>${typeText(p.pricing_type)} · ${p.note||''}${p.live_verified?' · 최신 페이지 재확인':''}</small>${(p.extras||[]).length?`<small>추가: ${(p.extras||[]).map(x=>`${x.name} ${krw(x.price_krw)}`).join(' · ')}</small>`:''}</div>${p.source&&p.source!=='#'?`<a href="${p.source}" target="_blank" rel="noopener noreferrer">대행사 확인</a>`:''}</article>`).join('');
 $('gradingProxyNote').textContent=(j.notice||'')+' · 확인 '+(j.checked_at||'');
}
async function load(force){const box=$('gradingProxyRows');if(!box)return;box.textContent='대행비용 확인 중…';try{const r=await fetch('/api/grading-proxy-costs?force='+(force?'1':'0')+'&t='+Date.now(),{cache:'no-store'});const j=await r.json();if(!r.ok||!j.ok)throw 0;window.__gradingProxyData=j;const active=document.querySelector('.gpp-chip.active')?.dataset.grader||'ALL';render(j,active)}catch(_){box.innerHTML='<span class="gpp-warn">태블릿/PC 서버 연결 후 대행비용을 확인할 수 있습니다.</span>'}}
function boot(){mount();setInterval(()=>{if($('gradingProxyPanel'))load(false)},6*60*60*1000)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
