// V572 proof-gated BOX pricing candidate. NOT loaded by tablet until a reviewed sync successor is approved.
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let marketCache={entries:{}};
function catalogRowsForCountry(){
 try{
  const all=typeof COUNTRY_BOX_DATA==='undefined'?[]:COUNTRY_BOX_DATA;
  const active=document.querySelector('.box-kb-country.active');
  const country=String(active?.dataset?.kbCountry||'ALL');
  return all.filter(x=>country==='ALL'||x.country===country);
 }catch(_){return []}
}
// V572: automatic BOX pricing from matched, dated market evidence.
// This never upgrades an asking price or search snippet into a completed sale.
function boxPriceSummaryV572(entry,identity,now=new Date()){
 const result={low:null,high:null,recommended:null,single:null,tier:'none',count:0,sources:0,age:null,reason:'동일 BOX의 검증 가격 근거 부족'};
 if(!entry||typeof entry!=='object'||!identity||!['KR','JP','US'].includes(identity.country))return result;
 if(entry.game&&identity.game&&String(entry.game)!==String(identity.game))return {...result,reason:'게임 식별 불일치'};
 const key=[identity.country,identity.name,'BOX'].join('|');
 const validDate=s=>{
  if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s))return null;
  const d=new Date(s+'T00:00:00+09:00');
  if(!Number.isFinite(d.getTime())||new Date(d.getTime()+9*3600000).toISOString().slice(0,10)!==s)return null;
  const age=Math.floor((now.getTime()-d.getTime())/86400000);
  return Number.isFinite(age)&&age>=0&&age<=30?age:null;
 };
 const amount=p=>Number.isSafeInteger(p)&&p>0&&p<=1e12?p:null;
 const marketHost=u=>{
  try {const x=new URL(u);if(x.protocol!=='https:'||x.username||x.password||(x.port&&x.port!=='443'))return '';
   const allowed=['kream.co.kr','ebay.com','ebay.co.jp','tcgplayer.com','cardmarket.com','bunjang.co.kr','joongna.com','daangn.com','snkrdunk.com','jp.mercari.com','auctions.yahoo.co.jp','pokard.io'];
   const host=x.hostname.toLowerCase();return allowed.find(d=>host===d||host.endsWith('.'+d))||'';
  }catch(_){return ''}
 };
 const observed=[];
 // Only exact product-key, BOX unit, sealed condition, documented KRW observations.
 for(const v of (Array.isArray(entry.price_observations)?entry.price_observations:[]).slice(0,160)){
  if(!v||v.product_key!==key||v.unit!=='BOX'||v.sealed!==true||v.currency!=='KRW')continue;
  const price=amount(v.price_krw),age=validDate(v.observed_at),host=marketHost(v.source_url);
  if(price===null||age===null||!host||!['asking','completed_sale'].includes(v.evidence_type))continue;
  const sold=v.evidence_type==='completed_sale'&&v.verified===true&&v.review_method==='source_page_crosscheck'&&
   typeof v.sale_id==='string'&&/^[\w:-]{8,100}$/.test(v.sale_id);
  // Unverified sold claims remain asking/reference only, never count as transactions.
  observed.push({price,age,host,tier:sold?'completed_sale':'asking',id:sold?v.sale_id:''});
 }
 const completed=observed.filter(x=>x.tier==='completed_sale');
 const asking=observed.filter(x=>x.tier==='asking');
 // Independent sale IDs (same sale mirrored by sites counts once).
 const seen=new Set(),sales=[];
 for(const x of completed){if(!seen.has(x.id)){seen.add(x.id);sales.push(x)}}
 const sourceMedians=[];
 for(const host of new Set(sales.map(x=>x.host))){
  const values=sales.filter(x=>x.host===host).map(x=>x.price).sort((a,b)=>a-b);
  const mid=Math.floor(values.length/2);sourceMedians.push(values.length%2?values[mid]:(values[mid-1]+values[mid])/2);
 }
 const samples=sales.length?sales:asking;
 if(samples.length){
  const prices=samples.map(x=>x.price);
  result.low=Math.min(...prices);result.high=Math.max(...prices);
  result.count=samples.length;result.sources=new Set(samples.map(x=>x.host)).size;
  result.age=Math.min(...samples.map(x=>x.age));result.tier=sales.length?'completed_sale':'asking';
  result.reason=sales.length?'검증 완료거래 범위':'최근 판매호가 범위 · 체결가 아님';
  if(sales.length>=2&&sourceMedians.length>=2&&sales.some(x=>x.age<=7)){
   sourceMedians.sort((a,b)=>a-b);const mid=Math.floor(sourceMedians.length/2);
   const med=sourceMedians.length%2?sourceMedians[mid]:(sourceMedians[mid-1]+sourceMedians[mid])/2;
   result.recommended=Math.round(med/1000)*1000;
  }
  return result;
 }
 // Legacy snapshot can be displayed as a *published quote/range*, not as
 // verified best marketplace prices or an inferred selling recommendation.
 const age=validDate(entry.source_date),host=marketHost(entry.source);
 if(age===null||!host)return {...result,reason:'가격 출처가 없거나 30일 경과'};
 const display=String(entry.display||'').trim();
 const m=display.match(/^₩([1-9]\d{0,2}(?:,\d{3})*)(?:\s*[~～-]\s*₩([1-9]\d{0,2}(?:,\d{3})*))?$/);
 if(!m)return {...result,reason:'원화 BOX 가격 구조 미확인'};
 const a=amount(Number(m[1].replace(/,/g,'')));
 const b=m[2]?amount(Number(m[2].replace(/,/g,''))):null;
 if(a===null||m[2]&&b===null||b!==null&&b<a)return {...result,reason:'가격 범위 비정상'};
 return {low:b===null?null:a,high:b,single:b===null?a:null,recommended:null,
  tier:'reference',count:1,sources:1,age,reason:b===null?'출처 표시가격 1건 · 최저·최고 미확인':'출처 표시범위 · 시장 전체 최저·최고 아님'};
}
window.TCGBoxPriceSummaryV572=Object.freeze({summarize:boxPriceSummaryV572});
function renderBoxPriceCardsV572(){
 const list=$('box12');if(!list)return;
 const rows=catalogRowsForCountry(),cards=list.querySelectorAll('.box-kb-card');
 const money=v=>v===null?'—':'₩'+Math.round(v).toLocaleString('ko-KR');
 cards.forEach((card,i)=>{
  const row=rows[i];if(!row)return;
  const key=[row.country,row.name,'BOX'].join('|');
  const entry=(marketCache.entries||{})[key];
  const p=boxPriceSummaryV572(entry,{country:row.country,name:row.name,game:row.game});
  let panel=card.querySelector('.boxkb-price-trio-v572');
  if(!panel){
   panel=document.createElement('section');panel.className='boxkb-price-trio-v572';
   (card.querySelector('.box-kb-price')||card.querySelector('.box-kb-body')||card).insertAdjacentElement('afterend',panel);
  }
  panel.innerHTML='<div class="boxkb-price-trio-grid"><div><span>최저가</span><b>'+money(p.low)+'</b></div>'+
    '<div><span>최고가</span><b>'+money(p.high)+'</b></div><div><span>추천판매가</span><b>'+money(p.recommended)+'</b></div></div>'+
    (p.single!==null?'<div class="boxkb-price-single">관측가 '+money(p.single)+'</div>':'')+
    '<p>'+esc(p.reason)+' · '+(p.age===null?'날짜 미확인':p.age+'일 전')+
    ' · '+p.sources+'곳 / '+p.count+'건 · 수수료·배송비 별도</p>';
 });
}


window.TCGBoxPriceCandidateV572=Object.freeze({
 render:renderBoxPriceCardsV572,
 refresh:async()=>{
  const r=await fetch('market_prices.json?_='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw Error('market_prices unavailable');
  const d=await r.json();
  if(!d||typeof d.entries!=='object'||Array.isArray(d.entries))throw Error('market_prices schema');
  marketCache=d;renderBoxPriceCardsV572();
 }
});
})();
