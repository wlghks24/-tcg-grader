"use strict";
(() => {
  const VERSION = "v403-video-market-home";
  const URLS = Object.freeze({
    report: "./tablet_autonomy_v400_report.json",
    prices: "./market_prices.json",
    watch: "./market_watch.json",
    purchases: "./purchase_sources.json"
  });
  const ANSAN = Object.freeze({lat:37.3219,lon:126.8309,label:"안산 기준"});
  const GAME_VALUES = Object.freeze([
    ["ALL","전체"],["Pokémon","포켓몬"],["ONE PIECE","원피스"],["NARUTO","나루토"]
  ]);
  const HOME_MODULES = Object.freeze(["market","box","top","nearby"]);
  const REFRESH_MIN_MS = 45000;
  const state = {
    game:"ALL",report:null,prices:null,watch:null,purchases:null,aiOrder:true,
    originalModuleOrder:[...HOME_MODULES],lastLoadAt:0,loading:null
  };

  const byId = (id) => document.getElementById(id);
  const clean = (value) => String(value == null ? "" : value).trim();

  function node(tag,className,value){
    const n=document.createElement(tag);
    if(className)n.className=className;
    if(value!==undefined&&value!==null)n.textContent=String(value);
    return n;
  }
  function btn(label,className){
    const n=node("button",className||"",label);
    n.type="button";
    return n;
  }
  function clear(n){while(n&&n.firstChild)n.removeChild(n.firstChild);}
  function badge(value,extra){return node("span","tmh-badge"+(extra?" "+extra:""),value);}

  function scrollToId(id){
    const target=byId(id);
    if(!target)return false;
    try{
      const reduced=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target.scrollIntoView({behavior:reduced?"auto":"smooth",block:"start"});
    }catch(_){target.scrollIntoView&&target.scrollIntoView();}
    return true;
  }

  function activatePurchasePanel(){
    try{
      if(window.TCGFeatureCategoryNav&&window.TCGFeatureCategoryNav.activateTopPanel&&
         window.TCGFeatureCategoryNav.activateTopPanel("purchasePanel"))return true;
    }catch(_){}
    const tab=[...document.querySelectorAll(".top-info-tab")]
      .find((item)=>item&&item.dataset&&item.dataset.topPanel==="purchasePanel");
    if(tab&&typeof tab.click==="function")tab.click();
    return Boolean(tab);
  }

  function openFeatureSearch(value){
    const input=byId("featureQuickSearch");
    scrollToId("featureCategories");
    if(!input)return;
    input.value=value;
    try{
      if(window.TCGAppShellV272&&window.TCGAppShellV272.filterFeatures){
        window.TCGAppShellV272.filterFeatures(value);
      }
    }catch(_){}
    setTimeout(()=>input.focus&&input.focus(),100);
  }

  function setMarketQuery(query,region,asset){
    const q=byId("query12"),r=byId("market12"),a=byId("asset12"),g=byId("v12Game");
    if(q)q.value=query;
    if(r&&[...r.options].some((o)=>o.value===(region||"ALL")))r.value=region||"ALL";
    if(a&&[...a.options].some((o)=>o.value===(asset||"ALL")))a.value=asset||"ALL";
    if(g&&[...g.options].some((o)=>o.value===state.game))g.value=state.game;
    scrollToId("market12section");
    setTimeout(()=>{const s=byId("search12");if(s&&typeof s.click==="function")s.click();},100);
  }

  function formatDate(value){
    const stamp=Date.parse(clean(value));
    if(!Number.isFinite(stamp))return clean(value)||"날짜 미확인";
    try{return new Intl.DateTimeFormat("ko-KR",{year:"2-digit",month:"2-digit",day:"2-digit"}).format(stamp);}
    catch(_){return clean(value).slice(0,10)||"날짜 미확인";}
  }
  function freshnessDays(value){
    const stamp=Date.parse(clean(value));
    if(!Number.isFinite(stamp))return 99999;
    return Math.max(0,(Date.now()-stamp)/86400000);
  }
  function gameMatches(blob){
    if(state.game==="ALL")return true;
    const value=clean(blob).toLocaleLowerCase("ko-KR");
    const aliases=state.game==="Pokémon"?["pokemon","pokémon","포켓몬"]:
      state.game==="ONE PIECE"?["one piece","원피스"]:["naruto","나루토"];
    return aliases.some((alias)=>value.includes(alias));
  }

  function parsePriceRows(asset){
    const entries=state.prices&&state.prices.entries;
    if(!entries||typeof entries!=="object"||Array.isArray(entries))return [];
    const rows=[];
    for(const pair of Object.entries(entries)){
      const key=pair[0],value=pair[1];
      if(!value||typeof value!=="object")continue;
      const parts=key.split("|");
      const region=parts[0]||"",name=parts[1]||"",rowAsset=parts[2]||"";
      if(asset!=="ALL"&&rowAsset!==asset)continue;
      if(!gameMatches([key,value.market,value.kind,value.transactions].join(" ")))continue;
      rows.push({
        key:key,region:region,name:name,asset:rowAsset,
        display:clean(value.display)||"가격 미확인",
        market:clean(value.market)||"출처 확인",
        kind:clean(value.kind)||"가격 근거",
        sourceDate:clean(value.source_date)
      });
    }
    rows.sort((x,y)=>{
      const date=freshnessDays(x.sourceDate)-freshnessDays(y.sourceDate);
      if(date)return date;
      const xa=/거래|중앙값|completed/i.test(x.kind)?1:0;
      const ya=/거래|중앙값|completed/i.test(y.kind)?1:0;
      return ya-xa||x.name.localeCompare(y.name,"ko");
    });
    return rows;
  }

  function marketWatchRows(){
    const rows=Array.isArray(state.watch&&state.watch.items)?state.watch.items:[];
    const score=(row)=>{
      let s=0;
      if(/거래중/.test(clean(row.sale_status)))s+=4;
      if(/정상/.test(clean(row.link_status)))s+=2;
      const age=freshnessDays(row.release_date);
      if(age<=45)s+=3;else if(age<=180)s+=2;else if(age<=365)s+=1;
      if(clean(row.release_type).includes("재발매"))s+=1;
      return s;
    };
    return rows.filter((row)=>{
      if(!row||typeof row!=="object")return false;
      if(!gameMatches([row.game,row.name,row.native].join(" ")))return false;
      return /거래|판매/.test(clean(row.sale_status));
    }).sort((x,y)=>score(y)-score(x)||clean(y.release_date).localeCompare(clean(x.release_date))).slice(0,10);
  }

  function haversine(a,b){
    const rad=Math.PI/180,lat1=a.lat*rad,lat2=b.lat*rad;
    const dlat=(b.lat-a.lat)*rad,dlon=(b.lon-a.lon)*rad;
    const h=Math.sin(dlat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dlon/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));
  }

  function nearbyRows(){
    const rows=Array.isArray(state.purchases&&state.purchases.sources)?state.purchases.sources:[];
    const expectedGame=state.game==="Pokémon"?"Pokemon":state.game;
    return rows.filter((row)=>row&&row.region==="KR"&&row.channel==="offline")
      .filter((row)=>state.game==="ALL"||(Array.isArray(row.games)&&row.games.includes(expectedGame)))
      .map((row)=>{
        const lat=Number(row.lat),lon=Number(row.lon);
        const distance=Number.isFinite(lat)&&Number.isFinite(lon)?haversine(ANSAN,{lat:lat,lon:lon}):null;
        return Object.assign({},row,{distance:distance});
      })
      .filter((row)=>row.distance!==null||/안산|경기/.test([row.address,row.note,row.name].join(" ")))
      .sort((x,y)=>(x.distance==null?99999:x.distance)-(y.distance==null?99999:y.distance))
      .slice(0,6);
  }

  function priceCard(row){
    const card=btn("","tmh-market-card");
    const top=node("div","tmh-card-top");
    top.append(badge(row.region||"—","region-"+clean(row.region).toLowerCase()),badge(row.asset||"시세"));
    card.append(top,node("strong","tmh-market-title",row.name||"이름 미확인"),
      node("b","tmh-market-price",row.display),
      node("small","tmh-market-meta",row.market+" · "+formatDate(row.sourceDate)+" · "+row.kind));
    card.addEventListener("click",()=>setMarketQuery(row.name,row.region||"ALL",row.asset||"ALL"));
    return card;
  }

  function renderPriceModule(id,asset,limit){
    const list=byId(id);if(!list)return;clear(list);
    const rows=parsePriceRows(asset).slice(0,limit);
    if(!rows.length){list.append(node("div","tmh-empty","검증된 저장 시세가 없습니다. 업데이트 후 다시 확인하세요."));return;}
    rows.forEach((row)=>list.append(priceCard(row)));
  }

  function renderTop(){
    const list=byId("tmhTopList");if(!list)return;clear(list);
    const rows=marketWatchRows();
    if(!rows.length){list.append(node("div","tmh-empty","거래·판매 상태가 확인된 항목이 없습니다."));return;}
    rows.forEach((row,index)=>{
      const item=btn("","tmh-rank-row");
      item.append(node("b","tmh-rank-number",String(index+1)));
      const body=node("span","tmh-rank-body");
      body.append(node("strong","",clean(row.name)||clean(row.native)||"이름 미확인"));
      body.append(node("small","",(clean(row.region)||"지역 미확인")+" · "+(clean(row.asset)||"상품")+" · "+
        (clean(row.sale_status)||"상태 미확인")+" · "+(clean(row.official_price)||"정가 미확인")));
      item.append(body,badge(clean(row.release_type)||"시장 확인"));
      item.addEventListener("click",()=>setMarketQuery(clean(row.name)||clean(row.native),clean(row.region)||"ALL",clean(row.asset)||"ALL"));
      list.append(item);
    });
  }

  function openPurchaseArea(area){
    activatePurchasePanel();scrollToId("releaseBoard");
    setTimeout(()=>{
      const areaInput=byId("purchaseAreaText"),sort=byId("purchaseSort"),preset=byId("purchaseAreaPreset");
      if(areaInput)areaInput.value=area;
      if(preset&&[...preset.options].some((o)=>o.value===area))preset.value=area;
      if(sort)sort.value="nearby";
      const offline=document.querySelector('[data-purchase-channel="offline"]');
      if(offline&&typeof offline.click==="function")offline.click();
      if(areaInput)areaInput.dispatchEvent(new Event("input",{bubbles:true}));
    },90);
  }

  function renderNearby(){
    const list=byId("tmhNearbyList");if(!list)return;clear(list);
    const rows=nearbyRows();
    if(!rows.length){list.append(node("div","tmh-empty","안산·경기 기준 좌표/주소가 확인된 오프라인 매장이 없습니다."));return;}
    rows.forEach((row)=>{
      const item=btn("","tmh-nearby-card");
      item.append(badge(clean(row.retailer_category)||"매장"));
      const body=node("span","tmh-nearby-body");
      body.append(node("strong","",clean(row.name)||"매장"));
      body.append(node("small","",(row.distance==null?"경기권":"약 "+row.distance.toFixed(1)+" km")+" · "+(clean(row.address)||"주소 확인 필요")));
      item.append(body);
      item.addEventListener("click",()=>openPurchaseArea(/안산/.test(clean(row.address))?"안산":"경기"));
      list.append(item);
    });
  }

  function priorityMap(){
    const order={market:100,box:101,top:102,nearby:103};
    const top=state.report&&state.report.v400_adaptive_layout&&
      state.report.v400_adaptive_layout.screen_module_plan&&
      state.report.v400_adaptive_layout.screen_module_plan.top_features;
    if(Array.isArray(top)){
      top.forEach((feature,index)=>{
        let key=null;
        if(/market|economics|trading/.test(feature))key="market";
        else if(/box/.test(feature))key="box";
        else if(/purchase/.test(feature))key="nearby";
        else if(/release|promo/.test(feature))key="top";
        if(key)order[key]=Math.min(order[key],index);
      });
    }
    return order;
  }

  function applyAiOrder(){
    const container=byId("tmhModuleGrid");if(!container)return;
    const modules=[...container.querySelectorAll("[data-tmh-module]")];
    if(!state.aiOrder){
      state.originalModuleOrder.forEach((key)=>{
        const found=modules.find((item)=>item.dataset.tmhModule===key);
        if(found)container.append(found);
      });
      return;
    }
    const priorities=priorityMap();
    modules.sort((x,y)=>(priorities[x.dataset.tmhModule]||999)-(priorities[y.dataset.tmhModule]||999));
    modules.forEach((item,index)=>{item.dataset.aiHomeRank=String(index+1);container.append(item);});
  }

  function renderStatus(){
    const status=byId("tmhAiStatus");if(!status)return;
    const activity=state.report&&state.report.v400_adaptive_layout&&state.report.v400_adaptive_layout.market_activity;
    const parts=[
      state.aiOrder?"AI 홈 정렬 켜짐":"기본 순서",
      "시세 "+Object.keys((state.prices&&state.prices.entries)||{}).length+"건",
      "시장관찰 "+(Array.isArray(state.watch&&state.watch.items)?state.watch.items.length:0)+"건",
      "구매처 "+(Array.isArray(state.purchases&&state.purchases.sources)?state.purchases.sources.length:0)+"곳"
    ];
    if(activity&&typeof activity==="object"){
      parts.push("출시 "+Number(activity.release_count||0)+" · 행사 "+Number(activity.event_count||0)+" · 거래 "+Number(activity.market_count||0));
    }
    status.textContent=parts.join(" · ");
  }

  function renderAll(){
    renderPriceModule("tmhMarketList","HIT",8);
    renderPriceModule("tmhBoxList","BOX",8);
    renderTop();renderNearby();applyAiOrder();renderStatus();
  }

  async function fetchJson(url){
    const response=await fetch(url+"?t="+Date.now(),{cache:"no-store",headers:{Accept:"application/json"}});
    if(!response.ok)throw new Error("HTTP "+response.status);
    return response.json();
  }

  async function loadData(force){
    const now=Date.now();
    if(!force&&state.lastLoadAt&&now-state.lastLoadAt<REFRESH_MIN_MS){renderAll();return true;}
    if(state.loading)return state.loading;
    state.loading=(async()=>{
      const rows=await Promise.allSettled([
        fetchJson(URLS.prices),fetchJson(URLS.watch),fetchJson(URLS.purchases),fetchJson(URLS.report)
      ]);
      if(rows[0].status==="fulfilled")state.prices=rows[0].value;
      if(rows[1].status==="fulfilled")state.watch=rows[1].value;
      if(rows[2].status==="fulfilled")state.purchases=rows[2].value;
      if(rows[3].status==="fulfilled")state.report=rows[3].value;
      if(rows.some((row)=>row.status==="fulfilled"))state.lastLoadAt=Date.now();
      renderAll();
      return rows.every((row)=>row.status==="fulfilled");
    })();
    try{return await state.loading;}finally{state.loading=null;}
  }

  function hideCameraPermission(){const overlay=byId("tmhCameraPermission");if(overlay)overlay.hidden=true;}
  function showCameraPermission(){
    const overlay=byId("tmhCameraPermission");if(!overlay)return;
    overlay.hidden=false;
    const confirm=overlay.querySelector("[data-tmh-camera-confirm]");
    if(confirm&&confirm.focus)confirm.focus();
  }
  function confirmCameraPermission(){
    hideCameraPermission();scrollToId("simpleGradeV32");
    setTimeout(()=>{const start=byId("startAutoCamera");if(start&&typeof start.click==="function")start.click();},140);
  }

  function createModule(key,title,subtitle,listId,listClass){
    const section=node("section","tmh-module");section.dataset.tmhModule=key;
    const head=node("div","tmh-module-head"),words=node("div","");
    words.append(node("h3","",title),node("p","",subtitle));head.append(words);
    const list=node("div",listClass);list.id=listId;list.append(node("div","tmh-empty","자료를 불러오는 중입니다."));
    section.append(head,list);return section;
  }

  function buildHome(){
    if(byId("tabletMarketHomeV403"))return false;
    const nav=byId("featureCategories");if(!nav)return false;
    const home=node("section","tablet-market-home");home.id="tabletMarketHomeV403";home.dataset.version=VERSION;
    home.setAttribute("aria-labelledby","tmhTitle");

    const head=node("div","tmh-head"),words=node("div","");
    words.append(node("span","tmh-kicker","AI MARKET HOME · VERIFIED DATA"));
    const title=node("h2","","태블릿 AI 카드 홈");title.id="tmhTitle";
    words.append(title,node("p","","카드 검색·촬영·시세·BOX·구매처를 한 화면에서 확인하고 AI가 검증된 시장활동과 기능 우선순위로 모듈 순서를 조정합니다."));
    const aiToggle=btn("AI 홈 정렬","tmh-ai-toggle");aiToggle.setAttribute("aria-pressed","true");
    aiToggle.addEventListener("click",()=>{
      state.aiOrder=!state.aiOrder;
      aiToggle.setAttribute("aria-pressed",state.aiOrder?"true":"false");
      aiToggle.textContent=state.aiOrder?"AI 홈 정렬":"기본 순서";
      try{localStorage.setItem("tcgMarketHomeAiV403",state.aiOrder?"1":"0");}catch(_){}
      applyAiOrder();renderStatus();
    });
    head.append(words,aiToggle);

    const search=node("form","tmh-search");search.setAttribute("role","search");
    const input=node("input","tmh-search-input");input.id="tmhSearchInput";input.type="search";
    input.autocomplete="off";input.placeholder="카드명 · 카드번호 · BOX · 세트명 검색";input.setAttribute("aria-label","카드·BOX 시세 검색");
    const scan=btn("📷","tmh-scan");scan.setAttribute("aria-label","카메라로 카드 촬영");
    const submit=btn("검색","tmh-search-submit");submit.type="submit";
    const feature=btn("기능 찾기","tmh-feature-search");
    search.append(input,scan,submit,feature);
    search.addEventListener("submit",(event)=>{event.preventDefault();const q=clean(input.value);if(!q){input.focus();return;}setMarketQuery(q,"ALL","ALL");});
    scan.addEventListener("click",showCameraPermission);
    feature.addEventListener("click",()=>openFeatureSearch(clean(input.value)));

    const games=node("div","tmh-game-chips");
    GAME_VALUES.forEach((pair)=>{
      const chip=btn(pair[1],pair[0]==="ALL"?"active":"");chip.dataset.tmhGame=pair[0];
      chip.addEventListener("click",()=>{state.game=pair[0];games.querySelectorAll("button").forEach((x)=>x.classList.toggle("active",x===chip));renderAll();});
      games.append(chip);
    });

    const actions=node("div","tmh-actions");
    [
      ["📷","카드 등급 측정","촬영→OCR→1·4·8 정밀검증","grade"],
      ["💰","시세 확인","한국·일본·미국 교차가격","market"],
      ["📅","출시·프로모","재발매·행사·콜라보","release"],
      ["📍","구매처·거리","안산 기준·현재위치·오프라인","purchase"]
    ].forEach((row)=>{
      const action=btn("","tmh-action");action.dataset.tmhAction=row[3];
      action.append(node("span","tmh-action-icon",row[0]));
      const body=node("span","tmh-action-body");body.append(node("b","",row[1]),node("small","",row[2]));action.append(body);
      action.addEventListener("click",()=>{
        if(row[3]==="grade")scrollToId("simpleGradeV32");
        if(row[3]==="market")scrollToId("market12section");
        if(row[3]==="release")scrollToId("releaseBoard");
        if(row[3]==="purchase"){activatePurchasePanel();scrollToId("releaseBoard");}
      });
      actions.append(action);
    });

    const region=node("div","tmh-region-row");region.append(node("strong","","오프라인 지역"));
    ["안산","경기","서울","인천","부산","대구","대전","광주","울산","충북","충남","전북","전남","경북","경남","제주"].forEach((name)=>{
      const chip=btn(name,"tmh-region-chip");chip.addEventListener("click",()=>openPurchaseArea(name));region.append(chip);
    });

    const modules=node("div","tmh-module-grid");modules.id="tmhModuleGrid";
    modules.append(
      createModule("market","🔥 최근 카드 시세","검증된 저장 가격을 최신 확인일 우선으로 표시","tmhMarketList","tmh-scroll"),
      createModule("box","📦 BOX 시세","검증된 BOX 가격·시장·확인일을 빠르게 비교","tmhBoxList","tmh-scroll"),
      createModule("top","📈 시장 주목 TOP 10","거래상태·출시 최근성·출처상태 기준이며 인기·상승을 임의 추정하지 않음","tmhTopList","tmh-rank-list"),
      createModule("nearby","📍 안산·경기 오프라인 구매처","저장된 좌표·주소 기반 직선거리 참고 · 실제 재고는 매장 확인","tmhNearbyList","tmh-nearby-list")
    );

    const status=node("div","tmh-ai-status","시장 홈 자료를 불러오는 중입니다.");status.id="tmhAiStatus";
    status.setAttribute("role","status");status.setAttribute("aria-live","polite");

    const overlay=node("div","tmh-camera-permission");overlay.id="tmhCameraPermission";overlay.hidden=true;
    const dialog=node("div","tmh-camera-dialog");dialog.setAttribute("role","dialog");dialog.setAttribute("aria-modal","true");dialog.setAttribute("aria-labelledby","tmhCameraTitle");
    const dialogTitle=node("h3","","카드 촬영을 위해 카메라 권한이 필요합니다");dialogTitle.id="tmhCameraTitle";
    dialog.append(dialogTitle,node("p","","허용하면 카드 앞·뒷면 자동촬영 화면으로 이동합니다. 브라우저 권한창에서 카메라를 허용해 주세요."));
    const dialogActions=node("div","tmh-camera-actions"),confirm=btn("카메라 열기","primary"),cancel=btn("취소","");
    confirm.dataset.tmhCameraConfirm="1";confirm.addEventListener("click",confirmCameraPermission);cancel.addEventListener("click",hideCameraPermission);
    dialogActions.append(confirm,cancel);dialog.append(dialogActions);overlay.append(dialog);

    home.append(head,search,games,actions,region,modules,status,overlay);
    nav.parentNode&&nav.parentNode.insertBefore(home,nav);
    try{state.aiOrder=localStorage.getItem("tcgMarketHomeAiV403")!=="0";}catch(_){}
    aiToggle.setAttribute("aria-pressed",state.aiOrder?"true":"false");aiToggle.textContent=state.aiOrder?"AI 홈 정렬":"기본 순서";
    return true;
  }

  if(!buildHome())return;
  loadData(true);
  window.addEventListener("focus",()=>loadData(false));
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")loadData(false);});
  window.TCGTabletMarketHomeV403=Object.freeze({
    version:VERSION,refresh:()=>loadData(true),
    setGame:(value)=>{if(GAME_VALUES.some((pair)=>pair[0]===value)){state.game=value;renderAll();return true;}return false;},
    openPurchaseArea:openPurchaseArea
  });
})();
