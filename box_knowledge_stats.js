(()=>{
'use strict';
const $=id=>document.getElementById(id);
const normCountry=v=>['KR','JP','US'].includes(v)?v:'ALL';
const validImage=v=>/^https:\/\//i.test(String(v||''));
const priced=v=>{const d=String(v?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)};
let activeTab='RELEASED';
let marketCache={entries:{}};
let watchCache={items:[]};

function getCatalog(){try{return Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}}
async function loadMarket(){try{const r=await fetch('market_prices.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {entries:{}};const d=await r.json();return d&&typeof d==='object'?d:{entries:{}}}catch(_){return {entries:{}}}}
async function loadWatch(){try{const r=await fetch('market_watch.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {items:[]};const d=await r.json();return d&&Array.isArray(d.items)?d:{items:[]}}catch(_){return {items:[]}}}
function countryOfKey(k){return String(k||'').split('|')[0]||''}
function assetOfKey(k){return String(k||'').split('|')[2]||''}
function nameOfKey(k){return String(k||'').split('|')[1]||''}
function uniqueKey(c,n){return `${c}|${String(n||'').trim().toLowerCase()}`}
function hotKey(c,n,a){return `${String(c||'')}|${String(n||'').trim().toLowerCase()}|${String(a||'')}`}
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

function daysOld(value){
 const d=parseDate(value);if(!d)return 9999;
 return Math.max(0,Math.floor((today0().getTime()-d.getTime())/86400000));
}
function freshnessPoints(value){const days=daysOld(value);return days===0?40:days===1?36:days<=3?30:days<=7?20:days<=30?10:2}
function evidencePoints(row){
 const text=`${row?.transactions||''} ${row?.kind||''}`;
 const counts=[...text.matchAll(/(\d{1,4})\s*건/g)].map(m=>Number(m[1])).filter(Number.isFinite);
 const count=counts.length?Math.max(...counts):0;
 const explicit=/판매완료|체결|거래자료|거래시세/.test(text)?8:0;
 return Math.min(30,explicit+Math.min(22,count*2));
}
function watchMatch(region,name,asset){
 const n=String(name||'').trim().toLowerCase();
 const rows=Array.isArray(watchCache.items)?watchCache.items:[];
 let exact=rows.find(x=>hotKey(x.region,x.name,x.asset)===hotKey(region,name,asset));
 if(exact)return exact;
 if(n.length<4)return null;
 return rows.find(x=>String(x?.region||'')===String(region||'')&&String(x?.asset||'')===String(asset||'')&&(()=>{
   const other=String(x?.name||'').trim().toLowerCase();return other.length>=4&&(other.includes(n)||n.includes(other));
 })())||null;
}
function watchPoints(row){
 if(!row)return 0;
 let score=/거래중|판매중|판매·출시 확인 중/.test(String(row.sale_status||''))?12:0;
 const age=daysOld(row.release_date);
 if(age<=7)score+=8;else if(age<=30)score+=5;else if(age<=90)score+=2;
 return Math.min(20,score);
}
function linkPoints(row){return String(row?.link_status||'').trim()==='정상'?5:0}
function hotRows(asset){
 const entries=marketCache.entries||{};
 return Object.entries(entries).filter(([key,row])=>assetOfKey(key)===asset&&priced(row)).map(([key,row])=>{
   const region=countryOfKey(key),name=nameOfKey(key),watch=watchMatch(region,name,asset);
   const fresh=freshnessPoints(row.source_date),evidence=evidencePoints(row),watchScore=watchPoints(watch),link=linkPoints(row);
   const score=Math.min(100,fresh+evidence+watchScore+link);
   const reasons=[];
   if(fresh>=30)reasons.push('최근 시세');
   if(evidence>=12)reasons.push('거래 근거');
   if(watchScore>=12)reasons.push('판매·거래 상태');
   if(link===5)reasons.push('출처 정상');
   return {region,name,asset,row,watch,score,reasons};
 }).sort((a,b)=>b.score-a.score||daysOld(a.row.source_date)-daysOld(b.row.source_date)||a.name.localeCompare(b.name,'ko')).slice(0,5);
}
function ensureHotUi(){
 const section=$('v14section');if(!section)return null;
 let panel=$('hotMarketSignals');
 if(panel)return panel;
 panel=document.createElement('section');panel.id='hotMarketSignals';panel.className='status';
 panel.style.margin='10px 0 14px';panel.style.background='#fff7ed';panel.style.border='1px solid #fed7aa';
 const title=document.createElement('div');title.style.fontWeight='900';title.style.fontSize='15px';title.textContent='🔥 HOT 카드 · BOX — 최근 시장 활동 신호';
 const note=document.createElement('div');note.className='muted';note.style.marginTop='4px';note.textContent='가격 상승률 순위가 아니라 최근 수집일·거래 근거·판매 상태·출처 상태를 합산합니다.';
 const meta=document.createElement('div');meta.id='hotMarketMeta';meta.className='muted';meta.style.marginTop='4px';
 const grid=document.createElement('div');grid.id='hotMarketGrid';grid.style.display='grid';grid.style.gridTemplateColumns='repeat(auto-fit,minmax(220px,1fr))';grid.style.gap='8px';grid.style.marginTop='9px';
 panel.append(title,note,meta,grid);
 const anchor=section.querySelector('label')||section.firstChild;section.insertBefore(panel,anchor);
 return panel;
}
function hotColumn(asset,label){
 const wrap=document.createElement('div');wrap.style.background='#fff';wrap.style.borderRadius='12px';wrap.style.padding='10px';
 const head=document.createElement('b');head.textContent=label;wrap.appendChild(head);
 const rows=hotRows(asset);
 if(!rows.length){const empty=document.createElement('div');empty.className='muted';empty.style.marginTop='7px';empty.textContent='현재 검증된 시장 신호가 없습니다.';wrap.appendChild(empty);return wrap}
 rows.forEach((item,index)=>{
  const card=document.createElement('div');card.style.padding='8px 0';card.style.borderTop=index?'1px solid #eee':'0';
  const line=document.createElement('div');line.style.fontWeight='800';line.textContent=`${index+1}위 · ${item.region} · ${item.name}`;
  const detail=document.createElement('div');detail.className='muted';detail.textContent=`HOT ${item.score} · ${item.row.display||'가격 확인 중'} · ${item.reasons.join(' · ')||'수집 신호'}`;
  card.append(line,detail);
  const url=String(item.row.source||'');if(/^https:\/\//i.test(url)){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='시장 근거 보기';a.style.fontSize='11px';a.style.fontWeight='700';card.appendChild(a)}
  wrap.appendChild(card);
 });
 return wrap;
}
function renderHot(){
 const panel=ensureHotUi();if(!panel)return;
 const grid=$('hotMarketGrid');if(!grid)return;grid.replaceChildren(hotColumn('BOX','📦 HOT BOX'),hotColumn('HIT','🎴 HOT 카드'));
 const updated=String(marketCache.updated_at||'').replace('T',' ').replace('+00:00',' UTC');
 const meta=$('hotMarketMeta');if(meta)meta.textContent=`시장자료 갱신: ${updated||'확인 중'} · HOT 점수는 구매추천이 아니라 활동 신호입니다.`;
}
function syncAnalysisAssetMode(){
 const control=$('analysisAsset');if(!control)return;
 const value=String(control.value||'ALL');
 if(value==='BOX'||value==='HIT'){
  try{selectedCatalogMode=value}catch(_){}
 }
}
function hookAnalysisAsset(){
 const control=$('analysisAsset');if(!control||control.dataset.hotModeHook==='1')return;
 control.dataset.hotModeHook='1';
 control.addEventListener('change',()=>{syncAnalysisAssetMode();try{if(typeof renderCountryAnalysis==='function')renderCountryAnalysis()}catch(_){}});
 syncAnalysisAssetMode();
}

async function refresh(){
 ensureUi();hookAnalysisAsset();
 [marketCache,watchCache]=await Promise.all([loadMarket(),loadWatch()]);
 await refreshStatsOnly();applyTabFilter();renderHot();
}

// 기존 renderBoxKnowledge 실행 뒤 탭 필터를 다시 적용한다.
const hookRender=()=>{try{if(typeof window.renderBoxKnowledge==='function'&&!window.renderBoxKnowledge.__boxTabsHooked){const orig=window.renderBoxKnowledge;const wrapped=function(...args){const r=orig.apply(this,args);setTimeout(applyTabFilter,0);return r};wrapped.__boxTabsHooked=true;window.renderBoxKnowledge=wrapped}}catch(_){}};
window.addEventListener('tcg-market-catalog-expanded',()=>setTimeout(refresh,80));
document.addEventListener('click',e=>{const t=e.target.closest?.('button');if(!t||t.dataset.boxTab)return;if(/한국|일본|미국|전체/.test(t.textContent||''))setTimeout(()=>{refreshStatsOnly();applyTabFilter()},150)});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{hookRender();refresh()},550));else setTimeout(()=>{hookRender();refresh()},550);
setInterval(()=>{if(!document.hidden)refresh()},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});window.refreshBoxKnowledgeStats=refresh;
})();
