(()=>{
'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
async function serverOK(){try{const r=await fetch('/api/health?t='+Date.now(),{cache:'no-store'});return r.ok&&((await r.json()).ok===true)}catch(_){return false}}
function mount(){
 const live=document.getElementById('purchaseLive');
 if(!live||document.getElementById('officialInventoryLookup'))return;
 const box=document.createElement('section');
 box.id='officialInventoryLookup';
 box.className='inventory-lookup-card';
 box.innerHTML='<div class="inventory-lookup-head"><div><b>📦 실제 공식 재고조회</b><small>공식 재고조회 기능이 있는 업체만 표시합니다.</small></div><button id="inventoryLookupRun" type="button">재고조회 열기</button></div><div id="inventoryLookupResult" class="inventory-lookup-result"><span>상품명을 입력한 뒤 조회하세요.</span></div>';
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
   out.innerHTML=(j.items||[]).map(x=>`<article class="inventory-option"><div><b>${esc(x.retailer)} · ${esc(x.label)}</b><small>${esc(x.instructions)}</small></div><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">공식 재고조회 열기</a></article>`).join('')+`<p class="inventory-note">${esc(j.notice||'')}</p>`;
 }catch(e){out.innerHTML='<span class="inventory-warn">공식 재고조회 정보를 불러오지 못했습니다.</span>'}
 finally{btn.disabled=false;btn.textContent='재고조회 열기';}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
window.runOfficialInventoryLookup=run;
})();
