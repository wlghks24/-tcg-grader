/* V676 opt-in, read-only evidence gallery. Never mutate collection or train. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TCGUnifiedGalleryV676 = api;
  if (root && root.document) {
    const start = () => api.mount(root.document);
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";
  const REGIONS = ["ALL", "KR", "JP", "US", "CN"];
  const games = { pokemon:"포켓몬", onepiece:"원피스", naruto:"나루토" };
  const allowSource = ["pokemon-card.com","pokemon.cn","pokemon.co.jp","pokemon.com",
    "pokemonkorea.co.kr","pokemon-card.co.kr","onepiece-cardgame.kr",
    "onepiece-cardgame.com","naruto-official.com","naruto-ncg.cn",
    "naruto-cardgame.com","kream.co.kr","tcgplayer.com","snkrdunk.com",
    "ebay.com","ebay.co.jp","cardmarket.com","psacard.com","pavilion-tcg.com"];
  const IMG = /^\/api\/local-card-images\/file\/([a-f0-9]{32})$/;
  const short = (v, n=150) => typeof v === "string" ? v.trim().slice(0,n) : "";
  function gameId(v) {
    const s = short(v,120).toLowerCase();
    if (s === "pokemon" || /포켓몬|pok[eé]mon/.test(s)) return "pokemon";
    if (s === "onepiece" || /원피스|one[\s-]*piece/.test(s)) return "onepiece";
    if (s === "naruto" || /나루토/.test(s)) return "naruto";
    return "";
  }
  function regionTab(v) {
    return v === "CN-S" || v === "CN-T" ? "CN" : REGIONS.includes(v) ? v : "";
  }
  function safeSource(v) {
    if (typeof v !== "string" || v.length > 2048) return "";
    try {
      const u = new URL(v);
      if (u.protocol !== "https:" || u.username || u.password ||
          (u.port && u.port !== "443") || u.hash) return "";
      const host = u.hostname.toLowerCase();
      return allowSource.some(h => host === h || host.endsWith("." + h)) ? u.href : "";
    } catch (_) { return ""; }
  }
  function localImage(id) {
    return typeof id === "string" && /^[a-f0-9]{32}$/.test(id) ?
      "/api/local-card-images/file/" + id : "";
  }
  function stringArray(v, max) {
    return Array.isArray(v) && v.length <= max ? v : [];
  }
  function joinCatalog(data) {
    if (!data || data.ok !== true) return [];
    const images = new Map(), conflicted = new Set();
    for (const row of stringArray(data.local_catalog, 2500)) {
      if (!row || typeof row !== "object" || !localImage(row.id)) continue;
      if (!gameId(row.game_id) || !regionTab(row.region)) continue;
      if (conflicted.has(row.id)) continue;
      if (images.has(row.id)) { images.delete(row.id); conflicted.add(row.id); }
      else images.set(row.id, row);
    }
    const unique = new Map();
    for (const match of stringArray(data.catalog_matches, 2500)) {
      if (!match || match.match !== "CODE_MATCH" ||
          typeof match.source_record_id !== "string" ||
          !/^[a-f0-9]{32}$/.test(match.source_record_id) ||
          !localImage(match.id)) continue;
      const id = match.source_record_id;
      if (unique.has(id)) unique.set(id, null);
      else unique.set(id, match);
    }
    const used = new Set(), out = [], seen = new Set();
    for (const row of stringArray(data.source_catalog, 2500)) {
      if (!row || !/^[a-f0-9]{32}$/.test(short(row.source_record_id,40)) ||
          seen.has(row.source_record_id)) continue;
      const game = gameId(row.game_id), region = regionTab(row.region);
      const kind = ["CARD", "PROMO"].includes(row.kind) ? "CARD" :
          ["BOX","PACK","DECK","COLLECTION","BUNDLE"].includes(row.kind) ? "BOX" : "";
      if (!game || !region || !kind || !short(row.name)) continue;
      seen.add(row.source_record_id);
      let img = "", metadata = {}, imageState = "사진 검증 대기";
      const match = unique.get(row.source_record_id);
      if (match && !used.has(match.id) &&
          match.game_id === row.game_id && match.region === row.region &&
          match.kind === row.kind && match.catalog_kind === row.kind) {
        const local = images.get(match.id);
        if (local && local.game_id === row.game_id &&
            local.region === row.region && local.kind === row.kind &&
            local.linked_to_existing_catalog === true &&
            local.identity_verification === "CODE_MATCH" &&
            local.linked_source_record_id === row.source_record_id) {
          img = localImage(match.id);
          metadata = local.card_metadata && typeof local.card_metadata === "object" ?
            local.card_metadata : {};
          imageState = "동일 코드 이미지 연결 · 판본 실물 확인 별도";
          used.add(match.id);
        }
      }
      out.push({
        key: "source:" + row.source_record_id, game, region, edition: row.region, kind,
        title: short(row.name), code: stringArray(row.product_codes,24).map(x=>short(x,30)).join(" · "),
        image: img, imageState, source: safeSource(row.source_url), metadata,
        sourceState: row.source_health === "HEALTHY" ? "출처 연결 확인" : "출처 재확인 대기",
        date: short(row.observed_release_date,10), price: "", pricing: "실거래·매도가 검증 대기",
        review: "원본 사진/인증서와 홀드아웃 검증 전 등급 산출 보류"
      });
      if (out.length >= 1500) break;
    }
    // Unlinked photos stay independent; never attach them by fuzzy title matching.
    for (const [id, local] of images) {
      if (used.has(id) || out.length >= 2000) continue;
      const game=gameId(local.game_id),region=regionTab(local.region);
      const kind=["CARD","PROMO"].includes(local.kind)?"CARD":"BOX";
      out.push({
        key:"unlinked:"+id,game,region,edition:local.region,kind,
        title:short(local.name)||"로컬 사진",code:"",
        image:localImage(id),imageState:"미연결 이미지 · 판본/코드 확인 필요",
        metadata:local.card_metadata||{},source:safeSource(local.source_url),
        sourceState:"상품 연동 미검증",date:"",price:"",pricing:"시세 근거 없음",
        review:"사진만으로 등급·판매가 확정 불가"
      });
    }
    return out;
  }
  function events(data) {
    const out=[],seen=new Set();
    for (const row of stringArray(data && data.items,2000)) {
      if (!row || typeof row !== "object") continue;
      const game=gameId(row.game),region=regionTab(row.region);
      const title=short(row.name_ko || row.name_native || row.title);
      if (!game || !region || !title) continue;
      const url=safeSource(row.source);
      const key=[game,row.region,title,url].join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      let date="";
      if (row.tracking_only !== true && row.date_precision !== "unannounced" &&
          /^\d{4}-\d{2}-\d{2}$/.test(short(row.start_date,10))) {
        const v=row.start_date, parsed=new Date(v+"T00:00:00Z");
        if (!Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0,10)===v) date=v;
      }
      out.push({
        key:"event:"+key,game,region,edition:row.region,kind:"EVENT",
        title,code:short(row.category),image:"",imageState:"공식 행사 이미지 별도 확인",
        source:url,sourceState:row.source_grade==="official" && url?"공식 출처 기재 · 날짜 증빙 별도":"출처 재검증 대기",
        date,metadata:{},pricing:"판매가격과 무관",price:"",
        review:short(row.condition||row.status,110)||"행사 세부사항 확인 필요"
      });
      if(out.length>=1200)break;
    }
    return out;
  }
  function boxes(data) {
    const out=[], seen=new Set();
    for(const row of stringArray(data&&data.items,3000)){
      if(!row||typeof row!=="object"||row.asset!=="BOX")continue;
      const game=gameId(row.game),region=regionTab(row.region),title=short(row.name);
      if(!game||!region||!title)continue;
      const code=short(row.product_code,45),source=safeSource(row.source);
      const key=[game,row.region,code||title,source].join("|");
      if(seen.has(key))continue;seen.add(key);
      const rawPrice=short(row.official_price,80);
      const displayPrice=/^(?:₩\s*[0-9][0-9,]*|¥\s*[0-9][0-9,]*|\$\s*[0-9][0-9,.]*)/.test(rawPrice)?rawPrice:"";
      out.push({
        key:"box:"+key,game,region,edition:row.region,kind:"BOX",title,code,
        image:"",imageState:"정확한 BOX 이미지 검증 후 연결",metadata:{},
        source,sourceState:"등록 상품 · 원문 재확인 필요",
        date:short(row.release_date,10),
        price:displayPrice && displayPrice!=="확인 중"?displayPrice:"",
        pricing:"자료 기재 표시가격 · 현재 실거래가/판매가 아님",
        review:"BOX 구성·재발매 여부 검증 필요"
      });
      if(out.length>=800)break;
    }
    return out;
  }
  function filterRows(rows, selection) {
    const query=short(selection?.query,80).toLocaleLowerCase();
    return stringArray(rows,5000).filter(row=>
      (!selection?.game || selection.game==="ALL" || row.game===selection.game) &&
      (!selection?.region || selection.region==="ALL" || row.region===selection.region) &&
      (!selection?.type || selection.type==="ALL" || row.kind===selection.type) &&
      (!query || [row.title,row.code,row.edition,row.metadata?.set_name,
         row.metadata?.card_number,row.metadata?.generation]
          .some(value=>short(value,180).toLocaleLowerCase().includes(query)))
    );
  }
  const el = (doc,tag,text,className) => {
    const node=doc.createElement(tag);
    if(text!==undefined && text!==null)node.textContent=String(text);
    if(className)node.className=className;
    return node;
  };
  function draw(doc, container, items, selection, limit) {
    container.replaceChildren();
    const rows=filterRows(items,selection).slice(0,limit);
    for(const row of rows) {
      const card=el(doc,"article",null,"fusion-card");
      const cover=el(doc,"div",null,"fusion-cover");
      if(row.image && IMG.test(row.image)) {
        const img=el(doc,"img");img.src=row.image;img.loading="lazy";
        img.alt=row.title+" · 로컬 이미지";img.decoding="async";
        img.onerror=()=>{img.remove();cover.append(el(doc,"span","이미지 확인 필요","fusion-no-photo"));};
        cover.append(img);
      }else cover.append(el(doc,"span",row.kind==="EVENT"?"EVENT":row.kind==="BOX"?"BOX":"CARD","fusion-no-photo"));
      const body=el(doc,"div",null,"fusion-body");
      const chips=el(doc,"div",null,"fusion-chips");
      chips.append(el(doc,"span",games[row.game]||"TCG","fusion-chip"),
        el(doc,"span",row.edition,"fusion-chip"),el(doc,"span",row.kind,"fusion-chip"));
      body.append(chips,el(doc,"h3",row.title));
      const grid=el(doc,"dl",null,"fusion-facts");
      const details=[
        ["세트/번호",row.code||short(row.metadata?.card_number)||"확인 대기"],
        ["세대/시리즈",short(row.metadata?.generation)||"확인 대기"],
        ["이미지",row.imageState],
        ["시세/판매가",row.price?row.price+" · "+row.pricing:row.pricing],
        ["등급/상태",row.review],
      ];
      if(row.date)details.splice(1,0,["자료상 날짜",row.date]);
      for(const [key,value] of details){
        const dt=el(doc,"dt",key),dd=el(doc,"dd",value);
        grid.append(dt,dd);
      }
      body.append(grid,el(doc,"p",row.sourceState,"fusion-footnote"));
      if(row.source){const a=el(doc,"a","출처 원문 보기","fusion-source");a.href=row.source;a.target="_blank";a.rel="noopener noreferrer";body.append(a);}
      card.append(cover,body);container.append(card);
    }
    return {total:filterRows(items,selection).length,shown:rows.length};
  }
  async function fetchJson(url) {
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),6500);
    try {
      const response=await fetch(url,{cache:"no-store",credentials:"same-origin",signal:controller.signal});
      if(!response.ok)throw Error("HTTP "+response.status);
      const size=Number(response.headers.get("Content-Length")||0);
      if(Number.isFinite(size)&&size>9000000)throw Error("response too large");
      return await response.json();
    } finally {clearTimeout(timer);}
  }
  function mount(doc) {
    const panel=doc.getElementById("fusion-app");
    if(!panel)return;
    const list=doc.getElementById("fusion-list"),status=doc.getElementById("fusion-status"),
      count=doc.getElementById("fusion-count"),more=doc.getElementById("fusion-more"),
      search=doc.getElementById("fusion-query");
    if(!list||!status||!count||!more||!search)return;
    let items=[],show=24,selection={game:"ALL",region:"ALL",type:"ALL",query:""};
    const rerender=()=>{
      const v=draw(doc,list,items,selection,show);
      count.textContent=v.total+"개 중 "+v.shown+"개 표시";
      more.hidden=v.total<=v.shown;
    };
    for(const button of doc.querySelectorAll("[data-fusion-filter]")){
      button.addEventListener("click",()=>{
        const field=button.getAttribute("data-fusion-filter"),value=button.getAttribute("data-value");
        if(!["game","region","type"].includes(field))return;
        selection[field]=value;show=24;
        for(const peer of doc.querySelectorAll('[data-fusion-filter="'+field+'"]')){
          peer.setAttribute("aria-pressed",String(peer===button));
        }
        rerender();
      });
    }
    search.addEventListener("input",()=>{selection.query=search.value;show=24;rerender();});
    more.addEventListener("click",()=>{show=Math.min(show+24,300);rerender();});
    const refresh=doc.getElementById("fusion-refresh");
    const load=async()=>{
      if(refresh)refresh.disabled=true;status.textContent="로컬 자료 읽는 중 · 저장/변경 없음";
      try{
        const results=await Promise.allSettled([
          fetchJson("/api/local-card-images/catalog-links"),
          fetchJson("/promo_events.json"),
          fetchJson("/market_watch.json"),
        ]);
        const catalogs=results[0].status==="fulfilled"?joinCatalog(results[0].value):[];
        const ev=results[1].status==="fulfilled"?events(results[1].value):[];
        const b=results[2].status==="fulfilled"?boxes(results[2].value):[];
        items=[...catalogs,...ev,...b];
        const counts={
          CARD:items.filter(x=>x.kind==="CARD").length,
          BOX:items.filter(x=>x.kind==="BOX").length,
          EVENT:items.filter(x=>x.kind==="EVENT").length,
          LINKED:catalogs.filter(x=>x.image&&x.imageState.startsWith("동일")).length,
        };
        for(const kind of Object.keys(counts)){
          const node=doc.getElementById("fusion-stat-"+kind.toLowerCase());
          if(node)node.textContent=String(counts[kind]);
        }
        status.textContent=items.length ?
          "이미지 연결 "+counts.LINKED+
          "건 · 카드/BOX/행사 "+items.length+"건 · 출처 없는 값은 표시하지 않음":
          "표시 가능한 검증 자료 없음 · 로컬 서버/출처를 확인하세요";
        if(results.some(r=>r.status==="rejected"))status.textContent+=" · 일부 자료 읽기 실패";
        rerender();
      }catch(_){status.textContent="자료 형식 검증 대기 · 기존 데이터는 변경되지 않았습니다";}
      finally{if(refresh)refresh.disabled=false;}
    };
    if(refresh)refresh.addEventListener("click",load);
    load();
  }
  return Object.freeze({gameId,regionTab,safeSource,localImage,joinCatalog,events,boxes,filterRows,draw,mount});
});
