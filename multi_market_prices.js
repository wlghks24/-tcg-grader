(()=>{
'use strict';
const GLOBAL_KEY='__TCG_MULTI_MARKET_PRICES__';
if(globalThis[GLOBAL_KEY]?.loaded)return;
globalThis[GLOBAL_KEY]={loaded:true,version:181};
const $=id=>document.getElementById(id);
const krw=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'—';
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const statusText={ok:'수집됨',ready:'확인 대기',no_result:'결과 없음',not_configured:'API 키 필요',unsupported:'해당 게임 미지원',query_language_unsupported:'영문·일문 카드명 필요',cooldown_skip:'안전 대기',cooldown:'안전 대기',error:'일시 오류'};

function mount(){
 if($('multiMarketPanel'))return true;
 const out=$('market12out');if(!out)return false;
 const section=document.createElement('section');section.id='multiMarketPanel';section.className='multi-market-panel';
 section.innerHTML=`
  <div class="mmp-head"><div class="mmp-head-copy"><b>🌐 다중마켓 시세 교차검색</b><small>eBay · 국내외 마켓 · SNKRDUNK · JustTCG · TCGdex · Pavilion TCG</small></div><button id="multiMarketRefresh" type="button">↻ 다시 수집</button></div>
  <div id="multiMarketSummary" class="mmp-summary mmp-wait"><b>카드 인식 후 자동 검색</b><span>카드명이나 카드번호가 들어오면 여러 마켓을 동시에 확인합니다.</span></div>
  <div id="multiMarketSources" class="mmp-source-status" aria-label="추가 참고출처 상태"></div>
  <section id="multiMarketGrade" class="mmp-grade-section" hidden></section>
  <section id="multiMarketReferences" class="mmp-reference-section" hidden></section>
  <div id="multiMarketRows" class="mmp-rows"></div><div id="multiMarketNote" class="mmp-note"></div>`;
 out.insertAdjacentElement('afterend',section);
 $('multiMarketRefresh')?.addEventListener('click',()=>load(true));return true;
}

function sourceBadge(item){
 return `<span class="mmp-source">${esc(item.source)}</span><span class="mmp-kind">${esc(item.price_kind||'가격')}</span>${item.verified_api?'<span class="mmp-api">API</span>':''}`;
}

function renderSources(list){
 const box=$('multiMarketSources');if(!box)return;
 box.innerHTML=(list||[]).map(row=>`<div class="mmp-source-state mmp-state-${esc(row.status)}"><b>${esc(row.source)}</b><span>${esc(statusText[row.status]||row.status)}${Number(row.hits)>0?` · ${Number(row.hits)}건`:''}</span></div>`).join('');
}

function renderGrades(list){
 const box=$('multiMarketGrade');if(!box)return;
 const rows=Array.isArray(list)?list:[];box.hidden=!rows.length;
 if(!rows.length){box.innerHTML='';return;}
 box.innerHTML=`<div class="mmp-subhead"><div><b>등급별 참고시세</b><small>확인된 공개가격의 중앙값이며, 자료가 없는 등급은 추정하지 않습니다.</small></div><span>Pavilion형 보기</span></div><div class="mmp-grade-grid">${rows.map(row=>`<div class="mmp-grade-card${row.price_krw?'':' mmp-grade-empty'}"><span>${esc(row.grade)}</span><b>${krw(row.price_krw)}</b><small>${row.count?`${Number(row.count)}건 확인`:'공개가격 없음'}</small></div>`).join('')}</div>`;
}

function renderReferences(list){
 const box=$('multiMarketReferences');if(!box)return;
 const rows=Array.isArray(list)?list:[];box.hidden=!rows.length;
 if(!rows.length){box.innerHTML='';return;}
 box.innerHTML=`<div class="mmp-subhead"><div><b>추가 원문 교차확인</b><small>참고 사이트 가격은 원문에서 카드번호·언어·등급을 다시 확인하세요.</small></div></div><div class="mmp-reference-grid">${rows.map(row=>`<a href="${esc(row.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(row.label)}</b><span>${esc(row.detail)}</span><em>원문 열기 →</em></a>`).join('')}</div>`;
}

function render(data){
 const summary=$('multiMarketSummary'),rows=$('multiMarketRows');if(!summary||!rows)return;
 const info=data.summary||{};summary.className='mmp-summary';
 const basis=esc(info.basis||'동일 기준'),region=esc(info.region_scope||'ALL');
 summary.innerHTML=`<div><span>비교가능가격</span><b>${info.count||0}건</b><small>전체 ${info.total_count??info.count??0}건</small></div><div><span>출처</span><b>${info.source_count||0}곳</b><small>지역 ${region}</small></div><div><span>${basis} 중앙값</span><b>${krw(info.median_krw)}</b></div><div><span>동일기준 범위</span><b>${krw(info.min_krw)} ~ ${krw(info.max_krw)}</b></div>`;
 renderSources(data.source_status);renderGrades(data.grade_reference);renderReferences(data.reference_links);
 rows.innerHTML=(data.items||[]).slice(0,24).map(item=>`<article class="mmp-row"><div class="mmp-top"><div class="mmp-badges">${sourceBadge(item)}</div><strong>${krw(item.price_krw)}</strong></div><div class="mmp-title">${esc(item.title)}</div><div class="mmp-meta"><span>${item.currency&&item.price_native?`${esc(item.currency)} ${Number(item.price_native).toLocaleString()}`:'원화 환산'}</span><span>${esc(item.date||'최근 검색 확인')}</span></div><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원문 확인 →</a></article>`).join('')||'<div class="mmp-empty"><b>가격 결과 없음</b><span>현재 공개 검색결과에서 확인 가능한 가격을 찾지 못했습니다. 위 참고사이트 원문도 함께 확인해 주세요.</span></div>';
 $('multiMarketNote').textContent=(data.notice||'')+(data.errors?.length?` · 일부 출처 실패 ${data.errors.length}곳`:``);
}

async function load(force=false){
 if(!mount())return;const q=String($('query12')?.value||'').trim();
 if(!q){const summary=$('multiMarketSummary');summary.className='mmp-summary mmp-wait';summary.innerHTML='<b>카드 인식 후 자동 검색</b><span>카드명이나 카드번호가 들어오면 여러 마켓을 동시에 확인합니다.</span>';$('multiMarketRows').innerHTML='';$('multiMarketSources').innerHTML='';$('multiMarketGrade').hidden=true;$('multiMarketReferences').hidden=true;return;}
 const region=$('market12')?.value||'ALL',game=$('v12Game')?.value||'ALL',summary=$('multiMarketSummary');summary.className='mmp-summary mmp-wait';summary.innerHTML='<b>여러 마켓에서 가격 수집 중…</b><span>추가 API와 참고사이트를 교차확인하고 중복 결과를 정리하고 있습니다.</span>';$('multiMarketRows').innerHTML='';
 try{const url=`/api/multi-market-prices?q=${encodeURIComponent(q)}&region=${encodeURIComponent(region)}&game=${encodeURIComponent(game)}&force=${force?'1':'0'}&t=${Date.now()}`;const response=await fetch(url,{cache:'no-store'}),data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'load failed');window.__multiMarketPrices=data;render(data)}
 catch(_){summary.className='mmp-summary mmp-wait mmp-error';summary.innerHTML='<b>다중마켓 수집 실패</b><span>태블릿/PC 서버 연결을 확인한 뒤 다시 수집해 주세요.</span>';}
}

function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(mount()||tries>20)clearInterval(timer)},250);mount();$('search12')?.addEventListener('click',()=>setTimeout(()=>load(false),80));window.tcgMultiMarketPrice=Object.freeze({refresh:()=>load(true)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
