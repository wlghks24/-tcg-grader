/* V626 standalone, free and dependency-free official product browser.
 * Intentionally separate from the historically watched box_knowledge_stats.js.
 * Information is a curated offline snapshot, NOT completed sales or live stock.
 */
(function (root, make) {
  "use strict";
  const api = make();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root && root.document) {
    root.TcgOfficialBoxV626 = api;
    const launch = () => api.mount(root.document);
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", launch, { once: true });
    } else launch();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const HOSTS = Object.freeze({
    "Pokémon": ["pokemoncard.co.kr", "pokemon-card.com"],
    "ONE PIECE": ["onepiece-cardgame.kr"],
    "GUNDAM CARD GAME": ["gundam-gcg.com"],
    "Digimon Card Game": ["digimoncard.com"],
    "Star Wars: Unlimited": ["starwarsunlimited.com"],
    "DRAGON BALL SUPER: FUSION WORLD": ["dbs-cardgame.com"],
    "Yu-Gi-Oh!": ["yugioh-card.com"],
    "Disney Lorcana": ["disneylorcana.com"],
    "Godzilla Card Game": ["godzilla-cardgame.com"],
    "Palworld OFFICIAL CARD GAME": ["palworld-official-cardgame.com"],
    "Magic: The Gathering": ["magic.wizards.com"],
    "NARUTO": ["narutotcgmythos.com"],
    "UNION ARENA": ["unionarena-tcg.com"],
    "Weiß Schwarz": ["ws-tcg.com"],
    "Flesh and Blood TCG": ["fabtcg.com"],
    "Final Fantasy TCG": ["fftcg.square-enix-games.com"],
    "Cardfight!! Vanguard": ["cf-vanguard.com"],
    "hololive OFFICIAL CARD GAME": ["hololive-official-cardgame.com"],
    "Shadowverse: Evolve": ["shadowverse-evolve.com"],
    "Riftbound: League of Legends": ["merch.riotgames.com"],
    "Grand Archive TCG": ["gatcg.com"],
    "Sorcery: Contested Realm": ["sorcerytcg.com"],
    "Elestrals": ["shopelestrals.com"],
    "UniVersus": ["uvsgames.com"],
    "WIXOSS": ["takaratomy.co.jp"],
    "CookieRun: Braverse TCG": ["cookierunbraverse.com"],
    "Alpha Clash": ["alphaclashtcg.com"],
    "Rush of Ikorr": ["upperdeckstore.com"],
    "MetaZoo": ["metazootcg.com"],
    "Cyberpunk TCG": ["cyberpunktcg.com"]
  });
  const TYPES = Object.freeze({
    BOX: "미개봉 BOX",
    BOOSTER_PACK: "낱팩 / 부스터",
    PRERELEASE_BOX: "프리릴리즈 BOX"
  });
  const COUNTRIES = ["KR", "JP", "US"];
  const PAGE_SIZE = 12;

  function trustedSource(value, game) {
    if (typeof value !== "string" || value.length > 500) return false;
    const hosts = HOSTS[game];
    if (!hosts) return false;
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password &&
        (!url.port || url.port === "443") && !url.hash &&
        hosts.some(h => url.hostname === h || url.hostname.endsWith("." + h));
    } catch (_) { return false; }
  }
  function validProduct(p) {
    if (!p || typeof p !== "object" || Array.isArray(p)) return false;
    if (!Object.prototype.hasOwnProperty.call(TYPES, p.product_type)) return false;
    if (!COUNTRIES.includes(p.country)) return false;
    if (![p.name, p.set_code, p.id].every(x => typeof x === "string" && x.length > 0 && x.length <= 200)) return false;
    if (p.set_code.startsWith("LOCAL-") && p.set_code_verified !== false) return false;
    if (!trustedSource(p.source, p.game)) return false;
    if (!p.release_date && p.product_type !== "PRERELEASE_BOX" && !(p.release_date_unverified === true && typeof p.source_checked_at === "string")) return false;
    if (p.release_date && p.release_date_unverified === true) return false;
    if (p.product_type === "BOOSTER_PACK" && p.packs_per_box !== undefined) return false;
    if (p.product_type !== "BOOSTER_PACK" &&
        (!Number.isInteger(p.packs_per_box) || p.packs_per_box < 1 || p.packs_per_box > 100)) return false;
    const m = p.msrp;
    if (m !== undefined) {
      if (!m || typeof m !== "object" || !Number.isFinite(m.amount) || m.amount <= 0) return false;
      if (m.currency !== ({KR:"KRW",JP:"JPY",US:"USD"}[p.country])) return false;
      if (m.unit !== (p.product_type === "BOOSTER_PACK" ? "PACK" : "BOX")) return false;
    }
    return true;
  }
  function normalizeProducts(raw) {
    if (!raw || raw.schema_version !== 1 || !Array.isArray(raw.products)) return [];
    const seen = new Set();
    const safe = [];
    for (const p of raw.products) {
      if (!validProduct(p) || seen.has(p.id)) continue;
      seen.add(p.id);
      safe.push(p);
    }
    return safe;
  }
  function formatPrice(msrp) {
    if (!msrp || !Number.isFinite(msrp.amount) || msrp.amount <= 0) return "제조사 정가 미확인";
    let value;
    if (msrp.currency === "KRW") value = new Intl.NumberFormat("ko-KR",{maximumFractionDigits:0}).format(msrp.amount) + "원";
    else if (msrp.currency === "JPY") value = "¥" + new Intl.NumberFormat("ja-JP",{maximumFractionDigits:0}).format(msrp.amount);
    else if (msrp.currency === "USD") value = "$" + msrp.amount.toFixed(2);
    else return "제조사 정가 미확인";
    return "제조사 정가 " + value + " / " + (msrp.unit === "BOX" ? "BOX" : "팩");
  }
  function releaseLabels(p) {
    const labels = [];
    if (p.product_type === "PRERELEASE_BOX" && p.event_start_date)
      labels.push("프리릴리즈 행사 " + p.event_start_date);
    if (p.release_date) labels.push("상품 발매 " + p.release_date);
    else if (p.product_type === "PRERELEASE_BOX") labels.push("BOX 발매일 미확인");
    if (p.set_release_date) labels.push("세트 발매 " + p.set_release_date);
    if (!labels.length) labels.push("발매일 미확인");
    return labels;
  }
  function filterProducts(rows, filters) {
    const game = filters.game || "ALL", country = filters.country || "ALL";
    const kind = filters.kind || "ALL", term = (filters.search || "").trim().toLocaleLowerCase();
    return rows.filter(p =>
      (game === "ALL" || p.game === game) &&
      (country === "ALL" || p.country === country) &&
      (kind === "ALL" || p.product_type === kind) &&
      (!term || [p.name,p.set_code,p.game,p.notes || ""].join(" ").toLocaleLowerCase().includes(term))
    ).sort((a,b) => {
      const aDate = a.release_date || a.event_start_date || a.set_release_date || "";
      const bDate = b.release_date || b.event_start_date || b.set_release_date || "";
      return bDate.localeCompare(aDate) || a.id.localeCompare(b.id);
    });
  }
  function paginate(rows, page, pageSize) {
    const limit = Number.isInteger(pageSize) && pageSize > 0 ? Math.min(pageSize, 40) : PAGE_SIZE;
    const pages = Math.max(1, Math.ceil(rows.length / limit));
    const current = Number.isInteger(page) ? Math.max(0, Math.min(page, pages - 1)) : 0;
    return { rows: rows.slice(current * limit, (current + 1) * limit), page:current, pages, total:rows.length };
  }
  function mount(doc) {
    const root = doc.getElementById("boxV626App");
    if (!root) return;
    const gameControl = doc.getElementById("boxV626Game");
    const regionControl = doc.getElementById("boxV626Region");
    const typeControl = doc.getElementById("boxV626Type");
    const searchControl = doc.getElementById("boxV626Search");
    const filtersForm = doc.getElementById("boxV626Filters");
    const body = doc.getElementById("boxV626Results");
    const status = doc.getElementById("boxV626Status");
    const next = doc.getElementById("boxV626Next");
    const previous = doc.getElementById("boxV626Previous");
    const counter = doc.getElementById("boxV626Page");
    if (![gameControl,regionControl,typeControl,searchControl,body,status,next,previous,counter].every(Boolean)) return;
    let products=[],page=0,rejectedCount=0,supplementWarning=false,registry=null;
    const textNode = (tag,text,className) => {
      const el=doc.createElement(tag);
      if (className) el.className=className;
      el.textContent=String(text);
      return el;
    };
    const redraw = () => {
      const chosen=filterProducts(products,{game:gameControl.value,country:regionControl.value,kind:typeControl.value,search:searchControl.value});
      const paged=paginate(chosen,page,PAGE_SIZE);
      page=paged.page;
      body.replaceChildren();
      for (const p of paged.rows) {
        const card=doc.createElement("article");card.className="official-card";
        card.appendChild(textNode("span",(TYPES[p.product_type] || p.product_type)+" · "+p.country,"official-kind"));
        card.appendChild(textNode("h2",p.name));
        card.appendChild(textNode("p",p.set_code + (p.set_code_verified === false ? " · 내부 임시 코드(공식 코드 미확인)" : ""),"official-meta"));
        card.appendChild(textNode("p",releaseLabels(p).join(" · "),"official-meta"));
        const specs=[];
        if (p.packs_per_box) specs.push("BOX당 "+p.packs_per_box+"팩");
        if (p.cards_per_pack) specs.push("1팩 "+p.cards_per_pack+"장");
        card.appendChild(textNode("p",specs.join(" · ") || "팩 구성 미확인","official-meta"));
        card.appendChild(textNode("p",formatPrice(p.msrp),"official-price"));
        if (p.notes) card.appendChild(textNode("p",p.notes,"official-note"));
        const link=doc.createElement("a");
        link.href=p.source;link.target="_blank";link.rel="noopener noreferrer";
        link.textContent="제조사 원문 열기 ↗";
        // Offer recovery routes FIRST: a deep product URL may 404 despite a valid index.
        const routes=typeof globalThis!=="undefined"&&globalThis.TcgSourceRoutesV633;
        const fallback=routes&&registry?routes.sourceRoutes(p,registry):null;
        if(fallback){
          if(fallback.officialIndex){
            const hub=doc.createElement("a");
            hub.href=fallback.officialIndex;hub.target="_blank";hub.rel="noopener noreferrer";
            hub.textContent="제조사 제품 목록 ↗";card.appendChild(hub);
          }
          if(fallback.manufacturerSiteSearch){
            const lookup=doc.createElement("a");
            lookup.href=fallback.manufacturerSiteSearch;lookup.target="_blank";lookup.rel="noopener noreferrer";
            lookup.textContent="원문 404·접속 실패 시 제조사 사이트 검색 ↗";card.appendChild(lookup);
          }
          if(fallback.alternateSiteSearch){
            const alternate=doc.createElement("a");
            alternate.href=fallback.alternateSiteSearch;alternate.target="_blank";alternate.rel="noopener noreferrer";
            alternate.textContent="Google 검색 장애 시 Bing 제조사 검색 ↗";card.appendChild(alternate);
          }
          card.appendChild(textNode("p","제조사 사이트 검색 결과는 후보일 뿐 상품 확정 근거가 아닙니다","official-meta"));
        }
        card.appendChild(link);
        card.appendChild(textNode("p","상세 원문 링크 404·403·429·일시 장애 가능 · 유효성 미확인","official-meta"));
        body.appendChild(card);
      }
      if (!paged.total) body.appendChild(textNode("p","선택 조건에 일치하는 공식 상품 기록이 없습니다.","official-empty"));
      counter.textContent=(paged.page+1)+" / "+paged.pages+"페이지";
      previous.disabled=paged.page===0;next.disabled=paged.page>=paged.pages-1;
      status.textContent="등록된 공식 상품 "+products.length+"건 · 현재 필터 "+paged.total+"건 (실시간 재고·거래시세 아님)" + (rejectedCount ? " · 검증 실패 "+rejectedCount+"건 제외" : "") + (supplementWarning ? " · 추가 제조사 자료 일부 로드 실패(실제 표시 건수 기준)" : "");
    };
    function changed() {page=0;redraw();}
    if (filtersForm) filtersForm.addEventListener("submit",e=>e.preventDefault());
    for (const ctrl of [gameControl,regionControl,typeControl]) ctrl.addEventListener("change",changed);
    searchControl.addEventListener("input",changed);
    previous.addEventListener("click",()=>{page--;redraw();});
    next.addEventListener("click",()=>{page++;redraw();});
    status.textContent="로컬 공식 상품 목록 불러오는 중…";
    root.setAttribute("aria-busy","true");
    // Uses only a same-directory static JSON bundled with the app.
    fetch("./tcg_official_product_catalog_v599.json",{cache:"no-store"})
      .then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json();})
      .then(async json=>{
        // Supplemental manufacturer proofs remain separate from the pinned V599 snapshot.
        let additions=[];
        try {
          const r=await fetch("./tcg_official_product_supplement_v630.json",{cache:"no-store"});
          if(!r.ok)throw Error("SUPPLEMENT_NOT_AVAILABLE");
          const raw=await r.json();
          if(raw?.schema_version!==1 ||
             raw?.type!=="official_product_specifications_supplement" ||
             raw?.base_catalog!=="tcg_official_product_catalog_v599.json" ||
             !Array.isArray(raw.products))throw Error("INVALID_SUPPLEMENT");
          additions=raw.products;
        } catch (_) { supplementWarning=true; }
        // V636 is an optional second manufacturer-verified supplement.
        // Fail closed for invalid file contents; preserve all earlier 63 rows.
        try {
          const r=await fetch("./tcg_official_product_supplement_v636.json",{cache:"no-store"});
          if(!r.ok)throw Error("V636_NOT_AVAILABLE");
          const extra=await r.json();
          if(extra?.schema_version!==1 ||
             extra?.type!=="official_product_specifications_supplement" ||
             extra?.base_catalog!=="tcg_official_product_catalog_v599.json" ||
             extra?.append_after!=="tcg_official_product_supplement_v630.json" ||
             !Array.isArray(extra.products))throw Error("INVALID_V636_SUPPLEMENT");
          additions=additions.concat(extra.products);
        } catch (_) { supplementWarning=true; }
        // V637 is an optional appended manufacturer proof set.
        try {
          const r=await fetch("./tcg_official_product_supplement_v637.json",{cache:"no-store"});
          if(!r.ok)throw Error("V637_NOT_AVAILABLE");
          const newer=await r.json();
          if(newer?.schema_version!==1||
             newer?.type!=="official_product_specifications_supplement"||
             newer?.base_catalog!=="tcg_official_product_catalog_v599.json"||
             newer?.append_after!=="tcg_official_product_supplement_v636.json"||
             !Array.isArray(newer.products))throw Error("INVALID_V637");
          additions=additions.concat(newer.products);
        }catch(_){supplementWarning=true;}
        // V649 adds four newly-covered games; optional and never erases older rows.
        try {
          const r=await fetch("./tcg_official_product_supplement_v649.json",{cache:"no-store"});
          if(!r.ok)throw Error("V649_NOT_AVAILABLE");
          const supplement=await r.json();
          if(supplement?.schema_version!==1||
             supplement?.type!=="official_product_specifications_supplement"||
             supplement?.base_catalog!=="tcg_official_product_catalog_v599.json"||
             supplement?.append_after!=="tcg_official_product_supplement_v637.json"||
             !Array.isArray(supplement.products))throw Error("INVALID_V649");
          additions=additions.concat(supplement.products);
        }catch(_){supplementWarning=true;}
        if (json?.schema_version===1 && Array.isArray(json.products)) {
          json={...json,products:json.products.concat(additions)};
        }
        if (json?.schema_version!==1 || !Array.isArray(json?.products)) throw Error("INVALID_CATALOG");
        // Registry unavailable must never hide locally validated official product samples.
        try{
          const r=await fetch("./tcg_game_registry.json",{cache:"no-store"});
          if(r.ok){
            const result=await r.json();
            if(result.schema_version===1&&Array.isArray(result.games)&&result.games.length===30)
              registry=result;
          }
        }catch(_){registry=null;}
        products=normalizeProducts(json);
        rejectedCount=json.products.length-products.length;
        const games=[...new Set(products.map(p=>p.game))].sort((a,b)=>a.localeCompare(b));
        for (const game of games) {
          const option=doc.createElement("option");option.value=game;option.textContent=game;
          gameControl.appendChild(option);
        }
        redraw();
      })
      .catch(()=>{
        status.textContent="상품 목록을 불러오지 못했습니다. 인터넷 연결 또는 로컬 서버 설정을 확인하세요.";
        body.replaceChildren(textNode("p","검증된 상품 데이터를 불러올 수 없어 결과를 표시하지 않습니다."));
        counter.textContent="–";next.disabled=true;previous.disabled=true;
      })
      .finally(()=>{root.setAttribute("aria-busy","false");});
  }
  return {trustedSource,validProduct,normalizeProducts,formatPrice,releaseLabels,filterProducts,paginate,mount};
});
