(()=>{
'use strict';
const $=id=>document.getElementById(id);
const normCountry=v=>['KR','JP','US'].includes(v)?v:'ALL';
const validImage=v=>/^https:\/\//i.test(String(v||''));
const priced=v=>{const d=String(v?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)};
let activeTab='RELEASED';
let marketCache={entries:{}};

function getCatalog(){try{return Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}}
async function loadMarket(){try{const r=await fetch('market_prices.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {entries:{}};const d=await r.json();return d&&typeof d==='object'?d:{entries:{}}}catch(_){return {entries:{}}}}
function countryOfKey(k){return String(k||'').split('|')[0]||''}
function assetOfKey(k){return String(k||'').split('|')[2]||''}
function nameOfKey(k){return String(k||'').split('|')[1]||''}
function uniqueKey(c,n){return `${c}|${String(n||'').trim().toLowerCase()}`}
function parseDate(v){
 const s=String(v||'').trim();
 if(!s||/최근 시장 발견|확인 중|미정|예정$/.test(s))return null;
 let m=s.match(/(20\d{2})\D+(\d{1,2})\D+(\d{1,2})/);
 if(!m)m=s.match(/(20\d{2})-(\d{1,2})-(\d{1,2})/);
 if(!m)return null;
 const d=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]),0,0,0,0);
 return Number.isNaN(d.getTime())?null:d;
}
function today0(){const d=new Date();return new Date(d.getFullYear(),d.getMonth(),d.getDate())}
function releaseState(row){const d=parseDate(row?.release||row?.release_date||row?.source_date);if(!d)return 'UNKNOWN';return d<=today0()?'RELEASED':'UPCOMING'}
function marketTradingSet(entries){const set=new Set();for(const [k,v] of Object.entries(entries||{})){if(assetOfKey(k)!=='BOX'||!priced(v))continue;set.add(uniqueKey(countryOfKey(k),nameOfKey(k)))}return set}

function ensureUi(){
 const count=$('boxKbCount');if(!count)return null;
 let panel=$('boxKnowledgeStats');
 if(!panel){
  panel=document.createElement('section');panel.id='boxKnowledgeStats';panel.className='boxkb-stats';
  panel.innerHTML=`
   <div class="boxkb-tabs" role="tablist" aria-label="BOX 제품 상태">
    <button type="button" class="boxkb-tab active" data-box-tab="RELEASED">📦 지금까지 출시된 제품</button>
    <button type="button" class="boxkb-tab" data-box-tab="TRADING">💹 현재 거래중인 제품</button>
    <button type="button" class="boxkb-tab" data-box-tab="UPCOMING">🗓️ 앞으로 출시될 제품</button>
   </div>
   <div class="boxkb-stat-grid">
    <article><span>📚 누적 출시 확인</span><strong id="boxStatReleased">-</strong><small>오늘까지 출시일 확인</small></article>
    <article><span>💹 현재 거래 확인</span><strong id="boxStatTrading">-</strong><small>현재 가격 신호 확인</small></article>
    <article><span>🗓️ 출시 예정 확인</span><strong id="boxStatUpcoming">-</strong><small>오늘 이후 공식 출시일</small></article>
    <article><span>🖼️ 이미지 확인 BOX</span><strong id="boxStatImages">-</strong><small>HTTPS 상품 이미지 확보</small></article>
   </div>
   <div id="boxStatNote" class="boxkb-stat-note">기본 등록 목록은 참고자료이며 시장 전체 수량을 뜻하지 않습니다.</div>`;
  count.insertAdjacentElement('afterend',panel);
  panel.querySelectorAll('[data-box-tab]').forEach(btn=>btn.addEventListener('click',()=>{activeTab=btn.dataset.boxTab;panel.querySelectorAll('[data-box-tab]').forEach(x=>x.classList.toggle('active',x===btn));applyTabFilter();refreshStatsOnly()}));
 }
 return panel;
}

function catalogRowsForCountry(){const country=normCountry(window.selectedBoxKbCountry||'ALL');return getCatalog().filter(x=>country==='ALL'||x.country===country)}
function passesTab(row,trading){const key=uniqueKey(row.country,row.name);if(activeTab==='TRADING')return trading.has(key);const state=releaseState(row);return activeTab==='UPCOMING'?state==='UPCOMING':state==='RELEASED'}
function applyTabFilter(){
 const list=$('box12');if(!list)return;
 const rows=catalogRowsForCountry();const trading=marketTradingSet(marketCache.entries||{});const kids=[...list.children];
 let shown=0;
 kids.forEach((el,i)=>{const row=rows[i];const ok=!!row&&passesTab(row,trading);el.style.display=ok?'':'none';if(ok)shown++});
 const country=normCountry(window.selectedBoxKbCountry||'ALL');const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';
 const tabLabel=activeTab==='RELEASED'?'지금까지 출시':activeTab==='TRADING'?'현재 거래중':'앞으로 출시 예정';
 const count=$('boxKbCount');if(count)count.textContent=`📦 ${label} · ${tabLabel} BOX ${shown}개`;
 if(shown===0&&!list.querySelector('.boxkb-tab-empty')){const d=document.createElement('div');d.className='boxkb-tab-empty';d.textContent='이 조건에서 확인된 BOX가 없습니다.';list.appendChild(d)}
 const empty=list.querySelector('.boxkb-tab-empty');if(empty)empty.style.display=shown?'none':'block';
}
async function refreshStatsOnly(){
 if(!ensureUi())return;
 const country=normCountry(window.selectedBoxKbCountry||'ALL');const catalog=getCatalog();const entries=marketCache.entries||{};const inCountry=c=>country==='ALL'||c===country;
 const released=new Set(),upcoming=new Set(),trading=new Set(),images=new Set(),base=new Set();
 for(const x of catalog){const c=x.country||'';if(!inCountry(c))continue;const k=uniqueKey(c,x.name);base.add(k);const st=releaseState(x);if(st==='RELEASED')released.add(k);if(st==='UPCOMING')upcoming.add(k);if(validImage(x.boxImage))images.add(k)}
 for(const [key,v] of Object.entries(entries)){if(assetOfKey(key)!=='BOX')continue;const c=countryOfKey(key);if(!inCountry(c))continue;const k=uniqueKey(c,nameOfKey(key));if(priced(v))trading.add(k);const st=releaseState(v);if(st==='RELEASED')released.add(k);if(st==='UPCOMING')upcoming.add(k);if(validImage(v?.image_url))images.add(k)}
 $('boxStatReleased').textContent=`${released.size}개`;$('boxStatTrading').textContent=`${trading.size}개`;$('boxStatUpcoming').textContent=`${upcoming.size}개`;$('boxStatImages').textContent=`${images.size}개`;
 const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';const note=$('boxStatNote');if(note)note.textContent=`${label} 기준 · 출시/예정은 확인된 출시일로 구분하고, 거래중은 현재 가격 신호가 있는 BOX만 집계합니다. 기본 등록 ${base.size}개는 참고용입니다.`;
}
async function refresh(){ensureUi();marketCache=await loadMarket();await refreshStatsOnly();applyTabFilter()}

// 기존 renderBoxKnowledge 실행 뒤 탭 필터를 다시 적용한다.
const hookRender=()=>{try{if(typeof window.renderBoxKnowledge==='function'&&!window.renderBoxKnowledge.__boxTabsHooked){const orig=window.renderBoxKnowledge;const wrapped=function(...args){const r=orig.apply(this,args);setTimeout(applyTabFilter,0);return r};wrapped.__boxTabsHooked=true;window.renderBoxKnowledge=wrapped}}catch(_){}};
window.addEventListener('tcg-market-catalog-expanded',()=>setTimeout(refresh,80));
document.addEventListener('click',e=>{const t=e.target.closest?.('button');if(!t||t.dataset.boxTab)return;if(/한국|일본|미국|전체/.test(t.textContent||''))setTimeout(()=>{refreshStatsOnly();applyTabFilter()},150)});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{hookRender();refresh()},550));else setTimeout(()=>{hookRender();refresh()},550);
setInterval(refresh,60000);window.refreshBoxKnowledgeStats=refresh;
})();
