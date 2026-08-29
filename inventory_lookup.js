(()=>{
'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const CAP={
 realtime_stock:['🟢 실시간 재고조회','inventory-cap realtime'],
 store_stock_lookup:['🔵 점포 상품·재고 확인','inventory-cap lookup'],
 guided_stock_check:['🟡 점포 재고 확인 경로','inventory-cap guided'],
 online_store_availability:['🟣 온라인 취급·재고 확인','inventory-cap online'],
 phone_confirmation:['☎ 매장 재고 문의','inventory-cap contact']
};
async function serverOK(){try{const r=await fetch('/api/health?t='+Date.now(),{cache:'no-store'});return r.ok&&((await r.json()).ok===true)}catch(_){return false}}
function mount(){
 const live=document.getElementById('purchaseLive');
 if(!live||document.getElementById('officialInventoryLookup'))return;
 const box=document.createElement('section');
 box.id='officialInventoryLookup';
 box.className='inventory-lookup-card';
 box.innerHTML='<div class="inventory-lookup-head"><div><b>📦 공식 재고·상품 확인</b><small>업체가 실제 제공하는 기능 수준대로 표시합니다.</small></div><button id="inventoryLookupRun" type="button">확인 경로 보기</button></div><div id="inventoryLookupResult" class="inventory-lookup-result"><span>상품명을 입력한 뒤 확인하세요.</span></div>';
 live.parentNode.insertBefore(box,live);
 document.getElementById('inventoryLookupRun')?.addEventListener('click',run);
}
async function run(){
 const out=document.getElementById('inventoryLookupResult'),btn=document.getElementById('inventoryLookupRun');
 const q=(document.getElementById('purchaseQuery')?.value||'').trim();
 const game=document.getElementById('purchaseGame')?.value||'';
 if(!q){out.innerHTML='<span class="inventory-warn">카드명·BOX·세트명을 먼저 입력하세요.</span>';return;}
 btn.disabled=true;btn.textContent='확인 중…';
 try{
   if(!(await serverOK())){out.innerHTML='<span class="inventory-warn">태블릿/PC 서버 연결이 필요합니다.</span>';return;}
   const r=await fetch('/api/inventory-lookup?q='+encodeURIComponent(q)+'&game='+encodeURIComponent(game),{cache:'no-store'});
   const j=await r.json();
   if(!r.ok||!j.ok)throw new Error(j.error||'lookup failed');
   out.innerHTML=(j.items||[]).map(x=>{
     const cap=CAP[x.capability]||['ℹ 공식 확인','inventory-cap'];
     return `<article class="inventory-option"><div><b>${esc(x.retailer)} · ${esc(x.label)}</b><span class="${cap[1]}">${cap[0]}</span><small>${esc(x.instructions)}</small></div><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.action_label||'공식 확인 열기')}</a></article>`;
   }).join('')+`<p class="inventory-note">${esc(j.notice||'')}</p>`;
 }catch(e){out.innerHTML='<span class="inventory-warn">공식 재고·상품 확인 정보를 불러오지 못했습니다.</span>'}
 finally{btn.disabled=false;btn.textContent='확인 경로 보기';}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
window.runOfficialInventoryLookup=run;
})();
