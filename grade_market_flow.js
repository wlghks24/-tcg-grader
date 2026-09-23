(()=>{
'use strict';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const norm=s=>String(s||'').toLowerCase().replace(/\s+/g,'').replace(/[^0-9a-z가-힣/.-]/g,'');
const money=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'거래자료 없음';
const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const REFERENCE_HOSTS=new Set([
 'collectory.cc','web.joongna.com','kream.co.kr','m.bunjang.co.kr','www.daangn.com','wyyyes.com',
 'auctions.yahoo.co.jp','jp.mercari.com','snkrdunk.com','www.ebay.com','www.tcgplayer.com',
 'www.pricecharting.com','130point.com','www.psacard.com','www.cardmarket.com','app.getcollectr.com',
 'www.cardladder.com','www.tcgfish.net','www.pokevalues.com'
]);
const REFERENCE_FALLBACK=[
 {id:'collectory',name:'Collectory',region:'KR',region_label:'국내 · 다국가 비교',evidence_group:'mixed',evidence_label:'집계 · 실거래/매물 혼합',url:'https://collectory.cc/',search_url_template:'https://collectory.cc/?q={query}',recommended:true,auto_collected:false,note:'한국·일본·미국 등 판본 비교와 가격 이력 교차확인'},
 {id:'joongna',name:'중고나라 시세조회',region:'KR',region_label:'국내',evidence_group:'mixed',evidence_label:'등록가 · 판매가 분리',url:'https://web.joongna.com/',search_url_template:'https://web.joongna.com/search-price/{query}',recommended:true,auto_collected:false,note:'BID 등록가와 EXECUTION 판매가를 나눠 확인'},
 {id:'kream',name:'KREAM',region:'KR',region_label:'국내',evidence_group:'mixed',evidence_label:'공개 거래 · 시장 참고',url:'https://kream.co.kr/',search_url_template:'https://kream.co.kr/search?keyword={query}',recommended:true,auto_collected:true,note:'국내 공개 거래/상품 페이지를 카드·판본별로 교차확인'},
 {id:'bunjang',name:'번개장터',region:'KR',region_label:'국내',evidence_group:'asking',evidence_label:'판매중 · 호가 참고',url:'https://m.bunjang.co.kr/',search_url_template:'https://m.bunjang.co.kr/search/products?q={query}',recommended:false,auto_collected:false,note:'현재 판매 희망가 확인용 · 체결가로 자동 간주하지 않음'},
 {id:'daangn',name:'당근',region:'KR',region_label:'국내 · 지역거래',evidence_group:'asking',evidence_label:'지역 매물 · 호가 참고',url:'https://www.daangn.com/kr/buy-sell/',search_url_template:'',recommended:false,auto_collected:false,note:'지역 매물/판매완료 표시는 참고하고 실제 체결금액은 별도 확인'},
 {id:'wyyyes',name:'WYYYES',region:'KR',region_label:'국내 · 해외판 포함',evidence_group:'mixed',evidence_label:'판매중 · 판매완료 구분',url:'https://wyyyes.com/',search_url_template:'',recommended:true,auto_collected:true,note:'앱이 공개 페이지만 제한 수집하며 호가와 판매완료를 분리'},
 {id:'yahoo_auction_jp',name:'Yahoo!オークション 낙찰',region:'JP',region_label:'일본',evidence_group:'sold',evidence_label:'낙찰 완료',url:'https://auctions.yahoo.co.jp/closedsearch/closedsearch',search_url_template:'https://auctions.yahoo.co.jp/closedsearch/closedsearch?p={query}',recommended:true,auto_collected:false,note:'종료된 경매의 낙찰가 확인 · 동일 판본/상태/등급 확인 필수'},
 {id:'mercari_jp',name:'Mercari Japan',region:'JP',region_label:'일본',evidence_group:'asking',evidence_label:'판매중 · 매물 참고',url:'https://jp.mercari.com/',search_url_template:'https://jp.mercari.com/search?keyword={query}',recommended:false,auto_collected:false,note:'일본 현지 매물가 확인용 · 판매중 가격은 체결가가 아님'},
 {id:'snkrdunk',name:'SNKRDUNK',region:'JP',region_label:'일본 · 글로벌',evidence_group:'guide',evidence_label:'거래시장 · 시장가이드',url:'https://snkrdunk.com/en/brands/pokemon/trading-cards?categoryId=25',search_url_template:'',recommended:true,auto_collected:false,note:'일본 TCG 거래량·시장가 리포트와 현재 시장 참고'},
 {id:'ebay_sold',name:'eBay Sold',region:'US_GLOBAL',region_label:'미국 · 글로벌',evidence_group:'sold',evidence_label:'판매완료 검색',url:'https://www.ebay.com/',search_url_template:'https://www.ebay.com/sch/i.html?_nkw={query}&LH_Sold=1&LH_Complete=1',recommended:true,auto_collected:false,note:'판매완료 비교용 · Best Offer/배송비/상태/판본 차이 확인'},
 {id:'tcgplayer',name:'TCGplayer',region:'US_GLOBAL',region_label:'미국',evidence_group:'guide',evidence_label:'최근 판매 기반 Market Price',url:'https://www.tcgplayer.com/',search_url_template:'https://www.tcgplayer.com/search/all/product?q={query}&view=grid',recommended:true,auto_collected:false,note:'최근 판매 기반 Market Price와 Most Recent Sale 교차확인'},
 {id:'pricecharting',name:'PriceCharting',region:'US_GLOBAL',region_label:'미국 · 글로벌',evidence_group:'guide',evidence_label:'판매이력 · 등급별 가이드',url:'https://www.pricecharting.com/',search_url_template:'https://www.pricecharting.com/search-products?type=prices&q={query}',recommended:true,auto_collected:false,note:'Ungraded·Grade 9·PSA 10 등 등급별 가격과 sold listings 확인'},
 {id:'130point',name:'130point Sales',region:'US_GLOBAL',region_label:'미국 · 글로벌',evidence_group:'sold',evidence_label:'판매완료 집계 참고',url:'https://130point.com/sales/',search_url_template:'',recommended:true,auto_collected:false,note:'여러 경매/마켓 판매완료를 교차확인하는 보조 확인처'},
 {id:'psa_apr',name:'PSA Auction Prices Realized',region:'US_GLOBAL',region_label:'미국 · 글로벌',evidence_group:'sold',evidence_label:'PSA 등급품 낙찰결과',url:'https://www.psacard.com/auctionprices',search_url_template:'',recommended:true,auto_collected:false,note:'PSA 등급품의 경매 결과를 등급·기간별로 확인'},
 {id:'collectr',name:'Collectr',region:'US_GLOBAL',region_label:'글로벌 · 포트폴리오',evidence_group:'guide',evidence_label:'카드·밀봉·등급품 시세 가이드',url:'https://app.getcollectr.com/',search_url_template:'',recommended:true,auto_collected:false,note:'Raw·밀봉·등급카드 가격과 언어별 포트폴리오 흐름을 글로벌 참고값으로 확인'},
 {id:'card_ladder',name:'Card Ladder',region:'US_GLOBAL',region_label:'미국 · 글로벌',evidence_group:'guide',evidence_label:'공개 판매이력 · 장기 시장가이드',url:'https://www.cardladder.com/ladder',search_url_template:'',recommended:true,auto_collected:false,note:'eBay·Goldin·Heritage·Fanatics 등 공개 판매이력을 묶어 장기 시세와 최근 판매를 교차확인'},
 {id:'tcgfish',name:'TCGFish',region:'US_GLOBAL',region_label:'글로벌 · 포켓몬',evidence_group:'guide',evidence_label:'일일 시세 · 시장지수',url:'https://www.tcgfish.net/pokemon-cards',search_url_template:'',recommended:false,auto_collected:false,note:'포켓몬 Raw/미감정 기준 일일 시세·시장지수·세트 모멘텀을 보조 지표로 확인'},
 {id:'pokevalues_jp',name:'PokeValues Japanese',region:'JP',region_label:'일본 · 포켓몬',evidence_group:'guide',evidence_label:'일본판 세트별 가격 가이드',url:'https://www.pokevalues.com/japanese',search_url_template:'',recommended:false,auto_collected:false,note:'일본판 포켓몬 세트별 가격을 글로벌 참고값으로 비교할 때 사용하는 보조 가이드'},
 {id:'cardmarket',name:'Cardmarket',region:'EU',region_label:'유럽',evidence_group:'asking',evidence_label:'유럽 매물 · 시장 참고',url:'https://www.cardmarket.com/en/Pokemon',search_url_template:'https://www.cardmarket.com/en/Pokemon/Products/Search?searchString={query}',recommended:false,auto_collected:false,note:'유럽 P2P 마켓 가격 수준 비교용 · 지역 차이를 감안'}
];
let lastIdentity='',lastGrades='',platformMarket=null,platformLoaded=false,platformLoading=false,sourceFilter='core';
function el(id){return document.getElementById(id)}
function editionCode(value){
 const low=String(value||'').toLowerCase();
 if(/(^|\b)(jp|japan|japanese)(\b|$)|일본|일판|일어판|日版|日本版/.test(low))return 'JP';
 if(/(^|\b)(kr|korea|korean)(\b|$)|한국|한글판|국판/.test(low))return 'KR';
 if(/(^|\b)(us|usa|english)(\b|$)|미국|영문판/.test(low))return 'US';
 return 'UNKNOWN';
}
function editionLabel(code){return ({KR:'🇰🇷 한국판',JP:'🇯🇵 일본판',US:'🇺🇸 미국/영문판',UNKNOWN:'🌐 판본 미확인'})[code]||'🌐 판본 미확인'}
function quoteTypeLabel(row){
 if(row?.price_type==='sold')return '체결/판매완료';
 if(row?.price_type==='auction_result')return '경매결과';
 return '판매중/제안가';
}
function safeSourceUrl(value){
 try{const u=new URL(String(value||''),location.href);if(u.protocol==='https:'&&(u.hostname==='wyyyes.com'||u.hostname==='www.wyyyes.com'))return u.href}catch(_){ }
 return '';
}
function normalizedHost(value){return String(value||'').toLowerCase().replace(/^www\./,'')}
function safeReferenceUrl(row,query){
 let value=String(row?.url||'');
 const template=String(row?.search_url_template||'');
 if(query&&template.includes('{query}'))value=template.replaceAll('{query}',encodeURIComponent(query));
 try{
   const u=new URL(value,location.href);
   const exact=u.hostname.toLowerCase();
   const noWww=normalizedHost(exact);
   const allowed=[...REFERENCE_HOSTS].some(host=>normalizedHost(host)===noWww);
   return u.protocol==='https:'&&allowed?u.href:'';
 }catch(_){return ''}
}
function marketQuery(){
 const name=(el('identityCardName')?.value||'').trim();
 const number=(el('identityCardNumber')?.value||'').trim();
 return [name,number].filter(Boolean).join(' ').trim();
}
function referenceSources(){
 const live=platformMarket?.market_reference_sources;
 return Array.isArray(live)&&live.length?live:REFERENCE_FALLBACK;
}
function evidenceIcon(group){return ({sold:'✅',guide:'📊',mixed:'🔄',asking:'🏷️'})[group]||'ℹ️'}
function evidenceClass(group){return ['sold','guide','mixed','asking'].includes(group)?group:'mixed'}
function sourceMatches(row){
 if(sourceFilter==='all')return true;
 if(sourceFilter==='core')return row?.recommended===true;
 return String(row?.region||'')===sourceFilter;
}
function updateSourceTabs(){
 document.querySelectorAll('[data-market-filter]').forEach(btn=>{
   const active=btn.dataset.marketFilter===sourceFilter;
   btn.classList.toggle('is-active',active);btn.setAttribute('aria-pressed',active?'true':'false');
 });
}
function renderReferenceSources(){
 const grid=el('agmSourceGrid');if(!grid)return;
 updateSourceTabs();
 const query=marketQuery();
 const rows=referenceSources().filter(sourceMatches);
 if(!rows.length){grid.textContent='이 구역의 참고처 정보가 없습니다.';return}
 grid.innerHTML=rows.map(row=>{
   const url=safeReferenceUrl(row,query);
   const hasSearch=Boolean(query&&String(row?.search_url_template||'').includes('{query}'));
   const action=url?`<a class="agm-source-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${hasSearch?'이 카드 검색':'사이트 열기'} ↗</a>`:'<span class="agm-source-disabled">링크 확인 필요</span>';
   const auto=row?.auto_collected===true?'<span class="agm-source-auto">앱 자동수집</span>':'';
   const group=evidenceClass(String(row?.evidence_group||''));
   return `<article class="agm-source-card" data-source-region="${esc(row?.region||'')}">
     <div class="agm-source-card-head"><div><small>${esc(row?.region_label||'')}</small><b>${esc(row?.name||'시세 참고처')}</b></div>${auto}</div>
     <span class="agm-evidence agm-evidence-${group}">${evidenceIcon(group)} ${esc(row?.evidence_label||'참고자료')}</span>
     <p>${esc(row?.note||'카드번호·판본·등급·상태를 맞춰 교차확인하세요.')}</p>${action}
   </article>`;
 }).join('');
 const hint=el('agmSourceQueryHint');
 if(hint)hint.textContent=query?`현재 검색어: ${query}`:'카드 촬영/인식 후 각 사이트의 “이 카드 검색” 링크가 자동 생성됩니다.';
}
function mount(){
 if(el('autoGradeMarketFlow'))return;
 const anchor=el('gradingEconomics')||el('quickPriceResults');
 if(!anchor)return;
 const section=document.createElement('section');
 section.id='autoGradeMarketFlow';section.className='card auto-grade-market-flow';
 section.innerHTML=`<div class="agm-head"><div><h3>🎴 자동 카드인식 · 시세 · 등급별 거래가</h3><p>촬영한 카드의 이름·번호·판본을 연결하고, 실제 거래/시장가이드/판매중 호가를 구분해 국내외 시세를 교차확인합니다.</p></div><span class="agm-auto">AUTO</span></div>
 <div class="agm-identity"><div><span>카드명</span><b id="agmName">인식 대기</b></div><div><span>카드번호</span><b id="agmNumber">-</b></div><div><span>판본</span><b id="agmRegion">-</b></div></div>
 <div class="agm-raw"><span>등급 측정 전 RAW 현재 시세</span><b id="agmRawPrice">카드 인식 후 자동 조회</b><small id="agmRawSource">확인된 저장/수집 거래자료만 표시</small></div>
 <div><div class="agm-title">🇰🇷🇯🇵🇺🇸 판본별 자동수집 공개시세</div><div id="agmPlatformQuotes" class="agm-grade-rows">카드 인식 후 WYYYES 등 자동수집 공개시장 자료를 연결합니다.</div><small id="agmPlatformPolicy">판매중/가격제안 값과 실제 체결·낙찰 값은 섞지 않고 구분해 표시합니다.</small></div>
 <div class="agm-source-guide"><div class="agm-title">🔎 국내·해외 시세 교차확인</div>
   <div class="agm-source-legend"><b>쉽게 보는 순서</b><span>✅ 체결·낙찰 → 📊 최근판매 기반 시장가이드 → 🔄 혼합 집계 → 🏷️ 판매중 호가</span><small>같은 카드라도 카드번호·한국/일본/영문판·등급·상태·거래일이 다르면 가격이 달라집니다. 한 곳만 보지 말고 최소 2~3곳을 교차확인하세요.</small></div>
   <div class="agm-source-tabs" role="group" aria-label="시세 참고지역"><button type="button" class="agm-source-tab is-active" data-market-filter="core" aria-pressed="true">⭐ 핵심</button><button type="button" class="agm-source-tab" data-market-filter="KR" aria-pressed="false">🇰🇷 국내</button><button type="button" class="agm-source-tab" data-market-filter="JP" aria-pressed="false">🇯🇵 일본</button><button type="button" class="agm-source-tab" data-market-filter="US_GLOBAL" aria-pressed="false">🌎 미국·글로벌</button><button type="button" class="agm-source-tab" data-market-filter="EU" aria-pressed="false">🇪🇺 유럽</button><button type="button" class="agm-source-tab" data-market-filter="all" aria-pressed="false">전체</button></div>
   <small id="agmSourceQueryHint" class="agm-source-query">카드 촬영/인식 후 각 사이트의 “이 카드 검색” 링크가 자동 생성됩니다.</small><div id="agmSourceGrid" class="agm-source-grid"></div>
 </div>
 <div><div class="agm-title">등급 측정 후 업체별 거래시세</div><div id="agmGradeRows" class="agm-grade-rows">앞·뒷면 분석 완료 후 자동 표시됩니다.</div></div>`;
 section.addEventListener('click',event=>{
   const btn=event.target.closest('[data-market-filter]');if(!btn||!section.contains(btn))return;
   sourceFilter=btn.dataset.marketFilter||'core';renderReferenceSources();
 });
 anchor.parentNode.insertBefore(section,anchor);
 if(el('gradingEconomics'))el('gradingEconomics').classList.add('economics-engine-hidden');
 renderReferenceSources();
}
async function loadPlatformQuotes(){
 if(platformLoaded||platformLoading)return;
 platformLoading=true;
 try{
   const response=await fetch('market_prices.json',{cache:'no-store'});
   if(!response.ok)throw new Error('market prices unavailable');
   const data=await response.json();
   platformMarket=(data&&typeof data==='object')?data:null;
 }catch(_){platformMarket=null}
 finally{platformLoaded=true;platformLoading=false;renderPlatformQuotes();renderReferenceSources()}
}
function quoteScore(row,name,number,region){
 if(!row||row.platform!=='WYYYES')return -999;
 const title=norm(row.title),n=norm(name),cn=norm(number),qcn=norm(row.card_number);
 let score=0;
 if(cn&&qcn&&cn===qcn)score+=120;
 if(n&&n.length>=4&&(title.includes(n)||n.includes(title)))score+=50;
 const tokens=String(name||'').toLowerCase().match(/[0-9a-z가-힣]{2,}/g)||[];
 const hits=tokens.filter(t=>title.includes(norm(t))).length;
 score+=Math.min(30,hits*10);
 const wanted=editionCode(region),actual=editionCode(row.card_region||'UNKNOWN');
 if(wanted!=='UNKNOWN'&&actual===wanted)score+=20;
 else if(wanted!=='UNKNOWN'&&actual!==wanted)return -999;
 if(Number(row.price)>0)score+=5;
 return score;
}
function matchingPlatformQuotes(name,number,region){
 const all=platformMarket?.platform_quotes?.WYYYES;
 if(!Array.isArray(all))return [];
 return all.map(row=>({row,score:quoteScore(row,name,number,region)}))
   .filter(x=>x.score>=25)
   .sort((a,b)=>b.score-a.score||Number(b.row?.is_completed_sale===true)-Number(a.row?.is_completed_sale===true))
   .slice(0,6).map(x=>x.row);
}
function renderPlatformQuotes(){
 const box=el('agmPlatformQuotes');if(!box)return;
 const name=(el('identityCardName')?.value||'').trim(),number=(el('identityCardNumber')?.value||'').trim(),region=(el('identityRegion')?.value||'').trim();
 if(!name&&!number){box.textContent='카드 인식 후 판본별 자동수집 공개시장 자료를 연결합니다.';renderReferenceSources();return}
 if(!platformLoaded){box.textContent='공개시장 자료 불러오는 중…';loadPlatformQuotes();return}
 const rows=matchingPlatformQuotes(name,number,region);
 if(!rows.length){
   box.textContent='현재 정확히 일치하는 자동수집 WYYYES 시세가 없습니다. 아래 교차확인에서 국내·일본·미국·유럽 참고처를 바로 확인할 수 있습니다.';
   renderReferenceSources();return;
 }
 box.innerHTML=rows.map(row=>{
   const grade=row.grading_company&&row.grade?`${esc(row.grading_company)} ${esc(row.grade)}`:'미감정/등급 미확인';
   const type=quoteTypeLabel(row),url=safeSourceUrl(row.source_url),source=url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">WYYYES</a>`:'WYYYES';
   return `<div class="agm-row"><b>${editionLabel(String(row.card_region||'UNKNOWN').toUpperCase())}</b><span>${esc(type)} · ${grade}<br><small>${esc(row.title||'')}</small></span><strong>${money(row.price)}<br><small>${source}</small></strong></div>`;
 }).join('');
 renderReferenceSources();
}
function findMarketKey(name,number){
 const select=el('econCard'); if(!select)return '';
 const direct=(el('identityMarketKey')?.value||'').trim();
 if(direct&&[...select.options].some(o=>o.value===direct))return direct;
 const n=norm(name),cn=norm(number);
 let best='';
 for(const o of [...select.options]){
   if(!o.value)continue; const blob=norm(o.textContent+' '+o.value);
   if(cn&&blob.includes(cn))return o.value;
   if(n&&blob.includes(n)&&!best)best=o.value;
 }
 return best;
}
function applyIdentity(){
 const name=(el('identityCardName')?.value||'').trim();
 const number=(el('identityCardNumber')?.value||'').trim();
 const region=(el('identityRegion')?.value||'').trim();
 const sig=[name,number,region,el('identityMarketKey')?.value||''].join('|');
 if(sig===lastIdentity)return; lastIdentity=sig;
 el('agmName').textContent=name||'인식 대기'; el('agmNumber').textContent=number||'-'; el('agmRegion').textContent=region||'-';
 if(!name&&!number){el('agmRawPrice').textContent='카드 인식 후 자동 조회';renderPlatformQuotes();renderReferenceSources();return}
 const q=[name,number].filter(Boolean).join(' ');
 if(el('quickCardQuery')){el('quickCardQuery').value=q; el('quickPriceSearch')?.click();}
 const key=findMarketKey(name,number),select=el('econCard');
 if(key&&select){
   select.value=key;
   try{if(typeof applyEconomicsProfile==='function')applyEconomicsProfile()}catch(_){ }
   const raw=Number(el('econRaw')?.value||0);
   el('agmRawPrice').textContent=raw>0?money(raw):'저장 시세 연결됨 · RAW 거래자료 없음';
   el('agmRawSource').textContent=(el('econSource')?.textContent||'확인된 저장/수집 거래자료').trim();
 }else{
   el('agmRawPrice').textContent='저장 시세 자동 연결 대기';
   el('agmRawSource').textContent='빠른 시세검색은 자동 실행됨 · 정확히 일치하는 카드 키 확인 중';
 }
 renderPlatformQuotes();renderReferenceSources();updateGrades(true);
}
function gradeSale(company,grade){
 const exact=Number(grade),normalizedCompany=String(company||'').toUpperCase();
 if(!Number.isFinite(exact)||!Number.isInteger(exact)||exact<1||exact>10||!COMPANIES.includes(normalizedCompany))return 0;
 const comp=el('econCompany'),gr=el('econGrade');if(!comp||!gr)return 0;
 const gradeValue=String(exact);
 if(![...gr.options].some(option=>option.value===gradeValue))return 0;
 const oldC=comp.value,oldG=gr.value;
 try{
   comp.value=normalizedCompany;gr.value=gradeValue;
   if(typeof renderEconomics!=='function')return 0;
   const result=renderEconomics(),sale=Number(result?.expectedSale||0);
   return Number.isFinite(sale)&&sale>0?sale:0;
 }catch(_){return 0}
 finally{comp.value=oldC;gr.value=oldG}
}
function updateGrades(force=false){
 const grades=window.tcgLastGrades||{}; const sig=COMPANIES.map(c=>`${c}:${grades[c]??''}`).join('|');
 if(!force&&sig===lastGrades)return; lastGrades=sig;
 const box=el('agmGradeRows');if(!box)return;
 const has=COMPANIES.some(c=>Number.isFinite(Number(grades[c])));
 if(!has){box.textContent='앞·뒷면 분석 완료 후 자동 표시됩니다.';return}
 box.innerHTML=COMPANIES.map(c=>{
   const g=Number(grades[c]); if(!Number.isFinite(g))return `<div class="agm-row"><b>${c}</b><span>등급 대기</span><strong>-</strong></div>`;
   const sale=gradeSale(c,g),price=Number.isInteger(g)?money(sale):'정확 등급 거래자료 없음';
   return `<div class="agm-row"><b>${c}</b><span>예상 ${g.toFixed(g%1?1:0)}등급</span><strong>${price}</strong></div>`;
 }).join('');
}
function tick(){mount();if(el('autoGradeMarketFlow')){applyIdentity();updateGrades(false)}}
let tickTimer=0;
function startTicking(){if(tickTimer||document.hidden)return;tickTimer=setInterval(tick,600)}
function stopTicking(){if(tickTimer){clearInterval(tickTimer);tickTimer=0}}
function boot(){mount();loadPlatformQuotes();tick();startTicking();document.addEventListener('visibilitychange',()=>{if(document.hidden)stopTicking();else{tick();startTicking()}})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot()
window.refreshAutoGradeMarketFlow=()=>{lastIdentity='';lastGrades='';renderPlatformQuotes();renderReferenceSources();tick()};
})();