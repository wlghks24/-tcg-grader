/* V676 opt-in read-only gallery; no training, model or inventory writes. */
(function (root) {
  "use strict";
  const IMAGE_RE = /^\/api\/local-card-images\/file\/([a-f0-9]{32})$/;
  const ID_RE = /^[a-f0-9]{32}$/;
  const REGIONS = new Set(["KR","JP","US","CN-S","CN-T"]);
  const KINDS = new Set(["CARD","PROMO","BOX","PACK","DECK","COLLECTION","BUNDLE","ACCESSORY"]);
  const HOSTS = [
    "pokemon-card.com","pokemon.cn","pokemonkorea.co.kr","pokemon.com",
    "onepiece-cardgame.com","onepiece-cardgame.kr","naruto-official.com",
    "kream.co.kr","pokard.io","tcgplayer.com","ebay.com","ebay.co.jp",
    "snkrdunk.com","cardmarket.com","tcgdex.net","tcgfish.net",
    "psacard.com","asia.pokemon-card.com","bandainamcoent.com"
  ];
  const COUNTRY = {"KR":"한국판","JP":"일본판","US":"미국판","CN-S":"중국판 · 간체","CN-T":"중국판 · 번체"};
  const LIMIT = 1800;
  function clean(value, max=130) {
    if (typeof value !== "string") return "";
    return value.trim().replace(/[\u0000-\u001f\u007f]/g, "").slice(0,max);
  }
  function safeLink(value) {
    if(typeof value!=="string" || value.length>2048) return "";
    try {
      const u = new URL(value);
      if(u.protocol!=="https:" || u.username || u.password || (u.port && u.port!=="443") || u.hash) return "";
      const host=u.hostname.toLowerCase();
      return HOSTS.some(h=>host===h || host.endsWith("."+h))?u.href:"";
    } catch (_) {return "";}
  }
  function photoPath(row) {
    if(!row || !ID_RE.test(String(row.id||""))) return "";
    const value=typeof row.image_url==="string"?row.image_url:"";
    if(value && (!IMAGE_RE.test(value) || IMAGE_RE.exec(value)[1]!==row.id)) return "";
    return "/api/local-card-images/file/"+row.id;
  }
  function kindOf(kind) {
    if(kind==="CARD" || kind==="PROMO") return "CARD";
    if(KINDS.has(kind)) return "BOX";
    return "";
  }
  function linkRecords(report) {
    const out=new Map();
    if(!report || report.ok!==true || !Array.isArray(report.catalog_matches) ||
       !Array.isArray(report.local_catalog) || !Array.isArray(report.source_catalog))return out;
    const local=new Map(),sources=new Map(),imgCount=new Map(),srcCount=new Map();
    for(const r of report.local_catalog.slice(0,2500)){
      if(!r || !photoPath(r))continue;
      if(!local.has(r.id))local.set(r.id,r);
      else local.delete(r.id); // duplicate never becomes trusted
    }
    for(const s of report.source_catalog.slice(0,1500)){
      if(!s || !ID_RE.test(String(s.source_record_id||"")))continue;
      if(!sources.has(s.source_record_id))sources.set(s.source_record_id,s);
      else sources.delete(s.source_record_id);
    }
    for(const m of report.catalog_matches.slice(0,1500)){
      if(!m || m.match!=="CODE_MATCH")continue;
      imgCount.set(m.id,(imgCount.get(m.id)||0)+1);
      srcCount.set(m.source_record_id,(srcCount.get(m.source_record_id)||0)+1);
    }
    for(const m of report.catalog_matches.slice(0,1500)){
      if(!m || m.match!=="CODE_MATCH" || imgCount.get(m.id)!==1 ||
         srcCount.get(m.source_record_id)!==1)continue;
      const p=local.get(m.id),s=sources.get(m.source_record_id);
      if(!p || !s || p.linked_to_existing_catalog!==true ||
         p.identity_verification!=="CODE_MATCH" || p.linked_source_record_id!==s.source_record_id ||
         p.game_id!==s.game_id || p.region!==s.region || p.kind!==s.kind ||
         m.game_id!==s.game_id || m.region!==s.region || m.kind!==s.kind ||
         m.catalog_kind!==s.kind || m.image_url!==photoPath(p))continue;
      out.set(s.source_record_id,p);
    }
    return out;
  }
  function makeRows(report,localAlbum,watch,events) {
    const entries=[],linked=linkRecords(report),sourceIds=new Set(),images=new Set();
    const reportOk=report && report.ok===true;
    if(reportOk){
      for(const s of report.source_catalog.slice(0,1200)){
        if(!s || !REGIONS.has(s.region) || !kindOf(s.kind) ||
           !ID_RE.test(String(s.source_record_id||"")) || sourceIds.has(s.source_record_id))continue;
        sourceIds.add(s.source_record_id);
        const photo=linked.get(s.source_record_id);
        if(photo)images.add(photo.id);
        entries.push({
          id:"source:"+s.source_record_id,category:kindOf(s.kind),
          rawKind:s.kind,region:s.region,game:clean(s.game_id,70),
          title:clean(s.name),code:clean((s.product_codes||[]).join(" "),90),
          image:photo?photoPath(photo):"",linked:!!photo,source:safeLink(s.source_url),
          evidence:photo?"상품 코드 연결 · 카드 아트·실물 판본 확인 별도":
            "상품 출처 확인 · 연결 이미지 없음",
          grade:"미확인",price:"미확인",generation:
            photo?clean(photo.card_metadata?.generation,45):"",
          set:photo?clean(photo.card_metadata?.set_name,110):"",
          release:clean(s.observed_release_date,20),marketVerified:false
        });
      }
    }
    const local=reportOk&&Array.isArray(report.local_catalog)?
      report.local_catalog:Array.isArray(localAlbum?.items)?localAlbum.items:[];
    for(const row of local.slice(0,2500)){
      if(!row || !REGIONS.has(row.region) || !kindOf(row.kind) ||
         !/^[a-z0-9-]{2,64}$/.test(String(row.game_id||"")) ||
         !photoPath(row) || images.has(row.id))continue;
      images.add(row.id);
      const meta=row.card_metadata&&typeof row.card_metadata==="object"?row.card_metadata:{};
      entries.push({
        id:"local:"+row.id,category:kindOf(row.kind),rawKind:row.kind,
        region:row.region,game:clean(row.game_id,70),title:clean(row.name),
        code:clean(meta.card_number||meta.card_code||meta.set_code,70),
        image:photoPath(row),linked:false,source:safeLink(row.source_url),
        evidence:"로컬 이미지 · 상품 동일성 미확인",grade:"미확인",
        price:"미확인",generation:clean(meta.generation,45),
        set:clean(meta.set_name,110),release:"",marketVerified:false
      });
    }
    if(Array.isArray(watch?.items)){
      for(const row of watch.items.slice(0,200)){
        if(!row || !REGIONS.has(row.region) || !clean(row.name) ||
           !["BOX","PACK","DECK"].includes(row.asset) || !safeLink(row.source))continue;
        entries.push({
          id:"watch:"+entries.length,category:"BOX",rawKind:row.asset,
          region:row.region,game:clean(row.game,70),title:clean(row.name),
          code:clean(row.product_code,80),image:"",linked:false,
          source:safeLink(row.source),
          evidence:"출시·판매 참고 자료 · 미연결 이미지",
          grade:"해당 없음",price:clean(row.official_price,70)||"미확인",
          generation:"",set:"",release:clean(row.release_date,20),marketVerified:false
        });
      }
    }
    if(Array.isArray(events?.items)){
      for(const row of events.items.slice(0,250)){
        const title=clean(row.name_ko||row.title||row.name_native);
        if(!row || !REGIONS.has(row.region) || !title || !safeLink(row.source))continue;
        const category=clean(row.category,35).toUpperCase();
        const eventKind=/COLLAB/.test(category)?"콜라보":
          /EXHIBITION|POPUP/.test(category)?"행사":
          /PROMO/.test(category)?"프로모":"이벤트";
        entries.push({
          id:"event:"+entries.length,category:"EVENT",rawKind:eventKind,
          region:row.region,game:clean(row.game,70),title,
          code:"",image:"",linked:false,source:safeLink(row.source),
          evidence:row.source_grade==="official" && row.tracking_only!==true?
            "공식 자료 기록 · 일정 최신성 재확인 필요":"발표·일정 확인 대기",
          grade:"해당 없음",price:"해당 없음",generation:"",set:"",
          release:clean(row.start_date,20),marketVerified:false
        });
      }
    }
    return {entries:entries.slice(0,LIMIT),linked:linked.size,
      photos:images.size,events:entries.filter(r=>r.category==="EVENT").length,
      gaps:reportOk?Number(report.summary?.catalog_to_image_gaps)||0:null,
      sourceErrors:reportOk?(report.source_errors||[]).length:null};
  }
  function select(rows,{q="",region="ALL",kind="ALL"}={}) {
    const query=String(q).trim().toLocaleLowerCase();
    return rows.filter(row=>(region==="ALL"||row.region===region||
      (region==="CN"&&["CN-S","CN-T"].includes(row.region))) &&
      (kind==="ALL"||row.category===kind) &&
      (!query||[row.title,row.game,row.code,row.set,row.rawKind]
        .some(v=>String(v||"").toLocaleLowerCase().includes(query))));
  }
  function init(d) {
    const gallery=d.getElementById("gallery"),summary=d.getElementById("summary"),
      detail=d.getElementById("detail"),modal=d.getElementById("detail-body");
    if(!gallery || !summary || !detail || !modal)return;
    let state={region:"ALL",kind:"ALL",q:""},data={entries:[],photos:0,linked:0,events:0,gaps:null,sourceErrors:null},limit=48;
    const el=(tag,text,cls)=>{const node=d.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;};
    function render(){
      const chosen=select(data.entries,state);
      gallery.replaceChildren();
      const visible=chosen.slice(0,limit);
      for(const row of visible){
        const article=el("article",undefined,"tile"),visual=el("div",undefined,"visual");
        if(row.image){
          const img=el("img");img.src=row.image;img.alt=row.title+" 사진";img.loading="lazy";
          img.decoding="async";visual.append(img);
        }else visual.append(el("span","이미지 확인 대기","no-image"));
        visual.append(el("span",row.category==="EVENT"?"EVENT":row.category==="BOX"?"BOX":"CARD","chip"));
        const body=el("div",undefined,"tilebody");
        body.append(el("div",(COUNTRY[row.region]||"지역 확인")+
          "  /  "+row.game,"overline"),el("h3",row.title));
        const metas=el("div",undefined,"metas");
        for(const text of [row.code,row.set,row.generation&&"세대 "+row.generation,row.rawKind]){
          if(text)metas.append(el("span",text));
        }
        body.append(metas);
        body.append(el("div",row.evidence,"evidence"+(row.linked?" verified":"")));
        const button=el("button","사진·상세 정보 보기","details");
        button.type="button";button.addEventListener("click",()=>showDetail(row));
        body.append(button);article.append(visual,body);gallery.append(article);
      }
      d.getElementById("empty").hidden=chosen.length>0;
      d.getElementById("more").hidden=chosen.length<=limit;
      summary.textContent=chosen.length+"건 표시 가능 · 현재 "+visible.length+
        "건 · 정확한 판본/등급/거래가 검증 여부를 구분합니다.";
    }
    function showDetail(row){
      modal.replaceChildren();
      const cover=el("div",undefined,"cover");
      if(row.image){const img=el("img");img.src=row.image;img.alt=row.title;cover.append(img);}
      else cover.append(el("span","검증된 연결 사진 없음","no-image"));
      modal.append(cover,el("h2",row.title));
      const dl=el("dl");
      const fields=[
        ["구분",row.rawKind],["게임",row.game],["판본",COUNTRY[row.region]||row.region],
        ["카드/상품 코드",row.code||"미확인"],["세트",row.set||"미확인"],
        ["세대/시리즈",row.generation||"미확인"],["출시/행사 시작 자료일",row.release||"미확인"],
        ["감정 등급/예상등급",row.grade],["가격 참고값",row.price],
        ["가격 증빙","실거래·판매가 교차검증 전 / 수익 예측 금지"],
        ["이미지 관계",row.evidence]
      ];
      for(const [key,val] of fields){dl.append(el("dt",key),el("dd",val));}
      modal.append(dl);
      if(row.source){
        const link=el("a","원문 출처 열기","source");
        link.href=row.source;link.rel="noopener noreferrer";link.target="_blank";modal.append(link);
      }
      if(typeof detail.showModal==="function")detail.showModal();
    }
    for(const grp of ["regions","kinds"]){
      d.getElementById(grp).addEventListener("click",e=>{
        const b=e.target.closest("button");if(!b || !b.parentElement||b.parentElement.id!==grp)return;
        if(grp==="regions")state.region=b.dataset.region;else state.kind=b.dataset.kind;
        for(const n of b.parentElement.querySelectorAll("button"))n.setAttribute("aria-pressed",String(n===b));
        limit=48;render();
      });
    }
    d.getElementById("search").addEventListener("input",e=>{
      state.q=String(e.target.value||"").slice(0,100);limit=48;render();
    });
    d.getElementById("more").addEventListener("click",()=>{limit+=48;render();});
    async function getJson(url){
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
      try{
        const r=await fetch(url,{credentials:"same-origin",cache:"no-store",signal:controller.signal});
        if(!r.ok)throw Error("HTTP "+r.status);
        return await r.json();
      }finally{clearTimeout(timer);}
    }
    async function reload(){
      const button=d.getElementById("reload");button.disabled=true;summary.textContent="자료 연결 중…";
      try{
        const targets=[
          "/api/local-card-images/catalog-links",
          "/api/local-card-images",
          "market_watch.json","promo_events.json"
        ];
        const results=await Promise.allSettled(targets.map(getJson));
        const raw=results.map(x=>x.status==="fulfilled"?x.value:null);
        data=makeRows(...raw);limit=48;render();
        d.getElementById("stat-photos").textContent=data.photos;
        d.getElementById("stat-linked").textContent=data.linked;
        d.getElementById("stat-events").textContent=data.events;
        d.getElementById("stat-gaps").textContent=data.gaps===null?"미확인":data.gaps;
        if(results.some(x=>x.status==="rejected")||data.sourceErrors){
          summary.textContent+=" 일부 자료 확인 실패 · 화면에 나온 자료도 최신 재검증 필요.";
        }
      }catch(_){summary.textContent="로컬 자료 형식 확인 실패 · 원본 데이터는 유지됩니다.";}
      finally{button.disabled=false;}
    }
    d.getElementById("reload").addEventListener("click",reload);
    reload();
  }
  const api={safeLink,photoPath,linkRecords,makeRows,select,init};
  if(typeof module==="object" && module.exports)module.exports=api;
  if(typeof document!=="undefined")init(document);
})(this);
