(()=>{
'use strict';
const GLOBAL_KEY='__TCG_MULTI_MARKET_PRICES__';
if(globalThis[GLOBAL_KEY]?.loaded)return;
globalThis[GLOBAL_KEY]={loaded:true,version:482};
const $=id=>document.getElementById(id);
const krw=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'—';
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const statusText={ok:'수집됨',ready:'확인 대기',no_result:'결과 없음',not_configured:'API 키 필요',unsupported:'해당 게임 미지원',query_language_unsupported:'영문·일문 카드명 필요',cooldown_skip:'안전 대기',cooldown:'안전 대기',error:'일시 오류'};
const variantLabels={manga:'만화 레어',parallel:'패러렐',special_art:'스페셜 아트',alt_art:'얼터 아트',full_art:'풀 아트',reverse_holo:'리버스 홀로',standard:'일반판',holo:'홀로',foil:'포일',promo:'프로모'};
const variantTerms={manga:'manga rare',parallel:'parallel',special_art:'special art rare',alt_art:'alt art',full_art:'full art',reverse_holo:'reverse holo',standard:'standard',holo:'holo',foil:'foil',promo:'promo'};
const freshnessText={FRESH:'최신',AGING:'최근',STALE:'노후',EXPIRED:'오래됨',UNKNOWN:'날짜 미확인'};
let variantOverride='',lastBaseQuery='';

function mount(){
 if($('multiMarketPanel'))return true;
 const out=$('market12out');if(!out)return false;
 const section=document.createElement('section');section.id='multiMarketPanel';section.className='multi-market-panel';
 section.innerHTML=`
  <div class="mmp-head"><div class="mmp-head-copy"><b>🌐 다중마켓 시세 교차검색</b><small>eBay · 국내외 마켓 · SNKRDUNK · JustTCG · TCGdex · Pavilion TCG</small></div><div class="mmp-head-actions"><button id="multiMarketExportCsv" type="button">CSV 저장</button><button id="multiMarketExportJson" type="button">JSON 저장</button><button id="multiMarketRefresh" type="button">↻ 다시 수집</button></div></div>
  <div id="multiMarketSummary" class="mmp-summary mmp-wait"><b>카드 인식 후 자동 검색</b><span>카드명이나 카드번호가 들어오면 여러 마켓을 동시에 확인합니다.</span></div>
  <section id="multiMarketVariant" class="mmp-variant-control" hidden></section>
  <section id="multiMarketRecommendation" class="mmp-recommendation" hidden></section>
  <div id="multiMarketSources" class="mmp-source-status" aria-label="추가 참고출처 상태"></div>
  <section id="multiMarketGrade" class="mmp-grade-section" hidden></section>
  <section id="multiMarketReferences" class="mmp-reference-section" hidden></section>
  <div id="multiMarketRows" class="mmp-rows"></div><div id="multiMarketNote" class="mmp-note"></div>`;
 out.insertAdjacentElement('afterend',section);
 $('multiMarketRefresh')?.addEventListener('click',()=>load(true));
 $('multiMarketExportCsv')?.addEventListener('click',()=>downloadEvidence('csv'));
 $('multiMarketExportJson')?.addEventListener('click',()=>downloadEvidence('json'));
 return true;
}

function freshnessBadge(row){
 const status=String(row?.freshness_status||'UNKNOWN'),label=freshnessText[status]||status;
 const age=Number.isFinite(Number(row?.freshness_age_days))?` · ${Number(row.freshness_age_days)}일`:'';
 return `<span class="mmp-fresh mmp-fresh-${esc(status.toLowerCase())}">${esc(label)}${age}</span>`;
}
function sourceBadge(item){
 const identity=item.summary_eligible===false?'<span class="mmp-kind">참고만</span>':(String(item.identity_basis||'').includes('card_number')?'<span class="mmp-api">카드일치</span>':'');
 return `<span class="mmp-source">${esc(item.source)}</span><span class="mmp-kind">${esc(item.price_kind||'가격')}</span>${item.verified_api?'<span class="mmp-api">API</span>':''}${identity}${freshnessBadge(item)}`;
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
 const rows=Array.isArray(list)?list:[];box.hidden=!rows.length;
 if(!rows.length){box.innerHTML='';return;}
 box.innerHTML=`<div class="mmp-subhead"><div><b>추가 원문 교차확인</b><small>참고 사이트 가격은 원문에서 카드번호·언어·등급을 다시 확인하세요.</small></div></div><div class="mmp-reference-grid">${rows.map(row=>`<a href="${esc(row.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(row.label)}</b><span>${esc(row.detail)}</span><em>원문 열기 →</em></a>`).join('')}</div>`;
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
  $('multiMarketVariantSelect')?.addEventListener('change',event=>{variantOverride=String(event.target.value||'');if(variantOverride)load(true)});
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
 const info=data.summary||{},rows=[['카드검색',data.query],['지역',data.region],['게임',data.game],['추천거래가_KRW',info.recommended_trade_krw||''],['추천범위_최저_KRW',info.recommendation_min_krw||''],['추천범위_최고_KRW',info.recommendation_max_krw||''],['추천신뢰도',info.recommendation_confidence||''],['가격최신성',info.recommendation_freshness||''],[],['출처','기준','출처중앙가_KRW','최저_KRW','최고_KRW','표본수','최신성','경과일','추천가반영','원문']];
 for(const row of (data.source_breakdown||[]))rows.push([row.source||row.source_id||'',row.basis||'',row.price_krw||'',row.min_krw||'',row.max_krw||'',row.count||0,freshnessText[row.freshness_status]||row.freshness_status||'',row.freshness_age_days??'',row.contributes_to_recommendation===true?'Y':'N',row.sample_url||'']);
 downloadBlob(`tcg_${safe}_market.csv`,'text/csv;charset=utf-8','\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\n'));
}

function renderRecommendation(data){
 const box=$('multiMarketRecommendation');if(!box)return;
 const info=data?.summary||{},recommendation=Number(info.recommended_trade_krw||0);
 const rows=Array.isArray(data?.source_breakdown)?data.source_breakdown:[];
 const visible=rows.filter(row=>Number(row?.price_krw)>0).slice(0,8);
 if(!(recommendation>0)&&!visible.length){box.hidden=true;box.innerHTML='';return}
 box.hidden=false;
 const range=(Number(info.recommendation_min_krw)>0&&Number(info.recommendation_max_krw)>0)
   ?`${krw(info.recommendation_min_krw)} ~ ${krw(info.recommendation_max_krw)}`:'근거 부족';
 const headline=recommendation>0
   ?`<div class="mmp-recommendation-head"><div><span>추천 거래 기준가</span><b>${krw(recommendation)}</b><small>${esc(info.recommendation_basis||info.basis||'동일 기준')} · 신뢰도 ${esc(info.recommendation_confidence||'낮음')} · 최신성 ${esc(info.recommendation_freshness||'확인 중')}</small></div><div><span>관측 범위</span><b>${range}</b><small>${Number(info.recommendation_source_count)||0}곳 · ${Number(info.recommendation_sample_count)||0}건${Number.isFinite(Number(info.recommendation_latest_age_days))?` · 최신근거 ${Number(info.recommendation_latest_age_days)}일 전`:''}</small></div></div>`
   :`<div class="mmp-recommendation-hold"><b>추천 거래금액 보류</b><span>${esc(info.basis||'정확한 카드번호·판본·변형 근거가 부족합니다.')}</span></div>`;
 const sources=visible.length?`<div class="mmp-source-price-title">어디서 얼마인지</div><div class="mmp-source-price-grid">${visible.map(row=>{
   const contributes=row.contributes_to_recommendation===true?'<em>추천가 반영</em>':'<em class="reference-only">참고만</em>';
   return `<div class="mmp-source-price"><div><b>${esc(row.source||row.source_id||'출처')}</b>${contributes}</div><strong>${krw(row.price_krw)}</strong><small>${esc(row.basis||'가격')} · ${Number(row.count)||0}건${Number(row.min_krw)>0&&Number(row.max_krw)>0&&Number(row.min_krw)!==Number(row.max_krw)?` · ${krw(row.min_krw)}~${krw(row.max_krw)}`:''}</small><div class="mmp-source-freshness">${freshnessBadge(row)}</div></div>`;
 }).join('')}</div>`:'';
 box.innerHTML=headline+sources+`<p>추천가는 같은 카드번호·판본·변형에서 가장 강한 증거등급만 사용하고, 출처별 중앙값을 다시 중앙값으로 합산합니다. 판매중 호가는 완료거래보다 낮은 우선순위로 취급합니다.</p>`;
}


function render(data){
 const summary=$('multiMarketSummary'),rows=$('multiMarketRows');if(!summary||!rows)return;
 const info=data.summary||{};summary.className='mmp-summary';
 const basis=esc(info.basis||'동일 기준'),region=esc(info.region_scope||'ALL');
 summary.innerHTML=`<div><span>비교가능가격</span><b>${info.count||0}건</b><small>정확범위 ${info.total_count??info.count??0}건${Number(info.identity_excluded_count)>0?` · 불일치 제외 ${Number(info.identity_excluded_count)}건`:''}</small></div><div><span>출처</span><b>${info.source_count||0}곳</b><small>지역 ${region}</small></div><div><span>${basis} 중앙값</span><b>${krw(info.median_krw)}</b></div><div><span>동일기준 범위</span><b>${krw(info.min_krw)} ~ ${krw(info.max_krw)}</b></div>`;
 renderSources(data.source_status);renderGrades(data.grade_reference);renderReferences(data.reference_links);renderVariantControl(info);renderRecommendation(data);
 rows.innerHTML=(data.items||[]).slice(0,24).map(item=>`<article class="mmp-row"><div class="mmp-top"><div class="mmp-badges">${sourceBadge(item)}</div><strong>${krw(item.price_krw)}</strong></div><div class="mmp-title">${esc(item.title)}</div><div class="mmp-meta"><span>${item.currency&&item.price_native?`${esc(item.currency)} ${Number(item.price_native).toLocaleString()}`:'원화 환산'}</span><span>${esc(item.source_date||item.date||'날짜 미확인')}</span></div><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원문 확인 →</a></article>`).join('')||'<div class="mmp-empty"><b>가격 결과 없음</b><span>현재 공개 검색결과에서 확인 가능한 가격을 찾지 못했습니다. 위 참고사이트 원문도 함께 확인해 주세요.</span></div>';
 $('multiMarketNote').textContent=(data.notice||'')+(data.errors?.length?` · 일부 출처 실패 ${data.errors.length}곳`:``);
 try{window.dispatchEvent(new CustomEvent('tcg:multi-market-updated',{detail:{summary:data.summary||{},source_breakdown:data.source_breakdown||[],grade_reference:data.grade_reference||[]}}))}catch(_){}
 try{window.TCGAppShellV272?.refreshGradeSummary?.()}catch(_){}
}

async function load(force=false){
 if(!mount())return;const baseQuery=String($('query12')?.value||'').trim();
 if(baseQuery!==lastBaseQuery){variantOverride='';lastBaseQuery=baseQuery}
 const q=(baseQuery+(variantOverride?` ${variantTerms[variantOverride]||variantOverride}`:'')).trim();
 if(!q){const summary=$('multiMarketSummary');summary.className='mmp-summary mmp-wait';summary.innerHTML='<b>카드 인식 후 자동 검색</b><span>카드명이나 카드번호가 들어오면 여러 마켓을 동시에 확인합니다.</span>';$('multiMarketRows').innerHTML='';$('multiMarketSources').innerHTML='';$('multiMarketGrade').hidden=true;$('multiMarketReferences').hidden=true;$('multiMarketVariant').hidden=true;$('multiMarketRecommendation').hidden=true;$('multiMarketRecommendation').innerHTML='';window.__multiMarketPrices=null;return;}
 const region=$('market12')?.value||'ALL',game=$('v12Game')?.value||'ALL',summary=$('multiMarketSummary');summary.className='mmp-summary mmp-wait';summary.innerHTML='<b>여러 마켓에서 가격 수집 중…</b><span>추가 API와 참고사이트를 교차확인하고 중복 결과를 정리하고 있습니다.</span>';$('multiMarketRows').innerHTML='';
 try{const url=`/api/multi-market-prices?q=${encodeURIComponent(q)}&region=${encodeURIComponent(region)}&game=${encodeURIComponent(game)}&force=${force?'1':'0'}&t=${Date.now()}`;const response=await fetch(url,{cache:'no-store'}),data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'load failed');window.__multiMarketPrices=data;render(data)}
 catch(_){summary.className='mmp-summary mmp-wait mmp-error';summary.innerHTML='<b>다중마켓 수집 실패</b><span>태블릿/PC 서버 연결을 확인한 뒤 다시 수집해 주세요.</span>';}
}

function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(mount()||tries>20)clearInterval(timer)},250);mount();$('search12')?.addEventListener('click',()=>setTimeout(()=>load(false),80));window.tcgMultiMarketPrice=Object.freeze({refresh:()=>load(true)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
