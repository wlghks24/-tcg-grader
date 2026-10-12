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
    "Pokémon": ["pokemoncard.co.kr", "pokemon-card.com", "pokemon.com"],
    "ONE PIECE": ["onepiece-cardgame.kr", "en.onepiece-cardgame.com", "cp.onepiece-cardgame.com"],
    "GUNDAM CARD GAME": ["gundam-gcg.com"],
    "Digimon Card Game": ["digimoncard.com"],
    "Star Wars: Unlimited": ["starwarsunlimited.com"],
    "DRAGON BALL SUPER: FUSION WORLD": ["dbs-cardgame.com"],
    "Yu-Gi-Oh!": ["yugioh-card.com", "yu-gi-oh.jp"],
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

  // V658: manufacturer-specific, fail-closed additive proof; never mark search leads as verified.
  function validateV657(doc, previous=[]) {
    const spec={
      "lorcana-US-shimmering-skies-2024": ["Disney Lorcana","US","2024-08-23","12","LOCAL-LOR-SHIMMERING-SKIES-US"],
      "digi-US-EX12-digital-world-shambala-2026": ["Digimon Card Game","US","2026-07-03","12","EX-12"],
      "swu-US-spark-of-rebellion-2024": ["Star Wars: Unlimited","US","2024-03-08","16","LOCAL-SWU-SPARK-OF-REBELLION-US"]
    };
    if(!doc||doc.schema_version!==1||doc.type!=="official_product_specifications_supplement"||
       doc.base_catalog!=="tcg_official_product_catalog_v599.json"||
       doc.append_after!=="tcg_official_product_supplement_v654.json"||
       doc.policy?.no_paid_dependency!==true||!Array.isArray(doc.products)||doc.products.length!==3)
       throw Error("INVALID_V657_CHAIN");
    const known=new Set(previous.map(p=>p.id)),seen=new Set();
    const allowed=new Set(["id","game","country","product_type","set_code","set_code_verified",
      "name","release_date","source","release_date_source","packs_per_box","cards_per_pack","notes"]);
    const actualNames={
      "lorcana-US-shimmering-skies-2024":"Disney Lorcana Shimmering Skies Booster Display Box",
      "digi-US-EX12-digital-world-shambala-2026":"DIGIMON CARD GAME EXTRA BOOSTER DIGITAL WORLD SHAMBALA [EX-12] Booster Box",
      "swu-US-spark-of-rebellion-2024":"Star Wars: Unlimited Spark of Rebellion Booster Display Box"
    };
    for(const p of doc.products){
      const row=p&&spec[p.id];
      if(!row||seen.has(p.id)||known.has(p.id)||!validProduct(p)||
         Object.keys(p).some(k=>!allowed.has(k))||
         p.name!==actualNames[p.id]||typeof p.notes!=="string"||
         (p.set_code.startsWith("LOCAL-")&&p.set_code_verified!==false)||
         p.game!==row[0]||p.country!==row[1]||p.product_type!=="BOX"||
         p.release_date!==row[2]||p.cards_per_pack!==row[3]||p.set_code!==row[4]||
         p.packs_per_box!==24||("msrp" in p)||
         ["market_price","verified_sales","verified_stock","pull_rate","psa_grade"].some(k=>k in p)||
         (p.release_date_source&&!trustedSource(p.release_date_source,p.game)))
         throw Error("UNTRUSTED_V657_PRODUCT");
      seen.add(p.id);
    }
    return doc.products;
  }

  // V659 two Japanese manufacturer source proofs, separate from promotions and prices.
  function validateV659(doc,previous=[]) {
    const spec={
      "pokemon-JP-SV9a-2025":{
        game:"Pokémon",country:"JP",set_code:"SV9a",
        name:"Pokémon Scarlet & Violet 熱風のアリーナ Booster BOX",release_date:"2025-03-14",
        source:"https://www.pokemon-card.com/products/sv/sv9a.html",
        release_date_source:null,packs_per_box:30,cards_per_pack:"5"},
      "onepiece-JP-OP13-2025":{
        game:"ONE PIECE",country:"JP",set_code:"OP-13",
        name:"ONE PIECE 受け継がれる意志 [OP-13] Booster BOX",release_date:"2025-08-23",
        source:"https://cp.onepiece-cardgame.com/festa/2025_summer/goods",
        release_date_source:"https://www.bandai.co.jp/catalog/item.php?jan_cd=4582769864865000",
        packs_per_box:24,cards_per_pack:"6"}
    };
    if(!doc||doc.schema_version!==1||doc.type!=="official_product_specifications_supplement"||
       doc.base_catalog!=="tcg_official_product_catalog_v599.json"||
       doc.append_after!=="tcg_official_product_supplement_v657.json"||
       doc.policy?.no_paid_dependency!==true||!Array.isArray(doc.products)||doc.products.length!==2)
       throw Error("INVALID_V659_CHAIN");
    const known=new Set(previous.map(p=>p.id)),seen=new Set();
    const allowed=new Set(["id","game","country","product_type","set_code","set_code_verified",
      "name","release_date","source","release_date_source","packs_per_box","cards_per_pack","notes"]);
    for(const p of doc.products){
      const s=p&&spec[p.id];
      if(!s||known.has(p.id)||seen.has(p.id)||!validProduct(p)||p.product_type!=="BOX"||
         Object.keys(p).some(k=>!allowed.has(k))||typeof p.notes!=="string"||
         Object.entries(s).some(([k,v])=>((p[k]===undefined?null:p[k])!==v))||
         ["msrp","market_price","verified_stock","verified_sales","pull_rate","psa_grade"].some(k=>k in p))
        throw Error("UNTRUSTED_V659_PRODUCT");
      seen.add(p.id);
    }
    return doc.products;
  }

  // V662: exact Japanese-market manufacturer records; boxes, not starter kits.
  function validateV662(doc,previous=[]) {
    const specs={
      "mtg-JP-ECL-play-booster-2026":{
        game:"Magic: The Gathering",country:"JP",product_type:"BOX",
        set_code:"LOCAL-MTG-ECL-JP",set_code_verified:false,
        name:"Magic: The Gathering Lorwyn Eclipsed Play Booster Display (Japanese market)",
        release_date:"2026-01-23",packs_per_box:30,cards_per_pack:"14",
        source:"https://magic.wizards.com/ja/news/feature/collecting-lorwyn-eclipsed",
        release_date_source:"https://magic.wizards.com/ja/news/announcements/everything-announced-for-magic-the-gathering-in-2026"
      },
      "ws-JP-ALL-bplb-2026":{
        game:"Weiß Schwarz",country:"JP",product_type:"BOX",
        set_code:"LOCAL-WS-ALL-LB-JP",set_code_verified:false,
        name:"Weiß Schwarz アサルトリリィ Last Bullet Booster BOX",
        release_date:"2026-02-27",packs_per_box:12,cards_per_pack:"8",
        source:"https://ws-tcg.com/products/all_bplb/",
        msrp:{currency:"JPY",amount:5280,unit:"BOX"}
      },
      "dbsfw-JP-FB10-cross-force-2026":{
        game:"DRAGON BALL SUPER: FUSION WORLD",country:"JP",product_type:"BOX",
        set_code:"FB10",name:"Dragon Ball Super Fusion World CROSS FORCE [FB10] Booster BOX",
        release_date:"2026-06-13",packs_per_box:24,cards_per_pack:"6",
        source:"https://www.dbs-cardgame.com/fw/jp/events/01_446.html",
        release_date_source:"https://www.dbs-cardgame.com/fw/jp/products/01_400.html"
      }
    };
    if(!doc||doc.schema_version!==1||doc.type!=="official_product_specifications_supplement"||
      doc.base_catalog!=="tcg_official_product_catalog_v599.json"||
      doc.append_after!=="tcg_official_product_supplement_v659.json"||
      doc.policy?.no_paid_dependency!==true||!Array.isArray(doc.products)||doc.products.length!==3)
      throw Error("INVALID_V662_CHAIN");
    const known=new Set(previous.map(p=>p.id)),seen=new Set();
    const restricted=["market_price","verified_sales","verified_stock","pull_rate","psa_grade","hit_probability"];
    const allowed=new Set(["id","game","country","product_type","set_code","set_code_verified",
      "name","release_date","source","release_date_source","packs_per_box","cards_per_pack","msrp","notes"]);
    for(const p of doc.products) {
      const required=p&&specs[p.id];
      if(!required||seen.has(p.id)||known.has(p.id)||!validProduct(p)||
         Object.keys(p).some(k=>!allowed.has(k))||typeof p.notes!=="string"||
         Object.entries(required).some(([k,v])=>{
           const current=p[k];
           return k==="msrp"?
             !current||Object.keys(current).length!==3||current.currency!==v.currency||current.amount!==v.amount||current.unit!==v.unit:
             current!==v;
         })||restricted.some(k=>k in p)||
         (p.id!=="ws-JP-ALL-bplb-2026"&&"msrp" in p))
         throw Error("UNTRUSTED_V662_PRODUCT");
      seen.add(p.id);
    }
    return doc.products;
  }

  function validateV663(doc,previous=[]) {
    const id="pokemon-US-me-perfect-order-2026";
    const spec={game:"Pokémon",country:"US",product_type:"BOX",
      set_code:"LOCAL-POK-ME-PO-US",set_code_verified:false,
      name:"Pokémon TCG: Mega Evolution—Perfect Order Booster Display Box",
      release_date:"2026-03-27",
      source:"https://www.pokemon.com/us/news/pokemon-tcg-mega-evolution-perfect-order-product-showcase",
      packs_per_box:36,cards_per_pack:"10"};
    if(!doc||doc.schema_version!==1||doc.type!=="official_product_specifications_supplement"||
       doc.base_catalog!=="tcg_official_product_catalog_v599.json"||
       doc.append_after!=="tcg_official_product_supplement_v662.json"||
       doc.policy?.no_paid_dependency!==true||!Array.isArray(doc.products)||doc.products.length!==1)
       throw Error("INVALID_V663_CHAIN");
    const p=doc.products[0];
    const allowed=new Set(["id",...Object.keys(spec),"notes"]);
    if(!p||Object.keys(p).some(k=>!allowed.has(k))||p.id!==id||
       previous.some(row=>row.id===id)||!validProduct(p)||
       Object.entries(spec).some(([k,v])=>p[k]!==v)||
       ["msrp","market_price","verified_sales","verified_stock","pull_rate",
        "hit_probability","psa_grade","card_number"].some(k=>k in p))
       throw Error("UNTRUSTED_V663_PRODUCT");
    return doc.products;
  }
  function validatePromoV663(doc) {
    const source="https://www.pokemon.com/us/news/celebrate-pokemon-tcg-mega-evolution-perfect-order-with-promo-cards";
    const expected={
      "pokemon-US-perfect-order-gengar-gamestop-2026":["Gengar","GameStop"],
      "pokemon-US-perfect-order-luxray-bestbuy-2026":["Luxray","Best Buy"],
      "pokemon-US-perfect-order-aurorus-retail-2026":["Aurorus","Hot Topic / Barnes & Noble"]
    };
    if(!doc||doc.schema_version!==1||doc.type!=="OFFICIAL_PROMO_CAMPAIGN_NAME_ONLY"||
      doc.source!==source||doc.game!=="Pokémon"||doc.market!=="US"||
      doc.campaign_release_date!=="2026-03-27"||
      doc.evidence_policy!=="OFFICIAL_PROMO_PROGRAM_NOT_BOX_HIT_OR_CARD_NUMBER"||
      doc.purchase_threshold?.amount!==15||doc.purchase_threshold?.currency!=="USD"||
      doc.purchase_threshold?.unit!=="ELIGIBLE_TCG_PURCHASE"||
      !Array.isArray(doc.records)||doc.records.length!==3)
       throw Error("INVALID_V663_PROMO");
    const seen=new Set();
    for(const p of doc.records) {
      const row=p&&expected[p.id];
      if(!row||Object.keys(p).some(k=>!["id","card_name","retailer","market",
         "card_number","printing","eligibility"].includes(k))||
         seen.has(p.id)||p.card_name!==row[0]||p.retailer!==row[1]||
         p.market!=="US"||p.card_number!==null||
         p.printing!=="PROMO_CARD_NUMBER_UNVERIFIED"||
         p.eligibility!=="Eligible Pokémon TCG purchase of at least USD 15, while supplies last"||
         ["verified_stock","market_price","hit_probability","pull_rate","psa_grade"].some(k=>k in p))
        throw Error("UNTRUSTED_V663_PROMO");
      seen.add(p.id);
    }
    return doc.records;
  }

  // Manufacturer BOX proof for Japan UNION ARENA UA50BT; not pack price or HIT odds.
  function validateV665(doc,previous=[]) {
    const spec={id:"unionarena-JP-UA50BT-inuyasha-2026",game:"UNION ARENA",country:"JP",
      product_type:"BOX",set_code:"UA50BT",
      name:"UNION ARENA ブースターパック 犬夜叉 [UA50BT] Booster BOX",
      release_date:"2026-05-29",
      source:"https://www.unionarena-tcg.com/jp/products/boosters/iys-1.php",
      packs_per_box:16,cards_per_pack:"8"};
    if(!doc||doc.schema_version!==1||doc.type!=="official_product_specifications_supplement"||
       doc.base_catalog!=="tcg_official_product_catalog_v599.json"||
       doc.append_after!=="tcg_official_product_supplement_v663.json"||
       doc.policy?.no_paid_dependency!==true||!Array.isArray(doc.products)||doc.products.length!==1)
       throw Error("INVALID_V665_CHAIN");
    const p=doc.products[0];
    const allowed=new Set([...Object.keys(spec),"notes"]);
    if(!p||Object.keys(p).length!==allowed.size||Object.keys(p).some(k=>!allowed.has(k))||
       Object.entries(spec).some(([k,v])=>p[k]!==v)||typeof p.notes!=="string"||
       previous.some(row=>row.id===spec.id)||!validProduct(p))
       throw Error("UNTRUSTED_V665_PRODUCT");
    return doc.products;
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
        // V664: begin all optional local JSON reads concurrently, then validate
        // each evidence generation in chronological order. A single broken
        // optional file cannot block or erase the previously validated snapshot.
        const versions=["630","636","637","649","654","657","659","662","663","665"];
        const prefetch=Object.fromEntries(versions.map(version=>[
          version,
          fetch("./tcg_official_product_supplement_v"+version+".json",{cache:"no-store"})
            .catch(()=>null)
        ]));
        const promoFetch=fetch("./tcg_official_promo_evidence_v663.json",
          {cache:"no-store"}).catch(()=>null);
        // Supplemental manufacturer proofs remain separate from the pinned V599 snapshot.
        let additions=[];
        try {
          const r=await prefetch["630"];
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
          const r=await prefetch["636"];
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
          const r=await prefetch["637"];
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
          const r=await prefetch["649"];
          if(!r.ok)throw Error("V649_NOT_AVAILABLE");
          const supplement=await r.json();
          if(supplement?.schema_version!==1||
             supplement?.type!=="official_product_specifications_supplement"||
             supplement?.base_catalog!=="tcg_official_product_catalog_v599.json"||
             supplement?.append_after!=="tcg_official_product_supplement_v637.json"||
             !Array.isArray(supplement.products))throw Error("INVALID_V649");
          additions=additions.concat(supplement.products);
        }catch(_){supplementWarning=true;}
        // V654: direct Japanese manufacturer BOX proof for three gap scopes.
        let hasV654=false;
        try{
          const r=await prefetch["654"];
          if(!r.ok)throw Error("V654_MISSING");
          const newest=await r.json();
          if(newest?.schema_version!==1||
             newest?.type!=="official_product_specifications_supplement"||
             newest?.base_catalog!=="tcg_official_product_catalog_v599.json"||
             newest?.append_after!=="tcg_official_product_supplement_v649.json"||
             !Array.isArray(newest.products))throw Error("INVALID_V654");
          additions=additions.concat(newest.products);
          hasV654=true;
        }catch(_){supplementWarning=true;}
        let hasV657=false;
        // V657: allow only the exactly source-matched three official US BOX rows.
        // If V654 is missing or invalid, V657 does not skip its parent.
        try{
          if(!hasV654)throw Error("V657_PARENT_NOT_VERIFIED");
          const parentProducts=json.products.concat(additions);
          if(normalizeProducts({schema_version:1,products:parentProducts}).length!==parentProducts.length)
            throw Error("V657_PARENT_HAS_INVALID_PRODUCT");
          const r=await prefetch["657"];
          if(!r.ok)throw Error("V657_NOT_AVAILABLE");
          const newest=await r.json();
          additions=additions.concat(validateV657(newest,json.products.concat(additions)));
          hasV657=true;
        }catch(_){supplementWarning=true;}
        let hasV659=false;
        // V659 is optional and cannot bypass its V657 parent.
        try{
          if(!hasV657)throw Error("V659_PARENT_NOT_VERIFIED");
          const parentProducts=json.products.concat(additions);
          if(normalizeProducts({schema_version:1,products:parentProducts}).length!==parentProducts.length)
            throw Error("V659_PARENT_HAS_INVALID_PRODUCT");
          const r=await prefetch["659"];
          if(!r.ok)throw Error("V659_MISSING");
          const jp=await r.json();
          additions=additions.concat(validateV659(jp,parentProducts));
          hasV659=true;
        }catch(_){supplementWarning=true;}
        let hasV662=false;
        // V662 must retain the entire previously checked chain on bad inputs.
        try{
          if(!hasV659)throw Error("V662_PARENT_NOT_VERIFIED");
          const prior=json.products.concat(additions);
          if(normalizeProducts({schema_version:1,products:prior}).length!==prior.length)
            throw Error("V662_PARENT_CONTAINS_UNTRUSTED_PRODUCT");
          const r=await prefetch["662"];
          if(!r.ok)throw Error("V662_NOT_AVAILABLE");
          const extra=await r.json();
          additions=additions.concat(validateV662(extra,prior));
          hasV662=true;
        }catch(_){supplementWarning=true;}
        let hasV663=false;
        // Keep optional promo evidence separate from sealed BOX product records.
        try{
          if(!hasV662)throw Error("V663_PARENT_NOT_VERIFIED");
          const prior=json.products.concat(additions);
          if(normalizeProducts({schema_version:1,products:prior}).length!==prior.length)
            throw Error("V663_PARENT_HAS_INVALID_PRODUCTS");
          const [p,events]=await Promise.all([
            prefetch["663"],
            promoFetch
          ]);
          if(!p.ok||!events.ok)throw Error("V663_PROOFS_UNAVAILABLE");
          const [proof,program]=await Promise.all([p.json(),events.json()]);
          validatePromoV663(program);
          additions=additions.concat(validateV663(proof,prior));
          hasV663=true;
        }catch(_){supplementWarning=true;}
        // V665: only add the exact Japan UNION ARENA manufacturer 16-pack proof.
        try{
          if(!hasV663)throw Error("V665_PARENT_NOT_VERIFIED");
          const prior=json.products.concat(additions);
          if(normalizeProducts({schema_version:1,products:prior}).length!==prior.length)
            throw Error("V665_PARENT_INVALID");
          const r=await prefetch["665"];
          if(!r.ok)throw Error("V665_NOT_AVAILABLE");
          const proof=await r.json();
          additions=additions.concat(validateV665(proof,prior));
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
  return {trustedSource,validProduct,validateV657,validateV659,validateV662,validateV663,validatePromoV663,validateV665,normalizeProducts,formatPrice,releaseLabels,filterProducts,paginate,mount};
});
