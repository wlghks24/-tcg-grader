(()=>{
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normCountry=v=>['KR','JP','US'].includes(v)?v:'ALL';
const validImage=v=>/^https:\/\//i.test(String(v||''));
const priced=v=>{const d=String(v?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)};
let activeTab='RELEASED';
let selectedGame='ALL';
let registryCache=[];
let marketCache={entries:{}};
let watchCache={items:[]};

function getCatalog(){try{return Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}}
async function loadMarket(){try{const r=await fetch('market_prices.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {entries:{}};const d=await r.json();return d&&typeof d==='object'?d:{entries:{}}}catch(_){return {entries:{}}}}
async function loadWatch(){try{const r=await fetch('market_watch.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return {items:[]};const d=await r.json();return d&&Array.isArray(d.items)?d:{items:[]}}catch(_){return {items:[]}}}
async function loadRegistry(){try{const r=await fetch('tcg_game_registry.json?_='+Date.now(),{cache:'no-store'});if(!r.ok)return [];const d=await r.json();return Array.isArray(d?.games)?d.games.filter(x=>x&&x.capabilities?.market===true):[]}catch(_){return []}}
function currentCountry(){const active=document.querySelector('.box-kb-country.active');return normCountry(active?.dataset?.kbCountry||'ALL')}
function registryRow(value){return registryCache.find(x=>String(x?.canonical||'')===String(value||''))||null}
function gameLabel(value){if(value==='ALL')return '전체 게임';const row=registryRow(value);return String(row?.label_ko||row?.canonical||value||'게임')}
function marketGame(country,name,row={}){
 const direct=String(row?.game||'').trim();
 if(direct)return direct;
 const found=getCatalog().find(x=>String(x.country||'')===String(country||'')&&String(x.name||'').trim().toLowerCase()===String(name||'').trim().toLowerCase());
 return String(found?.game||'').trim();
}
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
 const year=Number(m[1]),month=Number(m[2]),day=Number(m[3]);
 if(month<1||month>12||day<1||day>31)return null;
 const d=new Date(year,month-1,day,0,0,0,0);
 return d.getFullYear()===year&&d.getMonth()===month-1&&d.getDate()===day?d:null;
}
function today0(){const d=new Date();return new Date(d.getFullYear(),d.getMonth(),d.getDate())}
function releaseState(row){
 // A market observation date is not a verified product release date.
 const d=parseDate(row?.release||row?.release_date);
 if(!d)return 'UNKNOWN';
 return d<=today0()?'RELEASED':'UPCOMING';
}
// A dated listing is a recent market signal, not proof of a completed trade.
const RECENT_MARKET_DAYS=14;
function recentVerifiedMarketSignal(row){
 if(!priced(row)||daysOld(row?.market_observed_at||row?.source_date)>RECENT_MARKET_DAYS)return false;
 if(String(row?.link_status||'').trim()!=='정상')return false;
 try{
  const url=new URL(String(row?.source||''));
  return url.protocol==='https:'&&!url.username&&!url.password&&(!url.port||url.port==='443');
 }catch(_){return false}
}
function marketTradingSet(entries){const set=new Set();for(const [k,v] of Object.entries(entries||{})){if(assetOfKey(k)!=='BOX'||!recentVerifiedMarketSignal(v))continue;set.add(uniqueKey(countryOfKey(k),nameOfKey(k)))}return set}


/* V638: exact-one-BOX price lens; a dated asking price is not a completed sale. */
const BOX_PRICE_HOSTS=['kream.co.kr','pokard.io','snkrdunk.com','ebay.com','ebay.co.jp','tcgplayer.com','pricecharting.com','cardmarket.com'];
function boxSafeSource(value,specific=false){
 try{const u=new URL(String(value||''));
  if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443')||u.hash)return '';
  if(!BOX_PRICE_HOSTS.some(h=>u.hostname===h||u.hostname.endsWith('.'+h)))return '';
  if(specific&&u.pathname==='/'&&!u.search)return '';
  return u.href;
 }catch(_){return ''}
}
function boxParseRange(value){
 const m=/^([₩¥$])\s*(\d+(?:,\d{3})*)(?:\s*[~～–-]\s*(?:\1\s*)?(\d+(?:,\d{3})*))?$/.exec(String(value||'').trim());
 if(!m)return null;
 const low=Number(m[2].replace(/,/g,'')),high=Number((m[3]||m[2]).replace(/,/g,''));
 if(!Number.isSafeInteger(low)||!Number.isSafeInteger(high)||low<100||high<low||high>1000000000)return null;
 return {currency:{'₩':'KRW','¥':'JPY','$':'USD'}[m[1]],low,high};
}
function boxSameName(a,b){return String(a||'').normalize('NFKC').trim().toLocaleLowerCase()===String(b||'').normalize('NFKC').trim().toLocaleLowerCase()}
function boxMedian(numbers){const a=[...numbers].sort((x,y)=>x-y),i=Math.floor(a.length/2);return a.length?(a.length%2?a[i]:(a[i-1]+a[i])/2):null}
function boxMarketAssessment(country,name,game,entries=marketCache.entries){
 const matches=Object.entries(entries||{}).filter(([key,row])=>
  assetOfKey(key)==='BOX'&&countryOfKey(key)===country&&boxSameName(nameOfKey(key),name)&&
  String(row?.game||'')===String(game||'')&&game&&
  (row.box_quantity===undefined||row.box_quantity===1)&&
  !/\b(?:case|carton|packs?|master\s*case)\b|\d+\s*(?:box|박스|팩)\b/i.test(String(name||'')+' '+String(row?.product_name||'')+' '+String(row?.kind||'')));
 const notFound={low:null,high:null,unit:'KRW',recommended:null,basis:'동일 판본 BOX 가격근거 없음',recorded:''};
 if(!matches.length)return notFound;
 const sales=[],transactions=new Set();
 for(const [,row] of matches){
  for(const sale of (Array.isArray(row.completed_sales)?row.completed_sales.slice(0,100):[])){
   if(!sale||sale.verified!==true||sale.evidence_class!=='completed'||sale.sealed!==true||
    sale.unit!=='BOX'||sale.box_quantity!==1||sale.currency!=='KRW'||
    sale.country!==country||sale.game!==game||!boxSameName(sale.product_name,name)||
    !Number.isSafeInteger(sale.price_krw)||sale.price_krw<1000||sale.price_krw>100000000||
    !sale.transaction_id||daysOld(sale.sold_at)>30||!boxSafeSource(sale.source_url,true))continue;
   const url=new URL(sale.source_url),key=url.hostname+'|'+String(sale.transaction_id);
   if(transactions.has(key))continue;transactions.add(key);
   sales.push({price:sale.price_krw,host:url.hostname,url:url.href});
  }
 }
 if(sales.length){
  const low=Math.min(...sales.map(x=>x.price)),high=Math.max(...sales.map(x=>x.price)),groups=new Map();
  for(const sale of sales)groups.set(sale.host,[...(groups.get(sale.host)||[]),sale.price]);
  const enough=sales.length>=3&&groups.size>=2&&high<=low*2;
  return {low,high,unit:'KRW',recommended:enough?Math.round(boxMedian([...groups.values()].map(boxMedian))):null,
   basis:enough?'검증 완료거래 '+sales.length+'건 · 독립 출처 '+groups.size+'곳 · 수수료 제외':
   '완료거래 '+sales.length+'건 · 추천가 산정 근거 부족 또는 편차 큼',
   recorded:'',url:sales[0].url};
 }
 const recent=matches.map(([,v])=>v).filter(v=>daysOld(v?.market_observed_at||v?.source_date)<=14&&
  String(v?.link_status||'')==='정상'&&boxSafeSource(v?.source)&&boxParseRange(v?.display));
 const direct=recent.filter(v=>boxSafeSource(v.source,true))
  .sort((a,b)=>daysOld(a.market_observed_at||a.source_date)-daysOld(b.market_observed_at||b.source_date));
 if(direct.length){
  const v=direct[0],p=boxParseRange(v.display);
  return {low:p.low,high:p.high,unit:p.currency,recommended:null,
   basis:'단일 출처 관측범위 · 시장 전체 최저/최고와 실거래가 아님',
   recorded:'',url:boxSafeSource(v.source,true),observed_at:v.market_observed_at||v.source_date};
 }
 const reference=recent[0];
 return {...notFound,basis:reference?'상품 상세원문 불명 · 가격 교차검증 보류':'최근 14일 내 검증가격 없음',
  recorded:reference?String(reference.display||''):'',url:reference?boxSafeSource(reference.source):''};
}
function updateBoxPriceCard(el,row){
 if(!el||!row)return;
 let panel=el.querySelector('.boxkb-market-comparison');
 if(!panel){panel=document.createElement('section');panel.className='boxkb-market-comparison';panel.setAttribute('aria-label','BOX 가격비교');el.querySelector('.box-kb-body')?.appendChild(panel)}
 if(!panel)return;
 const r=boxMarketAssessment(row.country,row.name,row.game);
 const signature=[r.low,r.high,r.unit,r.recommended,r.basis,r.recorded,r.url,r.observed_at||''].join('|');
 if(panel.dataset.priceSignature===signature)return;
 panel.dataset.priceSignature=signature;panel.replaceChildren();
 const title=document.createElement('strong');title.className='boxkb-market-heading';title.textContent='📊 BOX 가격 교차검증';panel.appendChild(title);
 const grid=document.createElement('div');grid.className='boxkb-market-price-grid';
 const symbol={KRW:'₩',JPY:'¥',USD:'$'}[r.unit]||'';
 for(const [label,value] of [['관측 최저',r.low],['관측 최고',r.high],['판매추천가',r.recommended]]){
  const item=document.createElement('div');item.className='boxkb-market-metric';
  if(label==='판매추천가')item.classList.add('boxkb-market-recommend');
  const caption=document.createElement('span');caption.textContent=label;
  const amount=document.createElement('b');amount.textContent=value===null?(label==='판매추천가'?'산정 보류':'—'):symbol+value.toLocaleString('ko-KR');
  item.append(caption,amount);grid.appendChild(item);
 }
 panel.appendChild(grid);
 const note=document.createElement('small');note.className='boxkb-market-reason';note.textContent=r.basis+(r.observed_at?' · '+r.observed_at:'');
 panel.appendChild(note);
 if(r.recorded){const backup=document.createElement('small');backup.className='boxkb-market-reference';backup.textContent='과거/간접 표시값: '+r.recorded;panel.appendChild(backup)}
 if(r.url){const link=document.createElement('a');link.href=r.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='자료 출처 확인 ↗';panel.appendChild(link)}
}

function ensureGameToolbar(){
 const section=$('box12section');const tabs=section?.querySelector('.box-kb-tabs');if(!section||!tabs)return null;
 let bar=$('boxKbFilterBar');
 if(!bar){
  bar=document.createElement('div');bar.id='boxKbFilterBar';bar.className='boxkb-filterbar';
  bar.innerHTML=`
   <div class="boxkb-filter-copy"><span class="boxkb-filter-kicker">빠른 필터</span><strong>게임을 먼저 고르세요</strong><small>선택한 게임에 맞춰 출시 · 거래 · 예정 BOX를 함께 정리합니다.</small></div>
   <label class="boxkb-game-filter"><span>🎴 게임</span><select id="boxKbGame" aria-label="BOX 지식베이스 게임 선택"><option value="ALL">전체 게임</option></select></label>
   <div id="boxKbFilterState" class="boxkb-filter-state" aria-live="polite">전체 게임 · 전체 국가</div>`;
  tabs.insertAdjacentElement('beforebegin',bar);
  bar.querySelector('#boxKbGame')?.addEventListener('change',e=>{selectedGame=String(e.target.value||'ALL');renderBoxKnowledgeSafe();applyTabFilter();refreshStatsOnly()});
 }
 return bar;
}
function ensureUi(){
 const count=$('boxKbCount');if(!count)return null;
 ensureGameToolbar();
 let panel=$('boxKnowledgeStats');
 if(!panel){
  panel=document.createElement('section');panel.id='boxKnowledgeStats';panel.className='boxkb-stats';
  panel.innerHTML=`
   <div class="boxkb-tabs" role="tablist" aria-label="BOX 제품 상태">
    <button type="button" class="boxkb-tab active" data-box-tab="RELEASED"><span>📦</span><b>출시됨</b><small>지금까지 출시</small></button>
    <button type="button" class="boxkb-tab" data-box-tab="TRADING"><span>💹</span><b>최근 시세</b><small>14일 내 출처 확인</small></button>
    <button type="button" class="boxkb-tab" data-box-tab="UPCOMING"><span>🗓️</span><b>출시 예정</b><small>앞으로 출시</small></button>
   </div>
   <div class="boxkb-stat-grid">
    <article><span>📚 누적 출시</span><strong id="boxStatReleased">-</strong><small>오늘까지 출시일 확인</small></article>
    <article><span>💹 최근 시세</span><strong id="boxStatTrading">-</strong><small>14일 내 확인된 가격 신호</small></article>
    <article><span>🗓️ 출시 예정</span><strong id="boxStatUpcoming">-</strong><small>오늘 이후 공식 출시일</small></article>
    <article><span>🖼️ 이미지 확보</span><strong id="boxStatImages">-</strong><small>HTTPS 상품 이미지</small></article>
   </div>
   <div id="boxStatNote" class="boxkb-stat-note">기본 등록 목록은 참고자료이며 시장 전체 수량을 뜻하지 않습니다.</div>`;
  count.insertAdjacentElement('afterend',panel);
  panel.querySelectorAll('[data-box-tab]').forEach(btn=>btn.addEventListener('click',()=>{activeTab=btn.dataset.boxTab;panel.querySelectorAll('[data-box-tab]').forEach(x=>x.classList.toggle('active',x===btn));applyTabFilter();refreshStatsOnly()}));
 }
 return panel;
}

function catalogRowsForCountry(){const country=currentCountry();return getCatalog().filter(x=>country==='ALL'||x.country===country)}
function gameMatches(row){return selectedGame==='ALL'||String(row?.game||'')===selectedGame}
function populateGameFilter(){
 const select=$('boxKbGame');if(!select)return;
 const previous=selectedGame;
 const groups=[
  ['핵심 TCG',registryCache.filter(x=>x.state==='core')],
  ['확장 수집 활성',registryCache.filter(x=>x.state==='promoted')],
  ['WATCH · 수집 관찰',registryCache.filter(x=>x.state==='watch')]
 ];
 select.innerHTML='<option value="ALL">🌐 전체 게임</option>'+groups.filter(([,rows])=>rows.length).map(([label,rows])=>`<optgroup label="${esc(label)}">${rows.map(x=>`<option value="${esc(x.canonical||'')}">${esc(x.label_ko||x.canonical||x.id||'')}</option>`).join('')}</optgroup>`).join('');
 const values=new Set([...select.options].map(x=>x.value));selectedGame=values.has(previous)?previous:'ALL';select.value=selectedGame;
 updateBoxFilterState();
}
function updateBoxFilterState(){
 const state=$('boxKbFilterState');if(!state)return;
 const country=currentCountry(),countryLabel=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';
 state.textContent=`${gameLabel(selectedGame)} · ${countryLabel}`;
}
function renderBoxKnowledgeSafe(){try{if(typeof window.renderBoxKnowledge==='function')window.renderBoxKnowledge()}catch(_){}}
function passesTab(row,trading){const key=uniqueKey(row.country,row.name);if(activeTab==='TRADING')return trading.has(key);const state=releaseState(row);return activeTab==='UPCOMING'?state==='UPCOMING':state==='RELEASED'}
function applyTabFilter(){
 const list=$('box12');if(!list)return;
 const rows=catalogRowsForCountry();const trading=marketTradingSet(marketCache.entries||{});const kids=[...list.querySelectorAll('.box-kb-card')];
 let shown=0;
 kids.forEach((el,i)=>{const row=rows[i];const ok=!!row&&gameMatches(row)&&passesTab(row,trading);el.style.display=ok?'':'none';if(ok){shown++;updateBoxPriceCard(el,row)}});
 const country=currentCountry();const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';
 const tabLabel=activeTab==='RELEASED'?'지금까지 출시':activeTab==='TRADING'?'최근 14일 시세 확인':'앞으로 출시 예정';
 const count=$('boxKbCount');if(count)count.textContent=`📦 ${gameLabel(selectedGame)} · ${label} · ${tabLabel} ${shown}개`;
 updateBoxFilterState();
 if(shown===0&&!list.querySelector('.boxkb-tab-empty')){
  const d=document.createElement('div');d.className='boxkb-tab-empty';
  d.innerHTML='<div class="boxkb-empty-icon">📭</div><b>이 조건에서 확인된 BOX가 아직 없습니다.</b><span>다른 상태를 선택하거나 전체 게임·전체 국가로 넓혀 보세요.</span><div class="boxkb-empty-actions"><button type="button" data-box-empty="all-game">전체 게임 보기</button><button type="button" data-box-empty="all-country">전체 국가 보기</button></div>';
  d.querySelector('[data-box-empty="all-game"]')?.addEventListener('click',()=>{selectedGame='ALL';const sel=$('boxKbGame');if(sel)sel.value='ALL';renderBoxKnowledgeSafe();applyTabFilter();refreshStatsOnly()});
  d.querySelector('[data-box-empty="all-country"]')?.addEventListener('click',()=>{document.querySelector('.box-kb-country[data-kb-country="ALL"]')?.click()});
  list.appendChild(d);
 }
 const empty=list.querySelector('.boxkb-tab-empty');if(empty)empty.style.display=shown?'none':'grid';
}
async function refreshStatsOnly(){
 if(!ensureUi())return;
 const country=currentCountry();const catalog=getCatalog();const entries=marketCache.entries||{};const inCountry=c=>country==='ALL'||c===country;
 const released=new Set(),upcoming=new Set(),trading=new Set(),images=new Set(),base=new Set();
 for(const x of catalog){const c=x.country||'';if(!inCountry(c)||!gameMatches(x))continue;const k=uniqueKey(c,x.name);base.add(k);const st=releaseState(x);if(st==='RELEASED')released.add(k);if(st==='UPCOMING')upcoming.add(k);if(validImage(x.boxImage))images.add(k);}
 for(const [key,v] of Object.entries(entries)){if(assetOfKey(key)!=='BOX')continue;const c=countryOfKey(key);if(!inCountry(c)||!gameMatches(v))continue;const k=uniqueKey(c,nameOfKey(key));if(recentVerifiedMarketSignal(v))trading.add(k);const st=releaseState(v);if(st==='RELEASED')released.add(k);if(st==='UPCOMING')upcoming.add(k);if(validImage(v?.image_url))images.add(k);}
 $('boxStatReleased').textContent=`${released.size}개`;$('boxStatTrading').textContent=`${trading.size}개`;$('boxStatUpcoming').textContent=`${upcoming.size}개`;$('boxStatImages').textContent=`${images.size}개`;
 const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';const labelGame=gameLabel(selectedGame);const note=$('boxStatNote');if(note)note.textContent=`${labelGame} · ${label} 기준 · 출시/예정은 확인된 출시일로 구분하고 최근 시세는 최근 14일 내 관측일·HTTPS 원문·정상 링크를 확인한 BOX만 집계합니다. 현재 확인 가능한 기본 목록 ${base.size}개.`;
}

function daysOld(value){
 // Market observations must be an entire canonical day, never a date-like
 // substring in an unverified provider message or a malformed timestamp.
 const source=String(value||'').trim();
 if(!/^20\d{2}-\d{2}-\d{2}$/.test(source))return 9999;
 const d=parseDate(source),today=today0();
 // Future or malformed observations cannot earn fresh-market ranking points.
 if(!d||d.getTime()>today.getTime())return 9999;
 return Math.floor((today.getTime()-d.getTime())/86400000);
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
 // New release dates never establish recent trades or source activity.
 const age=daysOld(row?.market_observed_at||row?.source_date);
 if(age<=7)score+=8;else if(age<=30)score+=5;else if(age<=90)score+=2;
 return Math.min(20,score);
}
function linkPoints(row){return String(row?.link_status||'').trim()==='정상'?5:0}
function hotRows(asset){
 const entries=marketCache.entries||{};
 const selected=document.getElementById('analysisGame')?.value||'ALL';
 const country=document.getElementById('analysisCountry')?.value||'ALL';
 return Object.entries(entries).filter(([key,row])=>{
  if(assetOfKey(key)!==asset||!recentVerifiedMarketSignal(row))return false;
  const region=countryOfKey(key),name=nameOfKey(key),game=marketGame(region,name,row);
  return (country==='ALL'||region===country)&&(selected==='ALL'||game===selected);
 }).map(([key,row])=>{
   const region=countryOfKey(key),name=nameOfKey(key),watch=watchMatch(region,name,asset);
   const fresh=freshnessPoints(row?.market_observed_at||row?.source_date),evidence=evidencePoints(row),watchScore=watchPoints(watch),link=linkPoints(row);
   const score=Math.min(100,fresh+evidence+watchScore+link);
   const reasons=[];
   if(fresh>=30)reasons.push('최근 시세');
   if(evidence>=12)reasons.push('거래 근거');
   if(watchScore>=12)reasons.push('판매·거래 상태');
   if(link===5)reasons.push('출처 정상');
   return {region,name,asset,row,watch,score,reasons,game:marketGame(region,name,row)};
 }).sort((a,b)=>b.score-a.score||daysOld(a.row?.market_observed_at||a.row?.source_date)-daysOld(b.row?.market_observed_at||b.row?.source_date)||a.name.localeCompare(b.name,'ko')).slice(0,5);
}
function ensureHotUi(){
 const section=$('v14section');if(!section)return null;
 let panel=$('hotMarketSignals');
 if(panel)return panel;
 panel=document.createElement('section');panel.id='hotMarketSignals';panel.className='hot-market-signals';
 panel.innerHTML='<div class="hot-market-head"><div><span class="hot-market-kicker">LIVE SIGNAL</span><strong>🔥 최근 시장 활동</strong><small>가격 상승률 순위가 아니라 최근 수집일·거래 근거·판매 상태·출처 상태를 합산합니다.</small></div><span class="hot-market-badge">구매추천 아님</span></div><div id="hotMarketMeta" class="hot-market-meta"></div><div id="hotMarketGrid" class="hot-market-grid"></div>';
 const anchor=section.querySelector('#learningKey')||section.querySelector('.analysis-count')||null;
 if(anchor)section.insertBefore(panel,anchor);else section.appendChild(panel);
 return panel;
}
function hotColumn(asset,label){
 const wrap=document.createElement('div');wrap.className='hot-market-column';
 const head=document.createElement('b');head.className='hot-market-column-title';head.textContent=label;wrap.appendChild(head);
 const rows=hotRows(asset);
 if(!rows.length){const empty=document.createElement('div');empty.className='hot-market-empty';empty.textContent=`${gameLabel(document.getElementById('analysisGame')?.value||'ALL')}에서 현재 검증된 ${asset==='BOX'?'BOX':'카드'} 시장 신호가 없습니다.`;wrap.appendChild(empty);return wrap}
 rows.forEach((item,index)=>{
  const card=document.createElement('div');card.className='hot-market-item';
  const line=document.createElement('div');line.className='hot-market-item-title';line.textContent=`${index+1}위 · ${item.region} · ${item.name}`;
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
 const meta=$('hotMarketMeta');if(meta){const g=document.getElementById('analysisGame')?.value||'ALL',c=document.getElementById('analysisCountry')?.value||'ALL';meta.textContent=`${gameLabel(g)} · ${c==='ALL'?'전체 국가':c} · 시장자료 ${updated||'확인 중'} · HOT 점수는 구매추천이 아니라 활동 신호입니다.`;}
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
 control.addEventListener('change',syncAnalysisAssetMode);
 ['analysisAsset','analysisGame','analysisCountry','analysisSort'].forEach(id=>{
  const el=$(id);if(!el||el.dataset.boxHitModernHook==='1')return;el.dataset.boxHitModernHook='1';
  el.addEventListener('change',()=>{syncAnalysisAssetMode();renderHot();setTimeout(renderExpandedAnalysisFallback,0)});
 });
 syncAnalysisAssetMode();
}
function expandedAnalysisRows(){
 const selected=$('analysisGame')?.value||'ALL',country=$('analysisCountry')?.value||'ALL',asset=$('analysisAsset')?.value||'ALL',query=String($('analysisQuery')?.value||'').trim().toLowerCase();
 const keys=new Set([...Object.keys(marketCache.entries||{}),...(Array.isArray(watchCache.items)?watchCache.items.map(x=>hotKey(x.region,x.name,x.asset)):[])]);
 return [...keys].map(key=>{
  const [region,name,kind]=String(key).split('|'),price=(marketCache.entries||{})[key]||{},watch=watchMatch(region,name,kind)||{},game=marketGame(region,name,price)||String(watch.game||'');
  return {key,region,name,asset:kind,price,watch,game};
 }).filter(x=>(asset==='ALL'||x.asset===asset)&&(country==='ALL'||x.region===country)&&(selected==='ALL'||x.game===selected))
 .filter(x=>!query||[x.name,x.price.card_name,x.price.product_name,x.watch.native,x.game,gameLabel(x.game)].filter(Boolean).join(' ').toLowerCase().includes(query))
 .sort((a,b)=>String(b.price.source_date||b.watch.release_date||'').localeCompare(String(a.price.source_date||a.watch.release_date||''))).slice(0,40);
}
function renderExpandedAnalysisFallback(){
 const list=$('countryAnalysisList'),count=$('analysisCount');if(!list||!count)return;
 const current=String(count.textContent||'');
 if(!/검색 결과 0건/.test(current)&&!list.querySelector('.analysis-empty'))return;
 const selected=$('analysisGame')?.value||'ALL',rows=expandedAnalysisRows();
 if(rows.length){
  count.textContent=`🔎 검증 시장자료 ${rows.length}건 · ${gameLabel(selected)} · COUNTRY_BOX_DATA 외 확장 수집 결과`;
  list.innerHTML=rows.map((x,i)=>{
   const display=String(x.price.display||x.watch.official_price||'가격 확인 중'),source=String(x.price.source||x.watch.source||''),status=priced(x.price)?'✅ 가격 확인':'🕒 가격 검증 중';
   return `<article class="analysis-box analysis-market-fallback"><div class="analysis-head"><div class="analysis-title"><span class="analysis-rank">${i+1}</span>${x.asset==='BOX'?'📦':'🎴'} ${esc(x.name)}<span class="analysis-native">${esc(gameLabel(x.game))}</span></div><div class="analysis-sub">${esc(x.region)} · ${status}</div></div><div class="analysis-parts"><div class="analysis-part"><h4>💹 현재 확인값</h4><div class="analysis-value">${esc(display)}</div></div><div class="analysis-part"><h4>🧾 수집 상태</h4><div class="analysis-value">${esc(x.price.kind||x.watch.sale_status||'시장 교차검증 중')}</div><div class="analysis-text">${esc(x.price.transactions||'검증 가능한 공개 근거를 수집 중입니다.')}</div></div></div>${/^https:\/\//i.test(source)?`<a class="analysis-source" href="${esc(source)}" target="_blank" rel="noopener noreferrer">시장 근거 보기</a>`:''}</article>`;
  }).join('');
  return;
 }
 const selectedText=gameLabel(selected);
 list.innerHTML=`<div class="analysis-empty analysis-empty-modern"><span class="analysis-empty-icon">🔎</span><b>${esc(selectedText)}의 검증 자료가 아직 없습니다.</b><span>고장이 아니라 현재 필터에 맞는 출시/시장 교차검증 자료가 0건입니다. 전체 게임으로 넓히거나 전체 자료 수집을 실행하세요.</span><div class="analysis-empty-actions"><button type="button" data-analysis-empty="all">전체 게임 보기</button><button type="button" data-analysis-empty="collect">전체 자료 수집</button></div></div>`;
 list.querySelector('[data-analysis-empty="all"]')?.addEventListener('click',()=>{const game=$('analysisGame');if(game){game.value='ALL';game.dispatchEvent(new Event('change',{bubbles:true}))}});
 list.querySelector('[data-analysis-empty="collect"]')?.addEventListener('click',()=>{$('siteUpdateAll')?.click()});
}
function decorateTargetSections(){
 const box=$('box12section'),analysis=$('v14section');box?.classList.add('tcg-modern-section','tcg-box-knowledge-modern');analysis?.classList.add('tcg-modern-section','tcg-box-hit-modern');
 const boxTitle=box?.querySelector(':scope > h3'),boxHelp=box?.querySelector(':scope > .muted');
 if(boxTitle)boxTitle.textContent='📦 BOX 지식베이스';
 if(boxHelp)boxHelp.textContent='게임을 먼저 고른 뒤 국가와 상태를 선택하면 출시 BOX · 현재 거래 · 출시 예정 정보를 한 화면에서 확인할 수 있습니다.';
 const analysisTitle=analysis?.querySelector(':scope > h3'),analysisHelp=analysis?.querySelector(':scope > .muted');
 if(analysisTitle)analysisTitle.textContent='⭐ BOX · HIT 시장 분석';
 if(analysisHelp)analysisHelp.textContent='게임 · 국가 · 대상을 선택하면 같은 조건으로 HOT 신호와 BOX/HIT 결과를 함께 보여줍니다. 검증자료가 없으면 0건 이유를 구분해 표시합니다.';
 analysis?.querySelector('.analysis-controls')?.classList.add('tcg-modern-filter-grid');
 const q=$('analysisQuery');q?.classList.add('tcg-modern-search');
 const primary=$('analysisSearchBtn'),clear=$('analysisClearBtn');primary?.classList.add('tcg-modern-primary');clear?.classList.add('tcg-modern-secondary');
}

async function refresh(){
 decorateTargetSections();ensureUi();hookAnalysisAsset();
 [marketCache,watchCache,registryCache]=await Promise.all([loadMarket(),loadWatch(),loadRegistry()]);
 populateGameFilter();await refreshStatsOnly();applyTabFilter();renderHot();
}

// 기존 renderBoxKnowledge 실행 뒤 탭 필터를 다시 적용한다.
const hookRender=()=>{try{
 if(typeof window.renderBoxKnowledge==='function'&&!window.renderBoxKnowledge.__boxTabsHooked){const orig=window.renderBoxKnowledge;const wrapped=function(...args){const r=orig.apply(this,args);setTimeout(()=>{applyTabFilter();refreshStatsOnly()},0);return r};wrapped.__boxTabsHooked=true;window.renderBoxKnowledge=wrapped}
 if(typeof window.renderCountryAnalysis==='function'&&!window.renderCountryAnalysis.__expandedFallbackHooked){const origA=window.renderCountryAnalysis;const wrappedA=function(...args){const r=origA.apply(this,args);setTimeout(()=>{renderExpandedAnalysisFallback();renderHot()},0);return r};wrappedA.__expandedFallbackHooked=true;window.renderCountryAnalysis=wrappedA}
}catch(_){}};
window.addEventListener('tcg-market-catalog-expanded',()=>setTimeout(refresh,80));
document.addEventListener('click',e=>{const t=e.target.closest?.('button');if(!t||t.dataset.boxTab)return;if(/한국|일본|미국|전체/.test(t.textContent||''))setTimeout(()=>{updateBoxFilterState();refreshStatsOnly();applyTabFilter()},150)});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{hookRender();refresh()},550));else setTimeout(()=>{hookRender();refresh()},550);
setInterval(()=>{if(!document.hidden)refresh()},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});window.refreshBoxKnowledgeStats=refresh;
})();

/* V599 independent official product-spec lens; deliberately NOT wired to market prices. */
;(()=>{
"use strict";
const URL_FILE="tcg_official_product_catalog_v599.json";
const TRUSTED={"ONE PIECE":"onepiece-cardgame.kr","GUNDAM CARD GAME":"gundam-gcg.com","Digimon Card Game":"digimoncard.com","Star Wars: Unlimited":"starwarsunlimited.com"};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let rows=[],last="";
function trusted(p){
 if(!p||!["BOX","PRERELEASE_BOX","BOOSTER_PACK"].includes(p.product_type)||!["KR","JP","US"].includes(p.country)||!p.name||!p.set_code)return false;
 try{const u=new URL(p.source),h=TRUSTED[p.game];return Boolean(h&&u.protocol==="https:"&&!u.username&&!u.password&&(!u.port||u.port==="443")&&(u.hostname===h||u.hostname.endsWith("."+h)))}catch(_){return false}
}
function render(){
 const parent=document.getElementById("boxKnowledgeStats");if(!parent)return;
 let box=document.getElementById("boxOfficialCatalog");
 if(!box){box=document.createElement("details");box.id="boxOfficialCatalog";box.className="boxkb-official";parent.appendChild(box)}
 const game=document.getElementById("boxKbGame")?.value||"ALL";
 const country=document.querySelector(".box-kb-country.active")?.dataset.kbCountry||"ALL";
 const key=game+"|"+country+"|"+rows.length;
 if(key===last)return;last=key;
 const chosen=rows.filter(p=>(game==="ALL"||p.game===game)&&(country==="ALL"||p.country===country))
  .sort((a,b)=>String(b.release_date||b.set_release_date||"").localeCompare(String(a.release_date||a.set_release_date||"")));
 const labels={BOX:"📦 미개봉 BOX",PRERELEASE_BOX:"📦 프리릴리즈 BOX",BOOSTER_PACK:"🃏 부스터팩"};
 const cards=chosen.slice(0,40).map(p=>{
  const date=p.release_date?"발매 "+p.release_date:p.set_release_date?"세트 발매 "+p.set_release_date+" · BOX 발매일 미확인":"발매일 미확인";
  const specs=[p.packs_per_box?"BOX "+p.packs_per_box+"팩":"",p.cards_per_pack?"1팩 "+p.cards_per_pack+"장":""].filter(Boolean).join(" · ");
  const price=Number.isFinite(p.msrp?.amount)?"제조사 정가 "+(p.msrp.currency==="KRW"?p.msrp.amount.toLocaleString("ko-KR")+"원":"$"+p.msrp.amount.toFixed(2))+"/"+p.msrp.unit:"정가 미확인";
  return '<article class="boxkb-official-card"><b>'+esc(labels[p.product_type])+' · '+esc(p.name)+'</b><small> ['+esc(p.set_code)+'] · '+esc(p.country)+'</small><div>'+esc(date)+' · '+esc(specs||"구성 추가 검증 필요")+'</div><strong>'+esc(price)+'</strong><small>'+esc(p.notes||"")+'</small><a href="'+esc(p.source)+'" target="_blank" rel="noopener noreferrer">제조사 원문 ↗</a></article>';
 }).join("");
 box.innerHTML='<summary>🏭 제조사 공식 상품정보 '+chosen.length+'건 <small>출시일 · 팩 구성 · 정가 (거래시세 아님)</small></summary><div class="boxkb-official-body"><p>공식 상품 사양만 표시합니다. 미개봉 BOX·프리릴리즈 BOX·낱팩을 구분하며 중고 시세나 실거래로 집계하지 않습니다.</p>'+(cards||'<p>선택 조건에 맞는 제조사 검증 상품정보가 없습니다.</p>')+'</div>';
}
async function init(){
 try{const res=await fetch(URL_FILE+"?_="+Date.now(),{cache:"no-store"});if(res.ok){const x=await res.json();if(x?.schema_version===1&&Array.isArray(x.products))rows=x.products.slice(0,100).filter(trusted)}}catch(_){rows=[]}
 render();
 document.addEventListener("change",e=>{if(e.target?.id==="boxKbGame")render()});
 document.addEventListener("click",e=>{if(e.target?.closest?.(".box-kb-country"))setTimeout(render,0)});
 document.addEventListener("visibilitychange",()=>{if(!document.hidden)render()});
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>setTimeout(init,950));else setTimeout(init,950);
})();
