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
 const d=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]),0,0,0,0);
 return Number.isNaN(d.getTime())?null:d;
}
function today0(){const d=new Date();return new Date(d.getFullYear(),d.getMonth(),d.getDate())}
function releaseState(row){const d=parseDate(row?.release||row?.release_date||row?.source_date);if(!d)return 'UNKNOWN';return d<=today0()?'RELEASED':'UPCOMING'}
function marketTradingSet(entries){const set=new Set();for(const [k,v] of Object.entries(entries||{})){if(assetOfKey(k)!=='BOX'||!priced(v))continue;set.add(uniqueKey(countryOfKey(k),nameOfKey(k)))}return set}

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
    <button type="button" class="boxkb-tab" data-box-tab="TRADING"><span>💹</span><b>거래중</b><small>가격 신호 확인</small></button>
    <button type="button" class="boxkb-tab" data-box-tab="UPCOMING"><span>🗓️</span><b>출시 예정</b><small>앞으로 출시</small></button>
   </div>
   <div class="boxkb-stat-grid">
    <article><span>📚 누적 출시</span><strong id="boxStatReleased">-</strong><small>오늘까지 출시일 확인</small></article>
    <article><span>💹 현재 거래</span><strong id="boxStatTrading">-</strong><small>검증 가격 신호</small></article>
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
 kids.forEach((el,i)=>{const row=rows[i];const ok=!!row&&gameMatches(row)&&passesTab(row,trading);el.style.display=ok?'':'none';if(ok)shown++;});
 const country=currentCountry();const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';
 const tabLabel=activeTab==='RELEASED'?'지금까지 출시':activeTab==='TRADING'?'현재 거래중':'앞으로 출시 예정';
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
 for(const [key,v] of Object.entries(entries)){if(assetOfKey(key)!=='BOX')continue;const c=countryOfKey(key);if(!inCountry(c)||!gameMatches(v))continue;const k=uniqueKey(c,nameOfKey(key));if(priced(v))trading.add(k);const st=releaseState(v);if(st==='RELEASED')released.add(k);if(st==='UPCOMING')upcoming.add(k);if(validImage(v?.image_url))images.add(k);}
 $('boxStatReleased').textContent=`${released.size}개`;$('boxStatTrading').textContent=`${trading.size}개`;$('boxStatUpcoming').textContent=`${upcoming.size}개`;$('boxStatImages').textContent=`${images.size}개`;
 const label=country==='KR'?'한국':country==='JP'?'일본':country==='US'?'미국':'전체 국가';const labelGame=gameLabel(selectedGame);const note=$('boxStatNote');if(note)note.textContent=`${labelGame} · ${label} 기준 · 출시/예정은 확인된 출시일로 구분하고 거래중은 실제 가격 신호가 있는 BOX만 집계합니다. 현재 확인 가능한 기본 목록 ${base.size}개.`;
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
 const selected=document.getElementById('analysisGame')?.value||'ALL';
 const country=document.getElementById('analysisCountry')?.value||'ALL';
 return Object.entries(entries).filter(([key,row])=>{
  if(assetOfKey(key)!==asset||!priced(row))return false;
  const region=countryOfKey(key),name=nameOfKey(key),game=marketGame(region,name,row);
  return (country==='ALL'||region===country)&&(selected==='ALL'||game===selected);
 }).map(([key,row])=>{
   const region=countryOfKey(key),name=nameOfKey(key),watch=watchMatch(region,name,asset);
   const fresh=freshnessPoints(row.source_date),evidence=evidencePoints(row),watchScore=watchPoints(watch),link=linkPoints(row);
   const score=Math.min(100,fresh+evidence+watchScore+link);
   const reasons=[];
   if(fresh>=30)reasons.push('최근 시세');
   if(evidence>=12)reasons.push('거래 근거');
   if(watchScore>=12)reasons.push('판매·거래 상태');
   if(link===5)reasons.push('출처 정상');
   return {region,name,asset,row,watch,score,reasons,game:marketGame(region,name,row)};
 }).sort((a,b)=>b.score-a.score||daysOld(a.row.source_date)-daysOld(b.row.source_date)||a.name.localeCompare(b.name,'ko')).slice(0,5);
}
function ensureHotUi(){
 const section=$('v14section');if(!section)return null;
 let panel=$('hotMarketSignals');
 if(panel)return panel;
 panel=document.createElement('section');panel.id='hotMarketSignals';panel.className='hot-market-signals';
 panel.innerHTML='<div class="hot-market-head"><div><span class="hot-market-kicker">LIVE SIGNAL</span><strong>🔥 최근 시장 활동</strong><small>가격 상승률 순위가 아니라 최근 수집일·거래 근거·판매 상태·출처 상태를 합산합니다.</small></div><span class="hot-market-badge">구매추천 아님</span></div><div id="hotMarketMeta" class="hot-market-meta"></div><div id="hotMarketGrid" class="hot-market-grid"></div>';
 const anchor=section.querySelector('label')||section.firstChild;section.insertBefore(panel,anchor);
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
