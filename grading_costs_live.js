(()=>{
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const usd=n=>`$${Number(n).toFixed(2)}`;
const krw=n=>`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`;
const jpy=n=>`¥${Math.round(Number(n)).toLocaleString('ja-JP')}`;
const money=(n,c)=>c==='KRW'?krw(n):c==='JPY'?jpy(n):usd(n);
function shippingText(v){return ({checkout_calculated:'결제 시 자동계산',return_shipping_flat_at_checkout:'반송배송비 결제 시 계산',domestic_carrier_actual:'국내 택배 실제요금',return_shipping_and_insurance_variable:'반송배송·보험 실제요금',declared_value_tier:'신고가액/서비스별'}[v]||'실제 결제값 확인')}
function insuranceText(c){
 if(c.insurance==='included_by_tier')return '서비스별 보험 포함';
 if(c.insurance==='tier_max_insured_value')return '서비스별 최대 보험가액';
 if(c.insurance==='declared_value_tier')return '신고가액 한도 기준';
 if(c.insurance==='carrier_actual')return '택배사 보험 실제요금';
 return '보험/보상 실제 결제조건 확인';
}
function serviceText(x,currency){
 const fee=x.fee==null?'가격 확인 필요':money(x.fee,currency);
 const tat=x.turnaround_business_days?` · 약 ${x.turnaround_business_days}영업일`:'';
 const state=x.availability==='paused'?' · 접수중지':x.availability==='retired'?' · 종료':'';
 return `${esc(x.name)} ${esc(fee)}${tat}${state}`;
}
function regionalText(c){
 const markets=c.regional_markets||{};
 return Object.entries(markets).map(([market,m])=>{
  const rows=(m.services||[]).filter(x=>!['paused','retired'].includes(x.availability)).slice(0,5);
  if(!rows.length)return '';
  return `<small><b>${esc(market)}</b> ${rows.map(x=>serviceText(x,m.currency||c.currency)).join(' · ')}</small>`;
 }).filter(Boolean).join('');
}
function changeText(row){
 const type={service_added:'신규 서비스',service_changed:'서비스 변경',service_removed:'서비스 종료',official_announcement:'공식 공지',official_page_changed_unparsed:'공식 페이지 변경 감지'}[row.type]||row.type||'변경';
 const svc=row.service?` · ${row.service}`:'';
 if(row.type==='service_changed'&&row.changes){
  const bits=Object.entries(row.changes).map(([k,v])=>`${k}: ${v.before??'-'} → ${v.after??'-'}`);
  return `${type}${svc} · ${bits.join(', ')}`;
 }
 return `${type}${svc}${row.title?` · ${row.title}`:''}`;
}
function renderChanges(j){
 const target=$('gradingCostChanges');if(!target)return;
 const changes=(j.recent_changes||[]).slice(-8).reverse();
 const events=(j.grading_events||[]).slice(-6).reverse();
 if(!changes.length&&!events.length){target.innerHTML='<small>최근 공식 변경 이력이 없습니다. 감시기는 공식 업체 페이지를 주기적으로 확인합니다.</small>';return;}
 const a=changes.map(x=>`<li>${esc(changeText(x))}${x.url?` <a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">공식</a>`:''}</li>`).join('');
 const b=events.map(x=>`<li>${esc(x.company||'')} · ${esc(x.title||'')} <a href="${esc(x.url||'#')}" target="_blank" rel="noopener noreferrer">공식</a></li>`).join('');
 target.innerHTML=`${a?`<b>최근 요금·서비스 변경</b><ul>${a}</ul>`:''}${b?`<b>업체 이벤트·공지</b><ul>${b}</ul>`:''}`;
}
function renderLive(j){
 const box=$('gradingCostRows');if(!box)return;
 box.innerHTML=Object.entries(j.companies||{}).map(([name,c])=>{
  const active=(c.services||[]).filter(x=>!['paused','retired'].includes(x.availability));
  const tiers=active.slice(0,5).map(x=>serviceText(x,c.currency)).join(' · ');
  const ins=(active.find(x=>x.insurance_per_card)||active.find(x=>x.max_insured_value)||{});
  const cap=ins.insurance_per_card?` · 보험 ${usd(ins.insurance_per_card)}/장`:ins.max_insured_value?` · 최대보험 ${usd(ins.max_insured_value)}`:'';
  return `<article class="gcp-row"><div><b>${esc(name)}</b><span>${tiers||'요금 확인 필요'}</span><small>배송: ${esc(shippingText(c.shipping))} · 보험: ${esc(insuranceText(c))}${esc(cap)}</small>${regionalText(c)}</div><a href="${esc(c.source)}" target="_blank" rel="noopener noreferrer">공식 요금표</a></article>`;
 }).join('');
 renderChanges(j);
 $('gradingCostNote').textContent=(j.notice||'')+' · API 확인 '+(j.checked_at||'')+(j.watch_checked_at?` · 업체감시 ${j.watch_checked_at}`:'');
}
function renderStatic(w){
 const box=$('gradingCostRows');if(!box)return;
 box.innerHTML=Object.entries(w.companies||{}).map(([name,c])=>{
  const markets=c.markets||{};
  const body=Object.entries(markets).map(([market,m])=>`<span><b>${esc(market)}</b> ${(m.services||[]).slice(0,6).map(x=>serviceText(x,m.currency)).join(' · ')||'마지막 검증값 없음'}</span>`).join('');
  return `<article class="gcp-row"><div><b>${esc(name)}</b>${body}</div></article>`;
 }).join('')||'<span class="gcp-warn">업체 감시 스냅샷 준비 중</span>';
 renderChanges({recent_changes:w.recent_changes||[],grading_events:w.announcements||[]});
 $('gradingCostNote').textContent=`공식 업체 감시 정적 스냅샷 · ${w.checked_at||''}`;
}
function mount(){
 if($('gradingCostPanel'))return;
 const anchor=$('autoGradeMarketFlow'); if(!anchor)return;
 const s=document.createElement('section');s.id='gradingCostPanel';s.className='card grading-cost-panel';
 s.innerHTML='<div class="gcp-head"><div><h3>💳 업체별 감정비 · 배송 · 보험</h3><p>PSA/BGS/CGC/TAG/BRG 공식 출처 기준. 가격·서비스·납기·접수상태·이벤트 변경을 함께 감시합니다.</p></div><button id="gradingCostRefresh" type="button">요금 새로고침</button></div><div id="gradingCostRows" class="gcp-rows">불러오는 중…</div><div id="gradingCostChanges" class="gcp-note"></div><div id="gradingCostNote" class="gcp-note"></div>';
 anchor.insertAdjacentElement('afterend',s);$('gradingCostRefresh')?.addEventListener('click',load);
 load();
}
async function load(){
 const box=$('gradingCostRows'); if(!box)return;
 box.textContent='공식 요금·업체 변경사항 불러오는 중…';
 try{
  const r=await fetch('/api/grading-costs?t='+Date.now(),{cache:'no-store'});const j=await r.json();if(!r.ok||!j.ok)throw new Error('api');
  renderLive(j);return;
 }catch(_){}
 try{
  const r=await fetch('/grading_company_updates.json?t='+Date.now(),{cache:'no-store'});const w=await r.json();if(!r.ok||!w.policy?.official_sources_only)throw new Error('static');
  renderStatic(w);return;
 }catch(_){box.innerHTML='<span class="gcp-warn">공식 업체 감시 자료를 불러오지 못했습니다. 서버 연결 또는 다음 정적 갱신을 확인하세요.</span>'}
}
function boot(){mount();setInterval(()=>{if($('gradingCostPanel')&&document.visibilityState==='visible')load()},3*60*60*1000)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
