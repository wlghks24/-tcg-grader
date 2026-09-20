(()=>{
'use strict';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const norm=s=>String(s||'').toLowerCase().replace(/\s+/g,'').replace(/[^0-9a-z가-힣/.-]/g,'');
const money=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'거래자료 없음';
const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let lastIdentity='',lastGrades='',platformMarket=null,platformLoaded=false,platformLoading=false;
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
function mount(){
 if(el('autoGradeMarketFlow'))return;
 const anchor=el('gradingEconomics')||el('quickPriceResults');
 if(!anchor)return;
 const section=document.createElement('section');
 section.id='autoGradeMarketFlow';section.className='card auto-grade-market-flow';
 section.innerHTML=`<div class="agm-head"><div><h3>🎴 자동 카드인식 · 시세 · 등급별 거래가</h3><p>촬영한 카드의 이름과 번호를 자동 연결하고, 판본별 공개시장 시세와 측정 후 5개 업체별 거래시세를 한 번에 표시합니다.</p></div><span class="agm-auto">AUTO</span></div>
 <div class="agm-identity"><div><span>카드명</span><b id="agmName">인식 대기</b></div><div><span>카드번호</span><b id="agmNumber">-</b></div><div><span>판본</span><b id="agmRegion">-</b></div></div>
 <div class="agm-raw"><span>등급 측정 전 RAW 현재 시세</span><b id="agmRawPrice">카드 인식 후 자동 조회</b><small id="agmRawSource">확인된 저장/수집 거래자료만 표시</small></div>
 <div><div class="agm-title">🇰🇷🇯🇵🇺🇸 판본별 공개시장 시세</div><div id="agmPlatformQuotes" class="agm-grade-rows">카드 인식 후 WYYYES 등 공개시장 자료를 연결합니다.</div><small id="agmPlatformPolicy">판매중/가격제안 값과 실제 체결·낙찰 값은 구분해서 표시합니다.</small></div>
 <div><div class="agm-title">등급 측정 후 업체별 거래시세</div><div id="agmGradeRows" class="agm-grade-rows">앞·뒷면 분석 완료 후 자동 표시됩니다.</div></div>`;
 anchor.parentNode.insertBefore(section,anchor);
 if(el('gradingEconomics'))el('gradingEconomics').classList.add('economics-engine-hidden');
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
 finally{platformLoaded=true;platformLoading=false;renderPlatformQuotes()}
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
 const wanted=editionCode(region),actual=String(row.card_region||'UNKNOWN').toUpperCase();
 if(wanted!=='UNKNOWN'&&actual===wanted)score+=20;
 else if(wanted!=='UNKNOWN'&&actual!=='UNKNOWN'&&actual!==wanted)score-=40;
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
 if(!name&&!number){box.textContent='카드 인식 후 판본별 공개시장 자료를 연결합니다.';return}
 if(!platformLoaded){box.textContent='공개시장 자료 불러오는 중…';loadPlatformQuotes();return}
 const rows=matchingPlatformQuotes(name,number,region);
 if(!rows.length){
   box.textContent='현재 정확히 일치하는 WYYYES 공개시세가 없습니다. KREAM·당근·번개장터·중고나라·Collectory 등 기존 자료와 계속 교차확인합니다.';
   return;
 }
 box.innerHTML=rows.map(row=>{
   const grade=row.grading_company&&row.grade?`${esc(row.grading_company)} ${esc(row.grade)}`:'미감정/등급 미확인';
   const type=quoteTypeLabel(row),url=safeSourceUrl(row.source_url),source=url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">WYYYES</a>`:'WYYYES';
   return `<div class="agm-row"><b>${editionLabel(String(row.card_region||'UNKNOWN').toUpperCase())}</b><span>${esc(type)} · ${grade}<br><small>${esc(row.title||'')}</small></span><strong>${money(row.price)}<br><small>${source}</small></strong></div>`;
 }).join('');
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
 if(!name&&!number){el('agmRawPrice').textContent='카드 인식 후 자동 조회';renderPlatformQuotes();return}
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
 renderPlatformQuotes();updateGrades(true);
}
function gradeSale(company,grade){
 try{
   const comp=el('econCompany'),gr=el('econGrade'); if(!comp||!gr)return 0;
   const oldC=comp.value,oldG=gr.value; comp.value=company; gr.value=String(Math.max(1,Math.min(10,Math.floor(Number(grade)))));
   let sale=0;
   if(typeof renderEconomics==='function'){const r=renderEconomics(); sale=Number(r?.expectedSale||0)}
   comp.value=oldC;gr.value=oldG;return sale;
 }catch(_){return 0}
}
function updateGrades(force=false){
 const grades=window.tcgLastGrades||{}; const sig=COMPANIES.map(c=>`${c}:${grades[c]??''}`).join('|');
 if(!force&&sig===lastGrades)return; lastGrades=sig;
 const box=el('agmGradeRows');if(!box)return;
 const has=COMPANIES.some(c=>Number.isFinite(Number(grades[c])));
 if(!has){box.textContent='앞·뒷면 분석 완료 후 자동 표시됩니다.';return}
 box.innerHTML=COMPANIES.map(c=>{
   const g=Number(grades[c]); if(!Number.isFinite(g))return `<div class="agm-row"><b>${c}</b><span>등급 대기</span><strong>-</strong></div>`;
   const rounded=Math.max(1,Math.min(10,Math.floor(g))),sale=gradeSale(c,rounded);
   return `<div class="agm-row"><b>${c}</b><span>예상 ${g.toFixed(g%1?1:0)}등급</span><strong>${money(sale)}</strong></div>`;
 }).join('');
}
function tick(){mount();if(el('autoGradeMarketFlow')){applyIdentity();updateGrades(false)}}
let tickTimer=0;
function startTicking(){if(tickTimer||document.hidden)return;tickTimer=setInterval(tick,600)}
function stopTicking(){if(tickTimer){clearInterval(tickTimer);tickTimer=0}}
function boot(){mount();loadPlatformQuotes();tick();startTicking();document.addEventListener('visibilitychange',()=>{if(document.hidden)stopTicking();else{tick();startTicking()}})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot()
window.refreshAutoGradeMarketFlow=()=>{lastIdentity='';lastGrades='';renderPlatformQuotes();tick()};
})();
