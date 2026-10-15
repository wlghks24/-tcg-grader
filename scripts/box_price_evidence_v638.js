/* V638: separate, local-only BOX price evidence lens.
 * Historical box_knowledge_stats.js is deliberately not modified.
 * Market-wide "low/high" and recommended sell prices require exact completed sales;
 * single public asking quotes are reference-only.
 */
(function(root,factory){
 "use strict";
 const api=factory();
 if(typeof module==="object"&&module.exports)module.exports=api;
 if(root&&root.document){
  root.TcgBoxPriceV638=api;
  const boot=()=>api.mount(root.document,root.fetch?.bind(root));
  if(root.document.readyState==="loading")root.document.addEventListener("DOMContentLoaded",boot,{once:true});
  else boot();
 }
})(typeof globalThis==="object"?globalThis:this,function(){
 "use strict";
 const hosts=Object.freeze(["kream.co.kr","pokard.io","snkrdunk.com","ebay.com","ebay.co.jp","tcgplayer.com","pricecharting.com","cardmarket.com"]);
 const validCountry=new Set(["KR","JP","US","CN-S","CN-T"]);
 const validCurrency=new Set(["KRW","JPY","USD","CNY","TWD","HKD"]);
 const datePattern=/^20\d{2}-\d{2}-\d{2}$/;
 function normalize(v){return String(v||"").normalize("NFKC").trim().toLocaleLowerCase()}
 function sourceLink(value,detail=false){
  try{
   const u=new URL(String(value||""));
   if(u.protocol!=="https:"||u.username||u.password||(u.port&&u.port!=="443")||u.hash)return "";
   if(!hosts.some(d=>u.hostname===d||u.hostname.endsWith("."+d)))return "";
   if(detail&&u.pathname==="/"&&!u.search)return "";
   return u.href;
  }catch(_){return ""}
 }
 function daysOld(value,now=new Date()){
  const s=String(value||"");
  if(!datePattern.test(s))return null;
  const n=Date.parse(s+"T00:00:00Z");
  if(!Number.isFinite(n)||new Date(n).toISOString().slice(0,10)!==s)return null;
  const today=new Date(now.getTime()+9*3600000).toISOString().slice(0,10);
  const day=Date.parse(today+"T00:00:00Z");
  const age=Math.floor((day-n)/86400000);
  return age>=0?age:null;
 }
 function parseQuote(text){
  const m=/^([₩¥$])\s*(\d+(?:,\d{3})*)(?:\s*[~～–-]\s*(?:\1\s*)?(\d+(?:,\d{3})*))?$/.exec(String(text||"").trim());
  if(!m)return null;
  const low=Number(m[2].replace(/,/g,"")),high=Number((m[3]||m[2]).replace(/,/g,""));
  if(!Number.isSafeInteger(low)||!Number.isSafeInteger(high)||low<100||high<low||high>1000000000)return null;
  return {currency:{"₩":"KRW","¥":"JPY","$":"USD"}[m[1]],low,high};
 }
 function median(values){
  const sorted=[...values].sort((a,b)=>a-b),n=sorted.length;
  if(!n)return null;
  return n%2?sorted[(n-1)/2]:(sorted[n/2-1]+sorted[n/2])/2;
 }
 function groupKey(item){
  return [String(item?.country||""),normalize(item?.name),String(item?.game||"")].join("|");
 }
 function completedSales(row,request,now){
  const out=[],seen=new Set();
  for(const sale of (Array.isArray(row?.completed_sales)?row.completed_sales.slice(0,100):[])){
   if(!sale||sale.verified!==true||sale.evidence_class!=="completed"||
    sale.sealed!==true||sale.unit!=="BOX"||sale.box_quantity!==1||
    sale.country!==request.country||sale.game!==request.game||
    normalize(sale.product_name)!==normalize(request.name)||
    sale.currency!=="KRW"||!Number.isSafeInteger(sale.price_krw)||
    sale.price_krw<1000||sale.price_krw>100000000||
    typeof sale.transaction_id!=="string"||!sale.transaction_id.trim()||
    !(daysOld(sale.sold_at,now)<=30&&daysOld(sale.sold_at,now)!==null))continue;
   const url=sourceLink(sale.source_url,true);if(!url)continue;
   const host=new URL(url).hostname,key=host+"|"+sale.transaction_id.trim();
   if(seen.has(key))continue;
   seen.add(key);out.push({price:sale.price_krw,host,url});
  }
  return out;
 }
 function assess(request,entries,now=new Date()){
  const empty={low:null,high:null,recommended:null,currency:"KRW",basis:"동일 조건 확인자료 없음",observed:null,url:"",evidence_count:0};
  if(!request||!validCountry.has(request.country)||!request.game||!request.name)return {...empty,basis:"게임·국가·상품명 확인 필요"};
  const matched=[];
  for(const [key,row] of Object.entries(entries||{})){
   const parts=key.split("|");
   if(parts.length!==3||parts[2]!=="BOX"||parts[0]!==request.country||
    normalize(parts[1])!==normalize(request.name)||row?.game!==request.game||
    row?.sealed===false||row?.box_quantity!==undefined&&row.box_quantity!==1)continue;
   matched.push(row);
  }
  if(!matched.length)return empty;
  const sales=[],seen=new Set();
  for(const row of matched)for(const sale of completedSales(row,request,now)){
   const fingerprint=sale.host+"|"+sale.url+"|"+sale.price;
   if(seen.has(fingerprint))continue;
   seen.add(fingerprint);sales.push(sale);
  }
  if(sales.length){
   const prices=sales.map(s=>s.price),low=Math.min(...prices),high=Math.max(...prices),byHost=new Map();
   for(const s of sales)byHost.set(s.host,[...(byHost.get(s.host)||[]),s.price]);
   const strong=sales.length>=3&&byHost.size>=2&&high<=low*2;
   return {low,high,currency:"KRW",recommended:strong?Math.round(median([...byHost.values()].map(median))):null,
    basis:strong?"실제 완료거래 "+sales.length+"건 · 독립 출처 "+byHost.size+"곳 · 비용 제외":
    "완료거래 "+sales.length+"건 · 거래표본/출처/편차 부족으로 추천 보류",
    observed:null,url:sales[0].url,evidence_count:sales.length};
  }
  const quotes=matched.filter(row=>parseQuote(row.display)&&sourceLink(row.source));
  quotes.sort((a,b)=>{
   const da=daysOld(a.market_observed_at||a.source_date,now)??10000;
   const db=daysOld(b.market_observed_at||b.source_date,now)??10000;
   return da-db;
  });
  const chosen=quotes[0];if(!chosen)return {...empty,basis:"가격 형식 또는 출처 검증 불가"};
  const age=daysOld(chosen.market_observed_at||chosen.source_date,now);
  return {...empty,basis:age===null?"자료일 검증 불가 · 거래추천 보류":
   age>14?"과거 관측가 · "+age+"일 경과 · 현재 시세 아님":
   "판매호가/공개표시가격 · 실거래·수량·밀봉 확인 필요",
   observed:String(chosen.display||""),currency:parseQuote(chosen.display).currency,
   url:sourceLink(chosen.source),observed_at:String(chosen.market_observed_at||chosen.source_date||""),
   evidence_count:0};
 }
 function presentation(result){
  const fmt=v=>v===null?"—":new Intl.NumberFormat("ko-KR",{style:"currency",currency:result.currency,maximumFractionDigits:0}).format(v);
  return {
   low:result.low===null?"검증 보류":fmt(result.low),
   high:result.high===null?"검증 보류":fmt(result.high),
   sell:result.recommended===null?"산정 보류":fmt(result.recommended),
   basis:result.basis,observed:result.observed||"",date:result.observed_at||""
  };
 }
 function mount(doc,fetcher){
  const list=doc.getElementById("box12");
  if(!list||typeof fetcher!=="function")return false;
  const root=doc.defaultView||globalThis;
  if(list.dataset.v638Active==="1")return true;
  list.dataset.v638Active="1";
  let entries={},pending=false,lastFetch=0;
  const safeCatalog=()=>{try{return typeof COUNTRY_BOX_DATA==="object"&&Array.isArray(COUNTRY_BOX_DATA)?COUNTRY_BOX_DATA:[]}catch(_){return []}};
  function refreshCards(){
   pending=false;
   const country=doc.querySelector(".box-kb-country.active")?.dataset.kbCountry||"ALL";
   const products=safeCatalog().filter(x=>country==="ALL"||x.country===country);
   const cards=[...list.querySelectorAll(".box-kb-card")];
   cards.forEach((card,index)=>{
    const product=products[index],name=card.querySelector(".box-kb-name")?.textContent||"";
    if(!product||normalize(name)!==normalize(product.name))return;
    let panel=card.querySelector(".boxkb-market-comparison");
    if(!panel){
     panel=doc.createElement("section");panel.className="boxkb-market-comparison";
     panel.setAttribute("aria-label","BOX 최저 최고 판매가 검증");
     card.querySelector(".box-kb-body")?.appendChild(panel);
    }
    if(!panel)return;
    const result=assess(product,entries),view=presentation(result);
    const signature=[...Object.values(view),result.url].join("|");
    if(panel.dataset.pricingSignature===signature)return;
    panel.dataset.pricingSignature=signature;
    panel.replaceChildren();
    const title=doc.createElement("b");title.className="boxkb-market-heading";title.textContent="BOX 가격 근거";panel.appendChild(title);
    const grid=doc.createElement("div");grid.className="boxkb-market-price-grid";
    for(const [name,value] of [["검증 최저",view.low],["검증 최고",view.high],["판매추천",view.sell]]){
     const cell=doc.createElement("div");cell.className="boxkb-market-metric";
     const a=doc.createElement("span");a.textContent=name;
     const b=doc.createElement("strong");b.textContent=value;
     cell.append(a,b);grid.appendChild(cell);
    }
    panel.appendChild(grid);
    const reason=doc.createElement("small");reason.className="boxkb-market-reason";reason.textContent=view.basis;panel.appendChild(reason);
    if(view.observed){
     const obs=doc.createElement("small");obs.className="boxkb-market-observed";
     obs.textContent="참고 표기가격: "+view.observed+(view.date?" · "+view.date:"")+" (검증된 최저가 아님)";
     panel.appendChild(obs);
    }
    if(result.url){
     const a=doc.createElement("a");a.href=result.url;a.rel="noopener noreferrer";a.target="_blank";a.textContent="출처 확인 ↗";panel.appendChild(a);
    }
   });
  }
  function scheduleRefresh(){
   if(pending)return;
   pending=true;
   if(typeof root.requestAnimationFrame==="function")root.requestAnimationFrame(refreshCards);
   else root.setTimeout(refreshCards,0);
  }
  async function updateData(force=false){
   if(!force&&Date.now()-lastFetch<600000)return;
   lastFetch=Date.now();
   try{
    const r=await fetcher("market_prices.json",{cache:"no-store"});
    if(!r.ok)throw new Error("MARKET_HTTP");
    const data=await r.json();
    if(!data||!data.entries||typeof data.entries!=="object"||Array.isArray(data.entries))throw new Error("MARKET_SCHEMA");
    entries=data.entries;
   }catch(_){entries={}}
   scheduleRefresh();
  }
  if(typeof root.MutationObserver==="function"){
   new root.MutationObserver(records=>{
    if(records.every(record=>record.target?.closest?.(".boxkb-market-comparison")))return;
    scheduleRefresh();
   }).observe(list,{childList:true,subtree:true});
  }
  doc.addEventListener("visibilitychange",()=>{if(!doc.hidden)updateData()});
  root.addEventListener?.("tcg-market-catalog-expanded",()=>updateData(true));
  updateData(true);scheduleRefresh();
  return true;
 }
 return Object.freeze({assess,parseQuote,sourceLink,daysOld,presentation,mount});
});
