"use strict";
(() => {
  const VERSION = "v483";
  const REGISTRY_URL = "tcg_game_registry.json";
  const SIGNAL_URL = "promoted_tcg_source_signals_v413.json";
  const COVERAGE_URL = "promoted_tcg_multisource_coverage_v432.json";
  const MAX_GAMES = 64;
  const MARKET_SELECT_IDS = ["v12Game", "v13Game", "analysisGame", "tradeGame"];
  const VALID_STATES = new Set(["core", "promoted", "watch"]);
  let refreshBusy = false;

  function text(value, limit = 180) {
    return String(value == null ? "" : value).replace(/\s+/g, " ").trim().slice(0, limit);
  }

  function validHttps(value) {
    try {
      const url = new URL(String(value || ""));
      return url.protocol === "https:" ? url.href : "";
    } catch (_) {
      return "";
    }
  }

  async function fetchJson(path, optional = false, force = false) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const suffix = force ? (path.includes("?") ? "&" : "?") + "t=" + Date.now() : "";
      const response = await fetch(path + suffix, {cache: force ? "no-store" : "default", signal: controller.signal});
      if (!response.ok) throw new Error("HTTP_" + response.status);
      return await response.json();
    } catch (error) {
      if (optional) return null;
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function validateRegistry(payload) {
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.games)) throw new Error("REGISTRY_SHAPE");
    if (payload.games.length < 3 || payload.games.length > MAX_GAMES) throw new Error("REGISTRY_COUNT");
    const ids = new Set();
    const games = [];
    for (const raw of payload.games) {
      if (!raw || typeof raw !== "object") throw new Error("REGISTRY_ROW");
      const id = text(raw.id, 64);
      const canonical = text(raw.canonical, 120);
      const label = text(raw.label_ko, 80);
      const state = text(raw.state, 16);
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id) || ids.has(id)) throw new Error("REGISTRY_ID");
      if (!canonical || !label || !VALID_STATES.has(state)) throw new Error("REGISTRY_VALUE");
      const caps = raw.capabilities && typeof raw.capabilities === "object" ? raw.capabilities : {};
      const regions = Array.isArray(raw.regions)
        ? raw.regions.map((item) => text(item, 8)).filter((item) => ["KR", "JP", "US", "ASIA", "GLOBAL"].includes(item)).slice(0, 5)
        : [];
      ids.add(id);
      games.push({
        id,
        canonical,
        label_ko: label,
        state,
        purchase_value: text(raw.purchase_value || raw.canonical, 120),
        promo_value: text(raw.promo_value || raw.label_ko, 120),
        regions,
        activation_score: Number.isFinite(Number(raw.activation_score)) ? Math.max(0, Math.min(1, Number(raw.activation_score))) : 0,
        capabilities: {
          market: caps.market === true,
          release: caps.release === true,
          promo: caps.promo === true,
          purchase: caps.purchase === true,
          grading: caps.grading === true
        },
        official_source: validHttps(raw.official_source),
        market_source: validHttps(raw.market_source)
      });
    }
    return games;
  }

  function addOption(group, value, label, disabled) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.disabled = Boolean(disabled);
    group.appendChild(option);
  }

  function groupedOptions(select, rows, valueKey, options) {
    if (!select) return;
    const settings = Object.assign({all: true, watchVisible: false}, options || {});
    const previous = select.value;
    while (select.firstChild) select.removeChild(select.firstChild);
    if (settings.all) addOption(select, "ALL", "전체 게임", false);

    const definitions = [
      ["core", "핵심 등급·시장", false],
      ["promoted", "확장 수집·시장", false],
      ["watch", "WATCH · 관찰중", true]
    ];
    for (const [state, label, watchDisabled] of definitions) {
      const subset = rows.filter((row) => row.state === state);
      if (!subset.length || (state === "watch" && !settings.watchVisible)) continue;
      const group = document.createElement("optgroup");
      group.label = label;
      for (const row of subset) {
        const value = text(row[valueKey] || row.canonical, 120);
        addOption(group, value, row.label_ko + (state === "watch" ? " · WATCH" : ""), watchDisabled);
      }
      select.appendChild(group);
    }

    const values = new Set(Array.from(select.options).filter((item) => !item.disabled).map((item) => item.value));
    if (values.has(previous)) select.value = previous;
    else {
      const first = Array.from(select.options).find((item) => !item.disabled);
      if (first) select.value = first.value;
    }
  }

  function extendPurchaseTerms(rows) {
    try {
      if (typeof PURCHASE_TERMS !== "object" || !PURCHASE_TERMS) return;
      for (const row of rows) {
        if (row.state === "watch" || !row.capabilities.purchase) continue;
        const value = row.purchase_value;
        if (!value) continue;
        const canonical = row.canonical;
        const ko = row.label_ko;
        PURCHASE_TERMS[value] = {
          KR: [ko, canonical].filter(Boolean).join(" "),
          JP: canonical,
          US: canonical
        };
      }
    } catch (_) {
      /* The registry cockpit must never break the legacy purchase UI. */
    }
  }

  function populateSelectors(games) {
    const market = games.filter((row) => row.capabilities.market && (row.state === "core" || row.state === "promoted"));
    const marketVisible = games.filter((row) => row.capabilities.market);
    for (const id of MARKET_SELECT_IDS) {
      groupedOptions(document.getElementById(id), marketVisible, "canonical", {all: true, watchVisible: true});
    }

    const promo = games.filter((row) => row.capabilities.promo);
    groupedOptions(document.getElementById("promoGame"), promo, "promo_value", {all: true, watchVisible: true});

    const purchase = games.filter((row) => row.capabilities.purchase && row.state !== "watch");
    groupedOptions(document.getElementById("purchaseGame"), purchase, "purchase_value", {all: false, watchVisible: false});
    extendPurchaseTerms(purchase);

    try {
      if (typeof renderPromos === "function") renderPromos();
      if (typeof renderPurchaseSources === "function") renderPurchaseSources();
      if (typeof renderV12 === "function") renderV12();
      if (typeof renderV13 === "function") renderV13();
    } catch (_) {
      /* Rendering remains best-effort; selectors are already usable. */
    }

    return {market: market.length, promo: promo.length, purchase: purchase.length};
  }

  function signalMap(payload) {
    const map = new Map();
    if (!payload || !Array.isArray(payload.items)) return map;
    for (const row of payload.items.slice(0, MAX_GAMES)) {
      if (!row || typeof row !== "object") continue;
      const id = text(row.id, 64);
      if (id) map.set(id, row);
    }
    return map;
  }

  function coverageMap(payload) {
    const map = new Map();
    if (!payload || !Array.isArray(payload.games)) return map;
    for (const row of payload.games.slice(0, MAX_GAMES)) {
      if (!row || typeof row !== "object") continue;
      const id = text(row.id, 64);
      if (id) map.set(id, row);
    }
    return map;
  }

  function span(className, value) {
    const node = document.createElement("span");
    node.className = className;
    node.textContent = value;
    return node;
  }

  function addLink(parent, label, href) {
    const safe = validHttps(href);
    if (!safe) return;
    const link = document.createElement("a");
    link.href = safe;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    parent.appendChild(link);
  }

  function gameCard(game, signals, coverage) {
    const card = document.createElement("article");
    card.className = "tcg-registry-card" + (game.state === "watch" ? " watch" : "");

    const title = document.createElement("h4");
    title.textContent = game.label_ko;
    title.appendChild(span("tcg-registry-canonical", game.canonical));
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "tcg-registry-meta";
    const score = Math.round(game.activation_score * 100);
    const regionText = game.regions.length ? game.regions.join(" · ") : "지역 검증 대기";
    const liveBits = [];
    if (signals) {
      liveBits.push("공식 " + (signals.official_live === true ? "확인" : "대기"));
      liveBits.push("시장 " + (signals.market_live === true ? "확인" : "대기"));
      const catalog = Number(signals.marketplace_catalog_count);
      if (Number.isFinite(catalog) && catalog > 0) liveBits.push("시장목록 " + Math.round(catalog).toLocaleString("ko-KR"));
    }
    if (coverage && Number.isFinite(Number(coverage.coverage_ratio))) {
      liveBits.push("다중소스 " + Math.round(Number(coverage.coverage_ratio) * 100) + "%");
    }
    meta.textContent =
      (game.state === "promoted" ? "확장 수집" : game.state === "watch" ? "관찰 수집" : "핵심") +
      " · " + regionText + " · 검증점수 " + score + "%" +
      (liveBits.length ? " · " + liveBits.join(" · ") : " · 실시간 소스결과 수집 전");
    card.appendChild(meta);

    const tags = document.createElement("div");
    tags.className = "tcg-registry-tags";
    const capLabels = [
      ["market", "시세"],
      ["release", "출시"],
      ["promo", "행사"],
      ["purchase", "구매"]
    ];
    for (const [key, label] of capLabels) {
      if (game.capabilities[key]) tags.appendChild(span("tcg-registry-tag", label));
    }
    if (game.capabilities.grading) tags.appendChild(span("tcg-registry-tag", "등급"));
    else tags.appendChild(span("tcg-registry-tag blocked", "등급 미지원"));
    if (game.state === "watch") tags.appendChild(span("tcg-registry-tag blocked", "실시간 구매 차단"));
    card.appendChild(tags);

    const links = document.createElement("div");
    links.className = "tcg-registry-links";
    addLink(links, "공식 출처", game.official_source);
    addLink(links, "시장 출처", game.market_source);
    if (links.childNodes.length) card.appendChild(links);
    return card;
  }

  function addGroup(parent, titleText, games, signals, coverage, open) {
    const details = document.createElement("details");
    details.className = "tcg-registry-group";
    details.open = Boolean(open);
    const summary = document.createElement("summary");
    summary.textContent = titleText + " · " + games.length + "종";
    details.appendChild(summary);
    const grid = document.createElement("div");
    grid.className = "tcg-registry-grid";
    for (const game of games) grid.appendChild(gameCard(game, signals.get(game.id), coverage.get(game.id)));
    details.appendChild(grid);
    parent.appendChild(details);
  }

  function renderHub(games, signalPayload, coveragePayload) {
    const hub = document.getElementById("tcgRegistryMarketHub");
    if (!hub) return;
    while (hub.firstChild) hub.removeChild(hub.firstChild);
    hub.className = "tcg-registry-hub";

    const core = games.filter((row) => row.state === "core");
    const promoted = games.filter((row) => row.state === "promoted");
    const watch = games.filter((row) => row.state === "watch");

    const head = document.createElement("div");
    head.className = "tcg-registry-head";
    const intro = document.createElement("div");
    const title = document.createElement("div");
    title.className = "tcg-registry-title";
    title.textContent = "🌐 확장 TCG 수집 · 시장 현황";
    intro.appendChild(title);
    const sub = document.createElement("div");
    sub.className = "tcg-registry-sub";
    sub.textContent = "등급측정은 검증된 핵심 3종만 유지하고, 다른 TCG는 시장·출시·프로모·구매 소스와 승격 근거를 별도로 수집합니다.";
    intro.appendChild(sub);
    head.appendChild(intro);
    const counts = document.createElement("div");
    counts.className = "tcg-registry-counts";
    counts.appendChild(span("tcg-registry-pill", "핵심 " + core.length));
    counts.appendChild(span("tcg-registry-pill promoted", "확장 " + promoted.length));
    counts.appendChild(span("tcg-registry-pill watch", "WATCH " + watch.length));
    counts.appendChild(span("tcg-registry-pill", "총 " + games.length));
    head.appendChild(counts);
    hub.appendChild(head);

    const actions = document.createElement("div");
    actions.className = "tcg-registry-actions";
    const collect = document.createElement("button");
    collect.type = "button";
    collect.className = "primary";
    collect.textContent = "🔄 확장 TCG 포함 전체 자료 수집";
    collect.addEventListener("click", () => {
      const all = document.getElementById("siteUpdateAll");
      if (all && !all.disabled) all.click();
      else {
        const status = document.getElementById("tcgRegistryStatus");
        if (status) status.textContent = "전체 수집 버튼을 사용할 수 없습니다. 태블릿 로컬 서버 연결 상태를 확인하세요.";
      }
    });
    actions.appendChild(collect);
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "secondary";
    refresh.textContent = "↻ 수집상태 새로고침";
    refresh.addEventListener("click", () => window.tcgRegistryUIRefresh && window.tcgRegistryUIRefresh(true));
    actions.appendChild(refresh);
    hub.appendChild(actions);

    const status = document.createElement("div");
    status.id = "tcgRegistryStatus";
    status.className = "tcg-registry-status";
    const sourceTime = signalPayload && signalPayload.updated_at ? new Date(signalPayload.updated_at).toLocaleString("ko-KR") : "아직 확장 소스 수집 전";
    const coverage = coveragePayload && coveragePayload.summary ? coveragePayload.summary : {};
    const missing = Number(coverage.missing_cells);
    status.textContent =
      "registry " + games.length + "종 · 확장 소스 확인 " + sourceTime +
      (Number.isFinite(missing) ? " · 다중소스 미확인 셀 " + missing.toLocaleString("ko-KR") + "개" : "") +
      " · 확인되지 않은 가격/재고/수익은 생성하지 않습니다.";
    hub.appendChild(status);

    const signals = signalMap(signalPayload);
    const coverageById = coverageMap(coveragePayload);
    addGroup(hub, "✅ 확장 수집 활성", promoted, signals, coverageById, true);
    addGroup(hub, "👀 WATCH · 승격 근거 관찰", watch, signals, coverageById, false);

    const warning = document.createElement("div");
    warning.className = "tcg-registry-warning";
    warning.textContent = "WATCH TCG는 화면에서 수집·검증 상태만 보여주며 등급측정과 실시간 구매검색에는 넣지 않습니다. promoted TCG도 별도 등급 보정자료가 없으므로 등급측정은 비활성입니다.";
    hub.appendChild(warning);
  }

  async function refresh(force = false) {
    if (refreshBusy) return {ok: true, busy: true};
    refreshBusy = true;
    const hub = document.getElementById("tcgRegistryMarketHub");
    try {
      if (hub) {
        hub.className = "tcg-registry-hub";
        hub.textContent = "확장 TCG registry와 최근 수집상태를 확인하는 중입니다.";
      }
      const results = await Promise.all([
        fetchJson(REGISTRY_URL, false, force),
        fetchJson(SIGNAL_URL, true, force),
        fetchJson(COVERAGE_URL, true, force)
      ]);
      const games = validateRegistry(results[0]);
      const selectorCounts = populateSelectors(games);
      const publicGames = games.map((row) => ({
        id: row.id,
        canonical: row.canonical,
        label_ko: row.label_ko,
        state: row.state,
        purchase_value: row.purchase_value,
        promo_value: row.promo_value,
        regions: [...row.regions],
        capabilities: {...row.capabilities},
        official_source: row.official_source,
        market_source: row.market_source
      }));
      window.tcgRegistryGames = publicGames;
      try {
        window.dispatchEvent(new CustomEvent("tcg:registry-updated", {
          detail: {version: VERSION, games: publicGames}
        }));
      } catch (_) {
        /* Old WebViews may not expose CustomEvent; the global snapshot remains available. */
      }
      renderHub(games, results[1], results[2]);
      return {ok: true, version: VERSION, games: games.length, selectors: selectorCounts};
    } catch (error) {
      if (hub) {
        hub.className = "tcg-registry-hub";
        hub.textContent = "⚠️ 확장 TCG registry를 안전하게 불러오지 못했습니다. 기존 3종 UI는 그대로 유지합니다.";
      }
      return {ok: false, version: VERSION, error: String(error && error.message || error)};
    } finally {
      refreshBusy = false;
    }
  }

  window.tcgRegistryUIRefresh = refresh;

  const updateStatus = document.getElementById("siteUpdateStatus");
  if (updateStatus && typeof MutationObserver !== "undefined") {
    const observer = new MutationObserver(() => {
      const value = String(updateStatus.textContent || "");
      if (value.includes("전체정보 업데이트 완료") || value.includes("새로고침 완료")) {
        setTimeout(() => refresh(true), 250);
      }
    });
    observer.observe(updateStatus, {childList: true, subtree: true, characterData: true});
  }

  refresh(false);
})();
