(()=>{
'use strict';
const $=id=>document.getElementById(id);
const usd=n=>`$${Number(n).toFixed(2)}`;
const krw=n=>`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`;
const money=(n,c)=>c==='KRW'?krw(n):usd(n);
function shippingText(v){return ({checkout_calculated:'결제 시 자동계산',return_shipping_flat_at_checkout:'반송배송비 결제 시 계산',domestic_carrier_actual:'국내 택배 실제요금',return_shipping_and_insurance_variable:'반송배송·보험 실제요금',declared_value_tier:'신고가액/서비스별'}[v]||'실제 결제값 확인')}
function insuranceText(c){
 if(c.insurance==='included_by_tier')return '서비스별 보험 포함';
 if(c.insurance==='tier_max_insured_value')return '서비스별 최대 보험가액';
 if(c.insurance==='declared_value_tier')return '신고가액 한도 기준';
 if(c.insurance==='carrier_actual')return '택배사 보험 실제요금';
 return '보험/보상 실제 결제조건 확인';
}
function mount(){
 if($('gradingCostPanel'))return;
 const anchor=$('autoGradeMarketFlow'); if(!anchor)return;
 const s=document.createElement('section');s.id='gradingCostPanel';s.className='card grading-cost-panel';
 s.innerHTML='<div class="gcp-head"><div><h3>💳 업체별 감정비 · 배송 · 보험</h3><p>공식 요금표 기준. 서버가 켜져 있으면 최신 등록값을 불러옵니다.</p></div><button id="gradingCostRefresh" type="button">요금 새로고침</button></div><div id="gradingCostRows" class="gcp-rows">불러오는 중…</div><div id="gradingCostNote" class="gcp-note"></div>';
 anchor.insertAdjacentElement('afterend',s);$('gradingCostRefresh')?.addEventListener('click',load);
 load();
}
async function load(){
 const box=$('gradingCostRows'); if(!box)return;
 box.textContent='공식 요금 불러오는 중…';
 try{
  const r=await fetch('/api/grading-costs?t='+Date.now(),{cache:'no-store'});const j=await r.json();if(!r.ok||!j.ok)throw 0;
  box.innerHTML=Object.entries(j.companies||{}).map(([name,c])=>{
   const active=(c.services||[]).filter(x=>x.availability!=='paused');
   const tiers=active.slice(0,4).map(x=>`${x.name} ${money(x.fee,c.currency)}`).join(' · ');
   const ins=(active.find(x=>x.insurance_per_card)||active.find(x=>x.max_insured_value)||{});
   const cap=ins.insurance_per_card?` · 보험 ${usd(ins.insurance_per_card)}/장`:ins.max_insured_value?` · 최대보험 ${usd(ins.max_insured_value)}`:'';
   return `<article class="gcp-row"><div><b>${name}</b><span>${tiers||'요금 확인 필요'}</span><small>배송: ${shippingText(c.shipping)} · 보험: ${insuranceText(c)}${cap}</small></div><a href="${c.source}" target="_blank" rel="noopener noreferrer">공식 요금표</a></article>`;
  }).join('');
  $('gradingCostNote').textContent=(j.notice||'')+' · 확인 '+(j.checked_at||'');
 }catch(_){box.innerHTML='<span class="gcp-warn">태블릿/PC 서버 연결 후 최신 감정비를 불러올 수 있습니다.</span>'}
}
function boot(){mount();setInterval(()=>{if($('gradingCostPanel'))load()},6*60*60*1000)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
