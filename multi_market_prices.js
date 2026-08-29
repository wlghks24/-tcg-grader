(()=>{
'use strict';
const $=id=>document.getElementById(id);
const krw=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'-';
function mount(){
 if($('multiMarketPanel'))return true;
 const out=$('market12out');if(!out)return false;
 const s=document.createElement('section');s.id='multiMarketPanel';s.className='multi-market-panel';
 s.innerHTML=`<div class="mmp-head"><div><b>🌐 다중마켓 시세 교차검색</b><small>eBay · Amazon · KREAM · 당근 · 번개장터 · 중고나라 · Collectory · TCGplayer · Cardmarket · Mercari · Yahoo Japan</small></div><button id="multiMarketRefresh" type="button">다시 수집</button></div><div id="multiMarketSummary" class="mmp-summary">카드명/번호 검색 후 자동으로 확인합니다.</div><div id="multiMarketRows" class="mmp-rows"></div><div id="multiMarketNote" class="mmp-note"></div>`;
 out.insertAdjacentElement('afterend',s);$('multiMarketRefresh')?.addEventListener('click',()=>load(true));return true;
}
function sourceBadge(x){return `<span class="mmp-source">${x.source}</span><span class="mmp-kind">${x.price_kind||'가격'}</span>${x.verified_api?'<span class="mmp-api">API</span>':''}`}
function render(j){const sum=$('multiMarketSummary'),rows=$('multiMarketRows');if(!sum||!rows)return;const s=j.summary||{};sum.innerHTML=`<div><span>수집가격</span><b>${s.count||0}건</b></div><div><span>출처</span><b>${s.source_count||0}곳</b></div><div><span>중앙값</span><b>${krw(s.median_krw)}</b></div><div><span>최저~최고</span><b>${krw(s.min_krw)} ~ ${krw(s.max_krw)}</b></div>`;rows.innerHTML=(j.items||[]).slice(0,24).map(x=>`<article class="mmp-row"><div class="mmp-top">${sourceBadge(x)}<strong>${krw(x.price_krw)}</strong></div><div class="mmp-title">${String(x.title||'').replace(/[<>]/g,'')}</div><small>${x.currency&&x.price_native?`${x.currency} ${Number(x.price_native).toLocaleString()} · `:''}${x.date||'최근 검색 확인'}</small><a href="${x.url}" target="_blank" rel="noopener noreferrer">원문 확인</a></article>`).join('')||'<div class="mmp-empty">현재 공개 검색결과에서 가격을 확인하지 못했습니다.</div>';$('multiMarketNote').textContent=(j.notice||'')+(j.errors?.length?` · 일부 출처 실패 ${j.errors.length}곳`:``)}
async function load(force=false){if(!mount())return;const q=String($('query12')?.value||'').trim();if(!q){$('multiMarketSummary').textContent='카드명 또는 카드번호를 입력하세요.';return}const region=$('market12')?.value||'ALL',game=$('v12Game')?.value||'ALL';$('multiMarketSummary').textContent='여러 마켓에서 가격 수집 중…';$('multiMarketRows').innerHTML='';try{const u=`/api/multi-market-prices?q=${encodeURIComponent(q)}&region=${encodeURIComponent(region)}&game=${encodeURIComponent(game)}&force=${force?'1':'0'}&t=${Date.now()}`;const r=await fetch(u,{cache:'no-store'}),j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||'load failed');window.__multiMarketPrices=j;render(j)}catch(_){$('multiMarketSummary').textContent='다중마켓 수집을 불러오지 못했습니다. 태블릿/PC 서버 연결을 확인하세요.'}}
function boot(){let tries=0;const t=setInterval(()=>{tries++;if(mount()||tries>20)clearInterval(t)},250);mount();$('search12')?.addEventListener('click',()=>setTimeout(()=>load(false),80));window.tcgMultiMarketPrice=Object.freeze({refresh:()=>load(true)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
