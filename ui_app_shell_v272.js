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
    subtitle.textContent = "카드정보 · 세대/세트 · 예상등급 · PSA 확률 · RAW 시세를 한 화면에 모읍니다.";
    titleWrap.append(title, subtitle);
    const badge = document.createElement("span");
    badge.className = "grade-cockpit-ai-badge";
    badge.textContent = "AI 추정 · 공식등급 아님";
    head.append(titleWrap, badge);

    const grid = document.createElement("div");
    grid.className = "grade-cockpit-grid";
    addCockpitCell(grid, "카드", "gradeCockpitCard", true);
    addCockpitCell(grid, "판본", "gradeCockpitEdition");
    addCockpitCell(grid, "세대 / 세트", "gradeCockpitGeneration");
    addCockpitCell(grid, "종합 예상등급", "gradeCockpitOverall");
    addCockpitCell(grid, "분석 신뢰도", "gradeCockpitConfidence");
    addCockpitCell(grid, "RAW 현재 시세", "gradeCockpitRaw");

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

    const source = document.createElement("p");
    source.id = "gradeCockpitEvidence";
    source.className = "grade-cockpit-evidence";
    source.textContent = "시세는 체결·낙찰 / 시장가이드 / 판매중 호가를 구분해 확인하세요.";

    const note = document.createElement("p");
    note.className = "grade-cockpit-note";
    note.textContent = "포켓몬은 세대 정보를 표시하고, 원피스·나루토는 세대 대신 탄/세트·판본 기준으로 확인합니다.";

    panel.append(head, grid, probabilityBlock, companyBlock, source, note);
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

  function generationText() {
    const generation = byId("simplePokemonGeneration");
    if (generation && !generation.hidden) {
      const badge = nodeText("pokemonGenerationBadge");
      const title = nodeText("pokemonGenerationTitle");
      return [badge, title].filter(Boolean).join(" · ") || "판별 중";
    }
    const activeGame = document.querySelector("[data-simple-game].active")?.dataset?.simpleGame || "";
    if (activeGame === "onepiece" || activeGame === "naruto") return "탄/세트 기준";
    return activeGame === "pokemon" ? "세대 판별 대기" : "게임 선택 후 판별";
  }

  function formatCompanyGrade(company, grades) {
    const raw = boundedNumber(grades?.[company], 1, 10);
    if (raw === null) return "대기";
    return `${raw.toFixed(raw % 1 ? 1 : 0)} 예상`;
  }

  function syncGradeCockpit() {
    if (!ensureGradeCockpit()) return false;
    const grades = window.tcgLastGrades || {};
    const name = nodeValue("identityCardName") || nodeText("agmName") || "인식 대기";
    const number = nodeValue("identityCardNumber") || nodeText("agmNumber") || "";
    const edition = nodeValue("identityRegion") || nodeText("agmRegion") || "판본 미확인";
    const generation = generationText();
    const overall = nodeText("simpleGradeLabel") || "분석 전";
    const confidence = nodeText("simpleGradeConfidence") || "-";
    const rawPrice = nodeText("agmRawPrice") || "카드 인식 후 조회";
    const rawSource = nodeText("agmRawSource") || "확인된 거래자료만 표시";
    const p8 = probabilityText(8);
    const p9 = probabilityText(9);
    const p10 = probabilityText(10);
    const companyValues = RESULT_COMPANIES.map((company) => formatCompanyGrade(company, grades));
    const signature = [name, number, edition, generation, overall, confidence, rawPrice, rawSource, p8, p9, p10, ...companyValues].join("|");
    if (signature === gradeCockpitState.signature) return true;
    gradeCockpitState.signature = signature;

    byId("gradeCockpitCard").textContent = [name, number].filter(Boolean).join(" · ") || "인식 대기";
    byId("gradeCockpitEdition").textContent = edition || "판본 미확인";
    byId("gradeCockpitGeneration").textContent = generation;
    byId("gradeCockpitOverall").textContent = overall;
    byId("gradeCockpitConfidence").textContent = confidence;
    byId("gradeCockpitRaw").textContent = rawPrice;
    byId("gradeCockpitPsa8").textContent = p8;
    byId("gradeCockpitPsa9").textContent = p9;
    byId("gradeCockpitPsa10").textContent = p10;
    RESULT_COMPANIES.forEach((company, index) => {
      byId(`gradeCockpit${company}`).textContent = companyValues[index];
    });
    byId("gradeCockpitEvidence").textContent = `시세 근거: ${rawSource}`;

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
