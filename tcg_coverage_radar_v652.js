/* V652: Offline-first 30-game coverage radar and priority discovery queue.
 * A source link is a RESEARCH POINTER, not evidence of a live BOX, HIT, price,
 * sale, release or officially released country edition.
 */
(function(root,factory){
 "use strict";
 const api=factory();
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 if(root&&root.document){
  root.TcgCoverageRadarV652=api;
  const go=()=>api.mount(root.document);
  if(root.document.readyState==="loading")root.document.addEventListener("DOMContentLoaded",go,{once:true});
  else go();
 }
})(typeof globalThis!=="undefined"?globalThis:this,function(){
 "use strict";
 const LANES=["BOX","PACK","CARD","HIT","PROMO","PRICE"];
 const LABEL={BOX:"일반 BOX",PACK:"낱팩",CARD:"카드 목록·번호",
              HIT:"HIT 개별카드",PROMO:"프로모 개별카드",PRICE:"매입·판매·실거래"};
 const LANG={KR:{BOX:"박스 팩수",PACK:"낱팩 구성",CARD:"카드리스트 번호",
             HIT:"고레어 카드번호",PROMO:"프로모 카드번호",PRICE:"매입 실거래"},
             JP:{BOX:"BOX 入数",PACK:"パック 枚数",CARD:"カードリスト 番号",
             HIT:"高レア カード番号",PROMO:"プロモ 番号",PRICE:"買取 成約"},
             US:{BOX:"booster box packs",PACK:"booster pack cards",CARD:"card checklist numbers",
             HIT:"hit card rarity",PROMO:"promo card number",PRICE:"buylist completed sales"}};
 function safeHost(value){
  if(typeof value!=="string"||value.length>800)return null;
  try{
   const u=new URL(value);
   if(u.protocol!=="https:"||u.username||u.password||u.hash||u.port)return null;
   return u.hostname;
  }catch(_){return null;}
 }
 function build(reg,intake,base,s630,s636=null,s637=null,s649=null,dependency){
  const dep=dependency||{
   research:typeof globalThis!=="undefined"?globalThis.TcgSourceResearchV634:null,
   official:typeof globalThis!=="undefined"?globalThis.TcgOfficialBoxV626:null
  };
  if(!dep.research?.build||!dep.official?.normalizeProducts)
   throw Error("RESEARCH_OR_VALIDATION_MODULE_MISSING");
  const report=dep.research.build(reg,intake,base,s630,s636,s637,s649);
  const raw=[...base.products,...s630.products,...(s636?.products||[]),
             ...(s637?.products||[]),...(s649?.products||[])];
  // Every manufacturer row must pass the existing official-domain/product
  // validator. Never count invalid lines as verified product evidence.
  const validated=dep.official.normalizeProducts({schema_version:1,products:raw});
  if(validated.length!==raw.length)throw Error("UNVERIFIED_PRODUCT_IN_CATALOG");
  const productKinds=new Map();
  for(const p of validated){
   const k=p.game+"|"+p.country;
   if(!productKinds.has(k))productKinds.set(k,{BOX:0,PACK:0});
   if(p.product_type==="BOX")productKinds.get(k).BOX++;
   if(p.product_type==="BOOSTER_PACK")productKinds.get(k).PACK++;
  }
  const tasks=[],cells=[];
  const alias=(g,m)=>m==="KR"?(g.label_ko||g.canonical):g.canonical;
  const quote=v=>'"'+String(v).replace(/["<>\\\r\n]/g," ").slice(0,150).trim()+'"';
  for(const s of report.scopes){
   const {game,region}=s,declared=s.declared;
   const types=productKinds.get(game.canonical+"|"+region)||{BOX:0,PACK:0};
   const cell={game_id:game.id,game_name:game.label_ko||game.canonical,
     canonical:game.canonical,region,declared,
     official_product_samples:s.officialCount,
     actual_box_samples:types.BOX,actual_pack_samples:types.PACK,
     card_id_verified:false,hit_id_verified:false,promo_id_verified:false,
     price_verified:false,source_status:"SAMPLE_ONLY_NOT_FULL_CATALOG"};
   cells.push(cell);
   const seed=s.sourceHints.find(link=>safeHost(link))||game.official_source;
   const host=safeHost(seed);
   if(!host)throw Error("INVALID_OFFICIAL_SEARCH_SEED");
   const candidates={BOX:s.products.slice(0,3),PACK:s.products.slice(0,2),
     CARD:[],HIT:s.hit.slice(0,3),PROMO:s.promo.slice(0,3),PRICE:s.products.slice(0,2)};
   for(const lane of LANES){
    const count=lane==="BOX"?types.BOX:lane==="PACK"?types.PACK:0;
    const evidence=lane==="BOX"||lane==="PACK"?(count?"MANUFACTURER_PRODUCT_SAMPLED":"NO_LOCAL_MANUFACTURER_SAMPLE"):
      "NO_VERIFIED_CARD_ID_OR_TRANSACTION_IN_THIS_SNAPSHOT";
    const priority=!declared?4:
       lane==="BOX"&&!count?0:
       lane==="PACK"&&!count?1:
       (lane==="CARD"||lane==="HIT"||lane==="PROMO")?2:
       lane==="PRICE"?3:4;
    const term=LANG[region][lane];
    const tokens=[alias(game,region),term,...candidates[lane].slice(0,1)];
    const site="site:"+host+" "+tokens.map(quote).join(" ");
    const broad=tokens.map(quote).join(" ");
    const market=region==="JP"?"日本":region==="KR"?"한국":"USA";
    tasks.push({
      game_id:game.id,game_name:cell.game_name,region,lane,
      region_declared:declared,priority,
      priority_label:priority===0?"P0 BOX 누락":priority===1?"P1 낱팩 누락":
       priority===2?"P2 카드 검증":priority===3?"P3 가격 증거": "P4 표본 재검토/지역 탐색",
      official_product_samples:s.officialCount,
      existing_manufacturer_samples:count,
      local_evidence:evidence,manufacturer_host:host,
      candidates_unverified:candidates[lane],source_verification:"SEARCH_LINK_ONLY",
      found_sources:0,verified_product_updates:0,
      links:[
        {label:"제조사 Google",url:"https://www.google.com/search?q="+encodeURIComponent(site)},
        {label:"제조사 Bing",url:"https://www.bing.com/search?q="+encodeURIComponent(site)},
        {label:"시장 Google",url:"https://www.google.com/search?q="+encodeURIComponent(broad+" "+market)},
        {label:"X 최신 검색",url:"https://x.com/search?q="+encodeURIComponent(broad)+"&f=live"}
      ]
    });
   }
  }
  tasks.sort((a,b)=>a.priority-b.priority||a.game_id.localeCompare(b.game_id)||
             a.region.localeCompare(b.region)||LANES.indexOf(a.lane)-LANES.indexOf(b.lane));
  const declaredCells=cells.filter(c=>c.declared);
  const eligibleBox=declaredCells.filter(c=>c.actual_box_samples>0).length;
  const sampledGames=new Set(validated.map(p=>p.game)).size;
  return {schema_version:1,status:"OFFLINE_EVIDENCE_GAP_PLAN",games:30,
   region_scopes:90,declared_region_scopes:declaredCells.length,
   manufacturer_game_samples:sampledGames,
   official_product_samples:validated.length,
   official_box_samples:validated.filter(p=>p.product_type==="BOX").length,
   scoped_box_proofs:eligibleBox,declared_box_gaps:declaredCells.length-eligibleBox,
   card_ids_verified_by_this_plan:0,hit_ids_verified_by_this_plan:0,
   promo_ids_verified_by_this_plan:0,transactions_verified_by_this_plan:0,
   manual_search_tasks:tasks.length,paid_api_requests:0,
   cells,tasks,limitations:["SEARCH_LINKS_NOT_VERIFIED_FINDINGS","PRICE_UNKNOWN",
    "UNDECLARED_REGION_NOT_PROVEN_RELEASED","PACK_SAMPLE_NOT_SEALED_BOX_PROOF"]};
 }
 function filtered(tasks,{game="ALL",region="ALL",lane="ALL",gapOnly=false}={}){
  return tasks.filter(t=>(game==="ALL"||t.game_id===game)&&
     (region==="ALL"||t.region===region)&&(lane==="ALL"||t.lane===lane)&&
     (!gapOnly||(t.region_declared&&t.existing_manufacturer_samples===0)));
 }
 function mount(doc){
  const ids=["coverageApp","coverageSummary","coverageGame","coverageRegion",
   "coverageLane","coverageGapOnly","coverageList","coverageStatus"];
  const node=ids.map(x=>doc.getElementById(x));
  if(!node.every(Boolean))return;
  const [root,summary,game,region,lane,gap,list,status]=node;
  const el=(tag,value)=>{const n=doc.createElement(tag);n.textContent=String(value);return n;};
  const a=(title,url)=>{const n=el("a",title);n.href=url;n.target="_blank";
   n.rel="noopener noreferrer";return n;};
  let data=null;
  const render=()=>{
   if(!data)return;
   const matches=filtered(data.tasks,{game:game.value,region:region.value,
                lane:lane.value,gapOnly:gap.checked});
   list.replaceChildren();
   for(const t of matches.slice(0,60)){
    const li=doc.createElement("article");li.className="gap-result";
    li.appendChild(el("h3",t.game_name+" · "+t.region+" · "+LABEL[t.lane]));
    li.appendChild(el("p",t.priority_label+" · "+t.local_evidence+
      " · 후보 "+t.candidates_unverified.length+"개(미검증)"));
    const links=doc.createElement("div");links.className="linkrow";
    for(const u of t.links)links.appendChild(a(u.label+" ↗",u.url));
    li.appendChild(links);list.appendChild(li);
   }
   if(!matches.length)list.appendChild(el("p","해당 조건에서 조사할 항목이 없습니다."));
   summary.textContent="제조사 상품 표본 "+data.official_product_samples+
     "건 · 일반 BOX "+data.official_box_samples+"건 · 등록 국가별 BOX 공백 "+
     data.declared_box_gaps+"/"+data.declared_region_scopes+
     " · 현재 검색 과제 "+matches.length+"개 (60개씩 표시)";
  };
  const load=path=>fetch(path,{cache:"no-store"}).then(r=>{
   if(!r.ok)throw Error("LOCAL_INPUT_MISSING");return r.json();
  });
  Promise.all([
   load("./tcg_game_registry.json"),load("./tcg_user_research_intake_v625.json"),
   load("./tcg_official_product_catalog_v599.json"),load("./tcg_official_product_supplement_v630.json"),
   load("./tcg_official_product_supplement_v636.json").catch(()=>null),
   load("./tcg_official_product_supplement_v637.json").catch(()=>null),
   load("./tcg_official_product_supplement_v649.json").catch(()=>null)])
  .then(values=>{
   const [r,i,b,s630,s636,s637,s649]=values;
   // Bad optional supplement stops source promotion; retry last-known
   // official supplement level rather than exposing suspect new products.
   try{data=build(r,i,b,s630,s636,s637,s649);}
   catch(err){
    if(!s649)throw err;
    data=build(r,i,b,s630,s636,s637,null);
    status.textContent="신규 제조사 파일 검증 실패: 기존 표본만 표시";
   }
   for(const g of r.games){
    const opt=doc.createElement("option");opt.value=g.id;
    opt.textContent=g.label_ko||g.canonical;game.appendChild(opt);
   }
   render();if(!status.textContent)status.textContent="오프라인 공식 제품 표본 기반, 링크로 실제 출처 확인 필요";
  }).catch(_=>{status.textContent="검증되지 않은 입력 데이터: 자동 확정 중지";})
    .finally(()=>root.setAttribute("aria-busy","false"));
  for(const control of [game,region,lane])control.addEventListener("change",render);
  gap.addEventListener("change",render);
 }
 return Object.freeze({LANES,LABEL,build,filtered,mount});
});
