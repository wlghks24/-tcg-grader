(()=>{
'use strict';
const GLOBAL_KEY='__TCG_MULTI_MARKET_PRICES__';
if(globalThis[GLOBAL_KEY]?.loaded)return;
globalThis[GLOBAL_KEY]={loaded:true,version:483};
const $=id=>document.getElementById(id);
const krw=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'—';
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const statusText={ok:'수집됨',ready:'확인 대기',no_result:'결과 없음',not_configured:'API 키 필요',unsupported:'해당 게임 미지원',query_language_unsupported:'영문·일문 카드명 필요',cooldown_skip:'안전 대기',cooldown:'안전 대기',error:'일시 오류'};
const variantLabels={manga:'만화 레어',parallel:'패러렐',special_art:'스페셜 아트',alt_art:'얼터 아트',full_art:'풀 아트',reverse_holo:'리버스 홀로',standard:'일반판',holo:'홀로',foil:'포일',promo:'프로모'};
const variantTerms={manga:'manga rare',parallel:'parallel',special_art:'special art rare',alt_art:'alt art',full_art:'full art',reverse_holo:'reverse holo',standard:'standard',holo:'holo',foil:'foil',promo:'promo'};
const freshnessText={FRESH:'최신',AGING:'최근',STALE:'노후',EXPIRED:'오래됨',UNKNOWN:'날짜 미확인'};
const conditionLabels={ALL:'전체 상태',NM:'NM',LP:'LP',MP:'MP',HP:'HP',DMG:'DMG'};
const evidenceLabels={ALL:'전체 근거',completed:'완료거래',api_reference:'API 참고시세',asking:'판매중/호가'};
const HISTORY_KEY='tcg.multi.market.history.v483',RECENT_KEY='tcg.multi.market.recent.v483';
let variantOverride='',lastBaseQuery='',marketCondition='ALL',marketPrinting='ALL',evidenceView='ALL';

function mount(){
 if($('multiMarketPanel'))return true;
 const out=$('market12out');if(!out)return false;
 const section=document.createElement('section');section.id='multiMarketPanel';section.className='multi-market-panel';
 section.innerHTML=`
  <div class="mmp-head"><div class="mmp-head-copy"><b>🌐 다중마켓 시세 교차검색</b><small>eBay · 국내외 마켓 · SNKRDUNK · JustTCG · TCGdex · Pavilion TCG</small></div><div class="mmp-head-actions"><button id="multiMarketExportCsv" type="button">CSV 저장</button><button id="multiMarketExportJson" type="button">JSON 저장</button><button id="multiMarketRefresh" type="button">↻ 다시 수집</button></div></div>
  <div id="multiMarketSummary" class="mmp-summary mmp-wait"><b>카드 인식 후 자동 검색</b><span>카드명이나 카드번호가 들어오면 여러 마켓을 동시에 확인합니다.</span></div>
  <div id="multiMarketFilters" class="mmp-filterbar">
    <label><span>카드 상태</span><select id="multiMarketCondition"><option value="ALL">전체 상태</option><option value="NM">NM · Near Mint</option><option value="LP">LP · Lightly Played</option><option value="MP">MP · Moderately Played</option><option value="HP">HP · Heavily Played</option><option value="DMG">DMG · Damaged</option></select></label>
    <label><span>인쇄판</span><select id="multiMarketPrinting"><option value="ALL">자동/전체</option><option value="standard">일반판</option><option value="holo">홀로</option><option value="reverse_holo">리버스 홀로</option><option value="foil">포일</option><option value="parallel">패러렐</option><option value="special_art">스페셜 아트</option><option value="alt_art">얼터 아트</option><option value="full_art">풀 아트</option><option value="manga">만화 레어</option><option value="promo">프로모</option></select></label>
    <label><span>가격 근거 보기</span><select id="multiMarketEvidence"><option value="ALL">전체 근거</option><option value="completed">완료거래</option><option value="api_reference">API 참고시세</option><option value="asking">판매중/호가</option></select></label>
    <div class="mmp-edition-context"><span>언어/판본</span><b id="multiMarketEditionLabel">전체</b><small>위 국가/판본 선택과 연동</small></div>
  </div>
  <section id="multiMarketVariant" class="mmp-variant-control" hidden></section>
  <section id="multiMarketRecommendation" class="mmp-recommendation" hidden></section>
  <section id="multiMarketHistory" class="mmp-history" hidden></section>
  <section id="multiMarketRecent" class="mmp-recent" hidden></section>
  <div id="multiMarketSources" class="mmp-source-status" aria-label="추가 참고출처 상태"></div>
  <section id="multiMarketGrade" class="mmp-grade-section" hidden></section>
  <section id="multiMarketReferences" class="mmp-reference-section" hidden></section>
  <div id="multiMarketRows" class="mmp-rows"></div><div id="multiMarketNote" class="mmp-note"></div>`;
 out.insertAdjacentElement('afterend',section);
 $('multiMarketRefresh')?.addEventListener('click',()=>load(true));
 $('multiMarketExportCsv')?.addEventListener('click',()=>downloadEvidence('csv'));
 $('multiMarketExportJson')?.addEventListener('click',()=>downloadEvidence('json'));
 $('multiMarketCondition')?.addEventListener('change',event=>{marketCondition=String(event.target.value||'ALL').toUpperCase();load(true)});
 $('multiMarketPrinting')?.addEventListener('change',event=>{marketPrinting=String(event.target.value||'ALL');variantOverride=marketPrinting==='ALL'?'':marketPrinting;load(true)});
 $('multiMarketEvidence')?.addEventListener('change',event=>{evidenceView=String(event.target.value||'ALL');if(window.__multiMarketPrices)render(window.__multiMarketPrices)});
 updateEditionLabel();
 return true;
}

const MARKET_LINK_DOMAINS=new Set(['ebay.com','ebay.co.jp','amazon.com','amazon.co.jp','tcgplayer.com','cardmarket.com','snkrdunk.com','kream.co.kr','daangn.com','bunjang.co.kr','joongna.com','collectory.cc','mercari.com','yahoo.co.jp','justtcg.com','tcgdex.net','tcgdex.dev','pavilion-tcg.com','pokemon.com','pokemon-card.com','pokemonkorea.co.kr','onepiece-cardgame.com','onepiece-cardgame.kr']);
function safeMarketHref(value){
 try{
  const raw=String(value??'').trim();
  if(raw.length<11||raw.length>2048||!/^https:\/\//i.test(raw))return '';
  const url=new URL(raw);
  if(url.protocol!=='https:'||url.username||url.password||(url.port&&url.port!=='443'))return '';
  const host=url.hostname.toLowerCase();
  if(![...MARKET_LINK_DOMAINS].some(domain=>host===domain||host.endsWith('.'+domain)))return '';
  return esc(url.href);
 }catch(_){return ''}
}

function knownEvidenceAge(value) {
  // Missing observation dates are unknown, not an observation from today.
  if (value == null || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null;
  const days = Number(value);
  return Number.isSafeInteger(days) && days >= 0 ? days : null;
}
function freshnessBadge(row){
 const status=String(row?.freshness_status||'UNKNOWN'),label=freshnessText[status]||status;
 const ageDays = knownEvidenceAge(row?.freshness_age_days);
  const age = ageDays === null ? '' : ` · ${ageDays}일`;
 return `<span class="mmp-fresh mmp-fresh-${esc(status.toLowerCase())}">${esc(label)}${age}</span>`;
}
function sourceBadge(item){
 const identity=item.summary_eligible===false?'<span class="mmp-kind">참고만</span>':(String(item.identity_basis||'').includes('card_number')?'<span class="mmp-api">카드일치</span>':'');
 return `<span class="mmp-source">${esc(item.source)}</span><span class="mmp-kind">${esc(item.price_kind||'가격')}</span>${item.verified_api?'<span class="mmp-api">API</span>':''}${identity}${freshnessBadge(item)}`;
}

function updateEditionLabel(){
 const region=String($('market12')?.value||'ALL').toUpperCase();
 const labels={ALL:'전체',KR:'한국어/한국판',JP:'일본어/일본판',US:'영어/미국판'};
 const node=$('multiMarketEditionLabel');if(node)node.textContent=labels[region]||region;
}
function itemEvidenceClass(item){
 const direct=String(item?.evidence_class||'');
 if(direct)return direct;
 const kind=String(item?.price_kind||'').toLowerCase();
 if(kind.includes('완료')||kind.includes('실거래'))return 'completed';
 if(item?.verified_api===true&&!kind.includes('판매중')&&!kind.includes('판매가'))return 'api_reference';
 return 'asking';
}
function evidenceVisible(row){
 if(evidenceView==='ALL')return true;
 if(row?.basis){
  const basis=String(row.basis||'');
  return evidenceView==='completed'?basis.includes('완료거래'):evidenceView==='api_reference'?basis.includes('API 참고시세'):basis.includes('판매중/호가');
 }
 return itemEvidenceClass(row)===evidenceView;
}
function sellerText(row){
 const names=Array.isArray(row?.seller_names)?row.seller_names.filter(Boolean):[];
 if(names.length)return `판매자 ${names.slice(0,2).join(' · ')}${Number(row?.seller_count)>2?` 외 ${Number(row.seller_count)-2}명`:''}`;
 if(row?.seller_name)return `판매자 ${String(row.seller_name)}`;
 return '판매처 집계';
}
function safeLocalGet(key,fallback){
 try{const raw=localStorage.getItem(key);const value=raw?JSON.parse(raw):fallback;return value??fallback}catch(_){return fallback}
}
function safeLocalSet(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch(_){}}
function historyIdentity(data){
 const condition=String(data?.condition||marketCondition||'ALL'),printing=String(data?.printing||marketPrinting||'ALL');
 return [String(data?.game||'ALL'),String(data?.query||''),String(data?.region||'ALL'),condition,printing].join('|').toLowerCase();
}
function rememberMarket(data){
 const info=data?.summary||{};
 if(!data?.ok||info.identity_scope!=='exact_card_number'||info.variant_ambiguous===true)return;
 const identity=historyIdentity(data),now=new Date(),day=now.toISOString().slice(0,10);
 const row={identity,day,time:now.toISOString(),query:String(data.query||''),game:String(data.game||'ALL'),region:String(data.region||'ALL'),condition:String(data.condition||'ALL'),printing:String(data.printing||'ALL'),recommended:Number(info.recommended_trade_krw||0),median:Number(info.median_krw||0),source_count:Number(info.recommendation_source_count||info.source_count||0),confidence:String(info.recommendation_confidence||''),freshness:String(info.recommendation_freshness||'')};
 const history=Array.isArray(safeLocalGet(HISTORY_KEY,[]))?safeLocalGet(HISTORY_KEY,[]):[];
 const next=history.filter(x=>!(x&&x.identity===identity&&x.day===day));
 next.push(row);safeLocalSet(HISTORY_KEY,next.slice(-160));
 const recent=Array.isArray(safeLocalGet(RECENT_KEY,[]))?safeLocalGet(RECENT_KEY,[]):[];
 safeLocalSet(RECENT_KEY,[row,...recent.filter(x=>x&&x.identity!==identity)].slice(0,10));
}
function pctChange(current,base){return Number(base)>0?((Number(current)/Number(base)-1)*100):null}
function trendText(value){if(!Number.isFinite(value))return '데이터 축적 중';const sign=value>0?'+':'';return `${sign}${value.toFixed(1)}%`}
function renderHistory(data){
 const box=$('multiMarketHistory');if(!box)return;
 const identity=historyIdentity(data),history=(Array.isArray(safeLocalGet(HISTORY_KEY,[]))?safeLocalGet(HISTORY_KEY,[]):[]).filter(x=>x&&x.identity===identity&&Number(x.recommended)>0).sort((a,b)=>String(a.time).localeCompare(String(b.time)));
 if(!history.length){box.hidden=true;box.innerHTML='';return}
 const latest=history[history.length-1],latestMs=Date.parse(latest.time)||Date.now();
 const baseline=days=>{const target=latestMs-days*86400000;let best=null;for(const row of history){const t=Date.parse(row.time)||0;if(t<=target)best=row}return best};
 const p7=baseline(7),p30=baseline(30),c7=p7?pctChange(latest.recommended,p7.recommended):null,c30=p30?pctChange(latest.recommended,p30.recommended):null;
 box.hidden=false;
 box.innerHTML=`<div class="mmp-history-head"><div><b>🕘 이 기기 가격 조회이력</b><small>공식 거래이력이 아니라 이 태블릿/브라우저에서 확인한 추천가 스냅샷입니다.</small></div><button id="multiMarketHistoryClear" type="button">현재 카드 기록 지우기</button></div><div class="mmp-history-grid"><div><span>최근 추천가</span><b>${krw(latest.recommended)}</b><small>${esc(latest.day)} · ${esc(latest.freshness||'')}</small></div><div><span>7일 변화</span><b>${esc(trendText(c7))}</b></div><div><span>30일 변화</span><b>${esc(trendText(c30))}</b></div><div><span>저장 횟수</span><b>${history.length}회</b></div></div>`;
 $('multiMarketHistoryClear')?.addEventListener('click',()=>{const all=Array.isArray(safeLocalGet(HISTORY_KEY,[]))?safeLocalGet(HISTORY_KEY,[]):[];safeLocalSet(HISTORY_KEY,all.filter(x=>x?.identity!==identity));renderHistory(data)});
}
function renderRecent(){
 const box=$('multiMarketRecent');if(!box)return;
 const rows=Array.isArray(safeLocalGet(RECENT_KEY,[]))?safeLocalGet(RECENT_KEY,[]):[];
 if(!rows.length){box.hidden=true;box.innerHTML='';return}
 box.hidden=false;
 box.innerHTML=`<div class="mmp-recent-head"><b>최근 측정/조회</b><small>이 기기에만 저장 · 최대 10개</small></div><div class="mmp-recent-list">${rows.slice(0,8).map((row,index)=>`<button type="button" data-mmp-recent="${index}"><span>${esc(row.query)}</span><b>${krw(row.recommended)}</b><small>${esc(row.condition||'ALL')} · ${esc(variantLabels[row.printing]||row.printing||'ALL')}</small></button>`).join('')}</div>`;
 box.querySelectorAll('[data-mmp-recent]').forEach(btn=>btn.addEventListener('click',()=>{const row=rows[Number(btn.dataset.mmpRecent)];if(!row)return;const q=$('query12');if(q)q.value=row.query;const region=$('market12');if(region&&[...region.options].some(o=>o.value===row.region))region.value=row.region;const game=$('v12Game');if(game&&[...game.options].some(o=>o.value===row.game))game.value=row.game;marketCondition=row.condition||'ALL';marketPrinting=row.printing||'ALL';const c=$('multiMarketCondition'),p=$('multiMarketPrinting');if(c)c.value=marketCondition;if(p)p.value=marketPrinting;variantOverride=marketPrinting==='ALL'?'':marketPrinting;updateEditionLabel();load(false)}));
}

function renderSources(list){
 const box=$('multiMarketSources');if(!box)return;
 box.innerHTML=(list||[]).map(row=>`<div class="mmp-source-state mmp-state-${esc(row.status)}"><b>${esc(row.source)}</b><span>${esc(statusText[row.status]||row.status)}${Number(row.hits)>0?` · ${Number(row.hits)}건`:''}</span></div>`).join('');
}

function renderGrades(list){
 const box=$('multiMarketGrade');if(!box)return;
 const rows=Array.isArray(list)?list:[];box.hidden=!rows.length;
 if(!rows.length){box.innerHTML='';return;}
 box.innerHTML=`<div class="mmp-subhead"><div><b>등급별 참고시세</b><small>카드번호 일치 자료에서 업체·숫자등급을 분리하고, 완료거래→API 참고시세→판매중/호가 순으로 표시합니다.</small></div><span>Pavilion형 보기</span></div><div class="mmp-grade-grid">${rows.map(row=>`<div class="mmp-grade-card${row.price_krw?'':' mmp-grade-empty'}"><span>${esc(row.grade)}</span><b>${krw(row.price_krw)}</b><small>${row.count?`${Number(row.count)}건 · ${esc(row.basis||'공개가격')}`:'공개가격 없음'}</small></div>`).join('')}</div>`;
}

function renderReferences(list){
 const box=$('multiMarketReferences');if(!box)return;
 const rows=(Array.isArray(list)?list:[]).filter(row=>row&&safeMarketHref(row.url)).slice(0,24);box.hidden=!rows.length;
 if(!rows.length){box.innerHTML='';return;}
 box.innerHTML=`<div class="mmp-subhead"><div><b>추가 원문 교차확인</b><small>참고 사이트 가격은 원문에서 카드번호·언어·등급을 다시 확인하세요.</small></div></div><div class="mmp-reference-grid">${rows.map(row=>`<a href="${safeMarketHref(row.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(row.label)}</b><span>${esc(row.detail)}</span><em>원문 열기 →</em></a>`).join('')}</div>`;
}

function renderVariantControl(info){
 const box=$('multiMarketVariant');if(!box)return;
 const observed=Array.isArray(info?.observed_variants)?info.observed_variants.filter(Boolean):[];
 const ambiguous=info?.variant_ambiguous===true;
 const scope=String(info?.variant_scope||'');
 if(!ambiguous&&!observed.length){box.hidden=true;box.innerHTML='';return}
 box.hidden=false;
 if(ambiguous){
  const options=observed.map(key=>`<option value="${esc(key)}"${variantOverride===key?' selected':''}>${esc(variantLabels[key]||key)}</option>`).join('');
  box.innerHTML=`<div><b>🧩 변형/패러렐 확인 필요</b><span>같은 카드번호에서 여러 인쇄 변형이 섞였습니다. 하나를 선택하면 그 변형만 다시 조회합니다.</span></div><label>변형 선택<select id="multiMarketVariantSelect"><option value="">직접 선택</option>${options}</select></label>`;
  $('multiMarketVariantSelect')?.addEventListener('change',event=>{variantOverride=String(event.target.value||'');if(variantOverride){marketPrinting=variantOverride;const select=$('multiMarketPrinting');if(select)select.value=marketPrinting;load(true)}});
  return;
 }
 const label=variantLabels[scope]||scope||'미지정';
 box.innerHTML=`<div><b>✅ 변형 범위 ${esc(label)}</b><span>현재 가격 요약은 이 인쇄 변형 기준입니다.</span></div>`;
}

function csvCell(value){
 const text=String(value??'').replace(/"/g,'""');
 return `"${text}"`;
}
function measurementSnapshot(data){
 return {
  exported_at:new Date().toISOString(),
  card:{
   name:String($('identityCardName')?.value||$('agmName')?.textContent||''),
   number:String($('identityCardNumber')?.value||$('agmNumber')?.textContent||''),
   edition:String($('identityRegion')?.value||$('agmRegion')?.textContent||''),
   generation:String($('pokemonGenerationValue')?.textContent||$('gradeCockpitGeneration')?.textContent||''),
   expected_grade:String($('gradeCockpitOverall')?.textContent||''),
  },
  market:data||null
 };
}
function downloadBlob(name,type,text){
 const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function downloadEvidence(format){
 const data=window.__multiMarketPrices;if(!data?.ok)return;
 const safe=String(data.query||'card').replace(/[^0-9a-z가-힣_-]+/gi,'_').slice(0,60)||'card';
 if(format==='json'){
  downloadBlob(`tcg_${safe}_market.json`,'application/json;charset=utf-8',JSON.stringify(measurementSnapshot(data),null,2));return;
 }
 const info=data.summary||{},rows=[['카드검색',data.query],['지역/언어판본',data.region],['게임',data.game],['상태',data.condition||'ALL'],['인쇄판',data.printing||'ALL'],['추천거래가_KRW',info.recommended_trade_krw||''],['추천범위_최저_KRW',info.recommendation_min_krw||''],['추천범위_최고_KRW',info.recommendation_max_krw||''],['추천신뢰도',info.recommendation_confidence||''],['가격최신성',info.recommendation_freshness||''],[],['출처','판매자/상점','증거등급','출처중앙가_KRW','최저_KRW','최고_KRW','표본수','상태','인쇄판','최신성','경과일','추천가반영','원문']];
 const exportSourceRows=Array.isArray(data.evidence_source_breakdown)&&data.evidence_source_breakdown.length?data.evidence_source_breakdown:(data.source_breakdown||[]);
 for(const row of exportSourceRows)rows.push([row.source||row.source_id||'',Array.isArray(row.seller_names)?row.seller_names.join(' / '):'',row.basis||'',row.price_krw||'',row.min_krw||'',row.max_krw||'',row.count||0,Array.isArray(row.conditions)?row.conditions.join('/'):'',Array.isArray(row.printings)?row.printings.join('/'):'',freshnessText[row.freshness_status]||row.freshness_status||'',row.freshness_age_days??'',row.contributes_to_recommendation===true?'Y':'N',row.sample_url||'']);
 downloadBlob(`tcg_${safe}_market.csv`,'text/csv;charset=utf-8','\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\n'));
}

function renderRecommendation(data){
 const box=$('multiMarketRecommendation');if(!box)return;
 const info=data?.summary||{},recommendation=Number(info.recommended_trade_krw||0);
 const recommendationRows=Array.isArray(data?.source_breakdown)?data.source_breakdown:[];
 const latestAge = knownEvidenceAge(info.recommendation_latest_age_days);
 const evidenceRows=Array.isArray(data?.evidence_source_breakdown)?data.evidence_source_breakdown:[];
 const rows=evidenceView==='ALL'?recommendationRows:evidenceRows.filter(row=>String(row?.evidence_class||'')===evidenceView);
 const visible=rows.filter(row=>Number(row?.price_krw)>0).slice(0,12);
 if(!(recommendation>0)&&!visible.length){box.hidden=true;box.innerHTML='';return}
 box.hidden=false;
 const range=(Number(info.recommendation_min_krw)>0&&Number(info.recommendation_max_krw)>0)
   ?`${krw(info.recommendation_min_krw)} ~ ${krw(info.recommendation_max_krw)}`:'근거 부족';
 const headline=recommendation>0
   ?`<div class="mmp-recommendation-head"><div><span>추천 거래 기준가</span><b>${krw(recommendation)}</b><small>${esc(info.recommendation_basis||info.basis||'동일 기준')} · 신뢰도 ${esc(info.recommendation_confidence||'낮음')} · 최신성 ${esc(info.recommendation_freshness||'확인 중')}</small></div><div><span>관측 범위</span><b>${range}</b><small>${Number(info.recommendation_source_count)||0}곳 · ${Number(info.recommendation_sample_count)||0}건${latestAge === null ? '' : ` · 최신근거 ${latestAge}일 전`}</small></div></div>`
   :`<div class="mmp-recommendation-hold"><b>추천 거래금액 보류</b><span>${esc(info.basis||'정확한 카드번호·판본·변형 근거가 부족합니다.')}</span></div>`;
 const sources=visible.length?`<div class="mmp-source-price-title">어디서 얼마인지</div><div class="mmp-source-price-grid">${visible.map(row=>{
   const contributes=row.contributes_to_recommendation===true?'<em>추천가 반영</em>':(evidenceView==='ALL'?'<em class="reference-only">참고만</em>':`<em class="reference-only">${esc(evidenceLabels[evidenceView]||'근거별')}</em>`);
   const seller=`<span class="mmp-seller">${esc(sellerText(row))}</span>`;
   const filters=[...(Array.isArray(row.conditions)?row.conditions:[]),...(Array.isArray(row.printings)?row.printings.map(x=>variantLabels[x]||x):[])].filter(Boolean).join(' · ');
   const href=safeMarketHref(row.sample_url);const link=href?`<a class="mmp-source-link" href="${href}" target="_blank" rel="noopener noreferrer">판매처/원문 보기 →</a>`:'';
   return `<div class="mmp-source-price"><div><b>${esc(row.source||row.source_id||'출처')}</b>${contributes}</div><strong>${krw(row.price_krw)}</strong><small>${esc(row.basis||'가격')} · ${Number(row.count)||0}건${Number(row.min_krw)>0&&Number(row.max_krw)>0&&Number(row.min_krw)!==Number(row.max_krw)?` · ${krw(row.min_krw)}~${krw(row.max_krw)}`:''}</small>${seller}${filters?`<span class="mmp-filter-proof">${esc(filters)}</span>`:''}<div class="mmp-source-freshness">${freshnessBadge(row)}</div>${link}</div>`;
 }).join('')}</div>`:'';
 const printingLabel=(data?.printing==='ALL'||!data?.printing)?'자동/전체':(variantLabels[data.printing]||data.printing);
 const filterLabel=`${conditionLabels[data?.condition||'ALL']||data?.condition||'전체 상태'} · ${printingLabel} · ${evidenceLabels[evidenceView]||evidenceView}`;
 box.innerHTML=headline+sources+`<p>현재 보기: ${esc(filterLabel)}. 추천가는 같은 카드번호·판본·상태·변형에서 가장 강한 증거등급만 사용하고, 출처별 중앙값을 다시 중앙값으로 합산합니다. 판매중 호가는 완료거래보다 낮은 우선순위입니다.</p>`;
}


function render(data){
 const summary=$('multiMarketSummary'),rows=$('multiMarketRows');if(!summary||!rows)return;
 const info=data.summary||{};summary.className='mmp-summary';
 const basis=esc(info.basis||'동일 기준'),region=esc(info.region_scope||'ALL');
 summary.innerHTML=`<div><span>비교가능가격</span><b>${info.count||0}건</b><small>정확범위 ${info.total_count??info.count??0}건${Number(info.identity_excluded_count)>0?` · 불일치 제외 ${Number(info.identity_excluded_count)}건`:''}${Number(info.filter_excluded_count)>0?` · 상태/인쇄판 제외 ${Number(info.filter_excluded_count)}건`:''}</small></div><div><span>출처</span><b>${info.source_count||0}곳</b><small>${esc(conditionLabels[data.condition||'ALL']||data.condition||'전체 상태')} · ${region}</small></div><div><span>${basis} 중앙값</span><b>${krw(info.median_krw)}</b></div><div><span>동일기준 범위</span><b>${krw(info.min_krw)} ~ ${krw(info.max_krw)}</b></div>`;
 updateEditionLabel();
 renderSources(data.source_status);renderGrades(data.grade_reference);renderReferences(data.reference_links);renderVariantControl(info);renderRecommendation(data);
 const visibleItems=(data.items||[]).filter(evidenceVisible).slice(0,24);
 rows.innerHTML=visibleItems.map(item=>{const href=safeMarketHref(item?.url);const link=href?`<a href="${href}" target="_blank" rel="noopener noreferrer">원문 확인 →</a>`:`<span class="mmp-source-unavailable">원문 URL 확인 필요</span>`;return `<article class="mmp-row"><div class="mmp-top"><div class="mmp-badges">${sourceBadge(item)}</div><strong>${krw(item.price_krw)}</strong></div><div class="mmp-title">${esc(item.title)}</div><div class="mmp-meta"><span>${item.currency&&item.price_native?`${esc(item.currency)} ${Number(item.price_native).toLocaleString()}`:'원화 환산'}</span><span>${esc(item.source_date||item.date||'날짜 미확인')}</span></div>${item.seller_name?`<div class="mmp-row-seller">판매자/상점 · ${esc(item.seller_name)}</div>`:''}${link}</article>`}).join('')||'<div class="mmp-empty"><b>선택한 가격근거 결과 없음</b><span>현재 필터에서 확인 가능한 가격이 없습니다. 가격 근거 보기를 전체로 바꾸거나 상태/인쇄판을 확인해 주세요.</span></div>';
 rememberMarket(data);renderHistory(data);renderRecent();
 $('multiMarketNote').textContent=(data.notice||'')+(data.errors?.length?` · 일부 출처 실패 ${data.errors.length}곳`:``);
 try{window.dispatchEvent(new CustomEvent('tcg:multi-market-updated',{detail:{summary:data.summary||{},source_breakdown:data.source_breakdown||[],grade_reference:data.grade_reference||[]}}))}catch(_){}
 try{window.TCGAppShellV272?.refreshGradeSummary?.()}catch(_){}
}


let marketRequestSequence=0,marketRequestController=null;
function resetMarketDetails(){
 for(const id of ['multiMarketVariant','multiMarketRecommendation','multiMarketHistory','multiMarketGrade','multiMarketReferences']){
  const panel=$(id);if(panel){panel.hidden=true;panel.innerHTML='';}
 }
 for(const id of ['multiMarketRows','multiMarketSources']){
  const panel=$(id);if(panel)panel.innerHTML='';
 }
 const note=$('multiMarketNote');if(note)note.textContent='';
 window.__multiMarketPrices=null;
}

async function load(force=false){
 if(!mount())return;
 const requestId=++marketRequestSequence;
 if(marketRequestController){try{marketRequestController.abort()}catch(_){}}
 const controller=typeof AbortController==='function'?new AbortController():null;
 marketRequestController=controller;
 const baseQuery=String($('query12')?.value||'').trim();
 if(baseQuery!==lastBaseQuery){
  variantOverride='';marketPrinting='ALL';
  const printing=$('multiMarketPrinting');if(printing)printing.value='ALL';
  lastBaseQuery=baseQuery;
 }
 const q=(baseQuery+(variantOverride&&marketPrinting==='ALL'? ` ${variantTerms[variantOverride]||variantOverride}`:'')).trim();
 resetMarketDetails();
 const summary=$('multiMarketSummary');
 if(!q){
  summary.className='mmp-summary mmp-wait';
  summary.innerHTML='<b>카드 인식 후 자동 검색</b><span>카드명이나 카드번호가 들어오면 여러 마켓을 동시에 확인합니다.</span>';
  renderRecent();marketRequestController=null;return;
 }
 const region=$('market12')?.value||'ALL',game=$('v12Game')?.value||'ALL';
 summary.className='mmp-summary mmp-wait';
 summary.innerHTML='<b>여러 마켓에서 가격 수집 중…</b><span>새 조회가 시작되면 이전 카드의 가격을 숨깁니다.</span>';
 try{
  const url=`/api/multi-market-prices?q=${encodeURIComponent(q)}&region=${encodeURIComponent(region)}&game=${encodeURIComponent(game)}&condition=${encodeURIComponent(marketCondition)}&printing=${encodeURIComponent(marketPrinting)}&force=${force?'1':'0'}&t=${Date.now()}`;
  const options={cache:'no-store'};if(controller)options.signal=controller.signal;
  const response=await fetch(url,options);
  if(requestId!==marketRequestSequence)return;
  const data=await response.json();
  if(requestId!==marketRequestSequence)return;
  if(!response.ok||!data?.ok)throw new Error(data?.error||'load failed');
  window.__multiMarketPrices=data;render(data);
 }catch(error){
  if(requestId!==marketRequestSequence||error?.name==='AbortError')return;
  resetMarketDetails();
  summary.className='mmp-summary mmp-wait mmp-error';
  summary.innerHTML='<b>다중마켓 수집 실패</b><span>이전 카드의 가격은 숨겼습니다. 서버 연결을 확인하고 다시 수집해 주세요.</span>';
 }finally{
  if(requestId===marketRequestSequence)marketRequestController=null;
 }
}

function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(mount()||tries>20)clearInterval(timer)},250);mount();$('search12')?.addEventListener('click',()=>setTimeout(()=>load(false),80));$('market12')?.addEventListener('change',()=>{updateEditionLabel();if(String($('query12')?.value||'').trim())load(false)});renderRecent();window.tcgMultiMarketPrice=Object.freeze({refresh:()=>load(true),clearLocalHistory:()=>{safeLocalSet(HISTORY_KEY,[]);safeLocalSet(RECENT_KEY,[]);renderRecent()}})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();


;(()=>{
"use strict";
// V640: append-only BOX market lens, keeps historically reviewed BOX UI files immutable.
const list=()=>document.getElementById("box12");
let marketCache={entries:{}},officialRows=[],lastUpdate=0,task=null;
function countryOfKey(k){return String(k||"").split("|")[0]||""}
function assetOfKey(k){return String(k||"").split("|")[2]||""}
function nameOfKey(k){return String(k||"").split("|")[1]||""}
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

function officialBoxPriceText(msrp,country,kind){
 const curr={KR:'KRW',JP:'JPY',US:'USD'}[country],unit=kind==='BOOSTER_PACK'?'PACK':'BOX';
 if(!curr||!msrp||msrp.currency!==curr||msrp.unit!==unit||
    !Number.isFinite(msrp.amount)||msrp.amount<=0||msrp.amount>1000000000)return '제조사 정가 미확인';
 const n=Number(msrp.amount);
 const price=curr==='KRW'?new Intl.NumberFormat('ko-KR',{maximumFractionDigits:0}).format(n)+'원':
   curr==='JPY'?'¥'+new Intl.NumberFormat('ja-JP',{maximumFractionDigits:0}).format(n):
   '$'+n.toFixed(2);
 return '제조사 정가 '+price+' / '+(unit==='PACK'?'팩':'BOX');
}


function catalogRows(){
 try{
  const rows=typeof COUNTRY_BOX_DATA!=="undefined"&&Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[];
  const code=document.querySelector(".box-kb-country.active")?.dataset?.kbCountry||"ALL";
  return rows.filter(x=>code==="ALL"||x.country===code);
 }catch(_){return []}
}
function renderCards(){
 const box=list();if(!box)return;
 const rows=catalogRows(),cards=[...box.children].filter(x=>x.classList?.contains("box-kb-card"));
 cards.forEach((el,i)=>{if(rows[i])updateBoxPriceCard(el,rows[i])});
 const section=document.getElementById("box12section");
 if(section&&!document.getElementById("boxkbAllOfficialV640")){
  const a=document.createElement("a");a.id="boxkbAllOfficialV640";a.className="boxkb-official-all-link";
  a.href="./official_box_catalog_v626.html";a.textContent="🏭 제조사 공식 상품 전체 보기 · 게임/국가/팩/BOX 상세 필터 →";
  const target=document.getElementById("boxKbCount");target?.insertAdjacentElement("afterend",a);
 }
}
function officialPriceSafe(msrp,country,kind){return officialBoxPriceText(msrp,country,kind)}
function repairOfficialCurrency(){
 const parent=document.getElementById("boxOfficialCatalog");
 if(!parent)return;
 const cards=parent.querySelectorAll(".boxkb-official-card");
 for(const card of cards){
  const code=card.querySelector("small")?.textContent||"";
  const title=card.querySelector("b")?.textContent||"";
  const out=card.querySelector("strong");if(!out)continue;
  const candidate=officialRows.filter(p=>p&&code.includes("["+String(p.set_code||"")+"]")&&
    code.includes("· "+String(p.country||""))&&title.endsWith(String(p.name||"")));
  if(candidate.length===1)out.textContent=officialPriceSafe(candidate[0].msrp,candidate[0].country,candidate[0].product_type);
  else if(code.includes("· JP")&&out.textContent.includes("$"))out.textContent="제조사 정가 원문 재확인 필요";
 }
}
async function refreshSources(){
 if(task)return task;
 task=(async()=>{
  const now=Date.now();
  if(now-lastUpdate>300000){
   const responses=await Promise.allSettled([
    fetch("market_prices.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
    fetch("tcg_official_product_catalog_v599.json",{cache:"no-store"}).then(r=>r.ok?r.json():null)
   ]);
   const market=responses[0].status==="fulfilled"?responses[0].value:null;
   const official=responses[1].status==="fulfilled"?responses[1].value:null;
   if(market&&market.entries&&typeof market.entries==="object"&&!Array.isArray(market.entries))marketCache=market;
   if(official?.schema_version===1&&Array.isArray(official.products))officialRows=official.products.slice(0,100);
   lastUpdate=now;
  }
  renderCards();repairOfficialCurrency();
 })().finally(()=>{task=null});
 return task;
}
function refreshSoon(){setTimeout(()=>{renderCards();repairOfficialCurrency()},100)}
function boot(){
 const box=list();
 if(box&&typeof MutationObserver==="function"){
  const observer=new MutationObserver(records=>{
   if(records.some(record=>[...record.addedNodes].some(n=>n.nodeType===1&&n.classList?.contains("box-kb-card"))))refreshSoon();
  });
  observer.observe(box,{childList:true});
 }
 setTimeout(()=>{refreshSources()},1200);
 document.addEventListener("click",e=>{if(e.target?.closest?.(".box-kb-country"))refreshSoon()});
 document.addEventListener("change",e=>{if(e.target?.id==="boxKbGame")refreshSoon()});
 document.addEventListener("visibilitychange",()=>{if(!document.hidden)refreshSources()});
 setInterval(()=>{if(!document.hidden)refreshSources()},300000);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();


/* V638: additive BOX evidence lens. No direct edits to historically reviewed box UI. */
;(()=>{
 "use strict";
 if(!document.getElementById("box12")||document.getElementById("tcgBoxPriceLensV638Loader"))return;
 const s=document.createElement("script");
 s.id="tcgBoxPriceLensV638Loader";
 s.src="scripts/box_price_evidence_v638.js?v=638";
 s.async=false;
 document.body.appendChild(s);
})();
