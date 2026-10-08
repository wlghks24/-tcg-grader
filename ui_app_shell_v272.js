"use strict";
(() => {
  const VERSION = "v298-exact-psa9-probability";
  const main = document.querySelector("main.app");
  const nav = document.getElementById("featureCategories");
  if (!main || !nav) return;

  if (!main.id) main.id = "tcgMain";
  if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");

  let skip = document.querySelector(".ui-skip-link");
  if (!skip) {
    skip = document.createElement("a");
    skip.className = "ui-skip-link";
    skip.href = `#${main.id}`;
    skip.textContent = "본문 바로가기";
    document.body.insertBefore(skip, document.body.firstChild);
  }

  let host = nav.querySelector(".feature-quick-search");
  let input;
  let clear;
  let status;
  if (!host) {
    host = document.createElement("div");
    host.className = "feature-quick-search";
    host.setAttribute("role", "search");

    const label = document.createElement("label");
    label.htmlFor = "featureQuickSearch";
    label.textContent = "기능 빠른 검색";

    const row = document.createElement("div");
    row.className = "feature-quick-search-row";

    input = document.createElement("input");
    input.id = "featureQuickSearch";
    input.type = "search";
    input.inputMode = "search";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = "예: 시세, OCR, BOX, 태블릿";
    input.setAttribute("aria-describedby", "featureQuickSearchStatus");

    clear = document.createElement("button");
    clear.type = "button";
    clear.className = "feature-quick-search-clear";
    clear.textContent = "지우기";
    clear.disabled = true;
    clear.setAttribute("aria-label", "기능 검색어 지우기");

    status = document.createElement("div");
    status.id = "featureQuickSearchStatus";
    status.className = "feature-quick-search-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = "카테고리 또는 기능 이름을 입력하면 목록을 좁힙니다.";

    row.append(input, clear);
    host.append(label, row, status);
    const selected = nav.querySelector("#featureCategorySelected");
    if (selected?.nextSibling) nav.insertBefore(host, selected.nextSibling);
    else nav.append(host);
  } else {
    input = host.querySelector("input[type='search']");
    clear = host.querySelector(".feature-quick-search-clear");
    status = host.querySelector(".feature-quick-search-status");
  }
  if (!input || !clear || !status) return;

  const categories = [...nav.querySelectorAll(".feature-category")];
  const normalize = (value) => String(value || "").normalize("NFKC").trim().toLocaleLowerCase("ko-KR");

  function searchableText(node) {
    return normalize(node?.textContent || "").replace(/\s+/g, " ");
  }

  function resetNode(node, attr) {
    node.removeAttribute(attr);
  }

  function filterFeatures(query) {
    const needle = normalize(query);
    let visibleCategories = 0;
    let visibleShortcuts = 0;

    categories.forEach((category) => {
      const shortcuts = [...category.querySelectorAll(".feature-shortcut")];
      if (!needle) {
        resetNode(category, "data-ui-filter-hidden");
        resetNode(category, "data-ui-search-hit");
        shortcuts.forEach((shortcut) => resetNode(shortcut, "data-ui-filter-hidden"));
        visibleCategories += 1;
        visibleShortcuts += shortcuts.length;
        return;
      }

      const ownText = searchableText(category.querySelector("summary"));
      const categoryHit = ownText.includes(needle);
      let shortcutHits = 0;
      shortcuts.forEach((shortcut) => {
        const hit = categoryHit || searchableText(shortcut).includes(needle);
        shortcut.toggleAttribute("data-ui-filter-hidden", !hit);
        if (hit) shortcutHits += 1;
      });

      const categoryVisible = categoryHit || shortcutHits > 0;
      category.toggleAttribute("data-ui-filter-hidden", !categoryVisible);
      category.toggleAttribute("data-ui-search-hit", categoryVisible);
      if (categoryVisible) {
        visibleCategories += 1;
        visibleShortcuts += shortcutHits || shortcuts.length;
      } else if (category.open) {
        category.open = false;
      }
    });

    clear.disabled = !needle;
    if (!needle) {
      status.dataset.state = "idle";
      status.textContent = "카테고리 또는 기능 이름을 입력하면 목록을 좁힙니다.";
    } else if (visibleCategories) {
      status.dataset.state = "match";
      status.textContent = `${visibleCategories}개 카테고리 · ${visibleShortcuts}개 기능을 찾았습니다.`;
    } else {
      status.dataset.state = "empty";
      status.textContent = "일치하는 기능이 없습니다. 다른 검색어를 입력하세요.";
    }
    return { query: needle, visibleCategories, visibleShortcuts };
  }

  function clearSearch({ focus = false } = {}) {
    input.value = "";
    const result = filterFeatures("");
    if (focus) input.focus();
    return result;
  }

  input.addEventListener("input", () => filterFeatures(input.value));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && input.value) {
      event.preventDefault();
      clearSearch({ focus: true });
    }
  });
  clear.addEventListener("click", () => clearSearch({ focus: true }));

  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    const tag = String(target?.tagName || "").toLowerCase();
    if (target?.isContentEditable || ["input", "textarea", "select"].includes(tag)) return;
    event.preventDefault();
    input.focus();
    input.select();
  });

  skip.addEventListener("click", () => {
    setTimeout(() => main.focus({ preventScroll: true }), 0);
  });

  const RESULT_COMPANIES = Object.freeze(["PSA", "BGS", "CGC", "TAG", "BRG"]);
  const gradeCockpitState = { signature: "", timer: 0 };
  const byId = (id) => document.getElementById(id);
  const nodeText = (id) => String(byId(id)?.textContent || "").trim();
  const nodeValue = (id) => String(byId(id)?.value || "").trim();

  // Empty, boolean and out-of-range values are missing evidence, not grades.
  function boundedNumber(value, min, max) {
    if (typeof value !== "number" && typeof value !== "string") return null;
    if (typeof value === "string" && !value.trim()) return null;
    const number = Number(value);
    return Number.isFinite(number) && number >= min && number <= max ? number : null;
  }

  function addCockpitCell(grid, labelText, valueId, wide = false) {
    const cell = document.createElement("div");
    cell.className = wide ? "grade-cockpit-cell grade-cockpit-cell-wide" : "grade-cockpit-cell";
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("b");
    value.id = valueId;
    value.textContent = "-";
    cell.append(label, value);
    grid.append(cell);
  }

  function addProbabilityCell(grid, grade) {
    const cell = document.createElement("div");
    cell.className = "grade-cockpit-probability";
    const label = document.createElement("span");
    label.textContent = `PSA ${grade}`;
    const value = document.createElement("b");
    value.id = `gradeCockpitPsa${grade}`;
    value.textContent = "-";
    cell.append(label, value);
    grid.append(cell);
  }

  function addCompanyCell(grid, company) {
    const cell = document.createElement("div");
    cell.className = "grade-cockpit-company";
    const label = document.createElement("span");
    label.textContent = company;
    const value = document.createElement("b");
    value.id = `gradeCockpit${company}`;
    value.textContent = "대기";
    cell.append(label, value);
    grid.append(cell);
  }

  function ensureGradeCockpit() {
    if (byId("gradeResultCockpit")) return true;
    const anchor = byId("autoGradeMarketFlow");
    if (!anchor) return false;

    const panel = document.createElement("div");
    panel.id = "gradeResultCockpit";
    panel.className = "grade-result-cockpit";
    panel.dataset.state = "waiting";
    panel.setAttribute("aria-labelledby", "gradeResultCockpitTitle");

    const head = document.createElement("div");
    head.className = "grade-cockpit-head";
    const titleWrap = document.createElement("div");
    const title = document.createElement("h4");
    title.id = "gradeResultCockpitTitle";
    title.textContent = "📋 등급 결과 한눈에 보기";
    const subtitle = document.createElement("p");
    subtitle.textContent = "카드정보 · 세대/세트 · 예상등급 · PSA 확률 · RAW/예상등급 시세 · 추천 거래금액을 한 화면에 모읍니다. 게임별 세트정보와 구매처도 확인할 수 있습니다.";
    titleWrap.append(title, subtitle);
    const badge = document.createElement("span");
    badge.className = "grade-cockpit-ai-badge";
    badge.textContent = "AI 추정 · 공식등급 아님";
    head.append(titleWrap, badge);

    const grid = document.createElement("div");
    grid.className = "grade-cockpit-grid";
    addCockpitCell(grid, "카드", "gradeCockpitCard", true);
    addCockpitCell(grid, "게임", "gradeCockpitGame");
    addCockpitCell(grid, "판본", "gradeCockpitEdition");
    addCockpitCell(grid, "세대 / 세트", "gradeCockpitGeneration");
    addCockpitCell(grid, "종합 예상등급", "gradeCockpitOverall");
    addCockpitCell(grid, "분석 신뢰도", "gradeCockpitConfidence");
    addCockpitCell(grid, "RAW 현재 시세", "gradeCockpitRaw");
    addCockpitCell(grid, "추천 거래 기준가", "gradeCockpitRecommended");
    addCockpitCell(grid, "추천 거래 범위", "gradeCockpitRange");
    addCockpitCell(grid, "예상 PSA 시세", "gradeCockpitPsaMarket");

    const probabilityBlock = document.createElement("div");
    probabilityBlock.className = "grade-cockpit-block";
    const probabilityTitle = document.createElement("b");
    probabilityTitle.className = "grade-cockpit-block-title";
    probabilityTitle.textContent = "PSA 예상확률";
    const probabilityGrid = document.createElement("div");
    probabilityGrid.className = "grade-cockpit-probabilities";
    [8, 9, 10].forEach((grade) => addProbabilityCell(probabilityGrid, grade));
    probabilityBlock.append(probabilityTitle, probabilityGrid);

    const companyBlock = document.createElement("div");
    companyBlock.className = "grade-cockpit-block";
    const companyTitle = document.createElement("b");
    companyTitle.className = "grade-cockpit-block-title";
    companyTitle.textContent = "업체별 예상등급";
    const companyGrid = document.createElement("div");
    companyGrid.className = "grade-cockpit-companies";
    RESULT_COMPANIES.forEach((company) => addCompanyCell(companyGrid, company));
    companyBlock.append(companyTitle, companyGrid);

    const marketBlock = document.createElement("div");
    marketBlock.className = "grade-cockpit-block grade-cockpit-market-block";
    const marketTitle = document.createElement("b");
    marketTitle.className = "grade-cockpit-block-title";
    marketTitle.textContent = "💰 추천 거래금액 · 출처별 참고가";
    const marketMeta = document.createElement("p");
    marketMeta.id = "gradeCockpitMarketMeta";
    marketMeta.className = "grade-cockpit-market-meta";
    marketMeta.textContent = "카드번호·판본·변형이 확인되면 여러 마켓 근거를 교차확인합니다.";
    const marketSources = document.createElement("div");
    marketSources.id = "gradeCockpitMarketSources";
    marketSources.className = "grade-cockpit-market-sources";
    const marketWaiting = document.createElement("span");
    marketWaiting.className = "grade-cockpit-market-empty";
    marketWaiting.textContent = "시세 근거 수집 대기";
    marketSources.append(marketWaiting);
    marketBlock.append(marketTitle, marketMeta, marketSources);

    const purchaseBlock = document.createElement("div");
    purchaseBlock.className = "grade-cockpit-block grade-cockpit-purchase-block";
    const purchaseTitle = document.createElement("b");
    purchaseTitle.className = "grade-cockpit-block-title";
    purchaseTitle.textContent = "🛒 이 카드 구매처 찾기";
    const purchaseMeta = document.createElement("p");
    purchaseMeta.id = "gradeCockpitPurchaseMeta";
    purchaseMeta.className = "grade-cockpit-purchase-meta";
    purchaseMeta.setAttribute("role", "status");
    purchaseMeta.setAttribute("aria-live", "polite");
    purchaseMeta.textContent = "카드명을 확인하면 온라인과 주변 매장 후보를 검색할 수 있습니다.";
    const purchaseActions = document.createElement("div");
    purchaseActions.className = "grade-cockpit-purchase-actions";
    const purchaseOnline = document.createElement("button");
    purchaseOnline.id = "gradeCockpitPurchaseOnline";
    purchaseOnline.type = "button";
    purchaseOnline.textContent = "🌐 온라인 판매처";
    const purchaseNearby = document.createElement("button");
    purchaseNearby.id = "gradeCockpitPurchaseNearby";
    purchaseNearby.type = "button";
    purchaseNearby.textContent = "📍 주변 매장";
    purchaseActions.append(purchaseOnline, purchaseNearby);
    purchaseBlock.append(purchaseTitle, purchaseMeta, purchaseActions);

    const source = document.createElement("p");
    source.id = "gradeCockpitEvidence";
    source.className = "grade-cockpit-evidence";
    source.textContent = "시세는 체결·낙찰 / 시장가이드 / 판매중 호가를 구분해 확인하세요.";

    const note = document.createElement("p");
    note.className = "grade-cockpit-note";
    note.textContent = "포켓몬은 세대 정보를 표시하고, 원피스·나루토는 세대 대신 탄/세트·판본 기준으로 확인합니다.";

    panel.append(head, grid, probabilityBlock, companyBlock, marketBlock, purchaseBlock, source, note);
    const anchorHead = anchor.querySelector(".agm-head");
    if (anchorHead?.nextSibling) anchor.insertBefore(panel, anchorHead.nextSibling);
    else anchor.prepend(panel);
    return true;
  }

  function probabilityText(grade) {
    const probabilities = window.tcgGradeProbabilities || {};
    const raw = boundedNumber(probabilities[grade], 0, 100);
    if (raw !== null) return `${raw.toFixed(0)}%`;
    // PSA 9 must never fall back to the legacy p9prob element because that
    // element represents cumulative PSA 9+ rather than the exact PSA 9 bucket.
    if (grade === 10) {
      const fallback = nodeText("p10prob");
      if (fallback && fallback !== "-") return fallback;
    }
    return "-";
  }

  function activeGradeGame() {
    const token = document.querySelector("[data-simple-game].active")?.dataset?.simpleGame || "";
    return ["pokemon", "onepiece", "naruto"].includes(token) ? token : "";
  }

  function gradeGameLabel(game) {
    return ({pokemon: "포켓몬", onepiece: "원피스", naruto: "나루토"})[game] || "게임 확인 필요";
  }

  function generationText(number = nodeValue("identityCardNumber")) {
    const game = activeGradeGame();
    const generation = byId("simplePokemonGeneration");
    if (game === "pokemon" && generation && !generation.hidden) {
      const badge = nodeText("pokemonGenerationBadge");
      const title = nodeText("pokemonGenerationTitle");
      return [badge, title].filter(Boolean).join(" · ") || "판별 중";
    }
    const value = String(number || "").toUpperCase().replace(/\s+/g, "");
    if (game === "onepiece") {
      const matched = value.match(/^(OP|ST|EB|PRB|CP)(\d{1,2})-/);
      if (matched) {
        const set = matched[1] + "-" + matched[2].padStart(2, "0");
        return set + " · " + ({OP:"부스터",ST:"스타터",EB:"엑스트라 부스터",PRB:"프리미엄 부스터",CP:"제품 계열"})[matched[1]] + " 계열";
      }
      if (/^P-?\d{1,3}$/.test(value)) return "P · 프로모 계열";
      return "세트코드 확인 필요 · 포켓몬식 세대 미적용";
    }
    if (game === "naruto") return "세트/발행판 정보 확인 필요 · 세대 미확정";
    return game === "pokemon" ? "세대 판별 대기" : "게임 선택 후 판별";
  }

  function purchaseValueForGame(game) {
    return ({pokemon: "Pokemon", onepiece: "ONE PIECE", naruto: "NARUTO"})[game] || "";
  }

  function openPurchaseFinder(mode) {
    const meta = byId("gradeCockpitPurchaseMeta");
    const panel = byId("purchasePanel");
    const name = nodeValue("identityCardName") || nodeText("agmName");
    const number = nodeValue("identityCardNumber") || nodeText("agmNumber");
    const game = purchaseValueForGame(activeGradeGame());
    const gameSelect = byId("purchaseGame");
    const search = byId("purchaseQuery");
    const gameAvailable = Boolean(game && gameSelect && [...gameSelect.options].some((opt) => opt.value === game && !opt.disabled));
    if (!panel || !search || !gameAvailable || !name || name === "인식 대기" || name === "-") {
      if (meta) meta.textContent = "게임·카드명·구매처 선택을 확인해 주세요. 다른 게임의 판매처로 잘못 이동하지 않습니다.";
      return false;
    }
    const query = [name, number && number !== "-" ? number : ""].filter(Boolean).join(" ").trim();
    gameSelect.value = game;
    gameSelect.dispatchEvent(new Event("change", {bubbles: true}));
    search.value = query;
    search.dispatchEvent(new Event("input", {bubbles: true}));
    const asset = byId("purchaseAsset");
    if (asset && [...asset.options].some((opt) => opt.value === "card" && !opt.disabled)) {
      asset.value = "card";
      asset.dispatchEvent(new Event("change", {bubbles: true}));
    }
    const topTab = document.querySelector('.top-info-tab[data-top-panel="purchasePanel"]');
    if (topTab) topTab.click();
    else if (window.TCGFeatureCategoryNav?.activateTopPanel) window.TCGFeatureCategoryNav.activateTopPanel("purchasePanel");
    const offline = mode === "nearby";
    document.querySelector('[data-purchase-channel="' + (offline ? "offline" : "online") + '"]')?.click();
    if (offline && byId("purchaseSort")) byId("purchaseSort").value = "nearby";
    if (typeof window.renderPurchaseSources === "function") window.renderPurchaseSources();
    panel.scrollIntoView?.({behavior: "smooth", block: "start"});
    if (meta) meta.textContent = offline
      ? "주변 취급점 후보입니다. 위치 설정 후 거리순으로 확인하세요. 카드 취급 및 재고는 방문 전 문의하세요."
      : "온라인 판매처 검색 후보입니다. 판본·상태·판매자·배송비 및 실제 재고를 확인하세요.";
    return true;
  }

  function safeEvidenceHttps(value) {
    try {
      const original = String(value || "").trim();
      if (!original.startsWith("https://")) return "";
      const url = new URL(original);
      if (url.username || url.password || url.port) return "";
      const domain = url.hostname.toLowerCase();
      const allowed = ["ebay.com", "tcgplayer.com", "cardmarket.com", "snkrdunk.com",
        "amazon.com", "amazon.co.jp", "kream.co.kr", "daangn.com", "bunjang.co.kr",
        "joongna.com", "collectory.cc", "justtcg.com", "tcgdex.net", "pavilion-tcg.com",
        "mercari.com", "yahoo.co.jp"];
      if (!allowed.some((host) => domain === host || domain.endsWith("." + host))) return "";
      return url.href;
    } catch (_) {
      return "";
    }
  }

  function formatCompanyGrade(company, grades) {
    const raw = boundedNumber(grades?.[company], 1, 10);
    if (raw === null) return "대기";
    return `${raw.toFixed(raw % 1 ? 1 : 0)} 예상`;
  }

  function krwText(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? `₩${Math.round(number).toLocaleString("ko-KR")}` : "-";
  }

  function identityToken(value) {
    return normalize(value).replace(/[^0-9a-z가-힣]/g, "");
  }

  function canonicalMarketGame(value) {
    // The market selector uses "Pokémon"; grading and purchase use "Pokemon".
    const token = String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
    return ["pokemon", "onepiece", "naruto"].includes(token) ? token : "";
  }

  function marketIdentityMatches(market, name, number, game) {
    // A partial card-number match (025 within 1025), an unrelated game, or an
    // earlier search must never supply prices to the current grading result.
    if (!market || market.ok !== true) return false;
    const requestedGame = canonicalMarketGame(purchaseValueForGame(game));
    const actualGame = canonicalMarketGame(market.game);
    if (!requestedGame || requestedGame !== actualGame) return false;
    const requestedName = identityToken(name);
    const query = String(market.query || "");
    if (!requestedName || !identityToken(query).includes(requestedName)) return false;
    const requestedNumber = identityToken(number);
    if (!requestedNumber) return false;
    return query.split(/\s+/).some((part) => identityToken(part) === requestedNumber);
  }

  function marketView(grades, name, number) {
    const market = window.__multiMarketPrices && typeof window.__multiMarketPrices === "object"
      ? window.__multiMarketPrices
      : null;
    const safeMarket = marketIdentityMatches(market, name, number, activeGradeGame()) ? market : {};
    const info = safeMarket.summary && typeof safeMarket.summary === "object" ? safeMarket.summary : {};
    const recommended = Number(info.recommended_trade_krw || 0);
    const low = Number(info.recommendation_min_krw || 0);
    const high = Number(info.recommendation_max_krw || 0);
    const sourceCount = Number(info.recommendation_source_count || 0);
    const sampleCount = Number(info.recommendation_sample_count || 0);
    const recommendationText = recommended > 0 ? krwText(recommended) : "근거 부족";
    const rangeText = low > 0 && high > 0 ? `${krwText(low)} ~ ${krwText(high)}` : "근거 부족";
    const condition = String(safeMarket.condition || info.requested_condition || "ALL");
    const printing = String(safeMarket.printing || info.requested_printing || "ALL");
    const conditionText = condition === "ALL" ? "상태 전체" : `상태 ${condition}`;
    const printingNames = {ALL:"인쇄 자동/전체",standard:"일반판",holo:"홀로",reverse_holo:"리버스 홀로",foil:"포일",parallel:"패러렐",special_art:"스페셜 아트",alt_art:"얼터 아트",full_art:"풀 아트",manga:"만화 레어",promo:"프로모"};
    const printingText = printingNames[printing] || printing;
    const freshnessText = String(info.recommendation_freshness || "확인 중");
    const metaText = recommended > 0
      ? `추천 근거: ${String(info.recommendation_basis || info.basis || "동일 기준")} · ${sourceCount}곳/${sampleCount}건 · 신뢰도 ${String(info.recommendation_confidence || "낮음")} · ${conditionText} · ${printingText} · 최신성 ${freshnessText}`
      : `추천가 보류: ${String(info.basis || "카드번호·판본·상태·변형 근거를 확인 중")} · ${conditionText} · ${printingText}`;

    const psa = boundedNumber(grades?.PSA, 1, 10);
    const psaGrade = psa !== null && Number.isInteger(psa) ? psa : null;
    const gradeRows = Array.isArray(safeMarket.grade_reference) ? safeMarket.grade_reference : [];
    const psaRow = psaGrade === null ? null : gradeRows.find((row) => String(row?.grade || "") === `PSA ${psaGrade}`);
    const psaRecommended = Number(psaRow?.recommended_trade_krw || psaRow?.price_krw || 0);
    const psaSourceCount = Number(psaRow?.recommendation_source_count || psaRow?.source_count || 0);
    const psaText = psaGrade === null
      ? "정확 등급 확인 후"
      : psaRecommended > 0
        ? `PSA ${psaGrade} · ${krwText(psaRecommended)} · ${psaSourceCount}곳`
        : `PSA ${psaGrade} · 거래자료 없음`;

    const rawRows = Array.isArray(safeMarket.source_breakdown)
      ? safeMarket.source_breakdown.filter((row) => Number(row?.price_krw) > 0).slice(0, 4)
      : [];
    const psaRows = Array.isArray(psaRow?.sources)
      ? psaRow.sources.filter((row) => Number(row?.price_krw) > 0).slice(0, 4)
      : [];
    const rowSignature = [...rawRows.map((row) => `RAW:${row.source_id || row.source}:${row.price_krw}:${row.basis}`),
      ...psaRows.map((row) => `PSA${psaGrade}:${row.source_id || row.source}:${row.price_krw}:${row.basis}`)].join(";");
    return {
      recommendationText, rangeText, metaText, psaText, rawRows, psaRows, psaGrade,
      signature: [market?.query || "", recommendationText, rangeText, metaText, psaText, rowSignature].join("|"),
    };
  }

  function appendMarketSourceCard(host, row, scopeLabel) {
    const card = document.createElement("div");
    card.className = "grade-cockpit-market-source";
    const head = document.createElement("div");
    head.className = "grade-cockpit-market-source-head";
    const source = document.createElement("b");
    source.textContent = String(row?.source || row?.source_id || "출처");
    const scope = document.createElement("span");
    scope.textContent = scopeLabel;
    head.append(source, scope);
    const price = document.createElement("strong");
    price.textContent = krwText(row?.price_krw);
    const detail = document.createElement("small");
    const contributes = row?.contributes_to_recommendation === true ? "추천가 반영" : "참고만";
    const age = Number.isFinite(Number(row?.freshness_age_days)) ? `${Number(row.freshness_age_days)}일 전` : "날짜 미확인";
    const sellers = Array.isArray(row?.seller_names) ? row.seller_names.filter(Boolean).slice(0, 2) : [];
    const seller = sellers.length ? ` · 판매자 ${sellers.join(" / ")}` : "";
    const conditions = Array.isArray(row?.conditions) && row.conditions.length ? ` · ${row.conditions.join("/")}` : "";
    detail.textContent = `${String(row?.basis || "가격")} · ${Number(row?.count) || 0}건 · ${contributes} · ${age}${conditions}${seller}`;
    card.append(head, price, detail);
    const href = safeEvidenceHttps(row?.sample_url);
    if (href) {
      const link = document.createElement("a");
      link.className = "grade-cockpit-market-link";
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "가격 원문 확인 ↗";
      card.append(link);
    }
    host.append(card);
  }

  function renderMarketSources(view) {
    const host = byId("gradeCockpitMarketSources");
    if (!host) return;
    host.replaceChildren();
    view.rawRows.forEach((row) => appendMarketSourceCard(host, row, "RAW"));
    view.psaRows.forEach((row) => appendMarketSourceCard(host, row, `PSA ${view.psaGrade}`));
    if (!host.children.length) {
      const empty = document.createElement("span");
      empty.className = "grade-cockpit-market-empty";
      empty.textContent = "정확히 일치하는 출처별 가격 근거가 아직 없습니다.";
      host.append(empty);
    }
  }

  function syncGradeCockpit() {
    if (!ensureGradeCockpit()) return false;
    const grades = window.tcgLastGrades || {};
    const name = nodeValue("identityCardName") || nodeText("agmName") || "인식 대기";
    const number = nodeValue("identityCardNumber") || nodeText("agmNumber") || "";
    const edition = nodeValue("identityRegion") || nodeText("agmRegion") || "판본 미확인";
    const game = activeGradeGame();
    const generation = generationText(number);
    const overall = nodeText("simpleGradeLabel") || "분석 전";
    const confidence = nodeText("simpleGradeConfidence") || "-";
    const rawPrice = nodeText("agmRawPrice") || "카드 인식 후 조회";
    const rawSource = nodeText("agmRawSource") || "확인된 거래자료만 표시";
    const p8 = probabilityText(8);
    const p9 = probabilityText(9);
    const p10 = probabilityText(10);
    const companyValues = RESULT_COMPANIES.map((company) => formatCompanyGrade(company, grades));
    const market = marketView(grades, name, number);
    const signature = [game, name, number, edition, generation, overall, confidence, rawPrice, rawSource, p8, p9, p10, market.signature, ...companyValues].join("|");
    if (signature === gradeCockpitState.signature) return true;
    gradeCockpitState.signature = signature;

    byId("gradeCockpitCard").textContent = [name, number].filter(Boolean).join(" · ") || "인식 대기";
    byId("gradeCockpitGame").textContent = gradeGameLabel(game);
    byId("gradeCockpitEdition").textContent = edition || "판본 미확인";
    byId("gradeCockpitGeneration").textContent = generation;
    byId("gradeCockpitOverall").textContent = overall;
    byId("gradeCockpitConfidence").textContent = confidence;
    byId("gradeCockpitRaw").textContent = rawPrice;
    byId("gradeCockpitRecommended").textContent = market.recommendationText;
    byId("gradeCockpitRange").textContent = market.rangeText;
    byId("gradeCockpitPsaMarket").textContent = market.psaText;
    byId("gradeCockpitMarketMeta").textContent = market.metaText;
    renderMarketSources(market);
    byId("gradeCockpitPsa8").textContent = p8;
    byId("gradeCockpitPsa9").textContent = p9;
    byId("gradeCockpitPsa10").textContent = p10;
    RESULT_COMPANIES.forEach((company, index) => {
      byId(`gradeCockpit${company}`).textContent = companyValues[index];
    });
    byId("gradeCockpitEvidence").textContent = `시세 근거: ${rawSource}`;
    if (byId("gradeCockpitPurchaseMeta")) byId("gradeCockpitPurchaseMeta").textContent = name && name !== "인식 대기" ? `검색 준비: ${gradeGameLabel(game)} · ${[name, number].filter(Boolean).join(" · ")}` : "카드명 확인 후 구매처 후보를 검색할 수 있습니다.";

    const ready = RESULT_COMPANIES.some((company) => boundedNumber(grades?.[company], 1, 10) !== null);
    byId("gradeResultCockpit").dataset.state = ready ? "ready" : "waiting";
    return true;
  }

  function stopGradeCockpitTimer() {
    if (gradeCockpitState.timer) {
      clearInterval(gradeCockpitState.timer);
      gradeCockpitState.timer = 0;
    }
  }

  function startGradeCockpitTimer() {
    if (document.hidden || gradeCockpitState.timer) return;
    syncGradeCockpit();
    gradeCockpitState.timer = setInterval(syncGradeCockpit, 1000);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopGradeCockpitTimer();
    else startGradeCockpitTimer();
  });
  document.addEventListener("input", (event) => {
    if (["identityCardName", "identityCardNumber", "identityRegion"].includes(event.target?.id)) syncGradeCockpit();
  });
  document.addEventListener("change", (event) => {
    if (["identityCardName", "identityCardNumber", "identityRegion"].includes(event.target?.id)) syncGradeCockpit();
  });
  document.addEventListener("click", (event) => {
    const button = event.target?.closest?.("#gradeCockpitPurchaseOnline, #gradeCockpitPurchaseNearby");
    if (!button) return;
    event.preventDefault();
    openPurchaseFinder(button.id === "gradeCockpitPurchaseNearby" ? "nearby" : "online");
  });
  window.addEventListener("tcg:registry-updated", syncGradeCockpit);
  window.addEventListener("tcg:multi-market-updated", syncGradeCockpit);
  window.addEventListener("pagehide", stopGradeCockpitTimer);
  window.addEventListener("pageshow", startGradeCockpitTimer);
  startGradeCockpitTimer();

  window.TCGAppShellV272 = Object.freeze({
    version: VERSION,
    filterFeatures,
    clear: () => clearSearch(),
    refreshGradeSummary: syncGradeCockpit,
  });
})();
