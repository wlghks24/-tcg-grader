(()=>{
"use strict";
const VERSION="v403-video-informed";
const REPORT_URL="./tablet_autonomy_v400_report.json";
const DATA_URLS=Object.freeze({
  marketWatch:"./market_watch.json",
  marketPrices:"./market_prices.json",
  releases:"./releases.json",
  promos:"./promo_events.json",
  purchases:"./purchase_sources.json",
});
const REGION_KEY="tcgVideoRecentRegionsV403";
const PORTFOLIO_KEY="tcgVideoPortfolioV403";
const PROVINCES=["서울","경기","인천","부산","대구","대전","광주","울산","세종","강원","충북","충남","전북","전남","경북","경남","제주"];
const MODULE_DEFAULT=["market","release","capture","purchase","portfolio"];
const MODULE_FEATURES=Object.freeze({
  market:["market-search","trading-catalog","grading-economics","box-hit-analysis","box-knowledge"],
  release:["release-info","promo-event-info","box-knowledge"],
  capture:["precision-grade","auto-grade","card-ocr","verified-grade","learning-status"],
  purchase:["purchase-finder","purchase-distance"],
  portfolio:["grading-economics","market-search","verified-grade"],
});
let purchaseRows=[];
let localLocation=null;
let lastReport=null;

function el(tag,cls,text){
  const x=document.createElement(tag);
  if(cls)x.className=cls;
  if(text!==undefined&&text!==null)x.textContent=String(text);
  return x;
}
function num(value){
  const n=Number(value);
  return Number.isFinite(n)?n:null;
}
function safeJson(key,fallback){
  try{
    const raw=localStorage.getItem(key);
    const parsed=raw?JSON.parse(raw):fallback;
    return parsed??fallback;
  }catch(_){return fallback}
}
function saveJson(key,value){
  try{localStorage.setItem(key,JSON.stringify(value));return true}catch(_){return false}
}
async function getJson(url){
  try{
    const r=await fetch(url+"?t="+Date.now(),{cache:"no-store",headers:{"Accept":"application/json"}});
    if(!r.ok)throw new Error("HTTP_"+r.status);
    return await r.json();
  }catch(_){return null}
}
function isoTime(value){
  const t=Date.parse(String(value||""));
  return Number.isFinite(t)?t:0;
}
function dateLabel(value){
  const t=Date.parse(String(value||""));
  return Number.isFinite(t)?new Date(t).toLocaleDateString("ko-KR",{month:"numeric",day:"numeric"}):"날짜 확인";
}
function compact(value,max=38){
  const s=String(value??"").replace(/\s+/g," ").trim();
  return s.length>max?s.slice(0,max-1)+"…":s;
}
function layoutEnabled(){
  try{
    if(window.TCGTabletAutonomyV400?.adaptiveLayoutEnabled)return window.TCGTabletAutonomyV400.adaptiveLayoutEnabled();
  }catch(_){}
  try{return localStorage.getItem("tcgAdaptiveLayoutV400")!=="off"}catch(_){return true}
}
function activateFeature(key){
  const link=document.querySelector('[data-feature-key="'+key+'"]');
  if(link instanceof HTMLElement){link.click();return true}
  return false;
}
function row(rank,title,sub,value){
  const wrap=el("div","video-ai-row");
  wrap.append(el("span","video-ai-row-rank",rank));
  const main=el("span","video-ai-row-main");
  main.append(el("b","",compact(title,44)),el("small","",compact(sub,64)));
  wrap.append(main,el("span","video-ai-row-value",compact(value,20)));
  return wrap;
}
function moduleCard(key,title,note,featureKey){
  const card=el("article","video-ai-module");
  card.dataset.videoModule=key;
  const head=el("div","video-ai-module-head");
  const h=el("h3","",title);
  const a=el("a","","전체 보기");
  a.href="#";
  a.addEventListener("click",event=>{event.preventDefault();activateFeature(featureKey)});
  head.append(h,a);
  const p=el("p","video-ai-note",note);
  const list=el("div","video-ai-list");
  list.dataset.videoList=key;
  card.append(head,p,list);
  return card;
}
function mountHome(){
  if(document.getElementById("videoAiHomeV403"))return document.getElementById("videoAiHomeV403");
  const anchor=document.getElementById("featureCategories");
  if(!anchor||!anchor.parentNode)return null;
  const box=el("section","video-ai-home");
  box.id="videoAiHomeV403";
  const head=el("div","video-ai-home-head");
  const title=el("div");
  title.append(
    el("h2","","📊 AI 시장·작업 홈"),
    el("p","","검증된 시세·출시·행사·구매처와 신경망 우선순위만 사용합니다. TOP은 상승예측이 아니라 최신 활동/확인 우선순위입니다.")
  );
  const badge=el("span","video-ai-home-badge","AI 순서");
  badge.id="videoAiOrderBadge";
  head.append(title,badge);
  const grid=el("div","video-ai-grid");
  grid.append(
    moduleCard("market","💰 시장 활동 TOP","최근 확인된 카드·BOX 자료. 가격 상승순이 아닙니다.","market-search"),
    moduleCard("release","🆕 출시 · 프로모","공식 검증된 최근/예정 출시와 행사.","release-info"),
    moduleCard("capture","📷 촬영 품질","촬영 전에 노출·초점·흔들림을 빠르게 확인합니다.","auto-grade"),
    moduleCard("purchase","📍 가까운 구매처","긴 지역목록 대신 현재위치·최근지역·분할화면.","purchase-distance"),
    moduleCard("portfolio","🗂️ 내 카드","보유원가·현재가를 직접 저장해 로컬에서만 계산합니다.","grading-economics")
  );
  box.append(head,grid);
  anchor.parentNode.insertBefore(box,anchor);
  return box;
}
function reorderHome(report){
  const grid=document.querySelector("#videoAiHomeV403 .video-ai-grid");
  if(!grid)return;
  const modules=Array.from(grid.querySelectorAll("[data-video-module]"));
  const badge=document.getElementById("videoAiOrderBadge");
  if(!layoutEnabled()){
    MODULE_DEFAULT.forEach(key=>{const x=modules.find(m=>m.dataset.videoModule===key);if(x)grid.appendChild(x)});
    modules.forEach(x=>delete x.dataset.aiRank);
    if(badge)badge.textContent="원래 순서";
    return;
  }
  const top=report?.v400_adaptive_layout?.screen_module_plan?.top_features;
  const topFeatures=Array.isArray(top)?top.map(String):[];
  const score={};
  MODULE_DEFAULT.forEach((key,index)=>score[key]=30-index);
  topFeatures.forEach((feature,index)=>{
    const points=100-index*12;
    for(const [key,features] of Object.entries(MODULE_FEATURES)){
      if(features.includes(feature))score[key]=Math.max(score[key]||0,points);
    }
  });
  modules.sort((a,b)=>(score[b.dataset.videoModule]||0)-(score[a.dataset.videoModule]||0));
  modules.forEach((x,index)=>{x.dataset.aiRank=String(index+1);grid.appendChild(x)});
  if(badge)badge.textContent=topFeatures.length?"신경망·시장 순서":"증거기반 순서";
}
function renderMarket(watch,prices){
  const list=document.querySelector('[data-video-list="market"]');
  if(!list)return;
  list.replaceChildren();
  const rows=[];
  const items=Array.isArray(watch?.items)?watch.items:[];
  items.forEach(item=>{
    rows.push({
      title:item.name||item.native||item.product_code||"시장 항목",
      sub:[item.region,item.game,item.asset,item.sale_status,item.link_status].filter(Boolean).join(" · "),
      value:item.official_price||item.price||"가격 확인",
      time:Math.max(isoTime(item.link_checked_at),isoTime(item.release_date)),
    });
  });
  const entries=prices?.entries&&typeof prices.entries==="object"?prices.entries:{};
  Object.entries(entries).forEach(([key,value])=>{
    if(!value||typeof value!=="object")return;
    rows.push({
      title:key.split("|").slice(1).join(" · "),
      sub:[key.split("|")[0],value.market,value.kind,value.source_date].filter(Boolean).join(" · "),
      value:value.display||"가격 확인",
      time:Math.max(isoTime(value.link_checked_at),isoTime(value.source_date)),
    });
  });
  rows.sort((a,b)=>b.time-a.time);
  rows.slice(0,5).forEach((item,index)=>list.append(row(index+1,item.title,item.sub,item.value)));
  if(!list.children.length)list.append(el("div","video-ai-empty","검증된 시장자료가 없습니다. 사이트 전체정보 업데이트 후 다시 확인하세요."));
}
function renderRelease(releases,promos){
  const list=document.querySelector('[data-video-list="release"]');
  if(!list)return;
  list.replaceChildren();
  const rows=[];
  for(const item of Array.isArray(releases?.items)?releases.items:[]){
    if(item.lifecycle==="archived")continue;
    rows.push({
      title:item.name||"출시 정보",
      sub:[item.game,item.region,item.status].filter(Boolean).join(" · "),
      value:dateLabel(item.release_date),
      time:Math.max(isoTime(item.last_verified_at),isoTime(item.release_date)),
    });
  }
  for(const item of Array.isArray(promos?.items)?promos.items:[]){
    if(item.lifecycle==="archived")continue;
    rows.push({
      title:item.name_ko||item.name_native||"행사 정보",
      sub:[item.game,item.region,item.status].filter(Boolean).join(" · "),
      value:dateLabel(item.claim_deadline||item.end_date||item.start_date),
      time:Math.max(isoTime(item.link_checked_at),isoTime(item.start_date)),
    });
  }
  rows.sort((a,b)=>b.time-a.time);
  rows.slice(0,5).forEach((item,index)=>list.append(row(index+1,item.title,item.sub,item.value)));
  if(!list.children.length)list.append(el("div","video-ai-empty","현재 표시할 검증된 출시·행사 자료가 없습니다."));
}
function renderCaptureSummary(){
  const list=document.querySelector('[data-video-list="capture"]');
  if(!list)return;
  list.replaceChildren();
  const state=window.tcgCameraRuntime?.state?.();
  const values=[
    ["자동촬영",state?.active?"카메라 실행 중":"촬영 대기",state?.active?"ON":"대기"],
    ["앞면",state?.frontReady?"촬영 완료":"미촬영",state?.frontReady?"완료":"-"],
    ["뒷면",state?.backReady?"촬영 완료":"미촬영",state?.backReady?"완료":"-"],
  ];
  values.forEach((x,index)=>list.append(row(index+1,x[0],x[1],x[2])));
  const actions=el("div","video-ai-actions");
  const start=el("button","","📷 자동촬영 열기");
  start.type="button";start.addEventListener("click",()=>activateFeature("auto-grade"));
  const precision=el("button","","🔬 1→4→8 정밀");
  precision.type="button";precision.addEventListener("click",()=>activateFeature("precision-grade"));
  actions.append(start,precision);list.append(actions);
}
function installCapturePreflight(){
  const status=document.getElementById("cameraStatus");
  if(!status||document.getElementById("capturePreflightV403"))return;
  const box=el("section","capture-preflight-v403");
  box.id="capturePreflightV403";
  box.append(el("h4","","촬영 전 품질 확인"));
  const grid=el("div","capture-preflight-grid");
  const keys=[["exposure","노출"],["focus","초점"],["shake","흔들림"],["ready","촬영 준비"]];
  const chips={};
  keys.forEach(([key,label])=>{const c=el("div","capture-preflight-chip",label+" · 대기");c.dataset.preflight=key;chips[key]=c;grid.append(c)});
  const progress=el("div","capture-preflight-progress");progress.append(el("span"));
  const help=el("div","capture-preflight-help","카드를 가이드 안에 평평하게 두고 반사를 피하세요. 사선광은 정면 촬영 후 미세 스크래치 교차검증에 사용하세요.");
  box.append(grid,progress,help);
  status.insertAdjacentElement("afterend",box);
  const update=()=>{
    const text=status.textContent||"";
    const exposure=/노출 양호/.test(text),focus=/초점 양호/.test(text),shake=/흔들림 안정/.test(text);
    const p=Number((text.match(/자동촬영\s*(\d+)%/)||[])[1]||0);
    const values={
      exposure:["노출",exposure,text.includes("노출")],
      focus:["초점",focus,text.includes("초점")],
      shake:["흔들림",shake,text.includes("흔들림")],
      ready:["촬영 준비",exposure&&focus&&shake,text.includes("자동촬영")],
    };
    Object.entries(values).forEach(([key,[label,ok,seen]])=>{
      const c=chips[key];c.classList.toggle("ok",Boolean(ok));c.classList.toggle("warn",Boolean(seen&&!ok));
      c.textContent=label+" · "+(ok?"양호":seen?"조정":"대기");
    });
    const bar=progress.firstElementChild;if(bar)bar.style.width=Math.max(0,Math.min(100,p))+"%";
    renderCaptureSummary();
  };
  new MutationObserver(update).observe(status,{childList:true,subtree:true,characterData:true});
  update();
}
function haversine(a,b){
  const r=6371,toRad=v=>v*Math.PI/180,dLat=toRad(b.lat-a.lat),dLon=toRad(b.lon-a.lon);
  const q=Math.sin(dLat/2)**2+Math.cos(toRad(a.lat))*Math.cos(toRad(b.lat))*Math.sin(dLon/2)**2;
  return 2*r*Math.asin(Math.sqrt(q));
}
function recentRegions(){
  const rows=safeJson(REGION_KEY,[]);
  return Array.isArray(rows)?rows.filter(x=>typeof x==="string"&&x.trim()).slice(0,4):[];
}
function rememberRegion(value){
  const region=String(value||"").trim().slice(0,30);
  if(!region)return;
  saveJson(REGION_KEY,[region,...recentRegions().filter(x=>x!==region)].slice(0,4));
}
function purchaseSourceUrl(source){
  return String(source.url||source.url_template||source.stock_url||source.inventory_url||"").replace("{query}",encodeURIComponent(document.getElementById("purchaseQuery")?.value||"TCG"));
}
function setPurchaseArea(value){
  const input=document.getElementById("purchaseAreaText");
  if(input){input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}))}
  rememberRegion(value);
  renderRecentRegions();
  renderPurchaseMini();
}
function renderRecentRegions(){
  const wrap=document.getElementById("purchaseRecentRegionsV403");
  if(!wrap)return;
  wrap.replaceChildren();
  const values=recentRegions();
  if(!values.length){wrap.append(el("span","video-ai-note","최근지역 없음 · 지역명은 기기에만 저장됩니다."));return}
  values.forEach(value=>{const b=el("button","",value);b.type="button";b.addEventListener("click",()=>setPurchaseArea(value));wrap.append(b)});
}
function offlinePurchaseRows(){
  const text=(document.getElementById("purchaseAreaText")?.value||"").trim().toLowerCase();
  const category=document.getElementById("purchaseRetailerType")?.value||"ALL";
  const game=document.getElementById("purchaseGame")?.value||"Pokemon";
  let rows=purchaseRows.filter(x=>(x.channel||"online")==="offline");
  rows=rows.filter(x=>!Array.isArray(x.games)||x.games.includes(game));
  if(category!=="ALL")rows=rows.filter(x=>x.retailer_category===category);
  if(text)rows=rows.filter(x=>[x.name,x.address,x.note].some(v=>String(v||"").toLowerCase().includes(text)));
  return rows.map(x=>{
    const lat=num(x.lat),lon=num(x.lon);
    const distance=localLocation&&lat!==null&&lon!==null?haversine(localLocation,{lat,lon}):null;
    return {...x,_lat:lat,_lon:lon,_distance:distance};
  }).sort((a,b)=>(a._distance??999999)-(b._distance??999999)).slice(0,12);
}
function renderPurchaseMini(){
  const map=document.getElementById("purchaseMiniMapV403"),list=document.getElementById("purchaseMiniListV403");
  if(!map||!list)return;
  map.replaceChildren();list.replaceChildren();
  const rows=offlinePurchaseRows();
  const geo=rows.filter(x=>x._lat!==null&&x._lon!==null);
  if(!rows.length){
    list.append(el("div","video-ai-empty","선택 지역/게임에 등록된 오프라인 매장이 없습니다. 기존 구매처 목록에서 온라인 판매처도 함께 확인하세요."));
    return;
  }
  const coords=geo.concat(localLocation?[{_lat:localLocation.lat,_lon:localLocation.lon,_current:true}]:[]);
  if(coords.length){
    const lats=coords.map(x=>x._lat),lons=coords.map(x=>x._lon);
    let minLat=Math.min(...lats),maxLat=Math.max(...lats),minLon=Math.min(...lons),maxLon=Math.max(...lons);
    if(maxLat-minLat<.01){minLat-=.005;maxLat+=.005}
    if(maxLon-minLon<.01){minLon-=.005;maxLon+=.005}
    coords.forEach((x,index)=>{
      const left=8+84*(x._lon-minLon)/(maxLon-minLon),top=92-84*(x._lat-minLat)/(maxLat-minLat);
      const pin=el("button","purchase-mini-pin"+(x._current?" current":""),x._current?"":String(index+1));
      pin.type="button";pin.style.left=left+"%";pin.style.top=top+"%";
      if(!x._current){
        pin.title=x.name||"매장";
        pin.addEventListener("click",()=>document.querySelector('[data-mini-store="'+index+'"]')?.scrollIntoView({block:"nearest"}));
      }
      map.append(pin);
    });
  }else{
    map.append(el("div","video-ai-empty","등록 좌표가 있는 매장이 없어 목록만 표시합니다."));
  }
  rows.forEach((x,index)=>{
    const b=el("button","purchase-mini-row");
    b.type="button";b.dataset.miniStore=String(index);
    const title=el("b","",String(index+1)+". "+(x.name||"매장"));
    const meta=[x.address,x._distance!==null?"약 "+x._distance.toFixed(1)+" km":null,x.inventory_status||"재고 미확인"].filter(Boolean).join(" · ");
    b.append(title,el("small","",meta));
    b.addEventListener("click",()=>{
      const url=purchaseSourceUrl(x);
      if(/^https:\/\//.test(url))window.open(url,"_blank","noopener,noreferrer");
    });
    list.append(b);
  });
}
async function useCurrentLocation(){
  const status=document.getElementById("purchaseLocationStatus");
  if(!navigator.geolocation){if(status)status.textContent="이 브라우저에서는 위치 기능을 사용할 수 없습니다.";return}
  if(status)status.textContent="📍 현재 위치 확인 중…";
  navigator.geolocation.getCurrentPosition(
    pos=>{
      localLocation={lat:pos.coords.latitude,lon:pos.coords.longitude};
      if(status)status.textContent="📍 현재 위치 사용 중 · 위치 좌표는 저장하지 않습니다.";
      const sort=document.getElementById("purchaseSort");if(sort){sort.value="nearby";sort.dispatchEvent(new Event("change",{bubbles:true}))}
      renderPurchaseMini();
    },
    ()=>{if(status)status.textContent="📍 위치 권한을 사용할 수 없습니다. 지역명을 직접 입력하세요.";},
    {enableHighAccuracy:false,timeout:8000,maximumAge:300000}
  );
}
function installPurchaseWorkspace(){
  const panel=document.getElementById("purchasePanel");
  const status=document.getElementById("purchaseLocationStatus");
  if(!panel||!status||document.getElementById("purchaseVideoWorkspaceV403"))return;
  const box=el("section","purchase-video-workspace");box.id="purchaseVideoWorkspaceV403";
  const toolbar=el("div","purchase-video-toolbar");
  const province=el("select");province.id="purchaseProvinceV403";province.setAttribute("aria-label","빠른 시도 선택");
  province.append(new Option("시·도 빠른 선택",""));
  PROVINCES.forEach(x=>province.append(new Option(x,x)));
  const city=el("input");city.id="purchaseCityV403";city.placeholder="시·군·구 또는 동 검색";city.setAttribute("aria-label","지역 검색");
  const apply=el("button","","지역 적용");apply.type="button";
  const current=el("button","","📍 현재 위치");current.type="button";
  toolbar.append(province,city,apply,current);
  const recent=el("div","purchase-recent-regions");recent.id="purchaseRecentRegionsV403";
  const split=el("div","purchase-split-v403");
  const map=el("div","purchase-mini-map");map.id="purchaseMiniMapV403";
  const list=el("div","purchase-mini-list");list.id="purchaseMiniListV403";
  split.append(map,list);
  box.append(toolbar,recent,split);
  status.insertAdjacentElement("afterend",box);
  apply.addEventListener("click",()=>setPurchaseArea([province.value,city.value.trim()].filter(Boolean).join(" ")));
  city.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();apply.click()}});
  current.addEventListener("click",useCurrentLocation);
  [document.getElementById("purchaseGame"),document.getElementById("purchaseRetailerType")].forEach(x=>x?.addEventListener("change",renderPurchaseMini));
  renderRecentRegions();renderPurchaseMini();
}
function portfolioRows(){
  const rows=safeJson(PORTFOLIO_KEY,[]);
  return Array.isArray(rows)?rows.filter(x=>x&&typeof x==="object").slice(0,80):[];
}
function krw(value){
  const n=num(value);
  return n===null?"-":Math.round(n).toLocaleString("ko-KR")+"원";
}
function currentIdentity(){
  const name=document.getElementById("identityCardName")?.value||document.getElementById("agmName")?.textContent||"";
  const number=document.getElementById("identityCardNumber")?.value||document.getElementById("agmNumber")?.textContent||"";
  const grade=window.tcgLastGrades?.PSA;
  return {name:[name,number].filter(Boolean).join(" ").trim(),grade:num(grade)};
}
function mountPortfolio(){
  if(document.getElementById("videoPortfolioV403"))return;
  const home=document.getElementById("videoAiHomeV403");
  if(!home||!home.parentNode)return;
  const box=el("section","video-portfolio-v403");box.id="videoPortfolioV403";
  const head=el("div","video-portfolio-head");
  const h=el("div");h.append(el("h2","","🗂️ 내 카드 포트폴리오"),el("p","","기기 로컬에만 저장합니다. 현재가와 예상가는 자동으로 지어내지 않고 직접 입력한 값만 합산합니다."));
  const fill=el("button","","현재 분석 불러오기");fill.type="button";fill.style.width="auto";fill.style.margin="0";fill.style.padding="8px";fill.style.fontSize="10px";
  head.append(h,fill);
  const summary=el("div","video-portfolio-summary");summary.id="videoPortfolioSummaryV403";
  const form=el("form","video-portfolio-form");
  const name=el("input");name.placeholder="카드명·번호";name.required=true;name.maxLength=120;
  const qty=el("input");qty.type="number";qty.min="1";qty.max="999";qty.value="1";qty.placeholder="수량";
  const buy=el("input");buy.type="number";buy.min="0";buy.step="1";buy.placeholder="1장 보유원가(원)";
  const current=el("input");current.type="number";current.min="0";current.step="1";current.placeholder="1장 현재가(원)";
  const add=el("button","","추가");add.type="submit";
  form.append(name,qty,buy,current,add);
  const list=el("div","video-portfolio-list");list.id="videoPortfolioListV403";
  const disclaimer=el("div","video-portfolio-disclaimer","현재가/원가는 사용자가 확인해 입력한 값입니다. PSA 등급 예상치는 참고정보이며 포트폴리오 현재가로 자동 환산하지 않습니다.");
  box.append(head,summary,form,list,disclaimer);
  home.insertAdjacentElement("afterend",box);
  fill.addEventListener("click",()=>{
    const identity=currentIdentity();
    if(identity.name)name.value=identity.name;
    if(identity.grade!==null)name.value=(name.value?name.value+" · ":"")+"PSA 예상 "+identity.grade;
  });
  form.addEventListener("submit",event=>{
    event.preventDefault();
    const n=name.value.trim(),q=Math.max(1,Math.round(num(qty.value)||1)),b=Math.max(0,num(buy.value)||0),c=Math.max(0,num(current.value)||0);
    if(!n)return;
    const rows=portfolioRows();
    rows.unshift({id:Date.now(),name:n,qty:q,buy:b,current:c,added_at:new Date().toISOString()});
    saveJson(PORTFOLIO_KEY,rows.slice(0,80));
    name.value="";qty.value="1";buy.value="";current.value="";
    renderPortfolio();
  });
  renderPortfolio();
}
function renderPortfolio(){
  const summary=document.getElementById("videoPortfolioSummaryV403"),list=document.getElementById("videoPortfolioListV403");
  if(!summary||!list)return;
  const rows=portfolioRows();
  const invested=rows.reduce((s,x)=>s+(num(x.buy)||0)*(num(x.qty)||1),0);
  const current=rows.reduce((s,x)=>s+(num(x.current)||0)*(num(x.qty)||1),0);
  const profit=current-invested;
  const rate=invested>0?profit/invested*100:null;
  summary.replaceChildren();
  [["보유 종류",rows.length+"종"],["보유원가",krw(invested)],["입력 현재가",krw(current)],["손익",krw(profit)+(rate===null?"":" · "+rate.toFixed(1)+"%")]].forEach(([k,v])=>{
    const m=el("div","video-portfolio-metric");m.append(el("small","",k),el("b","",v));summary.append(m);
  });
  list.replaceChildren();
  rows.slice(0,12).forEach(x=>{
    const item=el("div","video-portfolio-row");
    const main=el("span");main.append(el("b","",x.name),el("small","",x.qty+"장 · 원가 "+krw(x.buy)+" · 현재가 "+krw(x.current)));
    const p=((num(x.current)||0)-(num(x.buy)||0))*(num(x.qty)||1);
    const strong=el("strong","",krw(p));
    const del=el("button","","삭제");del.type="button";del.addEventListener("click",()=>{saveJson(PORTFOLIO_KEY,portfolioRows().filter(r=>r.id!==x.id));renderPortfolio()});
    item.append(main,strong,del);list.append(item);
  });
  if(!rows.length)list.append(el("div","video-ai-empty","보유카드가 없습니다. 카드명·수량·확인한 가격을 입력해 로컬 포트폴리오를 시작하세요."));
}
function renderPurchaseHome(){
  const list=document.querySelector('[data-video-list="purchase"]');
  if(!list)return;
  list.replaceChildren();
  const rows=offlinePurchaseRows();
  rows.slice(0,3).forEach((x,index)=>list.append(row(index+1,x.name||"매장",x.address||x.note||"오프라인 구매처",x._distance!==null?x._distance.toFixed(1)+"km":"재고 확인")));
  if(!list.children.length)list.append(el("div","video-ai-empty","현재 위치 또는 지역을 선택하면 오프라인 구매처를 빠르게 비교할 수 있습니다."));
  const actions=el("div","video-ai-actions");
  const open=el("button","","📍 구매처 화면");open.type="button";open.addEventListener("click",()=>activateFeature("purchase-distance"));
  const ansan=el("button","","🏠 안산 기준");ansan.type="button";ansan.addEventListener("click",()=>{activateFeature("purchase-distance");setTimeout(()=>document.getElementById("purchaseUseAnsan")?.click(),150)});
  actions.append(open,ansan);list.append(actions);
}
async function loadData(){
  const [report,watch,prices,releases,promos,purchases]=await Promise.all([
    getJson(REPORT_URL),getJson(DATA_URLS.marketWatch),getJson(DATA_URLS.marketPrices),
    getJson(DATA_URLS.releases),getJson(DATA_URLS.promos),getJson(DATA_URLS.purchases),
  ]);
  lastReport=report||lastReport;
  purchaseRows=Array.isArray(purchases?.sources)?purchases.sources:[];
  renderMarket(watch,prices);renderRelease(releases,promos);
  reorderHome(lastReport||{});renderCaptureSummary();renderPurchaseMini();renderPurchaseHome();
}
function start(){
  if(!mountHome())return;
  mountPortfolio();
  installCapturePreflight();
  installPurchaseWorkspace();
  loadData();
  window.setInterval(loadData,120000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)loadData()});
  window.TCGVideoInformedTabletUIV403=Object.freeze({
    version:VERSION,
    refresh:loadData,
    renderPurchaseMini,
    renderPortfolio,
    privacy:Object.freeze({precise_location_persisted:false,portfolio_local_only:true,user_behavior_tracking:false}),
  });
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
