/* V676: local-only read-only unified Card / BOX / Event visual dashboard.
 * No inferred grade, price or identity; never writes source, model or inventory.
 */
(function(root,factory){
  "use strict";
  const api=factory();
  if(typeof module==="object" && module.exports) module.exports=api;
  if(root && root.document) {
    root.TCGUnifiedDashboardV676=api;
    root.document.addEventListener("DOMContentLoaded",function(){
      const mount=root.document.getElementById("tcg-v676");
      if(mount) api.start(mount);
    });
  }
})(typeof window==="undefined"?null:window,function(){
  "use strict";
  const KINDS=new Set(["CARD","PROMO","BOX","PACK","DECK","COLLECTION","BUNDLE","ACCESSORY"]);
  const REGIONS=new Set(["KR","JP","US","CN-S","CN-T"]);
  const LOCAL_ID=/^[a-f0-9]{32}$/;
  const REFS_ID=/^[a-f0-9]{32}$/;
  const GEN_LABEL={KR:"한국판",JP:"일본판",US:"미국판","CN-S":"중국 간체","CN-T":"중국 번체"};
  const CATEGORY={promo:"프로모",collab:"콜라보",collaboration:"콜라보",event:"행사",movie:"영화",campaign:"캠페인",exhibition:"전시"};
  const URL_HOSTS=[
    "pokemon-card.com","pokemon.com","pokemon.cn","pokemon.co.jp","asia.pokemon-card.com",
    "onepiece-cardgame.kr","onepiece-cardgame.com","naruto-official.com",
    "kream.co.kr","tcgplayer.com","ebay.com","ebay.co.jp",
    "mercari.com","snkrdunk.com","tcgdex.net","psacard.com"
  ];
  function txt(v,n=120) {
    if(typeof v!=="string") return "";
    const s=v.trim();
    return s && s.length<=n && !/[\u0000-\u001f\u007f]/.test(s)?s:"";
  }
  function safeLink(v){
    if(!txt(v,2048))return "";
    try{
      const u=new URL(v),host=u.hostname.toLowerCase();
      if(u.protocol!=="https:"||u.username||u.password||(u.port&&u.port!=="443"))return "";
      if(!URL_HOSTS.some(x=>host===x||host.endsWith("."+x)))return "";
      return u.href;
    }catch(_){return "";}
  }
  function imagePath(row){
    const id=typeof row?.id==="string"?row.id:"";
    const url=typeof row?.image_url==="string"?row.image_url:"";
    return LOCAL_ID.test(id) && url==="/api/local-card-images/file/"+id?url:"";
  }
  function officialGame(name){
    const s=String(name||"").toLowerCase();
    if(s.includes("pokemon")||s.includes("pokémon")||s.includes("포켓몬")||s.includes("ポケモン"))return "pokemon";
    if(s.includes("one piece")||s.includes("원피스")||s.includes("ワンピース"))return "onepiece";
    if(s.includes("naruto")||s.includes("나루토")||s.includes("ナルト"))return "naruto";
    return "other";
  }
  function gameName(v){
    return v==="pokemon"?"포켓몬":v==="onepiece"?"원피스":v==="naruto"?"나루토":txt(v,40)||"기타";
  }
  function normalize(local,events){
    const items=[];
    const source=Array.isArray(local?.source_catalog)?local.source_catalog.slice(0,1500):[];
    const images=Array.isArray(local?.local_catalog)?local.local_catalog.slice(0,2500):[];
    const matches=Array.isArray(local?.catalog_matches)?local.catalog_matches.slice(0,2500):[];
    const imageById=new Map();
    const sourceById=new Map();
    for(const x of images)if(x&&REGIONS.has(x.region)&&KINDS.has(x.kind)&&imagePath(x)&&txt(x.game_id,64)&&txt(x.name,130))
      imageById.set(x.id,x);
    for(const x of source)if(x&&REFS_ID.test(String(x.source_record_id||""))&&REGIONS.has(x.region)&&KINDS.has(x.kind)&&txt(x.name,130)&&txt(x.game_id,64))
      sourceById.set(x.source_record_id,x);
    const attached=new Map();
    const usedImages=new Set();
    for(const m of matches){
      if(!m||m.match!=="CODE_MATCH"||!LOCAL_ID.test(String(m.id||""))||!REFS_ID.test(String(m.source_record_id||"")))continue;
      const image=imageById.get(m.id),s=sourceById.get(m.source_record_id);
      if(!image||!s||image.game_id!==s.game_id||image.region!==s.region||image.kind!==s.kind||
         m.region!==s.region||m.game_id!==s.game_id||m.kind!==s.kind)continue;
      if(attached.has(s.source_record_id)||usedImages.has(image.id))continue;
      // A CODE_MATCH is metadata linkage, not a verified printing, grade or price.
      attached.set(s.source_record_id,image);
      usedImages.add(image.id);
    }
    const seen=new Set();
    for(const s of sourceById.values()){
      if(items.length>=600)break;
      const key="source:"+s.source_record_id;
      if(seen.has(key))continue;seen.add(key);
      const photo=attached.get(s.source_record_id);
      items.push({key,kind:s.kind,group:s.kind==="CARD"||s.kind==="PROMO"?"card":"box",
        game:s.game_id,region:s.region,name:s.name,image:photo?imagePath(photo):"",
        imageEvidence:photo?"CODE_MATCH":"NO_VERIFIED_IMAGE",
        meta:photo?.card_metadata||{},source:safeLink(s.source_url),
        sourceState:s.source_health==="HEALTHY"?"출처 링크 확인":"출처 재확인 필요",
        category:"상품",date:txt(s.observed_release_date,10),price:null,grade:null,
        gradePrediction:null,listingPrice:null,confidence:"식별·거래가 별도 검증"});
    }
    for(const image of imageById.values()){
      if(usedImages.has(image.id)||items.length>=900)continue;
      items.push({key:"photo:"+image.id,kind:image.kind,
        group:image.kind==="CARD"||image.kind==="PROMO"?"card":"box",
        game:image.game_id,region:image.region,name:image.name,image:imagePath(image),
        imageEvidence:"UNLINKED_LOCAL_PHOTO",meta:image.card_metadata||{},
        source:safeLink(image.source_url),sourceState:"로컬 사진 · 상품 매칭 미검증",
        category:"사진",date:"",price:null,grade:null,gradePrediction:null,
        listingPrice:null,confidence:"사진 출처와 실물 판본 확인 필요"});
    }
    const eventRows=Array.isArray(events?.items)?events.items.slice(0,1500):[];
    const eventIds=new Set();
    for(let i=0;i<eventRows.length&&items.length<1100;i++){
      const e=eventRows[i],name=txt(e?.name_ko||e?.name_native||e?.title,150);
      const region=typeof e?.region==="string"?e.region:"";
      const id=[name,region,String(e?.start_date||""),String(e?.category||"")].join("|");
      if(!name||!["KR","JP","US","CN","CN-S","CN-T"].includes(region)||eventIds.has(id))continue;
      eventIds.add(id);
      const official=e.source_grade==="official"&&Boolean(safeLink(e.source));
      const game=officialGame(e.game);
      items.push({key:"event:"+i,kind:"EVENT",group:"event",game,
        region:region==="CN"?"CN-S":region,name,image:"",imageEvidence:"EVENT_IMAGE_NOT_VERIFIED",
        meta:{},source:official?safeLink(e.source):"",
        sourceState:official?"공식 출처 표기":"공식 출처 검증 필요",
        category:CATEGORY[String(e.category||"").toLowerCase()]||"이벤트",
        date:txt(e.start_date,10),price:null,grade:null,gradePrediction:null,
        listingPrice:null,confidence:"행사 일정·제공 이미지 별도 검증"});
    }
    return items;
  }
  function filterRows(rows,{group="all",country="ALL",game="all",search=""}={}){
    const term=String(search||"").trim().toLocaleLowerCase().slice(0,90);
    return rows.filter(x=>(group==="all"||x.group===group)&&
      (country==="ALL"||country==="CN"&&x.region.startsWith("CN-")||x.region===country)&&
      (game==="all"||x.game===game)&&
      (!term||[x.name,x.game,x.region,x.kind,x.meta?.card_number,x.meta?.set_name,x.meta?.generation]
       .map(v=>String(v||"").toLocaleLowerCase()).some(v=>v.includes(term))));
  }
  function elt(tag,text,cls){
    const e=document.createElement(tag);
    if(cls)e.className=cls;
    if(text!==undefined&&text!==null)e.textContent=String(text);
    return e;
  }
  function makeButton(title,fn,cls){
    const b=elt("button",title,cls);b.type="button";b.addEventListener("click",fn);return b;
  }
  async function fetchJSON(path){
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(),9000);
    try{
      const r=await fetch(path,{cache:"no-store",credentials:"same-origin",signal:ctrl.signal});
      if(!r.ok)throw Error("HTTP "+r.status);
      const size=Number(r.headers.get("content-length")||0);
      if(size>8_000_000)throw Error("JSON oversized");
      return await r.json();
    }finally{clearTimeout(timer);}
  }
  function start(mount){
    if(!mount||mount.dataset.started==="yes")return;
    mount.dataset.started="yes";
    mount.replaceChildren();
    const status=elt("p","기기 안의 카드·BOX·행사 자료를 확인하고 있습니다.","v676-status");
    status.setAttribute("role","status");status.setAttribute("aria-live","polite");
    const summary=elt("div",null,"v676-stats"),controls=elt("div",null,"v676-controls"),
      grid=elt("div",null,"v676-grid"),detail=elt("section",null,"v676-detail");
    detail.hidden=true;
    const search=elt("input");search.type="search";search.placeholder="카드명, 번호, BOX, 세대 검색";
    search.setAttribute("aria-label","카드·BOX·행사 검색");
    const kinds=elt("div",null,"v676-tabs"),countries=elt("div",null,"v676-countries"),games=elt("div",null,"v676-games");
    controls.append(search,kinds,countries,games);
    mount.append(status,summary,controls,grid,detail);
    let rows=[],mode={group:"all",country:"ALL",game:"all",search:""},limit=48,unavailable=[];
    function panel(row){
      detail.replaceChildren();
      const close=makeButton("닫기",()=>{detail.hidden=true;detail.replaceChildren();},"v676-close");
      const media=elt("div",null,"v676-hero-media");
      if(row.image){const img=elt("img");img.src=row.image;img.alt=row.name+" 로컬 카드 이미지";img.loading="lazy";img.onerror=()=>{media.replaceChildren(elt("span","이미지 파일 확인 필요"))};media.append(img);}
      else media.append(elt("span",row.group==="event"?"공식 행사 이미지 확인 중":"해당 판본 이미지 미연결"));
      const content=elt("div",null,"v676-hero-copy");
      content.append(elt("span",gameName(row.game)+" · "+(GEN_LABEL[row.region]||row.region)+" · "+row.category,"v676-eyebrow"),
        elt("h2",row.name),elt("p",row.sourceState,"v676-note"));
      const d=elt("dl",null,"v676-facts");
      for(const [k,v] of [
        ["구분",row.kind],["세대·시리즈",txt(row.meta?.generation,40)||"확인 중"],
        ["세트",txt(row.meta?.set_name,130)||"확인 중"],
        ["카드 번호",txt(row.meta?.card_number,30)||"확인 중"],
        ["감정등급",row.grade===null?"실물 감정 미검증":row.grade],
        ["예상등급",row.gradePrediction===null?"검증된 예측 결과 없음":row.gradePrediction],
        ["시세·실거래",row.price===null?"검증된 실거래 근거 없음":row.price],
        ["판매 제안가",row.listingPrice===null?"미산정 · 수수료/실거래 근거 필요":row.listingPrice],
        ["이미지 연동",row.imageEvidence==="CODE_MATCH"?"상품 코드 일치 · 실물 추가 확인":"연동 근거 미확인"],
        ["일정/출시일",row.date||"확인 중"]]){
        d.append(elt("dt",k),elt("dd",v));
      }
      content.append(d,elt("p","기술 검증: 이미지 코드 일치 ≠ 동일 인쇄판·실물 등급·판매 체결 증거.","v676-warning"));
      if(row.source){const a=elt("a","원문 출처 확인");a.href=row.source;a.target="_blank";a.rel="noopener noreferrer";content.append(a);}
      const body=elt("div",null,"v676-hero");body.append(media,content);
      detail.append(close,body);detail.hidden=false;detail.scrollIntoView({behavior:"smooth",block:"start"});
    }
    function tiles(){
      const filtered=filterRows(rows,mode);
      grid.replaceChildren();
      const shown=filtered.slice(0,limit);
      for(const row of shown){
        const b=makeButton("",()=>panel(row),"v676-tile");
        const media=elt("div",null,"v676-tile-media");
        if(row.image){const img=elt("img");img.src=row.image;img.alt="";img.loading="lazy";img.onerror=()=>{media.replaceChildren(elt("span","이미지 확인 필요"))};media.append(img);}
        else media.append(elt("span",row.group==="event"?"행사 이미지 확인 중":"사진 연결 대기"));
        const info=elt("div",null,"v676-tile-info");
        info.append(elt("span",(GEN_LABEL[row.region]||row.region)+" · "+row.category,"v676-eyebrow"),
          elt("strong",row.name),elt("small",row.imageEvidence==="CODE_MATCH"?"상품 코드 연결됨":"증빙 추가 필요"));
        b.append(media,info);grid.append(b);
      }
      if(filtered.length>shown.length)grid.append(makeButton("더 보기 ("+shown.length+"/"+filtered.length+")",()=>{limit+=48;tiles();},"v676-more"));
      if(!filtered.length)grid.append(elt("p","조건에 맞는 자료가 없습니다. 미수집과 판매가 0원은 다릅니다.","v676-empty"));
      summary.replaceChildren();
      const counts=[
        ["확인 대상",rows.length],["카드",rows.filter(x=>x.group==="card").length],
        ["BOX·상품",rows.filter(x=>x.group==="box").length],["행사·콜라보",rows.filter(x=>x.group==="event").length],
        ["이미지 연결",rows.filter(x=>x.imageEvidence==="CODE_MATCH").length]
      ];
      for(const [label,value] of counts){const tile=elt("div",null,"v676-stat");tile.append(elt("strong",value),elt("span",label));summary.append(tile);}
      status.textContent=(unavailable.length?"일부 자료 확인 대기 ("+unavailable.join(", ")+"). ":"")+"현재 기기에 있는 검증/후보 자료만 표시합니다. 가격·등급·이미지 판본은 임의 추정하지 않습니다.";
    }
    function tabs(target,items,key){
      target.replaceChildren();
      for(const [value,label] of items){
        const b=makeButton(label,()=>{mode[key]=value;limit=48;detail.hidden=true;tabs(kinds,[["all","전체"],["card","카드"],["box","BOX"],["event","행사·콜라보"]],"group");tabs(countries,[["ALL","전체 판본"],["KR","한판"],["JP","일판"],["US","미판"],["CN","중국판"]],"country");tabs(games,[["all","전체 게임"],["pokemon","포켓몬"],["onepiece","원피스"],["naruto","나루토"]],"game");tiles();},"v676-choice");
        b.setAttribute("aria-pressed",String(mode[key]===value));target.append(b);
      }
    }
    function selectors(){
      tabs(kinds,[["all","전체"],["card","카드"],["box","BOX"],["event","행사·콜라보"]],"group");
      tabs(countries,[["ALL","전체 판본"],["KR","한판"],["JP","일판"],["US","미판"],["CN","중국판"]],"country");
      tabs(games,[["all","전체 게임"],["pokemon","포켓몬"],["onepiece","원피스"],["naruto","나루토"]],"game");
    }
    search.addEventListener("input",()=>{mode.search=search.value;limit=48;tiles();});
    selectors();
    (async function(){
      const [catalog,events]=await Promise.allSettled([fetchJSON("/api/local-card-images"),fetchJSON("/promo_events.json")]);
      const local=catalog.status==="fulfilled"&&catalog.value?.ok===true&&catalog.value.version===46?catalog.value:null;
      const eventRows=events.status==="fulfilled"&&Array.isArray(events.value?.items)?events.value:null;
      unavailable=(!local?["이미지·상품 연결"]:[]).concat(!eventRows?["행사 자료"]:[]);
      rows=normalize(local,eventRows);tiles();
    })().catch(()=>{status.textContent="기기 자료를 표시하지 못했습니다. 기존 데이터는 수정하지 않았습니다.";});
  }
  return {normalize,filterRows,safeLink,imagePath,officialGame,start};
});
