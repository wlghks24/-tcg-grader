(()=>{
'use strict';
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const norm=s=>String(s||'').toLowerCase().replace(/\s+/g,'').replace(/[^0-9a-z가-힣/.-]/g,'');
const money=n=>Number(n)>0?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'거래자료 없음';
let lastIdentity='',lastGrades='';
function el(id){return document.getElementById(id)}
function mount(){
 if(el('autoGradeMarketFlow'))return;
 const anchor=el('gradingEconomics')||el('quickPriceResults');
 if(!anchor)return;
 const section=document.createElement('section');
 section.id='autoGradeMarketFlow';section.className='card auto-grade-market-flow';
 section.innerHTML=`<div class="agm-head"><div><h3>🎴 자동 카드인식 · 시세 · 등급별 거래가</h3><p>촬영한 카드의 이름과 번호를 자동 연결하고, 등급 전 RAW 시세와 측정 후 5개 업체별 거래시세를 한 번에 표시합니다.</p></div><span class="agm-auto">AUTO</span></div>
 <div class="agm-identity"><div><span>카드명</span><b id="agmName">인식 대기</b></div><div><span>카드번호</span><b id="agmNumber">-</b></div><div><span>판본</span><b id="agmRegion">-</b></div></div>
 <div class="agm-raw"><span>등급 측정 전 RAW 현재 시세</span><b id="agmRawPrice">카드 인식 후 자동 조회</b><small id="agmRawSource">확인된 저장/수집 거래자료만 표시</small></div>
 <div><div class="agm-title">등급 측정 후 업체별 거래시세</div><div id="agmGradeRows" class="agm-grade-rows">앞·뒷면 분석 완료 후 자동 표시됩니다.</div></div>`;
 anchor.parentNode.insertBefore(section,anchor);
 if(el('gradingEconomics'))el('gradingEconomics').classList.add('economics-engine-hidden');
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
 if(!name&&!number){el('agmRawPrice').textContent='카드 인식 후 자동 조회';return}
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
 updateGrades(true);
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
function tick(){mount(); if(el('autoGradeMarketFlow')){applyIdentity();updateGrades(false)}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{mount();setInterval(tick,600)});else{mount();setInterval(tick,600)}
window.refreshAutoGradeMarketFlow=()=>{lastIdentity='';lastGrades='';tick()};
})();
