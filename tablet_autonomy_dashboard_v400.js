(() => {
  "use strict";

  const VERSION = "v400-screen-neural-champion";
  const REPORT_URL = "./tablet_autonomy_v400_report.json";
  const LAYOUT_PREF_KEY = "tcgAdaptiveLayoutV400";
  const EXPERIENCE_PREF_KEY = "tcgVideoExperienceV403";
  const EXPERIENCE_KEYS = Object.freeze([
    "home-market-pulse",
    "capture-quality-gate",
    "purchase-split-view",
    "hot-card-box-ranking",
    "portfolio-summary",
  ]);
  const EXPERIENCE_LABELS = Object.freeze({
    "home-market-pulse":"시장 흐름 홈",
    "capture-quality-gate":"촬영 품질 게이트",
    "purchase-split-view":"구매처 지도·지역",
    "hot-card-box-ranking":"HOT 카드·BOX",
    "portfolio-summary":"내 카드 요약",
  });
  const CATEGORY_KEYS = Object.freeze(["grading","market","box","news","purchase","learning","tablet","code"]);
  const FEATURE_KEYS = Object.freeze({
    grading:Object.freeze(["auto-grade","manual-photo","precision-grade"]),
    market:Object.freeze(["market-search","grading-economics","trading-catalog"]),
    box:Object.freeze(["box-knowledge","box-hit-analysis"]),
    news:Object.freeze(["release-info","promo-event-info"]),
    purchase:Object.freeze(["purchase-finder","purchase-distance"]),
    learning:Object.freeze(["card-ocr","verified-grade","learning-status"]),
    tablet:Object.freeze(["tablet-manager"]),
    code:Object.freeze(["code-audit","code-validation"]),
  });
  const FEATURE_TARGETS = Object.freeze({
    "auto-grade":"simpleGradeV32", "manual-photo":"gradeStart", "precision-grade":"precisionHub",
    "market-search":"market12section", "grading-economics":"gradingEconomics", "trading-catalog":"tradingCatalogSection",
    "box-knowledge":"box12section", "box-hit-analysis":"v14section",
    "release-info":"releaseBoard", "promo-event-info":"releaseBoard",
    "purchase-finder":"releaseBoard", "purchase-distance":"releaseBoard",
    "card-ocr":"simpleGradeV32", "verified-grade":"v30validation", "learning-status":"v31testdashboard",
    "tablet-manager":"tabletManagerHub", "code-audit":"audit15", "code-validation":"v31testdashboard",
  });
  const FEATURE_LABELS = Object.freeze({
    "auto-grade":"자동촬영 등급", "manual-photo":"사진 직접 등록", "precision-grade":"1→4→8 정밀측정",
    "market-search":"시세 검색", "grading-economics":"등급사 예상가", "trading-catalog":"거래중 카드·BOX",
    "box-knowledge":"BOX 지식", "box-hit-analysis":"BOX HIT 분석",
    "release-info":"출시·재발매", "promo-event-info":"프로모·콜라보",
    "purchase-finder":"구매처 찾기", "purchase-distance":"위치·거리",
    "card-ocr":"카드 OCR", "verified-grade":"실제등급 검증", "learning-status":"학습 상태",
    "tablet-manager":"태블릿 관리", "code-audit":"코드 오류검사", "code-validation":"자동검증 결과",
  });
  const categoryLabels = Object.freeze({
    grading:"카드 분석 · 등급", market:"카드 시세", box:"BOX · HIT", news:"출시 · 프로모 · 행사",
    purchase:"구매처 · 재고", learning:"OCR · 학습", tablet:"태블릿 관리", code:"코드 검사"
  });
  const labels = Object.freeze({
    ui:"UI · PWA",
    card_measurement:"카드 측정 · 등급",
    card_market:"카드 시세",
    card_release:"카드 발급 · 출시",
    collab_event:"콜라보 · 이벤트",
    purchase_availability:"구매처 · 재고신호",
    tablet_ops:"태블릿 운영",
  });
  let refreshMs = 45000;
  let timer = null;
  let lastLayout = null;
  let originalOrder = null;
  let originalFeatureOrders = null;
  let sessionLayoutPreference = null;
  let sessionExperiencePreference = null;
  let originalExperienceOrder = null;
  let marketExperienceCache = null;
  let marketExperienceLoadedAt = 0;
  let cameraQualityObserver = null;

  const asText = (value, fallback = "—") =>
    value === null || value === undefined || value === "" ? fallback : String(value);

  const pct = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? Math.round(Math.max(0, Math.min(1, n)) * 100) + "%" : "—";
  };

  function node(tag, cls, text) {
    const item = document.createElement(tag);
    if (cls) item.className = cls;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function metric(label) {
    const box = node("div", "tablet-autonomy-metric");
    box.append(node("span", "", label));
    const value = node("b", "", "—");
    box.append(value);
    return {box, value};
  }

  function layoutEnabled() {
    if (sessionLayoutPreference !== null) return sessionLayoutPreference;
    try { return localStorage.getItem(LAYOUT_PREF_KEY) !== "off"; }
    catch (_) { return true; }
  }

  function saveLayoutPreference(enabled) {
    sessionLayoutPreference = Boolean(enabled);
    try { localStorage.setItem(LAYOUT_PREF_KEY, enabled ? "on" : "off"); }
    catch (_) { /* sessionLayoutPreference still preserves the user's choice */ }
  }

  function experienceEnabled() {
    if (sessionExperiencePreference !== null) return sessionExperiencePreference;
    try { return localStorage.getItem(EXPERIENCE_PREF_KEY) !== "off"; }
    catch (_) { return true; }
  }

  function saveExperiencePreference(enabled) {
    sessionExperiencePreference = Boolean(enabled);
    try { localStorage.setItem(EXPERIENCE_PREF_KEY, enabled ? "on" : "off"); }
    catch (_) { /* session preference only */ }
  }

  function categoryContainer() {
    return document.getElementById("featureCategories");
  }

  function categoryNodes() {
    const container = categoryContainer();
    if (!container) return [];
    return [...container.querySelectorAll(".feature-category[data-category-key]")];
  }

  function featureNodes(category) {
    if (!category) return [];
    return [...category.querySelectorAll(".feature-shortcut[data-feature-key]")];
  }

  function captureOriginalFeatureOrders() {
    if (originalFeatureOrders) return originalFeatureOrders;
    const result = {};
    for (const category of categoryNodes()) {
      const key = String(category.dataset.categoryKey || "");
      if (!FEATURE_KEYS[key]) continue;
      const current = featureNodes(category).map((item) => String(item.dataset.featureKey || ""));
      const expected = FEATURE_KEYS[key];
      result[key] = current.length === expected.length
        && new Set(current).size === expected.length
        && expected.every((item) => current.includes(item))
        ? current
        : [...expected];
    }
    originalFeatureOrders = result;
    return originalFeatureOrders;
  }

  function validFeaturePlan(plan) {
    if (!plan || typeof plan !== "object") return false;
    if (!plan.feature_orders || typeof plan.feature_orders !== "object") return false;
    if (!plan.feature_allowlist || typeof plan.feature_allowlist !== "object") return false;
    return CATEGORY_KEYS.every((category) => {
      const expected = FEATURE_KEYS[category];
      const order = Array.isArray(plan.feature_orders[category]) ? plan.feature_orders[category].map(String) : [];
      const allowed = Array.isArray(plan.feature_allowlist[category]) ? plan.feature_allowlist[category].map(String) : [];
      return order.length === expected.length
        && allowed.length === expected.length
        && new Set(order).size === expected.length
        && new Set(allowed).size === expected.length
        && expected.every((key) => order.includes(key) && allowed.includes(key));
    });
  }

  function validModulePlan(plan) {
    const modulePlan = plan && plan.screen_module_plan;
    if (!modulePlan || typeof modulePlan !== "object") return false;
    if (modulePlan.existing_targets_only !== true || modulePlan.user_reversible !== true || modulePlan.dom_reorder !== false) return false;
    if (!Array.isArray(modulePlan.rankings) || modulePlan.rankings.length !== Object.keys(FEATURE_TARGETS).length) return false;
    if (!modulePlan.targets || typeof modulePlan.targets !== "object") return false;
    const featureSet = new Set(modulePlan.rankings.map((row) => String(row && row.feature_key || "")));
    return Object.entries(FEATURE_TARGETS).every(([feature, target]) =>
      featureSet.has(feature) && String(modulePlan.targets[feature] || "") === target
    );
  }

  function restoreAdaptiveModules() {
    const seen = new Set();
    Object.values(FEATURE_TARGETS).forEach((targetId) => {
      if (seen.has(targetId)) return;
      seen.add(targetId);
      const target = document.getElementById(targetId);
      if (!target) return;
      delete target.dataset.aiModuleRank;
      delete target.dataset.aiModulePriority;
      delete target.dataset.aiModuleFeature;
    });
    return true;
  }

  function applyAdaptiveModules(plan) {
    if (!validModulePlan(plan) || !layoutEnabled()) return false;
    const seenTargets = new Set();
    for (const [index, row] of plan.screen_module_plan.rankings.entries()) {
      const feature = String(row && row.feature_key || "");
      const targetId = FEATURE_TARGETS[feature];
      if (!targetId || String(row && row.target_id || "") !== targetId) return false;
      const target = document.getElementById(targetId);
      if (!target) return false;
      if (seenTargets.has(targetId)) continue;
      seenTargets.add(targetId);
      target.dataset.aiModuleRank = String(index + 1);
      target.dataset.aiModulePriority = pct(row.priority);
      target.dataset.aiModuleFeature = feature;
    }
    return true;
  }

  function captureOriginalOrder() {
    if (originalOrder) return originalOrder;
    const keys = categoryNodes().map((item) => String(item.dataset.categoryKey || ""));
    originalOrder = CATEGORY_KEYS.every((key) => keys.includes(key))
      ? keys.filter((key) => CATEGORY_KEYS.includes(key))
      : [...CATEGORY_KEYS];
    return originalOrder;
  }

  function validLayout(plan) {
    if (!plan || typeof plan !== "object" || plan.apply_layout !== true) return false;
    if (!Array.isArray(plan.order) || !Array.isArray(plan.allowlisted_categories)) return false;
    const order = plan.order.map(String);
    const allowed = new Set(plan.allowlisted_categories.map(String));
    if (order.length !== CATEGORY_KEYS.length || new Set(order).size !== CATEGORY_KEYS.length) return false;
    return CATEGORY_KEYS.every((key) => allowed.has(key) && order.includes(key))
      && validFeaturePlan(plan)
      && validModulePlan(plan);
  }

  function clearRanks() {
    categoryNodes().forEach((item) => {
      delete item.dataset.aiRank;
      item.removeAttribute("aria-description");
    });
    featureNodes(categoryContainer()).forEach((item) => {
      delete item.dataset.aiFeatureRank;
      item.removeAttribute("aria-description");
    });
    restoreAdaptiveModules();
  }

  function restoreOriginalFeatures() {
    const originals = captureOriginalFeatureOrders();
    const byCategory = Object.fromEntries(categoryNodes().map((item) => [String(item.dataset.categoryKey || ""), item]));
    for (const [categoryKey, order] of Object.entries(originals)) {
      const category = byCategory[categoryKey];
      const grid = category && category.querySelector(".feature-shortcut-grid");
      if (!grid) continue;
      const byKey = Object.fromEntries(featureNodes(category).map((item) => [String(item.dataset.featureKey || ""), item]));
      order.forEach((key) => { if (byKey[key]) grid.append(byKey[key]); });
    }
    return true;
  }

  function restoreOriginalOrder() {
    const container = categoryContainer();
    if (!container) return false;
    const byKey = Object.fromEntries(categoryNodes().map((item) => [String(item.dataset.categoryKey || ""), item]));
    captureOriginalOrder().forEach((key) => { if (byKey[key]) container.append(byKey[key]); });
    restoreOriginalFeatures();
    clearRanks();
    return true;
  }

  function applyAdaptiveFeatures(plan) {
    if (!validFeaturePlan(plan)) return false;
    captureOriginalFeatureOrders();
    const byCategory = Object.fromEntries(categoryNodes().map((item) => [String(item.dataset.categoryKey || ""), item]));
    for (const categoryKey of CATEGORY_KEYS) {
      const category = byCategory[categoryKey];
      const grid = category && category.querySelector(".feature-shortcut-grid");
      if (!grid) return false;
      const nodes = featureNodes(category);
      const byKey = Object.fromEntries(nodes.map((item) => [String(item.dataset.featureKey || ""), item]));
      const order = plan.feature_orders[categoryKey].map(String);
      if (!FEATURE_KEYS[categoryKey].every((key) => Boolean(byKey[key]))) return false;
      order.forEach((key, index) => {
        const item = byKey[key];
        item.dataset.aiFeatureRank = String(index + 1);
        item.setAttribute("aria-description", "AI 기능 우선순위 " + (index + 1) + "위");
        grid.append(item);
      });
    }
    return true;
  }

  function applyAdaptiveOrder(plan) {
    if (!validLayout(plan) || !layoutEnabled()) return false;
    const container = categoryContainer();
    if (!container) return false;
    captureOriginalOrder();
    const byKey = Object.fromEntries(categoryNodes().map((item) => [String(item.dataset.categoryKey || ""), item]));
    if (!CATEGORY_KEYS.every((key) => Boolean(byKey[key]))) return false;
    plan.order.forEach((key, index) => {
      const item = byKey[key];
      item.dataset.aiRank = String(index + 1);
      item.setAttribute("aria-description", "AI 추천 우선순위 " + (index + 1) + "위");
      container.append(item);
    });
    if (!applyAdaptiveFeatures(plan) || !applyAdaptiveModules(plan)) {
      restoreOriginalOrder();
      return false;
    }
    return true;
  }


  function validExperiencePlan(plan) {
    const experience = plan && plan.video_experience_plan;
    if (!experience || typeof experience !== "object" || experience.apply_layout !== true) return false;
    const order = Array.isArray(experience.order) ? experience.order.map(String) : [];
    const allowlist = Array.isArray(experience.allowlist) ? experience.allowlist.map(String) : [];
    return order.length === EXPERIENCE_KEYS.length
      && allowlist.length === EXPERIENCE_KEYS.length
      && new Set(order).size === EXPERIENCE_KEYS.length
      && EXPERIENCE_KEYS.every((key) => order.includes(key) && allowlist.includes(key))
      && experience.verified_data_only === true
      && experience.user_reversible === true
      && experience.market_direction_inferred === false
      && experience.stock_fact_invented === false
      && experience.precise_location_persisted === false
      && experience.user_behavior_tracking === false;
  }

  function experienceCard(key, icon, title, description) {
    const card = node("article", "video-experience-card");
    card.dataset.experienceKey = key;
    const head = node("div", "video-experience-card-head");
    head.append(node("span", "video-experience-icon", icon), node("div", "", ""));
    const copy = head.lastChild;
    copy.append(node("h4", "", title), node("p", "", description));
    const body = node("div", "video-experience-body");
    card.append(head, body);
    return {card, body};
  }

  function actionLink(label, targetId) {
    const button = node("button", "video-experience-action", label);
    button.type = "button";
    button.addEventListener("click", () => {
      const target = document.getElementById(targetId);
      if (target) target.scrollIntoView({behavior:"smooth", block:"start"});
    });
    return button;
  }

  function mountPurchaseAreaTools() {
    const panel = document.getElementById("purchasePanel");
    if (!panel) return null;
    let tools = document.getElementById("purchaseVideoAreaTools");
    if (tools) return tools;
    tools = node("section", "purchase-video-area-tools");
    tools.id = "purchaseVideoAreaTools";
    tools.setAttribute("aria-label", "빠른 지역 선택");
    const title = node("div", "purchase-video-area-title");
    title.append(node("b", "", "🗺️ 빠른 지역 선택"), node("span", "", "시·도만 기기에 저장하며 현재 위치 좌표는 저장하지 않습니다."));
    const select = document.createElement("select");
    select.id = "purchaseVideoRegion";
    select.setAttribute("aria-label", "구매처 지역 빠른 선택");
    ["","서울","경기","인천","부산","대구","대전","광주","울산","강원","충북","충남","전북","전남","경북","경남","제주"].forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value || "시·도 선택";
      select.append(option);
    });
    const current = node("button", "video-experience-action", "📍 내 위치");
    current.type = "button";
    current.addEventListener("click", () => document.getElementById("purchaseUseLocation")?.click());
    const recent = node("button", "video-experience-action secondary", "🕘 최근 지역");
    recent.type = "button";
    recent.addEventListener("click", () => {
      let value = "";
      try { value = localStorage.getItem("tcgPurchaseRecentRegionV403") || ""; } catch (_) {}
      if (!value) return;
      select.value = value;
      select.dispatchEvent(new Event("change", {bubbles:true}));
    });
    select.addEventListener("change", () => {
      const value = String(select.value || "");
      const input = document.getElementById("purchaseAreaText");
      if (!value || !input) return;
      input.value = value;
      input.dispatchEvent(new Event("input", {bubbles:true}));
      input.dispatchEvent(new Event("change", {bubbles:true}));
      try { localStorage.setItem("tcgPurchaseRecentRegionV403", value); } catch (_) {}
      if (typeof window.renderPurchaseSources === "function") window.renderPurchaseSources();
    });
    const controls = node("div", "purchase-video-area-controls");
    controls.append(select, current, recent);
    tools.append(title, controls);
    const nearby = document.getElementById("purchaseNearby");
    if (nearby) panel.insertBefore(tools, nearby);
    else panel.append(tools);
    return tools;
  }

  function setPurchaseSplit(enabled) {
    const panel = document.getElementById("purchasePanel");
    if (!panel) return false;
    panel.classList.toggle("video-purchase-split", Boolean(enabled));
    if (enabled) mountPurchaseAreaTools();
    return true;
  }

  function captureOriginalExperienceOrder(grid) {
    if (originalExperienceOrder) return originalExperienceOrder;
    const current = [...grid.querySelectorAll("[data-experience-key]")].map((item) => String(item.dataset.experienceKey || ""));
    originalExperienceOrder = EXPERIENCE_KEYS.every((key) => current.includes(key)) ? current : [...EXPERIENCE_KEYS];
    return originalExperienceOrder;
  }

  function restoreExperienceOrder(ui) {
    if (!ui || !ui.experienceGrid) return false;
    const byKey = Object.fromEntries(
      [...ui.experienceGrid.querySelectorAll("[data-experience-key]")].map((item) => [String(item.dataset.experienceKey || ""), item])
    );
    captureOriginalExperienceOrder(ui.experienceGrid).forEach((key) => {
      if (byKey[key]) {
        delete byKey[key].dataset.aiExperienceRank;
        ui.experienceGrid.append(byKey[key]);
      }
    });
    setPurchaseSplit(false);
    return true;
  }

  function applyExperienceOrder(ui, plan) {
    if (!ui || !ui.experienceGrid || !experienceEnabled() || !validExperiencePlan(plan)) return false;
    const order = plan.video_experience_plan.order.map(String);
    const byKey = Object.fromEntries(
      [...ui.experienceGrid.querySelectorAll("[data-experience-key]")].map((item) => [String(item.dataset.experienceKey || ""), item])
    );
    if (!EXPERIENCE_KEYS.every((key) => Boolean(byKey[key]))) return false;
    order.forEach((key, index) => {
      byKey[key].dataset.aiExperienceRank = String(index + 1);
      ui.experienceGrid.append(byKey[key]);
    });
    setPurchaseSplit(true);
    return true;
  }

  function mountVideoExperience() {
    const categories = categoryContainer();
    if (!categories || document.getElementById("videoExperienceV403")) return null;
    const root = node("section", "video-experience-v403");
    root.id = "videoExperienceV403";
    root.setAttribute("aria-labelledby", "videoExperienceTitle");
    const head = node("div", "video-experience-head");
    const intro = node("div", "");
    const title = node("h3", "", "✨ 영상 참고 · AI 적응형 태블릿 홈");
    title.id = "videoExperienceTitle";
    intro.append(
      node("span", "video-experience-kicker", "VIDEO-REFERENCE UX · VERIFIED DATA ONLY"),
      title,
      node("p", "", "시장흐름·촬영품질·구매지역·HOT 카드/BOX·내 카드요약을 검증된 자료만으로 묶고 AI가 필요한 순서로 배치합니다.")
    );
    const toggle = node("button", "video-experience-toggle", "");
    toggle.type = "button";
    toggle.setAttribute("aria-pressed", experienceEnabled() ? "true" : "false");
    head.append(intro, toggle);

    const grid = node("div", "video-experience-grid");
    const pulse = experienceCard("home-market-pulse", "📈", "시장 흐름 홈", "방향 예측이 아니라 최신 검증자료의 활동량과 최신성을 요약합니다.");
    pulse.body.id = "videoMarketPulse";
    pulse.body.append(node("div", "video-experience-loading", "검증된 시장자료를 불러오는 중…"));
    pulse.body.append(actionLink("시세센터", "market12section"), actionLink("출시·행사", "releaseBoard"));

    const capture = experienceCard("capture-quality-gate", "📷", "그레이딩 촬영 품질", "노출·초점·흔들림·반사 확인 상태를 촬영 화면과 함께 보여줍니다.");
    capture.body.id = "videoCaptureQuality";
    const chips = node("div", "video-quality-chips");
    ["노출","초점","흔들림","반사"].forEach((label) => {
      const chip = node("span", "video-quality-chip", label + " · 대기");
      chip.dataset.quality = label;
      chips.append(chip);
    });
    capture.body.append(chips, actionLink("자동촬영 열기", "simpleGradeV32"), actionLink("1→4→8 정밀측정", "precisionHub"));

    const purchase = experienceCard("purchase-split-view", "🗺️", "구매처 지도·지역", "긴 지역 목록 대신 현재위치·최근지역·시도 선택과 매장 후보를 나눠 봅니다.");
    purchase.body.id = "videoPurchaseSummary";
    purchase.body.append(
      node("p", "video-experience-note", "실제 재고는 판매처에서 최종 확인합니다. 현재 위치 좌표는 저장하지 않습니다."),
      actionLink("구매처 찾기", "releaseBoard")
    );

    const hot = experienceCard("hot-card-box-ranking", "🔥", "HOT 카드·BOX", "최근 검증·거래중·정상 링크 신호를 기준으로 주목 항목을 정렬합니다.");
    hot.body.id = "videoHotRanking";
    hot.body.append(node("div", "video-experience-loading", "검증된 거래·BOX 자료를 확인하는 중…"));

    const portfolio = experienceCard("portfolio-summary", "💼", "내 카드 요약", "현재 분석등급·검증기록·RAW 시세를 한곳에서 확인합니다.");
    portfolio.body.id = "videoPortfolioSummary";
    portfolio.body.append(node("div", "video-experience-loading", "현재 카드 분석 결과를 기다리는 중…"));
    portfolio.body.append(actionLink("등급 예상가", "gradingEconomics"), actionLink("실제등급 검증", "v30validation"));

    grid.append(pulse.card, capture.card, purchase.card, hot.card, portfolio.card);
    root.append(head, grid);
    categories.parentNode.insertBefore(root, categories);
    captureOriginalExperienceOrder(grid);
    return {
      root, toggle, experienceGrid:grid,
      pulseBody:pulse.body, captureBody:capture.body,
      purchaseBody:purchase.body, hotBody:hot.body, portfolioBody:portfolio.body,
    };
  }

  function setQualityChip(ui, label, state, text) {
    const chip = ui && ui.captureBody && ui.captureBody.querySelector('[data-quality="' + label + '"]');
    if (!chip) return;
    chip.dataset.state = state;
    chip.textContent = label + " · " + text;
  }

  function syncCaptureQuality(ui) {
    if (!ui) return;
    const status = document.getElementById("cameraStatus");
    const glare = document.getElementById("glare");
    const text = String(status?.textContent || "");
    setQualityChip(ui, "노출", text.includes("노출 양호") ? "good" : text.includes("노출") ? "warn" : "idle", text.includes("노출 양호") ? "양호" : text.includes("노출") ? "조정" : "대기");
    setQualityChip(ui, "초점", text.includes("초점 양호") ? "good" : text.includes("초점") ? "warn" : "idle", text.includes("초점 양호") ? "양호" : text.includes("초점") ? "맞추는 중" : "대기");
    setQualityChip(ui, "흔들림", text.includes("흔들림 안정") ? "good" : text.includes("흔들림") ? "warn" : "idle", text.includes("흔들림 안정") ? "안정" : text.includes("흔들림") ? "고정 필요" : "대기");
    const glareValue = Number.parseFloat(String(glare?.textContent || ""));
    setQualityChip(
      ui, "반사",
      Number.isFinite(glareValue) ? (glareValue <= 35 ? "good" : "warn") : "idle",
      Number.isFinite(glareValue) ? (glareValue <= 35 ? "낮음" : "재촬영 권장") : "사선광 권장"
    );
  }

  function observeCaptureQuality(ui) {
    if (!ui || cameraQualityObserver) return;
    const targets = [document.getElementById("cameraStatus"), document.getElementById("glare")].filter(Boolean);
    if (!targets.length || typeof MutationObserver !== "function") return;
    cameraQualityObserver = new MutationObserver(() => syncCaptureQuality(ui));
    targets.forEach((target) => cameraQualityObserver.observe(target, {subtree:true, childList:true, characterData:true}));
    syncCaptureQuality(ui);
  }

  function safeStoredArray(key) {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) { return []; }
  }

  function renderPortfolioExperience(ui) {
    if (!ui || !ui.portfolioBody) return;
    const grades = window.tcgLastGrades && typeof window.tcgLastGrades === "object" ? window.tcgLastGrades : {};
    const finiteGrades = Object.entries(grades).filter(([,value]) => Number.isFinite(Number(value)));
    const summary = node("div", "video-portfolio-grid");
    const gradeBox = node("div", "video-portfolio-metric");
    gradeBox.append(node("span", "", "현재 AI 예상등급"), node("b", "", finiteGrades.length ? finiteGrades.map(([key,value]) => key + " " + Number(value).toFixed(1)).join(" · ") : "분석 전"));
    const historyBox = node("div", "video-portfolio-metric");
    historyBox.append(node("span", "", "검증 학습기록"), node("b", "", safeStoredArray("tcg_v99_validation").length + "건"));
    const priceBox = node("div", "video-portfolio-metric");
    priceBox.append(node("span", "", "현재 RAW 시세"), node("b", "", asText(document.getElementById("agmRawPrice")?.textContent, "카드 인식 후 조회")));
    summary.append(gradeBox, historyBox, priceBox);
    const actions = [...ui.portfolioBody.querySelectorAll(".video-experience-action")];
    ui.portfolioBody.replaceChildren(summary, ...actions);
  }

  function dateScore(value) {
    const stamp = Date.parse(String(value || ""));
    if (!Number.isFinite(stamp)) return 0;
    const ageDays = Math.max(0, (Date.now() - stamp) / 86400000);
    return Math.max(0, 1 - ageDays / 45);
  }

  async function loadJsonAsset(path) {
    try {
      const response = await fetch(path + "?t=" + Date.now(), {cache:"no-store", headers:{"Accept":"application/json"}});
      if (!response.ok) throw new Error("HTTP_" + response.status);
      const data = await response.json();
      return data && typeof data === "object" ? data : null;
    } catch (_) { return null; }
  }

  async function marketExperienceData(force = false) {
    if (!force && marketExperienceCache && Date.now() - marketExperienceLoadedAt < 60000) return marketExperienceCache;
    const [watch, prices, releases, promos] = await Promise.all([
      loadJsonAsset("./market_watch.json"),
      loadJsonAsset("./market_prices.json"),
      loadJsonAsset("./releases.json"),
      loadJsonAsset("./promo_events.json"),
    ]);
    const watchItems = Array.isArray(watch?.items) ? watch.items.filter((row) => row && typeof row === "object") : [];
    const priceEntries = prices?.entries && typeof prices.entries === "object" && !Array.isArray(prices.entries)
      ? Object.entries(prices.entries) : [];
    const releaseItems = Array.isArray(releases?.items) ? releases.items.filter((row) => row && typeof row === "object") : [];
    const promoItems = Array.isArray(promos?.items) ? promos.items.filter((row) => row && typeof row === "object") : [];
    const rankedWatch = watchItems.map((row) => ({
      name:asText(row.name || row.native, "이름 미확인"),
      meta:[row.region,row.game,row.asset,row.sale_status].filter(Boolean).join(" · "),
      score:(String(row.link_status || "").includes("정상") ? 0.45 : 0.10)
        + 0.35 * dateScore(row.link_checked_at)
        + 0.20 * dateScore(row.release_date),
    })).sort((a,b) => b.score - a.score).slice(0,5);
    const rankedPrices = priceEntries.map(([key,row]) => ({
      name:key,
      meta:[row?.display,row?.kind,row?.market].filter(Boolean).join(" · "),
      score:(String(row?.link_status || "").includes("정상") ? 0.45 : 0.10)
        + 0.40 * dateScore(row?.source_date)
        + 0.15 * dateScore(row?.link_checked_at),
    })).sort((a,b) => b.score - a.score).slice(0,5);
    marketExperienceCache = {
      watch:rankedWatch,
      prices:rankedPrices,
      releases:releaseItems.filter((row) => String(row.lifecycle || "").toLowerCase() === "current").length,
      promos:promoItems.filter((row) => String(row.lifecycle || "").toLowerCase() === "current").length,
      watchCount:watchItems.length,
      updated:[watch?.updated_at,prices?.updated_at,releases?.updated_at,promos?.updated_at].filter(Boolean).sort().pop() || "",
    };
    marketExperienceLoadedAt = Date.now();
    return marketExperienceCache;
  }

  function renderMarketExperience(ui, data, plan) {
    if (!ui || !data) return;
    const activity = plan && plan.market_activity && typeof plan.market_activity === "object" ? plan.market_activity : {};
    const pulse = node("div", "video-pulse-grid");
    [
      ["거래·판매 관찰", asText(activity.market_watch_count, data.watchCount) + "건"],
      ["최근 출시", asText(activity.recent_release_count, data.releases) + "건"],
      ["현재 행사", asText(activity.current_event_count, data.promos) + "건"],
      ["최종 자료시각", data.updated ? String(data.updated).slice(0,16).replace("T"," ") : "확인 대기"],
    ].forEach(([label,value]) => {
      const item = node("div", "video-pulse-metric");
      item.append(node("span", "", label), node("b", "", value));
      pulse.append(item);
    });
    const pulseActions = [...ui.pulseBody.querySelectorAll(".video-experience-action")];
    ui.pulseBody.replaceChildren(pulse, node("p", "video-experience-note", "시장 방향을 예측하지 않고 검증자료의 활동량·최신성만 표시합니다."), ...pulseActions);

    const rows = [...data.watch.slice(0,3), ...data.prices.slice(0,3)]
      .sort((a,b) => b.score - a.score).slice(0,5);
    const list = node("div", "video-hot-list");
    if (!rows.length) list.append(node("div", "video-experience-loading", "검증된 HOT 후보 자료가 없습니다."));
    rows.forEach((row,index) => {
      const item = node("div", "video-hot-item");
      item.append(node("b", "video-hot-rank", String(index + 1)), node("div", "", ""));
      const copy = item.lastChild;
      copy.append(node("strong", "", row.name), node("small", "", row.meta || "검증자료"));
      list.append(item);
    });
    ui.hotBody.replaceChildren(list, node("p", "video-experience-note", "순위는 최근 검증·링크 상태·거래/판매 관찰 신호만 사용하며 가격 상승/하락 예측이 아닙니다."));
  }

  function renderExperience(ui, plan) {
    if (!ui) return;
    const enabled = experienceEnabled();
    ui.experienceToggle.textContent = enabled ? "영상형 AI 홈 켜짐" : "기본 홈";
    ui.experienceToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    if (enabled && validExperiencePlan(plan)) applyExperienceOrder(ui, plan);
    else restoreExperienceOrder(ui);
    observeCaptureQuality(ui);
    syncCaptureQuality(ui);
    renderPortfolioExperience(ui);
    marketExperienceData().then((data) => renderMarketExperience(ui, data, plan)).catch(() => {});
  }

  function mount() {
    const manager = document.getElementById("tabletManagerHub");
    if (!manager || document.getElementById("tabletAutonomyV400")) return null;
    captureOriginalOrder();
    captureOriginalFeatureOrders();
    const experience = mountVideoExperience();

    const panel = node("section", "tablet-autonomy-v400");
    panel.id = "tabletAutonomyV400";
    panel.setAttribute("aria-labelledby", "tabletAutonomyV400Title");

    const head = node("div", "tablet-autonomy-head");
    const intro = node("div", "tablet-autonomy-intro");
    intro.append(
      node("span", "tablet-autonomy-kicker", "AI SELF-EVOLUTION · DEDICATED SCREEN NEURAL"),
      node("h4", "", "🧠 태블릿 AI 자율진화 · 화면전용 신경망"),
      node("p", "", "기존 검증성과 메타 신경망에 더해 17입력→12 hidden→18기능 화면전용 신경망을 사용해 시장활동·영역상태·검증성과로 다음 화면 구성을 판단합니다.")
    );
    intro.querySelector("h4").id = "tabletAutonomyV400Title";

    const refresh = node("button", "tablet-autonomy-refresh", "상태 새로고침");
    refresh.type = "button";
    refresh.setAttribute("aria-label", "태블릿 AI 상태 새로고침");
    head.append(intro, refresh);

    const status = node("div", "tablet-autonomy-status", "최신 자율진화 보고서를 확인하는 중…");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const flow = node("div", "tablet-autonomy-flow");
    ["영역 진단","증거 신뢰도","시장활동","신경망 판단","목표 선택","UI 재배치","성과/롤백"].forEach((name) => {
      flow.append(node("span", "tablet-autonomy-flow-step", name));
    });

    const grid = node("div", "tablet-autonomy-grid");
    const defs = {
      focus:"현재 최우선 영역", urgency:"보완 긴급도", layout:"AI 화면 정렬",
      top:"화면 1순위", canary:"V400 Canary", rollback:"Rollback",
      source:"보호 PR 후보", needed:"필요 기능 후보", neural:"메타 신경망", screenNeural:"화면전용 신경망", modelGate:"모델 승격/롤백", feedback:"성과 피드백", gate:"안전 게이트",
    };
    const values = {};
    Object.entries(defs).forEach(([key, label]) => {
      const item = metric(label);
      values[key] = item.value;
      grid.append(item.box);
    });

    const layoutBox = node("section", "tablet-autonomy-layout");
    const layoutHead = node("div", "tablet-autonomy-layout-head");
    const layoutText = node("div", "");
    layoutText.append(
      node("b", "", "📱 AI 화면 구성"),
      node("span", "", "시장활동·영역 부족도·검증성과 신경망·이전 적용 후 영역점수 변화를 함께 사용하되 학습 보정폭은 작게 제한합니다.")
    );
    const layoutToggle = node("button", "tablet-autonomy-layout-toggle", "");
    layoutToggle.type = "button";
    layoutToggle.setAttribute("aria-pressed", layoutEnabled() ? "true" : "false");
    layoutHead.append(layoutText, layoutToggle);
    const layoutRank = node("div", "tablet-autonomy-layout-rank");
    const moduleTitle = node("b", "tablet-autonomy-module-title", "현재 주목 기능");
    const moduleRank = node("div", "tablet-autonomy-module-rank");
    layoutBox.append(layoutHead, layoutRank, moduleTitle, moduleRank);

    const surfaces = node("div", "tablet-autonomy-surfaces");
    const surfaceNodes = {};
    Object.entries(labels).forEach(([key, label]) => {
      const card = node("article", "tablet-autonomy-surface");
      card.dataset.surface = key;
      const top = node("div", "tablet-autonomy-surface-head");
      top.append(node("h5", "", label));
      const badge = node("span", "tablet-autonomy-surface-badge", "대기");
      top.append(badge);
      const score = node("div", "tablet-autonomy-surface-score", "—");
      const meta = node("div", "tablet-autonomy-surface-meta", "검증 신호 대기");
      const bar = node("div", "tablet-autonomy-bar");
      const fill = node("i", "");
      fill.style.width = "0%";
      bar.append(fill);
      card.append(top, score, meta, bar);
      surfaces.append(card);
      surfaceNodes[key] = {card, badge, score, meta, fill};
    });

    const footer = node("div", "tablet-autonomy-footer");
    footer.append(
      node("span", "", "✓ 검증값 없는 영역은 재측정 우선"),
      node("span", "", "✓ 메뉴·기능·본문 화면 강조는 언제든 원래 상태로 복원"),
      node("span", "", "✓ 선언형 기능만 자동 적용 · 코드 자가수정 금지"),
      node("span", "", "✓ 메타+화면전용 신경망 모두 검증결과 기반·보조 판단만"),
      node("span", "", "✓ 화면전용 신경망 17→12→18 · 기능 영향 ±5% · 전체 ±8%"),
      node("span", "", "✓ Champion/Challenger 홀드아웃 검증 · 개선된 모델만 승격"),
      node("span", "", "✓ 입력 드리프트 감지 · 마지막 정상 Champion 백업 롤백"),
      node("span", "", "✓ 사용자 클릭·행동 추적 없이 영역 성능결과만 학습"),
      node("span", "", "✓ 가격·등급·재고·출시·행사 사실 발명 금지")
    );

    panel.append(head, status, flow, grid, layoutBox, surfaces, footer);
    const managerHead = manager.querySelector(".tablet-manager-head");
    if (managerHead && managerHead.nextSibling) manager.insertBefore(panel, managerHead.nextSibling);
    else manager.append(panel);

    return {
      panel, refresh, status, values, surfaceNodes, layoutToggle, layoutRank, moduleRank,
      experienceRoot:experience?.root || null,
      experienceToggle:experience?.toggle || null,
      experienceGrid:experience?.experienceGrid || null,
      pulseBody:experience?.pulseBody || null,
      captureBody:experience?.captureBody || null,
      purchaseBody:experience?.purchaseBody || null,
      hotBody:experience?.hotBody || null,
      portfolioBody:experience?.portfolioBody || null,
    };
  }

  function surfaceMeta(row) {
    const ev = row && row.evidence && typeof row.evidence === "object" ? row.evidence : {};
    if (row.surface === "ui") {
      return "구성 " + asText(ev.passed, "0") + "/" + asText(ev.total, "0") + " · critical " + asText(ev.critical_failed, "0");
    }
    if (row.surface === "card_measurement") {
      const age = ev.verification_age_days === null || ev.verification_age_days === undefined ? "미확인" : Math.round(Number(ev.verification_age_days)) + "일";
      return "측정자산 " + asText(ev.present_assets, "0") + "/" + asText(ev.required_assets, "0") + " · 검증 " + age;
    }
    if (row.surface === "card_market") {
      return "시세 " + asText(ev.entry_count, "0") + "건 · " + (Array.isArray(ev.regions) ? ev.regions.join("/") : "지역 미확인") + " · 최신성 " + pct(ev.freshness);
    }
    if (row.surface === "card_release") {
      return "출시 " + asText(ev.item_count, "0") + "건 · " + (Array.isArray(ev.regions) ? ev.regions.join("/") : "지역 미확인") + " · 최근검증 " + pct(ev.verified_within_30d_ratio);
    }
    if (row.surface === "collab_event") {
      return "행사 " + asText(ev.item_count, "0") + "건 · 콜라보 " + asText(ev.collaboration_count, "0") + "건 · 감시 " + pct(ev.watched_game_region_ratio);
    }
    if (row.surface === "purchase_availability") {
      return "구매처 " + asText(ev.source_count, "0") + "개 · 신호 " + asText(ev.signal_count, "0") + "건 · 링크 " + pct(ev.healthy_link_ratio);
    }
    if (row.surface === "tablet_ops") {
      return "런타임 " + asText(ev.present_runtime_assets, "0") + "/" + asText(ev.required_runtime_assets, "0") + " · 검증 " + pct(ev.verification_freshness);
    }
    return "검증 신호 확인 중";
  }

  function renderLayout(ui, plan) {
    lastLayout = plan && typeof plan === "object" ? plan : null;
    const enabled = layoutEnabled();
    ui.layoutToggle.textContent = enabled ? "AI 정렬 켜짐" : "원래 순서";
    ui.layoutToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    ui.layoutToggle.dataset.enabled = enabled ? "true" : "false";
    ui.layoutRank.replaceChildren();

    const order = validLayout(lastLayout) ? lastLayout.order : CATEGORY_KEYS;
    order.forEach((key, index) => {
      const chip = node("span", "tablet-autonomy-layout-chip");
      chip.append(node("b", "", String(index + 1)), node("em", "", categoryLabels[key] || key));
      ui.layoutRank.append(chip);
    });
    ui.moduleRank.replaceChildren();
    const topFeatures = validLayout(lastLayout) && Array.isArray(lastLayout.screen_module_plan.top_features)
      ? lastLayout.screen_module_plan.top_features.slice(0, 5) : [];
    topFeatures.forEach((key, index) => {
      if (!FEATURE_TARGETS[key]) return;
      const chip = node("span", "tablet-autonomy-module-chip");
      chip.append(node("b", "", String(index + 1)), node("em", "", FEATURE_LABELS[key] || key));
      ui.moduleRank.append(chip);
    });

    if (enabled && validLayout(lastLayout)) applyAdaptiveOrder(lastLayout);
    else restoreOriginalOrder();
  }

  function render(ui, report) {
    const data = report && report.v400_ui && typeof report.v400_ui === "object" ? report.v400_ui : {};
    const plan = report && report.v400_adaptive_layout && typeof report.v400_adaptive_layout === "object"
      ? report.v400_adaptive_layout : data.adaptive_layout;
    const rows = Array.isArray(data.surfaces) ? data.surfaces : [];
    const bySurface = Object.fromEntries(rows.filter(Boolean).map((row) => [row.surface, row]));

    ui.values.focus.textContent = labels[data.selected_surface] || asText(data.selected_surface, "대기");
    ui.values.urgency.textContent = pct(data.selected_urgency);
    ui.values.layout.textContent = validLayout(plan) && layoutEnabled() ? "자동 적용" : layoutEnabled() ? "검증 대기" : "사용자 해제";
    ui.values.top.textContent = validLayout(plan) ? (categoryLabels[plan.order[0]] || plan.order[0]) : "기본 순서";
    ui.values.canary.textContent = asText(data.active_evaluation, "관찰 없음");
    ui.values.rollback.textContent = data.rollback_required ? "필요" : "불필요";
    ui.values.source.textContent = asText(data.protected_pr_candidates, "0") + "개";
    ui.values.needed.textContent = asText(data.protected_needed_feature_candidates, "0") + "개";
    const learning = plan && plan.policy_learning && typeof plan.policy_learning === "object" ? plan.policy_learning : {};
    const neural = learning.meta_neural && typeof learning.meta_neural === "object" ? learning.meta_neural : {};
    const screenNeural = learning.screen_neural && typeof learning.screen_neural === "object" ? learning.screen_neural : {};
    const outcome = learning.verified_outcome_feedback && typeof learning.verified_outcome_feedback === "object"
      ? learning.verified_outcome_feedback : {};
    const samples = Number(neural.sample_count);
    ui.values.neural.textContent = neural.active === true
      ? (Number.isFinite(samples) ? Math.max(0, Math.round(samples)) + "건 활성" : "활성")
      : (Number.isFinite(samples) ? Math.max(0, Math.round(samples)) + "건 · 대기" : "검증 대기");
    const screenSamples = Number(screenNeural.sample_count);
    const screenTraining = screenNeural.training && typeof screenNeural.training === "object"
      ? asText(screenNeural.training.status, "") : "";
    const modelState = report && report.v400_screen_neural && typeof report.v400_screen_neural === "object"
      ? report.v400_screen_neural : {};
    const modelEvaluation = modelState.evaluation && typeof modelState.evaluation === "object"
      ? modelState.evaluation : {};
    const modelRecovery = modelState.recovery && typeof modelState.recovery === "object"
      ? modelState.recovery : {};
    const evaluationStatus = asText(modelEvaluation.status, "");
    const recoveryStatus = asText(modelRecovery.status, "");
    ui.values.screenNeural.textContent = screenNeural.active === true
      ? (Number.isFinite(screenSamples) ? Math.max(0, Math.round(screenSamples)) + "행 활성" : "활성")
      : screenTraining.includes("CORRUPTION")
        ? "모델 격리"
        : (Number.isFinite(screenSamples) ? Math.max(0, Math.round(screenSamples)) + "행 · 대기" : "검증 대기");
    ui.values.modelGate.textContent = recoveryStatus.includes("ROLLBACK_RESTORED")
      ? "백업 롤백"
      : evaluationStatus.includes("PROMOTE")
        ? "Challenger 승격"
        : evaluationStatus.includes("DRIFT_HOLD")
          ? "드리프트 보류"
          : evaluationStatus.includes("REJECT")
            ? "Champion 유지"
            : "검증 대기";
    const transitions = Number(outcome.transitions_used);
    const bias = Number(learning.max_combined_bias);
    ui.values.feedback.textContent = (Number.isFinite(transitions) ? Math.max(0, Math.round(transitions)) : 0)
      + "회 · 최대 " + (Number.isFinite(bias) ? Math.round(Math.abs(bias) * 100) + "%" : "0%");
    ui.values.gate.textContent = asText(data.upstream_gate_status);

    Object.entries(ui.surfaceNodes).forEach(([surface, target]) => {
      const row = bySurface[surface] || {};
      target.card.dataset.status = asText(row.status, "observe");
      target.badge.textContent = asText(row.status, "대기");
      target.score.textContent = pct(row.score);
      target.meta.textContent = "신뢰 " + pct(row.confidence) + " · " + surfaceMeta(row);
      const score = Number(row.score);
      target.fill.style.width = Number.isFinite(score) ? Math.round(Math.max(0, Math.min(1, score)) * 100) + "%" : "0%";
    });

    renderLayout(ui, plan);
    renderExperience(ui, plan);

    const hold = asText(data.upstream_gate_status, "").includes("HOLD");
    const attention = rows.some((row) => row && row.status === "attention");
    ui.status.dataset.state = hold ? "hold" : "ok";
    ui.status.textContent = hold
      ? "상위 안전 게이트가 변경 실행을 보류했습니다. 화면은 검증된 기존 순서를 유지합니다."
      : attention
        ? "검증 신호가 약한 영역을 AI가 우선 보완 대상으로 선택하고, 허용된 메뉴·기능·본문 화면만 조정합니다."
        : "연결됨 · 분석/시세/발급/행사/구매/태블릿 운영을 함께 비교해 18개 기능과 본문 화면 우선순위를 조정합니다.";
    if (recoveryStatus.includes("ROLLBACK_RESTORED")) {
      ui.status.textContent += " · 화면 신경망 이상을 감지해 마지막 정상 Champion으로 자동 롤백했습니다.";
    }
    if (evaluationStatus.includes("PROMOTE")) {
      ui.status.textContent += " · Challenger가 홀드아웃 검증에서 기존 Champion보다 좋아 새 Champion으로 승격됐습니다.";
    } else if (evaluationStatus.includes("DRIFT_HOLD")) {
      ui.status.textContent += " · 입력 분포 변화가 커서 새 모델 승격을 보류하고 기존 Champion을 유지합니다.";
    } else if (evaluationStatus.includes("REJECT")) {
      ui.status.textContent += " · 새 Challenger가 기존 Champion을 이기지 못해 기존 모델을 유지합니다.";
    }
    if (screenNeural.active === true) {
      ui.status.textContent += " · 화면전용 17→12→18 신경망이 검증행 " + asText(screenNeural.sample_count, "0") + "개로 18개 기능을 직접 보조판단합니다.";
    } else if (screenTraining.includes("CORRUPTION")) {
      ui.status.textContent += " · 화면전용 신경망 모델 이상을 감지해 해당 어댑터만 격리하고 기존 안전 정책으로 동작합니다.";
    } else if (neural.active === true) {
      ui.status.textContent += " · 화면전용 신경망은 표본 대기 중이며 기존 검증성과 메타 신경망을 제한된 보조 신호로 사용합니다.";
    } else {
      ui.status.textContent += " · 신경망 검증표본이 부족할 때는 기존 증거기반 정책만 사용합니다.";
    }
    if (data.physical_tablet_runtime_verified !== true) {
      ui.status.textContent += " · 실제 태블릿 실행 결과는 기기 재검증 전까지 미확인입니다.";
    }
  }

  async function load(ui) {
    if (!ui) return;
    ui.refresh.disabled = true;
    ui.status.dataset.state = "loading";
    ui.status.textContent = "최신 자율진화 결과를 불러오는 중…";
    try {
      const response = await fetch(REPORT_URL + "?t=" + Date.now(), {
        cache:"no-store", headers: {"Accept": "application/json"},
      });
      if (!response.ok) throw new Error("HTTP_" + response.status);
      render(ui, await response.json());
    } catch (_error) {
      restoreOriginalOrder();
      restoreExperienceOrder(ui);
      ui.status.dataset.state = "idle";
      ui.status.textContent = "아직 실행 보고서가 없습니다. 태블릿에서 bash main evolve 실행 후 표시됩니다.";
    } finally {
      ui.refresh.disabled = false;
    }
  }

  function schedule(ui) {
    if (timer !== null) window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      if (document.visibilityState === "visible") await load(ui);
      schedule(ui);
    }, refreshMs);
  }

  function start() {
    const ui = mount();
    if (!ui) return;
    ui.refresh.addEventListener("click", () => load(ui));
    ui.layoutToggle.addEventListener("click", () => {
      const enabled = !layoutEnabled();
      saveLayoutPreference(enabled);
      if (enabled && validLayout(lastLayout)) applyAdaptiveOrder(lastLayout);
      else restoreOriginalOrder();
      renderLayout(ui, lastLayout);
    });
    ui.experienceToggle?.addEventListener("click", () => {
      const enabled = !experienceEnabled();
      saveExperiencePreference(enabled);
      renderExperience(ui, lastLayout);
    });
    document.addEventListener("tcg-grade-updated", () => renderPortfolioExperience(ui));
    window.setInterval(() => {
      if (document.visibilityState === "visible") {
        syncCaptureQuality(ui);
        renderPortfolioExperience(ui);
      }
    }, 5000);
    load(ui).finally(() => schedule(ui));
    window.TCGTabletAutonomyV400 = Object.freeze({
      version:VERSION,
      reportUrl:REPORT_URL,
      refresh:() => load(ui),
      adaptiveLayoutEnabled:layoutEnabled,
      restoreOriginalOrder,
      restoreOriginalFeatures,
      restoreAdaptiveModules,
      videoExperienceEnabled:experienceEnabled,
      restoreVideoExperience:() => restoreExperienceOrder(ui),
      refreshVideoExperience:() => renderExperience(ui, lastLayout),
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();