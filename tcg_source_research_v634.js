/* V634: all 30 TCGs x KR/JP/US candidate source-discovery, free/offline. */
(function(root,factory){
 "use strict";
 const api=factory();
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 if(root&&root.document){
  root.TcgSourceResearchV634=api;
  const start=()=>api.mount(root.document);
  if(root.document.readyState==="loading")root.document.addEventListener("DOMContentLoaded",start,{once:true});
  else start();
 }
})(typeof globalThis!=="undefined"?globalThis:this,function(){
 "use strict";
 const PAGE_SIZE=6;
 const FIELDS=["product_name_candidates","upcoming_name_candidates","hit_name_candidates","promo_name_candidates"];
 function build(reg,intake,base,sup,more=null){
  if(!reg||reg.schema_version!==1||!Array.isArray(reg.games)||reg.games.length!==30||
     !intake||intake.data_evidence_level!=="UNVERIFIED"||
     !Array.isArray(intake.records)||intake.records.length!==30||
     !base||base.schema_version!==1||!Array.isArray(base.products)||
     !sup||sup.schema_version!==1||sup.type!=="official_product_specifications_supplement"||
     sup.base_catalog!=="tcg_official_product_catalog_v599.json"||!Array.isArray(sup.products))
     throw Error("INVALID_SOURCE_INPUT");
  const names=new Map();
  for(const r of intake.records){
   if(!r||names.has(r.game_id)||r.status!=="USER_SUBMITTED_UNVERIFIED"||
      !FIELDS.every(k=>Array.isArray(r[k])&&r[k].every(v=>typeof v==="string")))
      throw Error("INVALID_USER_CANDIDATES");
   names.set(r.game_id,r);
  }
  if(new Set(reg.games.map(g=>g.id)).size!==30||reg.games.some(g=>!names.has(g.id)))
    throw Error("MISSING_GAME");
  if(more && (more.schema_version!==1||
     more.type!=="official_product_specifications_supplement"||
     more.base_catalog!=="tcg_official_product_catalog_v599.json"||
     more.append_after!=="tcg_official_product_supplement_v630.json"||
     !Array.isArray(more.products)))throw Error("INVALID_ADDITIONAL_OFFICIAL");
  const all=base.products.concat(sup.products,more?more.products:[]);
  if(new Set(all.map(p=>p.id)).size!==all.length)throw Error("DUPLICATE_PRODUCT");
  const counts=new Map();
  for(const p of all){
   const key=p.game+"\u0000"+p.country;counts.set(key,(counts.get(key)||0)+1);
  }
  const scopes=[];
  for(const game of reg.games)for(const region of ["KR","JP","US"]){
   const declared=game.regions.includes(region)||game.regions.includes("GLOBAL");
   const officialCount=counts.get(game.canonical+"\u0000"+region)||0;
   const row=names.get(game.id);
   scopes.push({game,region,declared,officialCount,
     products:row.product_name_candidates,upcoming:row.upcoming_name_candidates,
     hit:row.hit_name_candidates,promo:row.promo_name_candidates,
     priority:declared?(officialCount?"SAMPLED":"MISSING"):"EXPLORATORY"});
  }
  const total=key=>intake.records.reduce((n,r)=>n+r[key].length,0);
  return {scopes,summary:{games:30,searchScopes:90,
   declared:scopes.filter(x=>x.declared).length,
   missing:scopes.filter(x=>x.priority==="MISSING").length,
   official:all.length,product:total(FIELDS[0]),upcoming:total(FIELDS[1]),
   hit:total(FIELDS[2]),promo:total(FIELDS[3])}};
 }
 function filtered(scopes,options){
  const {game="ALL",region="ALL",priority="ALL",term=""}=options||{};
  const q=String(term).trim().toLocaleLowerCase();
  return scopes.filter(r=>(game==="ALL"||r.game.id===game)&&
   (region==="ALL"||r.region===region)&&(priority==="ALL"||r.priority===priority)&&
   (!q||[r.game.canonical,r.game.label_ko,...r.products,...r.upcoming,...r.hit,...r.promo]
     .join(" ").toLocaleLowerCase().includes(q)));
 }
 function paginate(rows,page){
  const pages=Math.max(1,Math.ceil(rows.length/PAGE_SIZE));
  const current=Number.isInteger(page)?Math.max(0,Math.min(page,pages-1)):0;
  return {current,pages,rows:rows.slice(current*PAGE_SIZE,(current+1)*PAGE_SIZE)};
 }
 function mount(doc){
  const ids=["researchApp","researchSummary","researchGame","researchRegion","researchPriority",
    "researchSearch","researchResults","researchStatus","researchPrev","researchNext","researchPage"];
  const nodes=ids.map(id=>doc.getElementById(id));if(!nodes.every(Boolean))return;
  const [root,summary,gameControl,regionControl,priorityControl,searchControl,
    results,status,prev,next,index]=nodes;
  const routes=typeof globalThis!=="undefined"?globalThis.TcgSourceRoutesV633:null;
  const text=(tag,value)=>{const el=doc.createElement(tag);el.textContent=String(value);return el;};
  const link=(label,url)=>{const a=doc.createElement("a");a.textContent=label;
    a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a;};
  let all=[],page=0;
  function render(){
   const matches=filtered(all,{game:gameControl.value,region:regionControl.value,
     priority:priorityControl.value,term:searchControl.value});
   const paged=paginate(matches,page);page=paged.current;results.replaceChildren();
   for(const r of paged.rows){
    const card=doc.createElement("article");card.className="research-card";
    card.appendChild(text("h2",r.game.label_ko+" · "+r.region));
    card.appendChild(text("p",r.priority==="MISSING"?"등록 지역 · 공식 상품 샘플 미수록":
      r.priority==="SAMPLED"?"공식 상품 "+r.officialCount+"건(부분 표본)":
      "정식 지역판 미확인 · 탐색 전용"));
    if(routes){
     const site=routes.safeUrl(r.game.official_source);
     if(site){
      card.appendChild(link("레지스트리 등록 제조사 사이트 ↗",site.href));
      const search=routes.siteSearch(site.href,r.game.canonical,"");
      if(search)card.appendChild(link("제조사 도메인 BOX 검색 ↗",search));
      const bing=routes.siteSearch(site.href,r.game.canonical,"","bing");
      if(bing)card.appendChild(link("Bing 제조사 도메인 검색 ↗",bing));
     }
    }
    const details=doc.createElement("details");
    details.appendChild(text("summary","저장된 BOX·제품 후보 "+r.products.length+"개 (검증 전)"));
    const list=doc.createElement("ul");
    for(const candidate of r.products){
     const li=doc.createElement("li");li.appendChild(text("span",candidate+" "));
     if(routes){
      const u=routes.siteSearch(r.game.official_source,candidate,"");
      if(u)li.appendChild(link("제조사 검색 ↗",u));
      const backup=routes.siteSearch(r.game.official_source,candidate,"","bing");
      if(backup)li.appendChild(link("Bing ↗",backup));
     }
     list.appendChild(li);
    }
    details.appendChild(list);card.appendChild(details);
    card.appendChild(text("p","출시 예정 "+r.upcoming.length+" · HIT "+r.hit.length+
      " · 프로모 "+r.promo.length+"건 (입력 원본 보존)"));
    results.appendChild(card);
   }
   if(!matches.length)results.appendChild(text("p","조건에 맞는 기록이 없습니다."));
   status.textContent="조회된 게임·국가 범위 "+matches.length+"개 · 상품 샘플은 BOX 전수 목록이 아님";
   index.textContent=(page+1)+" / "+paged.pages;
   prev.disabled=page===0;next.disabled=page>=paged.pages-1;
  }
  function change(){page=0;render();}
  [gameControl,regionControl,priorityControl].forEach(c=>c.addEventListener("change",change));
  searchControl.addEventListener("input",change);
  prev.addEventListener("click",()=>{page--;render();});
  next.addEventListener("click",()=>{page++;render();});
  const get=url=>fetch(url,{cache:"no-store"}).then(r=>{if(!r.ok)throw Error("LOCAL_FILE_MISSING");return r.json();});
  Promise.all([get("./tcg_game_registry.json"),get("./tcg_user_research_intake_v625.json"),
    get("./tcg_official_product_catalog_v599.json"),get("./tcg_official_product_supplement_v630.json"),
    get("./tcg_official_product_supplement_v636.json").catch(()=>null)])
    .then(([reg,intake,base,sup,more])=>{
     const data=build(reg,intake,base,sup,more);all=data.scopes;
     const s=data.summary;
     summary.textContent=s.games+"게임 · "+s.searchScopes+" 검색 지역 · 공식 상품 "+
       s.official+"건(표본) · 공식 상품 미수록 지역 "+s.missing+"/"+s.declared+
       " · BOX·제품 후보 "+s.product+"개";
     for(const g of reg.games){const opt=doc.createElement("option");
      opt.value=g.id;opt.textContent=g.label_ko;gameControl.appendChild(opt);}
     render();
     if(!more)status.textContent+=" · V636 공식 샘플 추가 파일 미확인";
    }).catch(()=>{
     summary.textContent="데이터 확인 실패";
     status.textContent="30종 입력 원본/공식 보강 파일 로드 실패 · 임의 생성 금지";
    }).finally(()=>root.setAttribute("aria-busy","false"));
 }
 return Object.freeze({build,filtered,paginate,mount,PAGE_SIZE});
});
