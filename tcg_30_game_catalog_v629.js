/* V629: free local viewer for ALL 30 user-entered TCG research records.
   User input is preserved. Candidate names are NOT verified BOX specifications,
   completed transactions, live inventory or guaranteed HIT probabilities. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root && root.document) {
    root.TcgUser30V629 = api;
    const launch = () => api.mount(root.document);
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", launch, { once: true });
    else launch();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const PAGE_SIZE = 6;
  const FIELDS = Object.freeze([
    ["product_name_candidates", "입력한 BOX·제품·세트 후보"],
    ["upcoming_name_candidates", "출시 예정 후보"],
    ["hit_name_candidates", "HIT 카드명 후보"],
    ["promo_name_candidates", "프로모 카드명 후보"]
  ]);
  function validIntake(data, registry) {
    if (!data || data.schema_version !== 1 ||
        data.source_kind !== "user_supplied_research_leads" ||
        data.data_evidence_level !== "UNVERIFIED" ||
        !Array.isArray(data.records) || data.records.length !== 30 ||
        !registry || !Array.isArray(registry.games) || registry.games.length !== 30) return false;
    const ids = new Set(registry.games.map(g => g.id));
    const seen = new Set();
    return data.records.every(r => {
      if (!r || r.status !== "USER_SUBMITTED_UNVERIFIED" ||
          !ids.has(r.game_id) || seen.has(r.game_id)) return false;
      seen.add(r.game_id);
      return FIELDS.every(([field]) => Array.isArray(r[field]) &&
        r[field].every(value => typeof value === "string" && value.length > 0 && value.length <= 250));
    });
  }
  function counts(records) {
    const totals = { games: records.length, product: 0, upcoming: 0, hit: 0, promo: 0 };
    records.forEach(r => {
      totals.product += r.product_name_candidates.length;
      totals.upcoming += r.upcoming_name_candidates.length;
      totals.hit += r.hit_name_candidates.length;
      totals.promo += r.promo_name_candidates.length;
    });
    return totals;
  }
  function officialCounts(catalog, registry, verifier=null) {
    const names = new Map(registry.games.map(g => [g.canonical, g.id]));
    const result = {};
    if (!catalog || catalog.schema_version !== 1 || !Array.isArray(catalog.products)) return result;
    // Manufacturer-domain verification is mandatory for records shown as
    // official; untrusted JSON must never inflate the 30-game summary.
    const checker=verifier ||
       (typeof globalThis!=="undefined" && globalThis.TcgOfficialBoxV626) ||
       (typeof require==="function"?require("./official_box_catalog_v626.js"):null);
    if(!checker||typeof checker.validProduct!=="function")return result;
    const ids = new Set();
    for (const product of catalog.products) {
      if (!product || typeof product.id !== "string" || ids.has(product.id) ||
          !checker.validProduct(product)) continue;
      ids.add(product.id);
      const id = names.get(product.game);
      if (id) result[id] = (result[id] || 0) + 1;
    }
    return result;
  }
  function filtered(records, registry, gameId, term) {
    const labels = new Map(registry.games.map(g => [g.id, [g.label_ko, g.canonical]]));
    const needle = String(term || "").trim().toLocaleLowerCase();
    return records.filter(r => {
      if (gameId && gameId !== "ALL" && r.game_id !== gameId) return false;
      if (!needle) return true;
      const pool = [r.game_id].concat(labels.get(r.game_id) || []);
      for (const [field] of FIELDS) pool.push(...r[field]);
      return pool.join(" ").toLocaleLowerCase().includes(needle);
    });
  }
  function paginate(records, page) {
    const pages = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
    const current = Number.isInteger(page) ? Math.max(0, Math.min(page, pages - 1)) : 0;
    return { current, pages, total: records.length, rows: records.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE) };
  }
  function mount(doc) {
    const root = doc.getElementById("user30App");
    if (!root) return;
    const game = doc.getElementById("user30Game"), search = doc.getElementById("user30Search"),
      status = doc.getElementById("user30Status"), total = doc.getElementById("user30Summary"),
      result = doc.getElementById("user30Results"), previous = doc.getElementById("user30Prev"),
      next = doc.getElementById("user30Next"), index = doc.getElementById("user30Page");
    if (![game,search,status,total,result,previous,next,index].every(Boolean)) return;
    const txt = (tag, value, className) => {
      const element = doc.createElement(tag);
      if (className) element.className = className;
      element.textContent = String(value);
      return element;
    };
    let records = [], registry = null, refs = {}, page = 0;
    function render() {
      const matches = filtered(records, registry, game.value, search.value);
      const slice = paginate(matches, page);
      page = slice.current;
      result.replaceChildren();
      const names = new Map(registry.games.map(g => [g.id, g.label_ko || g.canonical]));
      for (const r of slice.rows) {
        const article = txt("article", "", "game-card");
        article.appendChild(txt("h2", names.get(r.game_id) || r.game_id));
        article.appendChild(txt("p", "사용자 입력 보관 · 공식 검증 전 후보", "pending"));
        article.appendChild(txt("p", "이 게임의 별도 공식 제조사 제품 기록 " + (refs[r.game_id] || 0) + "건 · 후보와 1:1 검증 매칭을 뜻하지 않음", "meta"));
        for (const [field,label] of FIELDS) {
          const disclosure = doc.createElement("details");
          const heading = doc.createElement("summary");
          heading.textContent = label + " · " + r[field].length + "개";
          disclosure.appendChild(heading);
          const list = doc.createElement("ul");
          for (const candidate of r[field]) {
            const li = doc.createElement("li");
            li.textContent = candidate;
            list.appendChild(li);
          }
          disclosure.appendChild(list);
          article.appendChild(disclosure);
        }
        result.appendChild(article);
      }
      if (!slice.total) result.appendChild(txt("p", "검색 조건에 맞는 입력 자료가 없습니다.", "empty"));
      previous.disabled = slice.current === 0;
      next.disabled = slice.current + 1 >= slice.pages;
      index.textContent = (slice.current + 1) + " / " + slice.pages + "페이지";
      status.textContent = "입력된 30게임 중 " + slice.total + "게임 검색됨 · " + matches.reduce((n,r) => n + r.product_name_candidates.length, 0) + "개 제품·세트명 후보";
    }
    const change = () => { page = 0; render(); };
    game.addEventListener("change", change);
    search.addEventListener("input", change);
    previous.addEventListener("click", () => { page--; render(); });
    next.addEventListener("click", () => { page++; render(); });
    status.textContent = "로컬에서 입력 자료를 불러오는 중…";
    root.setAttribute("aria-busy", "true");
    const get = path => fetch(path, { cache: "no-store" }).then(response => {
      if (!response.ok) throw new Error("LOCAL_FILE_UNAVAILABLE");
      return response.json();
    });
    Promise.all([
      get("./tcg_user_research_intake_v625.json"),
      get("./tcg_game_registry.json"),
      get("./tcg_official_product_catalog_v599.json"),
      get("./tcg_official_product_supplement_v630.json").catch(() => null),
      get("./tcg_official_product_supplement_v636.json").catch(() => null),
      get("./tcg_official_product_supplement_v637.json").catch(() => null),
      get("./tcg_official_product_supplement_v649.json").catch(() => null),
      get("./tcg_official_product_supplement_v654.json").catch(() => null),
      get("./tcg_official_product_supplement_v657.json").catch(() => null),
      get("./tcg_official_product_supplement_v659.json").catch(() => null),
      get("./tcg_official_product_supplement_v662.json").catch(() => null),
      get("./tcg_official_product_supplement_v663.json").catch(() => null),
      get("./tcg_official_promo_evidence_v663.json").catch(() => null),
      get("./tcg_official_product_supplement_v665.json").catch(() => null)
    ]).then(([intake, loadedRegistry, catalog, supplement, supplement636, supplement637, supplement649, supplement654, supplement657, supplement659, supplement662, supplement663, promo663, supplement665]) => {
      if (!validIntake(intake, loadedRegistry)) throw new Error("INVALID_30_GAME_INPUT");
      records = intake.records;
      registry = loadedRegistry;
      // New manufacturer proofs are counted only when the supplement contract matches.
      // Candidate names are never automatically matched/verified to these product rows.
      const extraOk = supplement && supplement.schema_version === 1 &&
        supplement.type === "official_product_specifications_supplement" &&
        supplement.base_catalog === "tcg_official_product_catalog_v599.json" &&
        Array.isArray(supplement.products);
      const extra636Ok = supplement636 && supplement636.schema_version === 1 &&
        supplement636.type === "official_product_specifications_supplement" &&
        supplement636.base_catalog === "tcg_official_product_catalog_v599.json" &&
        supplement636.append_after === "tcg_official_product_supplement_v630.json" &&
        Array.isArray(supplement636.products);
      const extra637Ok = supplement637 && supplement637.schema_version === 1 &&
        supplement637.type === "official_product_specifications_supplement" &&
        supplement637.base_catalog === "tcg_official_product_catalog_v599.json" &&
        supplement637.append_after === "tcg_official_product_supplement_v636.json" &&
        Array.isArray(supplement637.products);
      const extra649Ok = supplement649 && supplement649.schema_version === 1 &&
        supplement649.type === "official_product_specifications_supplement" &&
        supplement649.base_catalog === "tcg_official_product_catalog_v599.json" &&
        supplement649.append_after === "tcg_official_product_supplement_v637.json" &&
        Array.isArray(supplement649.products);
      const extra654Ok = supplement654 && supplement654.schema_version === 1 &&
        supplement654.type === "official_product_specifications_supplement" &&
        supplement654.base_catalog === "tcg_official_product_catalog_v599.json" &&
        supplement654.append_after === "tcg_official_product_supplement_v649.json" &&
        Array.isArray(supplement654.products);
      const guard = typeof globalThis!=="undefined" ? globalThis.TcgOfficialBoxV626 : null;
      let extra657Ok=false;
      if(supplement657 && extra654Ok && guard && typeof guard.validateV657==="function") {
        try {
          guard.validateV657(supplement657,catalog.products.concat(
            extraOk ? supplement.products : [],extra636Ok ? supplement636.products : [],
            extra637Ok ? supplement637.products : [],extra649Ok ? supplement649.products : [],
            extra654Ok ? supplement654.products : []));
          extra657Ok=true;
        }catch(_){extra657Ok=false;}
      }
      let extra659Ok=false;
      if(supplement659 && extra657Ok && guard && typeof guard.validateV659==="function") {
        try{
          guard.validateV659(supplement659,catalog.products.concat(
            extraOk?supplement.products:[],extra636Ok?supplement636.products:[],
            extra637Ok?supplement637.products:[],extra649Ok?supplement649.products:[],
            extra654Ok?supplement654.products:[],supplement657.products));
          extra659Ok=true;
        }catch(_){extra659Ok=false;}
      }
      let extra662Ok=false;
      if(supplement662&&extra659Ok&&guard&&typeof guard.validateV662==="function"){
        try{
          guard.validateV662(supplement662,catalog.products.concat(
            extraOk?supplement.products:[],extra636Ok?supplement636.products:[],
            extra637Ok?supplement637.products:[],extra649Ok?supplement649.products:[],
            extra654Ok?supplement654.products:[],supplement657.products,supplement659.products));
          extra662Ok=true;
        }catch(_){extra662Ok=false;}
      }
      let extra663Ok=false;
      if(supplement663&&promo663&&extra662Ok&&guard&&
         typeof guard.validateV663==="function"&&typeof guard.validatePromoV663==="function"){
        try{
          guard.validatePromoV663(promo663);
          guard.validateV663(supplement663,catalog.products.concat(
            extraOk?supplement.products:[],extra636Ok?supplement636.products:[],
            extra637Ok?supplement637.products:[],extra649Ok?supplement649.products:[],
            extra654Ok?supplement654.products:[],supplement657.products,
            supplement659.products,supplement662.products));
          extra663Ok=true;
        }catch(_){extra663Ok=false;}
      }
      let extra665Ok=false;
      if(supplement665&&extra663Ok&&guard&&typeof guard.validateV665==="function"){
        try {
          guard.validateV665(supplement665,catalog.products.concat(
            extraOk?supplement.products:[],extra636Ok?supplement636.products:[],
            extra637Ok?supplement637.products:[],extra649Ok?supplement649.products:[],
            extra654Ok?supplement654.products:[],supplement657.products,
            supplement659.products,supplement662.products,supplement663.products));
          extra665Ok=true;
        }catch(_){extra665Ok=false;}
      }
      const official = catalog && Array.isArray(catalog.products)
        ? {...catalog, products: catalog.products.concat(
            extraOk ? supplement.products : [],
            extra636Ok ? supplement636.products : [],
            extra637Ok ? supplement637.products : [],
            extra649Ok ? supplement649.products : [],
            extra654Ok ? supplement654.products : [],
            extra657Ok ? supplement657.products : [],
            extra659Ok ? supplement659.products : [],
            extra662Ok ? supplement662.products : [],
            extra663Ok ? supplement663.products : [],
            extra665Ok ? supplement665.products : [])} : catalog;
      refs = officialCounts(official, registry);
      const c = counts(records);
      total.textContent = c.games + "게임 · 제품·세트 후보 " + c.product + "개 · 출시 예정 " + c.upcoming +
        "개 · HIT " + c.hit + "개 · 프로모 " + c.promo + "개";
      for (const g of registry.games) {
        const opt = doc.createElement("option");
        opt.value = g.id;
        opt.textContent = g.label_ko || g.canonical;
        game.appendChild(opt);
      }
      render();
      if (!extraOk || !extra636Ok || !extra637Ok || !extra649Ok || !extra654Ok || !extra657Ok || !extra659Ok || !extra662Ok || !extra663Ok || !extra665Ok) status.textContent += " · 일부 제조사 보강 자료 로드 실패(표시 건수 기준)";
    }).catch(() => {
      total.textContent = "입력된 자료 파일을 확인할 수 없습니다.";
      status.textContent = "로컬 30종 데이터 또는 검증된 레지스트리 로드 실패. 후보를 임의 복원하거나 생성하지 않습니다.";
    }).finally(() => root.setAttribute("aria-busy", "false"));
  }
  return Object.freeze({ validIntake, counts, officialCounts, filtered, paginate, mount, PAGE_SIZE });
});
