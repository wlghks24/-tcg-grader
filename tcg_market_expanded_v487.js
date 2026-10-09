"use strict";
(() => {
  const home = document.getElementById("tcgMarketHome");
  if (!home) return;

  // Guard the V485 home source anchors without changing its immutable template.
  const VERIFIED_MARKET_SOURCE_HOSTS = Object.freeze([
    "kream.co.kr", "pokard.io", "tcgplayer.com", "snkrdunk.com",
    "ebay.com", "ebay.co.jp", "cardmarket.com", "mercari.com",
    "amazon.com", "amazon.co.jp", "collectory.cc", "justtcg.com",
    "tcgdex.net", "pavilion-tcg.com", "narutomarket.com"
  ]);
  function verifiedMarketSourceUrl(raw) {
    const value = String(raw || "").trim();
    if (!/^https:\/\//i.test(value) || value.length > 2048) return "";
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) return "";
      const host = url.hostname.toLowerCase();
      return VERIFIED_MARKET_SOURCE_HOSTS.some(domain => host === domain || host.endsWith("." + domain)) ? url.href : "";
    } catch (_) { return ""; }
  }
  // V538: fail closed on calendar-impossible or future saved source dates.
  // The V485 template is intentionally immutable, so verify displayed dates
  // in the local same-origin enhancer without changing prices or requests.
  // Mirror market_price_context_v433.price_freshness day windows exactly.
  // JS cannot import the Python module; the V541 cross-language test prevents drift.
  function marketHomeDateState(label, referenceDate = new Date()) {
    const m = /^자료일 (20\d{2}-\d{2}-\d{2})$/.exec(String(label || "").trim());
    if (!m) return {status:"UNKNOWN", age:null};
    const epoch = Date.parse(m[1] + "T00:00:00Z");
    if (!Number.isFinite(epoch) || new Date(epoch).toISOString().slice(0, 10) !== m[1])
      return {status:"INVALID", age:null};
    // Date-only KR/JP observations follow the KST business day, independent
    // of Android device timezone, its locale, or the CI runner timezone.
    const kstToday = new Date(referenceDate.getTime() + 9 * 3600000).toISOString().slice(0, 10);
    const today = Date.parse(kstToday + "T00:00:00Z");
    const age = Math.floor((today - epoch) / 86400000);
    if (age < 0) return {status:"FUTURE", age:null};
    return {status:age<=2?"FRESH":age<=7?"AGING":age<=30?"STALE":"EXPIRED",age};
  }
  function verifiedMarketHomeDate(label, referenceDate = new Date()) {
    return ["FRESH","AGING","STALE","EXPIRED"].includes(marketHomeDateState(label, referenceDate).status);
  }
  function marketHomeSourceAgeDays(label, referenceDate = new Date()) {
    return marketHomeDateState(label, referenceDate).age;
  }
  function protectMarketHomeDates() {
    for (const date of home.querySelectorAll(".tcg-market-tile-date")) {
      // Preserve the original source day across rechecks and DOM observer runs.
      const label = String(date.dataset.marketSourceLabel || date.textContent || "").trim();
      if (!date.dataset.marketSourceLabel) date.dataset.marketSourceLabel = label;
      const result = marketHomeDateState(label);
      const status = result.status.toLowerCase();
      let message = label;
      if (result.status === "AGING") {
        message = "경과 " + result.age + "일 · " + label + " · 재확인 권장";
      } else if (result.status === "STALE") {
        message = "과거 " + label + " · 최신 시세 아님 (" + result.age + "일 경과)";
      } else if (result.status === "EXPIRED") {
        message = "만료된 과거 " + label + " · 최신 시세 아님 · 원문 재확인";
      } else if (result.status === "FUTURE") {
        message = "미래 자료일 · 가격 원문 재확인";
      } else if (result.status === "INVALID") {
        message = "자료일 검증 불가 · 가격 원문 재확인";
      }
      if (date.textContent !== message) date.textContent = message;
      date.dataset.dateStatus = status;
      const tile = date.closest?.(".tcg-market-tile");
      if (tile) tile.dataset.marketEvidenceStatus = status;
    }
  }
  function protectMarketHomeLinks() {
    for (const link of home.querySelectorAll(".tcg-market-tile-actions a")) {
      const safe = verifiedMarketSourceUrl(link.getAttribute("href"));
      if (safe) {
        if (link.href !== safe) link.href = safe;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      } else {
        const unavailable = document.createElement("span");
        unavailable.className = "tcg-market-art-empty";
        unavailable.textContent = "출처 URL 확인 필요";
        link.replaceWith(unavailable);
      }
    }
    protectMarketHomeDates();
  }
  home.addEventListener("click", event => {
    const link = event.target?.closest?.(".tcg-market-tile-actions a");
    if (!link || !home.contains(link)) return;
    if (!verifiedMarketSourceUrl(link.getAttribute("href"))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  if (typeof MutationObserver === "function") {
    const observer = new MutationObserver(protectMarketHomeLinks);
    observer.observe(home, {childList: true, subtree: true});
  }
  protectMarketHomeLinks();
  // Long-running tablets may cross midnight without rebuilding their cards.
  // Local-only rechecks do not fetch prices or change underlying evidence.
  const recheckVisibleMarketDates = () => {
    if (document.visibilityState !== "hidden") protectMarketHomeDates();
  };
  document.addEventListener("visibilitychange", recheckVisibleMarketDates);
  window.addEventListener("focus", recheckVisibleMarketDates);
  setInterval(recheckVisibleMarketDates, 60 * 60 * 1000);
  const tabs = home.querySelector(".tcg-market-game-tabs");
  if (!tabs) return;
  const info = document.createElement("div");
  info.id = "tcgMarketExpandedV487";
  info.className = "tcg-market-expanded-v487";
  const label = document.createElement("p");
  label.textContent = "확장 카드게임 · 게임별 시세 검색 (등급측정 제외)";
  info.append(label);
  const links = document.createElement("div");
  links.className = "tcg-market-expanded-links";
  const status = document.createElement("p");
  status.setAttribute("aria-live", "polite");
  status.textContent = "확인된 확장 게임만 표시하며 가격·재고는 상세 검색에서 확인합니다.";
  info.append(links,status);
  tabs.insertAdjacentElement("afterend",info);
  const style=document.createElement("style");
  style.textContent=".tcg-market-expanded-v487{padding:10px 9px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;margin:6px 0 14px}.tcg-market-expanded-v487 p{margin:3px 0 7px;font-size:11px;color:#475569}.tcg-market-expanded-links{display:flex;gap:7px;overflow-x:auto;padding:4px 0}.tcg-market-expanded-links button{margin:0;width:auto;flex:none;min-height:44px;padding:8px 12px;border-radius:99px;background:#fff;color:#0f172a;border:1px solid #cbd5e1;font-size:12px}.tcg-market-expanded-links button:focus-visible{outline:3px solid #2563eb;outline-offset:2px}";
  // V516: screenshot readability and touch-safe controls. Cosmetic only:
  // do not alter saved evidence, game/edition, grading or purchase links.
  style.textContent += `
    .tcg-market-home .tcg-market-refresh,
    .tcg-market-home .tcg-market-game,
    .tcg-market-home .tcg-market-more,
    .tcg-market-home .tcg-market-tile-actions :is(button,a){
      min-height:48px;min-width:44px;touch-action:manipulation;
    }
    .tcg-market-home .tcg-market-refresh,
    .tcg-market-home .tcg-market-more,
    .tcg-market-home .tcg-market-tile-actions :is(button,a){
      font-size:12px;line-height:1.3;
    }
    .tcg-market-home .tcg-market-home-meta,
    .tcg-market-home .tcg-market-section-heading small,
    .tcg-market-home .tcg-market-tile-label,
    .tcg-market-home .tcg-market-tile-kind,
    .tcg-market-home .tcg-market-tile-date,
    .tcg-market-home .tcg-market-home-warning{
      font-size:12px;line-height:1.5;overflow-wrap:anywhere;
    }
    .tcg-market-home .tcg-market-tile-price{
      font-variant-numeric:tabular-nums;overflow-wrap:anywhere;word-break:break-word;
    }
    .tcg-market-home .tcg-market-tile-date[data-date-status="aging"]{
      color:#92400e;font-weight:650;
    }
    .tcg-market-home .tcg-market-tile-date[data-date-status="stale"],
    .tcg-market-home .tcg-market-tile-date[data-date-status="expired"]{
      color:#92400e;font-weight:700;
    }
    .tcg-market-home .tcg-market-tile-date[data-date-status="invalid"],
    .tcg-market-home .tcg-market-tile-date[data-date-status="future"]{
      color:#b91c1c;font-weight:700;
    }
    .tcg-market-home .tcg-market-tile[data-market-evidence-status="stale"] .tcg-market-tile-price,
    .tcg-market-home .tcg-market-tile[data-market-evidence-status="expired"] .tcg-market-tile-price,
    .tcg-market-home .tcg-market-tile[data-market-evidence-status="future"] .tcg-market-tile-price,
    .tcg-market-home .tcg-market-tile[data-market-evidence-status="invalid"] .tcg-market-tile-price,
    .tcg-market-home .tcg-market-tile[data-market-evidence-status="unknown"] .tcg-market-tile-price{
      color:#64748b;
    }
    .tcg-market-home .tcg-market-tile-actions :is(button,a){
      padding:9px 5px;
    }
    @media(max-width:430px){
      .tcg-market-home .tcg-market-tile{flex-basis:clamp(160px,74vw,190px);}
      .tcg-market-home .tcg-market-section-heading{align-items:flex-start;}
    }
  `;
  document.head.append(style);
  fetch("tcg_game_registry.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(data=>{
    if(!data || data.schema_version!==1 || !Array.isArray(data.games) || data.games.length>64)return;
    for(const game of data.games.filter(x=>x && x.state==="promoted" && x.capabilities?.market===true).slice(0,12)){
      if(typeof game.canonical!=="string" || typeof game.label_ko!=="string")continue;
      const btn=document.createElement("button");
      btn.type="button";
      btn.textContent=game.label_ko+" ›";
      btn.setAttribute("aria-label",game.label_ko+" 시세 검색");
      btn.addEventListener("click",async()=>{
        const sel=document.getElementById("v12Game");
        if(!sel || !Array.from(sel.options).some(x=>!x.disabled && x.value===game.canonical)){
          status.textContent="해당 확장 게임 선택이 아직 준비되지 않았습니다.";return;
        }
        sel.value=game.canonical;
        const query=document.getElementById("query12");
        if(query)query.value="";
        const link=document.querySelector('.feature-shortcut[data-feature-key="market-search"]');
        if(link)link.click();else status.textContent="시세 검색 메뉴를 찾지 못했습니다.";
      });
      links.append(btn);
    }
    if(!links.childElementCount)info.remove();
  }).catch(()=>info.remove());
})();

/* V505: low-cost, same-origin, offline-capable portfolio loaded after market home. */
(() => {
  if (!document.getElementById("tcgMarketHome") ||
      document.getElementById("tcgLocalCollectionV505Loader")) return;
  const script=document.createElement("script");
  script.id="tcgLocalCollectionV505Loader";
  script.src="tcg_local_collection_v505.js?v=505";
  script.async=false;
  document.body.appendChild(script);
})();

/* V550: local-only free source handoff. The immutable grade_market_flow.js is not modified. */
(() => {
  "use strict";
  const home = document.getElementById("tcgMarketHome");
  if (!home) return;
  const hosts = new Set(["kream.co.kr", "collectory.cc"]);
  let prices = null, previousSig = "";
  const get = id => document.getElementById(id);
  const plain = value => String(value == null ? "" : value).trim();
  const norm = value => plain(value).toLowerCase().replace(/[^0-9a-z가-힣]/g, "");
  const regionCode = value => {
    const s = plain(value).toLowerCase();
    if (/(^|[^a-z])(kr|korean|korea)([^a-z]|$)|한국|국판|한글판/.test(s)) return "KR";
    if (/(^|[^a-z])(jp|japan|japanese)([^a-z]|$)|일본|일판/.test(s)) return "JP";
    if (/(^|[^a-z])(us|en|english)([^a-z]|$)|미국|영문/.test(s)) return "US";
    return "";
  };
  function recentProvider(report, rawHost, now = Date.now()) {
    if (!report || typeof report !== "object") return null;
    const hasLiveAudit = Array.isArray(report.degraded_hosts);
    const status = hasLiveAudit ? report : report.public_market_crosscheck;
    if (!status || typeof status !== "object") return null;
    const stamp = Date.parse(plain(status.updated_at));
    if (!Number.isFinite(stamp) || now - stamp < -120000 || now - stamp > 86400000) return null;
    const host = plain(rawHost).toLowerCase().replace(/^www\./, "");
    if (hasLiveAudit) {
      const found = status.degraded_hosts.find(row =>
        plain(row && row.host).toLowerCase().replace(/^www\./, "") === host);
      if (!found) return null;
      const blocked = Number(found.restricted) || 0;
      const delayed = Number(found.transient) || 0;
      if (blocked > 0) return {reason:"자동접속 제한", count:blocked};
      if (delayed > 0) return {reason:"일시적 오류", count:delayed};
      return null;
    }
    // Reuse a public, already-delivered collector summary. Never scrape the
    // storefront from this screen or expose the raw private audit report.
    const provider = host === "kream.co.kr" ? "KREAM" :
                     host === "collectory.cc" ? "Collectory" : "";
    const sources = status.sources;
    const source = provider && sources && typeof sources === "object" ? sources[provider] : null;
    if (!source || typeof source !== "object") return null;
    const attempts = Number(source.checked), errors = Number(source.errors);
    if (!Number.isSafeInteger(attempts) || !Number.isSafeInteger(errors) ||
        attempts < 1 || errors < 1 || errors > attempts) return null;
    return {reason:"최근 수집 오류 · 자동시세 확인 불가", count:errors};
  }
  function savedPrior(data, context, now = Date.now()) {
    if (!data || !data.entries || !context) return [];
    const key = plain(context.key), number = norm(context.number), name = norm(context.name);
    const region = regionCode(context.region);
    if (!key || !number || !name || !region || key.split("|")[0].toUpperCase() !== region) return [];
    const entry = data.entries[key];
    if (!entry || norm(entry.card_number) !== number) return [];
    if (entry.card_name && norm(entry.card_name) !== name) return [];
    const rows = Array.isArray(entry.source_crosschecks) ? entry.source_crosschecks : [];
    return rows.filter(row => {
      if (!row || !["KREAM", "Collectory"].includes(row.source)) return false;
      const value = Number(row.price_krw), date = plain(row.observed_at);
      if (!Number.isSafeInteger(value) || value < 100 || value > 500000000) return false;
      if (!Number.isFinite(Number(row.confidence)) || Number(row.confidence) < 0.8) return false;
      try {
        const sourceUrl = new URL(plain(row.url));
        const expected = row.source === "KREAM" ? "kream.co.kr" : "collectory.cc";
        if (sourceUrl.protocol !== "https:" || sourceUrl.hostname.toLowerCase() !== expected ||
            sourceUrl.username || sourceUrl.password || sourceUrl.port) return false;
      } catch (_) { return false; }
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(date)) return false;
      const age = now - Date.parse(date);
      return Number.isFinite(age) && age >= -120000;
    }).slice(0,6);
  }
  function browserLink(label, rawUrl, degraded) {
    const a = document.createElement("a");
    a.href = rawUrl;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = label + (degraded ? " · 브라우저 직접 확인 ↗" : " ↗");
    a.className = "tcg-free-link";
    a.style.cssText = "display:inline-block;margin:5px;padding:9px 12px;min-height:44px;border:1px solid #94a3b8;border-radius:12px;text-decoration:none;";
    return a;
  }
  function includePokemonCatalog(game) {
    return game === "ALL" || game === "Pokémon";
  }
  function render() {
    const target = get("tcgFreeFallbackV550Content");
    if (!target) return;
    const name = plain(get("identityCardName") && get("identityCardName").value);
    const number = plain(get("identityCardNumber") && get("identityCardNumber").value);
    const region = plain(get("identityRegion") && get("identityRegion").value);
    const key = plain(get("identityMarketKey") && get("identityMarketKey").value);
    const context = {name, number, region, key};
    const activeGame = plain(home.querySelector?.('.tcg-market-game[aria-pressed="true"]')?.dataset?.game || "ALL");
    const signature = [name, number, region, key, activeGame].join("|");
    if (signature === previousSig && target.childNodes.length) return;
    previousSig = signature;
    target.replaceChildren();
    const note = document.createElement("p");
    note.textContent = "무료 확인: 자동접속이 막힌 판매처도 원본을 일반 브라우저에서 확인할 수 있습니다. 다른 출처의 호가는 KREAM 체결가로 대체하지 않습니다.";
    target.appendChild(note);
    if (!name && !number) {
      const hint = document.createElement("p");
      hint.textContent = "카드 촬영·인식 후 이름, 카드번호, 판본을 선택하세요.";
      target.appendChild(hint);
      if (includePokemonCatalog(activeGame)) {
        target.appendChild(browserLink(
          "포켓몬 공식 확장팩 목록 · 판매처 재고 미확인",
          "https://new.pokemonkorea.co.kr/card/category/3", false));
      }
      return;
    }
    const query = [name, number, regionCode(region)].filter(Boolean).join(" ").slice(0,160);
    const term = encodeURIComponent(query);
    const destinations = [
      ["Collectory 교차확인", "https://collectory.cc/?q=" + term, "collectory.cc"],
      ["KREAM 원본", "https://kream.co.kr/search?keyword=" + term, "kream.co.kr"],
      ["eBay 판매완료", "https://www.ebay.com/sch/i.html?_nkw=" + term + "&LH_Sold=1&LH_Complete=1", "www.ebay.com"],
      ["Yahoo 일본 낙찰", "https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=" + term, "auctions.yahoo.co.jp"]
    ];
    if (includePokemonCatalog(activeGame)) {
      // Product index is first-party and current, but stock and prices are NOT verified.
      destinations.push([
        "포켓몬 공식 확장팩 목록 · 판매처 재고 미확인",
        "https://new.pokemonkorea.co.kr/card/category/3",
        "new.pokemonkorea.co.kr"
      ]);
    }
    const links = document.createElement("div");
    for (const row of destinations) {
      const failure = recentProvider(prices, row[2]);
      links.appendChild(browserLink(row[0], row[1], !!failure));
    }
    target.appendChild(links);
    const reports = destinations.map(row => {
      const result = recentProvider(prices, row[2]);
      return result ? row[0] + ": " + result.reason + " " + result.count + "건 (최근 감사)" : "";
    }).filter(Boolean);
    if (reports.length) {
      const message = document.createElement("small");
      message.textContent = reports.join(" · ") + " · 저장된 수집 이력 기준 · 브라우저도 접속을 보장하지 않습니다.";
      target.appendChild(message);
    }
    const saved = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = "동일 카드번호·판본의 이전 교차확인 가격";
    saved.appendChild(heading);
    const rows = savedPrior(prices, context);
    if (!rows.length) {
      const none = document.createElement("p");
      none.textContent = "확인 날짜와 카드 식별이 일치하는 저장 자료가 없습니다. 현재 시세를 임의로 만들지 않습니다.";
      saved.appendChild(none);
    }
    for (const row of rows) {
      const line = document.createElement("p");
      const age = Math.floor(Math.max(0, Date.now() - Date.parse(row.observed_at)) / 86400000);
      const ageText = age > 7 ? "오래된 자료 · 현재가 아님" : "저장된 확인 자료 · 현재가 보장 안 됨";
      line.textContent = row.source + " · " + row.observed_at.slice(0,10) +
        " · ₩" + Number(row.price_krw).toLocaleString("ko-KR") + " · " + ageText + " · 카드상태 재확인";
      try {
        const url = new URL(plain(row.url));
        if (url.protocol === "https:" && hosts.has(url.hostname.toLowerCase()) &&
            !url.username && !url.password && !url.port) {
          line.appendChild(browserLink("원본", url.href, false));
        }
      } catch (_) {}
      saved.appendChild(line);
    }
    target.appendChild(saved);
  }
  const panel = document.createElement("details");
  panel.id = "tcgFreeFallbackV550";
  panel.style.cssText = "margin:12px 0;padding:12px;border:1px solid #cbd5e1;border-radius:14px;";
  const heading = document.createElement("summary");
  heading.textContent = "무료 시세 대체 확인 · 이전 검증값 보기";
  heading.style.cssText = "cursor:pointer;font-weight:700;min-height:44px;";
  panel.appendChild(heading);
  const content = document.createElement("div");
  content.id = "tcgFreeFallbackV550Content";
  panel.appendChild(content);
  home.appendChild(panel);
  // Price figures and browser links are drawn only inside the opened panel.
  function refresh() {
    if (panel.open) render();
  }
  panel.addEventListener("toggle", refresh);
  document.addEventListener("change", refresh);
  document.addEventListener("input", refresh);
  document.addEventListener("click", event => {
    if (event.target?.closest?.(".tcg-market-game")) {
      previousSig = "";
      refresh();
    }
  });
  async function load(name, sink) {
    try {
      const response = await fetch(name, {cache:"no-store"});
      if (!response.ok) return;
      const data = await response.json();
      sink(data);
    } catch (_) {}
    previousSig = "";
    refresh();
  }
  load("market_prices.json", data => {prices = data && typeof data === "object" ? data : null;});
  // link_health_report.json is not public in the tablet server and its tracked
  // repository copy is stale. Market price summaries are the honest source.
  // Pure policy only: no network, credentials, mutation or browser automation.
  window.tcgFreeFallbackPolicyV550 = Object.freeze({recentProvider, savedPrior, includePokemonCatalog});
})();
