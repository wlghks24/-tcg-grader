/* V646: tablet 30-TCG event search and source-consolidated provenance UI.
 * Local JSON only; external buttons open user-initiated Google/Bing/X search.
 * No login, scraping, paid APIs, auto-entry, or misleading official approval.
 */
(function(root,factory){
 "use strict";
 const api=factory();
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 if(root&&root.document){
  root.TcgEventIntelligenceV646=api;
  const run=()=>api.mount(root.document);
  if(root.document.readyState==="loading")
   root.document.addEventListener("DOMContentLoaded",run,{once:true});
  else run();
 }
})(typeof globalThis!=="undefined"?globalThis:this,function(){
 "use strict";
 const TYPES=["EVENT","PROMO","TOURNAMENT","COLLAB","MOVIE","GIVEAWAY","GIFT",
              "LOTTERY","POPUP","FESTIVAL","PRERELEASE"];
 const NAMES={PROMO:"프로모 카드",EVENT:"공식 이벤트",TOURNAMENT:"대회·참가상",
 COLLAB:"콜라보",MOVIE:"영화·극장판",GIVEAWAY:"경품·증정",GIFT:"사은품·특전",
 LOTTERY:"추첨·응모",POPUP:"팝업",FESTIVAL:"축제·박람회",PRERELEASE:"선행체험"};
 const PHRASES={
 KR:{PROMO:"프로모 카드",EVENT:"이벤트",TOURNAMENT:"대회 참가상",COLLAB:"콜라보",
 MOVIE:"영화 극장판",GIVEAWAY:"경품 증정",GIFT:"사은품 특전",LOTTERY:"추첨 응모",
 POPUP:"팝업스토어",FESTIVAL:"페스티벌",PRERELEASE:"프리릴리즈"},
 JP:{PROMO:"プロモカード",EVENT:"イベント",TOURNAMENT:"大会 参加賞",COLLAB:"コラボ",
 MOVIE:"映画 劇場版",GIVEAWAY:"プレゼント 景品",GIFT:"購入特典",LOTTERY:"抽選 応募",
 POPUP:"ポップアップ",FESTIVAL:"フェス",PRERELEASE:"プレリリース"},
 US:{PROMO:"promo card",EVENT:"event",TOURNAMENT:"tournament prize",COLLAB:"collaboration",
 MOVIE:"movie film promo",GIVEAWAY:"giveaway sweepstakes",GIFT:"gift bonus",
 LOTTERY:"lottery raffle",POPUP:"pop-up",FESTIVAL:"convention",PRERELEASE:"prerelease"}
 };
 const clean=(x)=>String(x||"").normalize("NFKC").toLocaleLowerCase()
  .replace(/[^\p{L}\p{N}]/gu,"");
 function safeUrl(value){
  if(typeof value!=="string"||value.length>900)return null;
  try{
   const u=new URL(value);
   if(u.protocol!=="https:"||u.username||u.password||
      (u.port&&u.port!=="443")||u.hostname==="localhost"||
      /^\d+\.\d+\.\d+\.\d+$/.test(u.hostname)||
      /\.(local|test|invalid)$/.test(u.hostname))return null;
   return u;
  }catch(_){return null;}
 }
 function canonical(value){
  const u=safeUrl(value);if(!u)return null;
  ["utm_source","utm_medium","utm_campaign","utm_content","utm_term",
   "gclid","fbclid","igshid","mc_cid","mc_eid","ref_src","si","yclid"].forEach(x=>u.searchParams.delete(x));
  for(const k of [...u.searchParams.keys()]){
   if(k.toLowerCase().startsWith("utm_"))u.searchParams.delete(k);
  }
  const params=[...u.searchParams].sort(([a,x],[b,y])=>a.localeCompare(b)||x.localeCompare(y));
  const q=new URLSearchParams(params).toString();
  const path=u.pathname.replace(/\/+$/,"")||"/";
  return "https://"+u.hostname+path+(q?"?"+q:"");
 }
 function searchLinks(game,region,kind){
  if(!game||!["KR","JP","US"].includes(region)||!TYPES.includes(kind))return [];
  const homepage=safeUrl(game.official_source);
  if(!homepage)return [];
  const key=(region==="KR"?(game.label_ko||game.canonical):game.canonical);
  const terms=PHRASES[region][kind];
  const query='"'+String(key).replace(/"/g,"")+'" "'+terms+'"';
  const querySite="site:"+homepage.hostname+" "+query;
  const q=(base,v)=>base+encodeURIComponent(v);
  return [
   {label:"제조사 Google",url:q("https://www.google.com/search?q=",querySite)},
   {label:"제조사 Bing",url:q("https://www.bing.com/search?q=",querySite)},
   {label:"전체 웹 Google",url:q("https://www.google.com/search?q=",query)},
   {label:"Instagram 소식",url:q("https://www.google.com/search?q=","site:instagram.com "+query)},
   {label:"YouTube 소식",url:q("https://www.google.com/search?q=","site:youtube.com "+query)},
   {label:"X 최신 소식",url:q("https://x.com/search?q=",query)+"&f=live"}
  ];
 }
 function sourceRow(r){
  if(!r||!safeUrl(r.source_url))return null;
  return {url:r.source_url,canonical_url:canonical(r.source_url),
    source_type:String(r.source_type||"unknown"),
    observed_at:String(r.observed_at||""),
    source_trust:"SOURCE_PAGE_NOT_AUTOMATICALLY_CONTENT_VERIFIED",
    keywords_found:r.keyword?[String(r.keyword)]:[],
    found_via:[String(r.discovery_channel||"manual")],
    sightings:1};
 }
 // V648: categories are primary folders. Duplicate events and their links
 // are consolidated within one folder, NEVER across different categories.
 function categoryGroups(items){
  if(!Array.isArray(items))throw Error("INVALID_CATEGORY_ITEMS");
  return TYPES.map(category=>{
   const own=items.filter(item=>item&&item.category===category);
   return {category,label:NAMES[category],unique_items:own.length,
     source_links:own.reduce((count,e)=>count+(Array.isArray(e.sources)?e.sources.length:0),0),
     items:own};
  });
 }
 function groupSightings(items){
  if(!Array.isArray(items)||items.length>5000)throw Error("INVALID_SIGHTINGS");
  const groups=new Map();
  for(const r of items){
   if(!r||typeof r.title!=="string"||r.title.length>230||
      !TYPES.includes(r.category)||!["KR","JP","US"].includes(r.region)||
      typeof r.game_id!=="string"||!safeUrl(r.source_url))continue;
   const name=clean(r.title),venue=clean(r.location);
   if(!name)continue;
   // An undated item is grouped by the exact URL, not merely shared keywords.
   const parts=[r.game_id,r.region,r.category,name,r.start_date||"",
       r.start_date?venue:canonical(r.source_url)];
   const id=JSON.stringify(parts);
   if(!groups.has(id))groups.set(id,{
     event_id:id,game_id:r.game_id,region:r.region,category:r.category,
     title:r.title,start_date:r.start_date||null,end_dates:[],locations:[],
     rewards:[],eligibility:[],keywords:[],sources:[],source_count:0,
     confirmed:false,validation_status:"MANUAL_CONTENT_REVIEW_REQUIRED"});
   const entry=groups.get(id);
   for(const [from,to] of [["end_date","end_dates"],["location","locations"],
                            ["reward","rewards"],["eligibility","eligibility"],
                            ["keyword","keywords"]]){
    const value=String(r[from]||"");if(value&&!entry[to].includes(value))entry[to].push(value);
   }
   const src=sourceRow(r);if(!src)continue;
   const old=entry.sources.find(x=>x.canonical_url===src.canonical_url);
   if(old){
    old.sightings++;
    for(const word of src.keywords_found)if(!old.keywords_found.includes(word))
     old.keywords_found.push(word);
    for(const via of src.found_via)if(!old.found_via.includes(via))old.found_via.push(via);
   }else entry.sources.push(src);
  }
  const events=[...groups.values()];
  for(const e of events){
   e.source_count=e.sources.length;
   e.sources.sort((a,b)=>a.canonical_url.localeCompare(b.canonical_url));
   if(e.end_dates.length>1||e.rewards.length>1)
    e.validation_status="MULTIPLE_DETAILS_REVIEW_REQUIRED";
  }
  events.sort((a,b)=>(a.start_date||"9999").localeCompare(b.start_date||"9999")||
   a.game_id.localeCompare(b.game_id));
  return {schema_version:1,dataset_type:"TCG_EVENT_DISCOVERY_LEDGER",verified:false,
          unique_events:events.length,events,
          category_groups:categoryGroups(events).map(({category,unique_items,source_links,items})=>({
             category,unique_items,source_links,event_ids:items.map(e=>e.event_id)})),
          source_sightings_retained:events.reduce((n,x)=>n+x.source_count,0)};
 }
 function validateLedger(doc){
  if(!doc||doc.schema_version!==1||doc.dataset_type!=="TCG_EVENT_DISCOVERY_LEDGER"||
     !Array.isArray(doc.events)||doc.events.length>5000)throw Error("INVALID_LEDGER");
  for(const e of doc.events){
   if(!e||typeof e.title!=="string"||e.title.length>230||
      !TYPES.includes(e.category)||!["KR","JP","US"].includes(e.region)||
      !Array.isArray(e.sources)||e.sources.length>100||
      e.sources.some(s=>!s||!safeUrl(s.url)))throw Error("INVALID_LEDGER_RECORD");
  }
  return doc;
 }
 function mount(doc){
  const ids=["eventsApp","eventsStatus","eventsSummary","eventsGame","eventsRegion",
   "eventsCategory","eventsKeyword","eventsList","eventsSearchLinks","eventsImport",
   "eventsExport"];
  const nodes=ids.map(id=>doc.getElementById(id));if(!nodes.every(Boolean))return;
  const [root,status,summary,game,region,category,keyword,list,search,upload,exportBtn]=nodes;
  const el=(tag,text)=>{const e=doc.createElement(tag);e.textContent=String(text);return e;};
  const link=(label,url)=>{const a=el("a",label);a.href=url;a.target="_blank";
    a.rel="noopener noreferrer";return a;};
  let registry=null,ledger=null,shown=[];
  function render(){
   if(!registry||!ledger)return;
   const all=ledger.events;
   const q=keyword.value.trim().toLocaleLowerCase();
   shown=all.filter(e=>(game.value==="ALL"||e.game_id===game.value)&&
    (region.value==="ALL"||e.region===region.value)&&
    (category.value==="ALL"||e.category===category.value)&&
    (!q||[e.title,...(e.keywords||[]),...(e.rewards||[])].join(" ").toLocaleLowerCase().includes(q)));
   list.replaceChildren();
   // Render EVENT, PROMO, COLLAB, MOVIE, GIVEAWAY... in distinct sections.
   // Search keywords are filters only; they do not merge different categories.
   for(const bucket of categoryGroups(shown)){
    if(!bucket.items.length && category.value==="ALL")continue;
    const section=doc.createElement("section");
    section.className="category-section";
    section.setAttribute("aria-label",bucket.label+" 목록");
    const heading=doc.createElement("h2");
    heading.className="category-head";
    heading.textContent=bucket.label+" · 중복 통합 "+bucket.unique_items+
      "건 · 출처 "+bucket.source_links+"개";
    section.appendChild(heading);
    const grid=doc.createElement("div");
    grid.className="event-grid";
    for(const e of bucket.items){
    const article=doc.createElement("article");article.className="event-entry";
    article.appendChild(el("h2",e.title));
    article.appendChild(el("p",(NAMES[e.category]||e.category)+" · "+e.game_id+
     " · "+e.region+" · "+(e.start_date||"날짜 미확인")+
     ((e.end_dates&&e.end_dates.length)?" ~ "+e.end_dates.join(", "):"")));
    if(e.locations?.length)article.appendChild(el("p","지역: "+e.locations.join(", ")));
    if(e.rewards?.length)article.appendChild(el("p","경품/지급: "+e.rewards.join(" | ")));
    if(e.eligibility?.length)article.appendChild(el("p","참여 조건: "+e.eligibility.join(" | ")));
    article.appendChild(el("p","검색 키워드: "+(e.keywords?.join(" · ")||"미입력")));
    article.appendChild(el("p","통합된 출처 "+e.sources.length+"개 · 출처 페이지 내용 검토 필요"));
    const sources=doc.createElement("ol");
    for(const s of e.sources){
     const li=doc.createElement("li");
     const u=safeUrl(s.url);if(!u)continue;
     li.appendChild(link(u.hostname+" · "+String(s.source_type||"source"),u.href));
     li.appendChild(el("span"," · 발견: "+(s.found_via||[]).join(", ")+
       " · 횟수 "+(s.sightings||1)+" · 키워드: "+(s.keywords_found||[]).join(", ")+
       " · 확인일: "+(s.last_observed_at||s.observed_at||"미기록")));
     if(Array.isArray(s.discovered_in)&&s.discovered_in.length)
      li.appendChild(el("span"," · 입력 파일: "+s.discovered_in.slice(0,5).map(x=>
       String(x.file||"")+(x.row?" #"+x.row:"")).join(", ")));
     sources.appendChild(li);
    }
    article.appendChild(sources);grid.appendChild(article);
    }
    if(!bucket.items.length)grid.appendChild(el("p","이 분류에 수집·검토된 자료가 없습니다."));
    section.appendChild(grid);
    list.appendChild(section);
   }
   if(!shown.length && category.value==="ALL")
    list.appendChild(el("p","선택한 조건의 확인·수집 후보가 없습니다. 아래 무료 검색 링크로 조사할 수 있습니다."));
   const groupSummary=categoryGroups(shown).filter(b=>b.unique_items)
    .map(b=>b.label+" "+b.unique_items+"건").join(" · ");
   summary.textContent="분류별 중복 통합 · 총 "+all.length+"건 · 현재 "+shown.length+
     "건 · "+(groupSummary||"검색 결과 없음")+
     " · 같은 분류 안에서만 통합, 출처 원문 검토 필요";
   search.replaceChildren();
   if(game.value==="ALL"||region.value==="ALL"||category.value==="ALL"){
    search.appendChild(el("p","30종 가운데 게임·국가·행사 종류를 각각 선택하면 6가지 검색 경로를 제공합니다."));
   }else{
    const g=registry.games.find(x=>x.id===game.value);
    for(const item of searchLinks(g,region.value,category.value))
      search.appendChild(link(item.label+" ↗",item.url));
   }
   status.textContent="로컬 자료 준비 완료 · 외부 사이트는 링크를 눌렀을 때만 열림";
  }
  for(const ctrl of [game,region,category])ctrl.addEventListener("change",render);
  keyword.addEventListener("input",render);
  const get=url=>fetch(url,{cache:"no-store"}).then(r=>{
   if(!r.ok)throw Error("LOCAL_DATA_UNAVAILABLE");return r.json();
  });
  Promise.all([get("./tcg_game_registry.json"),get("./tcg_event_source_sightings_v645.json")])
   .then(([reg,seed])=>{
    if(reg.schema_version!==1||!Array.isArray(reg.games)||reg.games.length!==30||
       seed.schema_version!==1||!Array.isArray(seed.sightings))throw Error("INVALID_SEED");
    registry=reg;ledger=groupSightings(seed.sightings);
    for(const g of reg.games){const option=doc.createElement("option");
     option.value=g.id;option.textContent=g.label_ko||g.canonical;game.appendChild(option);}
    render();
   }).catch(()=>{status.textContent="로컬 이벤트 입력 자료 오류 · 출처를 임의 생성하지 않습니다";})
   .finally(()=>root.setAttribute("aria-busy","false"));
  upload.addEventListener("change",async()=>{
   const file=upload.files?.[0];if(!file)return;
   if(file.size>2_000_000){status.textContent="2MB 이내 JSON만 읽을 수 있습니다";return;}
   try{
    const data=JSON.parse(await file.text());
    if(data.dataset_type==="TCG_EVENT_DISCOVERY_LEDGER")ledger=validateLedger(data);
    else if(data.schema_version===1&&Array.isArray(data.sightings))
     ledger=groupSightings(data.sightings);
    else throw Error("UNKNOWN_JSON_FORMAT");
    render();status.textContent="기기 내부 JSON 병합 자료 불러옴 · 서버 업로드 없음";
   }catch(_){status.textContent="JSON 가져오기 실패 · 기존 자료 보존";}
  });
  exportBtn.addEventListener("click",()=>{
   if(!ledger)return;
   const blob=new Blob([JSON.stringify(ledger,null,2)],{type:"application/json;charset=utf-8"});
   const url=URL.createObjectURL(blob),a=doc.createElement("a");
   a.href=url;a.download="tcg_events_merged_sources.json";a.click();
   setTimeout(()=>URL.revokeObjectURL(url),1500);
  });
 }
 return Object.freeze({TYPES,NAMES,searchLinks,groupSightings,categoryGroups,validateLedger,canonical,mount});
});
