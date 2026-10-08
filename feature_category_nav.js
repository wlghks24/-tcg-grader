"use strict";
(() => {
  const VALID_TOP_PANELS = new Set(["releasePanel", "promoPanel", "purchasePanel"]);
  const VALID_TABLET_TARGETS = new Set(["v23dual", "v16update", "v20live", "tabletServerGuide"]);
  const VALID_TABLET_CLICKS = new Set(["v23check", "v20issues"]);
  // V407 video-informed persistent dock.
  // The screen neural may choose only these predeclared navigation capabilities;
  // it cannot invent DOM targets, commands, URLs or new executable features.
  const FIXED_DOCK_MENU = Object.freeze({ key: "menu", icon: "⌂", label: "홈", target: "featureCategories" });
  const FIXED_DOCK_PRIMARY = Object.freeze({ key: "scan", icon: "＋", label: "촬영", target: "simpleGradeV32", primary: true });
  const DEFAULT_DOCK_FEATURES = Object.freeze(["market-search", "purchase-finder", "tablet-manager"]);
  const DOCK_CATEGORY_BY_KEY = Object.freeze({
    "scan":"grading",
    "auto-grade":"grading",
    "manual-photo":"grading",
    "precision-grade":"grading",
    "market-search":"market",
    "grading-economics":"market",
    "trading-catalog":"market",
    "box-knowledge":"box",
    "box-hit-analysis":"box",
    "release-info":"news",
    "promo-event-info":"news",
    "purchase-finder":"purchase",
    "purchase-distance":"purchase",
    "card-ocr":"learning",
    "verified-grade":"learning",
    "learning-status":"learning",
    "tablet-manager":"tablet",
    "code-audit":"code",
    "code-validation":"code",
  });
  const ADAPTIVE_DOCK_FEATURES = Object.freeze({
    "auto-grade":Object.freeze({key:"auto-grade",icon:"🎴",label:"등급",target:"simpleGradeV32"}),
    "manual-photo":Object.freeze({key:"manual-photo",icon:"📷",label:"사진등록",target:"gradeStart"}),
    "precision-grade":Object.freeze({key:"precision-grade",icon:"🔬",label:"정밀측정",target:"precisionHub"}),
    "market-search":Object.freeze({key:"market-search",icon:"💰",label:"시세",target:"market12section"}),
    "grading-economics":Object.freeze({key:"grading-economics",icon:"🧮",label:"손익",target:"gradingEconomics"}),
    "trading-catalog":Object.freeze({key:"trading-catalog",icon:"📈",label:"거래",target:"tradingCatalogSection"}),
    "box-knowledge":Object.freeze({key:"box-knowledge",icon:"📦",label:"BOX",target:"box12section"}),
    "box-hit-analysis":Object.freeze({key:"box-hit-analysis",icon:"⭐",label:"HIT",target:"v14section"}),
    "release-info":Object.freeze({key:"release-info",icon:"📅",label:"출시",target:"releaseBoard",panel:"releasePanel"}),
    "promo-event-info":Object.freeze({key:"promo-event-info",icon:"🎁",label:"행사",target:"releaseBoard",panel:"promoPanel"}),
    "purchase-finder":Object.freeze({key:"purchase-finder",icon:"🛒",label:"구매처",target:"releaseBoard",panel:"purchasePanel"}),
    "purchase-distance":Object.freeze({key:"purchase-distance",icon:"📍",label:"거리",target:"releaseBoard",panel:"purchasePanel"}),
    "card-ocr":Object.freeze({key:"card-ocr",icon:"🔎",label:"OCR",target:"simpleGradeV32"}),
    "verified-grade":Object.freeze({key:"verified-grade",icon:"✅",label:"실등급",target:"v30validation"}),
    "learning-status":Object.freeze({key:"learning-status",icon:"🧠",label:"학습",target:"v31testdashboard"}),
    "tablet-manager":Object.freeze({key:"tablet-manager",icon:"📱",label:"태블릿",target:"tabletManagerHub"}),
    "code-audit":Object.freeze({key:"code-audit",icon:"🧪",label:"검사",target:"audit15"}),
    "code-validation":Object.freeze({key:"code-validation",icon:"🛡️",label:"검증",target:"v31testdashboard"}),
  });
  const categories = [...document.querySelectorAll(".feature-category")];
  const selectedStatus = document.getElementById("featureCategorySelected");
  const nav = document.getElementById("featureCategories");
  const fab = document.getElementById("featureCategoryFab");
  let syncing = false;
  // V430 recording-derived category focus mode: detailed feature surfaces stay
  // hidden until their category is selected. Targets are discovered only from
  // existing allowlisted shortcut hrefs; no arbitrary selector or code execution.
  const categoryTargets = new Map();
  const managedTargets = new Set();
  const managedSurfaces = new Set();
  const targetSurfaces = new Map();
  const targetCategories = new Map();
  const targetLabels = new Map();
  const advancedTargets = new Map();
  let activeCategory = null;

  const LEGACY_ADVANCED_RULES = Object.freeze([
    Object.freeze({category:"grading", match:"🧪 v10 검증·오류보정", label:"🧪 등급 기준·오류보정"}),
    Object.freeze({category:"grading", match:"📸 검증 사진 참고", label:"📸 검증 사진 참고"}),
    Object.freeze({category:"grading", id:"v30mode", label:"🧭 분석 유형·사진 점검"}),
    Object.freeze({category:"market", match:"📈 실시간 데이터 업데이트 원칙", label:"📈 데이터 업데이트 원칙"}),
    Object.freeze({category:"market", match:"💰 카드·BOX 가격 검색", label:"💰 구형 가격 검색"}),
    Object.freeze({category:"learning", match:"🧠 누적 오류 보정", label:"🧠 누적 오류 보정"}),
    Object.freeze({category:"learning", id:"v26graded", label:"🧾 확정등급 교차검증"}),
    Object.freeze({category:"code", match:"🌐 실시간 반영이 안 되는 기능", label:"🌐 실시간 반영 제한 안내"}),
    Object.freeze({category:"box", match:"💴 한국/해당국 출시원가", label:"💴 출시원가 세부정보"}),
  ]);

  function surfaceForTarget(target) {
    if (!target) return null;
    if (target.matches?.("section")) return target;
    return target.closest?.("section.card, section.release-board, section.simple-grade-card, section") || target;
  }

  function categoryByKey(key) {
    const value = String(key || "");
    return categories.find((item) => String(item.dataset.categoryKey || "") === value) || null;
  }

  function registerManagedTarget(category, target, label = "") {
    if (!category || !target) return false;
    const surface = surfaceForTarget(target);
    if (!surface) return false;
    managedTargets.add(target);
    managedSurfaces.add(surface);
    targetSurfaces.set(target, surface);
    if (!targetCategories.has(target)) targetCategories.set(target, category);
    if (label && !targetLabels.has(target)) targetLabels.set(target, label);
    return true;
  }

  categories.forEach((category) => {
    const targets = new Set();
    category.querySelectorAll(".feature-shortcut[href^='#']").forEach((link) => {
      const id = String(link.getAttribute("href") || "").slice(1);
      if (!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id)) return;
      const target = document.getElementById(id);
      if (!target) return;
      const label = String(link.childNodes?.[0]?.textContent || link.textContent || "").replace(/\s+/g, " ").trim();
      targets.add(target);
      registerManagedTarget(category, target, label);
    });
    categoryTargets.set(category, targets);
  });

  function registerLegacyAdvancedTargets() {
    const seen = new Set();
    for (const rule of LEGACY_ADVANCED_RULES) {
      const category = categoryByKey(rule.category);
      if (!category) continue;
      let target = rule.id ? document.getElementById(rule.id) : null;
      if (!target && rule.match) {
        target = [...document.querySelectorAll("section.card")].find((section) => {
          const heading = section.querySelector("h2,h3,h4");
          return heading && String(heading.textContent || "").includes(rule.match);
        }) || null;
      }
      if (!target) continue;
      const surface = surfaceForTarget(target);
      if (!surface || seen.has(surface)) continue;
      if (!surface.id) surface.id = "appAdvanced" + rule.category[0].toUpperCase() + rule.category.slice(1) + String(seen.size + 1);
      seen.add(surface);
      registerManagedTarget(category, surface, rule.label);
      const rows = advancedTargets.get(category) || [];
      rows.push(Object.freeze({target:surface, label:rule.label}));
      advancedTargets.set(category, rows);
    }
  }

  function ensureAdvancedMenus() {
    categories.forEach((category) => {
      const rows = advancedTargets.get(category) || [];
      if (!rows.length || category.querySelector(".feature-category-advanced")) return;
      const details = document.createElement("details");
      details.className = "feature-category-advanced";
      const summary = document.createElement("summary");
      summary.textContent = "고급 · 세부 기능 " + rows.length + "개";
      const grid = document.createElement("div");
      grid.className = "feature-advanced-grid";
      rows.forEach((row) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "feature-advanced-shortcut";
        button.textContent = row.label;
        button.addEventListener("click", () => {
          activeCategory = category;
          targetLabels.set(row.target, row.label);
          showManagedTarget(row.target);
          updateCategoryStatus(category, row.label);
          scrollTarget(targetSurfaces.get(row.target) || row.target, 0);
        });
        grid.append(button);
      });
      details.append(summary, grid);
      const shortcutGrid = category.querySelector(".feature-shortcut-grid");
      if (shortcutGrid) shortcutGrid.insertAdjacentElement("afterend", details);
      else category.append(details);
    });
  }

  function hideManagedSurfaces() {
    managedSurfaces.forEach((surface) => { surface.hidden = true; });
    document.body.removeAttribute("data-feature-view-active");
    nav?.removeAttribute("data-active-feature");
  }

  function setCategoryContent(category) {
    hideManagedSurfaces();
    if (!category || !categories.includes(category)) {
      activeCategory = null;
      document.body.removeAttribute("data-feature-category-active");
      nav?.removeAttribute("data-active-category");
      return true;
    }
    activeCategory = category;
    const key = String(category.dataset.categoryKey || "");
    document.body.setAttribute("data-feature-category-active", key || "selected");
    nav?.setAttribute("data-active-category", key || "selected");
    return true;
  }

  function returnToCategory(category) {
    const chosen = category && categories.includes(category) ? category : activeCategory;
    hideManagedSurfaces();
    if (chosen) {
      selectCategory(chosen);
      updateCategoryStatus(chosen);
    } else {
      updateCategoryStatus(null);
      setCategoryContent(null);
    }
    scrollTarget(nav);
    return true;
  }

  function closeFeatureView() {
    hideManagedSurfaces();
    categories.forEach((category) => { category.open = false; });
    updateCategoryStatus(null);
    setCategoryContent(null);
    scrollTarget(nav);
    return true;
  }

  function ensureFeatureToolbar(target, surface) {
    if (!target || !surface) return null;
    let toolbar = surface.querySelector(".app-feature-viewbar");
    if (!toolbar) {
      toolbar = document.createElement("div");
      toolbar.className = "app-feature-viewbar";
      const back = document.createElement("button");
      back.type = "button";
      back.className = "app-feature-back";
      back.textContent = "← 기능목록";
      back.addEventListener("click", () => returnToCategory(activeCategory || targetCategories.get(target)));
      const title = document.createElement("strong");
      title.className = "app-feature-current";
      const collapse = document.createElement("button");
      collapse.type = "button";
      collapse.className = "app-feature-collapse";
      collapse.textContent = "접기 ⌃";
      collapse.addEventListener("click", closeFeatureView);
      toolbar.append(back, title, collapse);
      surface.insertBefore(toolbar, surface.firstChild);
    }
    const title = toolbar.querySelector(".app-feature-current");
    if (title) title.textContent = targetLabels.get(target) || "선택한 기능";
    return toolbar;
  }

  function showManagedTarget(target) {
    if (!target || !managedTargets.has(target)) return false;
    const category = activeCategory || targetCategories.get(target) || null;
    if (category && !category.open) selectCategory(category);
    hideManagedSurfaces();
    const surface = targetSurfaces.get(target) || surfaceForTarget(target);
    if (!surface) return false;
    surface.hidden = false;
    target.hidden = false;
    ensureFeatureToolbar(target, surface);
    const id = String(target.id || surface.id || "selected");
    document.body.setAttribute("data-feature-view-active", id);
    nav?.setAttribute("data-active-feature", id);
    return true;
  }

  registerLegacyAdvancedTargets();
  ensureAdvancedMenus();

  function safeTarget(id) {
    const value = String(id || "");
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(value)) return null;
    return document.getElementById(value);
  }

  function reducedMotionPreferred() {
    try {
      return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
    } catch (_) {
      return false;
    }
  }

  function scrollTarget(target, delay = 0) {
    if (!target) return false;
    const run = () => {
      try {
        target.scrollIntoView({ behavior: reducedMotionPreferred() ? "auto" : "smooth", block: "start" });
      } catch (_) {
        target.scrollIntoView?.();
      }
    };
    if (delay > 0) setTimeout(run, delay);
    else run();
    return true;
  }

  function categoryLabel(category) {
    return String(category?.dataset?.categoryLabel || "").trim() || "선택한 카테고리";
  }

  function updateCategoryStatus(category, featureLabel = "") {
    if (!selectedStatus) return;
    if (!category) {
      selectedStatus.classList?.remove?.("active");
      selectedStatus.textContent = "카테고리를 선택하면 기능 목록만 펼쳐집니다.";
      return;
    }
    selectedStatus.classList?.add?.("active");
    selectedStatus.textContent = featureLabel
      ? `✅ ${categoryLabel(category)} · ${featureLabel}만 열었습니다.`
      : `✅ ${categoryLabel(category)} · 아래에서 기능 하나를 선택하세요. 상세화면은 한 번에 하나만 표시됩니다.`;
  }

  function selectCategory(category) {
    if (!category || !categories.includes(category)) return false;
    syncing = true;
    categories.forEach((item) => {
      item.open = item === category;
    });
    syncing = false;
    updateCategoryStatus(category);
    setCategoryContent(category);
    return true;
  }

  categories.forEach((category) => {
    category.open = false;
    category.addEventListener("toggle", () => {
      if (syncing) return;
      if (category.open) {
        selectCategory(category);
      } else if (!categories.some((item) => item.open)) {
        updateCategoryStatus(null);
  setCategoryContent(null);
      }
    });
  });
  updateCategoryStatus(null);
  setCategoryContent(null);

  function activateTopPanel(panelId) {
    const value = String(panelId || "");
    if (!VALID_TOP_PANELS.has(value)) return false;
    const tab = [...document.querySelectorAll(".top-info-tab")]
      .find((button) => button?.dataset?.topPanel === value);
    if (!tab || typeof tab.click !== "function") return false;
    tab.click();
    return true;
  }

  function navigateShortcut(link) {
    const href = String(link?.getAttribute?.("href") || "");
    if (!href.startsWith("#")) return false;
    const targetId = href.slice(1);
    const target = safeTarget(targetId);
    if (!target) return false;
    activeCategory = link.closest?.(".feature-category") || activeCategory;
    targetLabels.set(target, String(link.childNodes?.[0]?.textContent || link.textContent || "").replace(/\s+/g, " ").trim());
    showManagedTarget(target);

    const panelId = String(link?.dataset?.featureOpenPanel || "");
    if (panelId) activateTopPanel(panelId);

    if (selectedStatus) {
      selectedStatus.classList?.add?.("active");
      selectedStatus.textContent = "✅ 기능 화면으로 이동했습니다. 선택한 기능만 표시 중입니다. 위의 ‘기능목록’ 또는 ‘접기’를 누르면 긴 화면 없이 바로 돌아갈 수 있습니다.";
    }

    scrollTarget(targetSurfaces.get(target) || target, panelId ? 50 : 0);
    return true;
  }

  document.querySelectorAll(".feature-shortcut").forEach((link) => {
    link.addEventListener("click", (event) => {
      const href = String(link.getAttribute("href") || "");
      if (!href.startsWith("#")) return;
      event.preventDefault();
      navigateShortcut(link);
    });
  });

  function openTabletAction(button) {
    const targetId = String(button?.dataset?.tabletTarget || "");
    if (!VALID_TABLET_TARGETS.has(targetId)) return false;
    const target = safeTarget(targetId);
    if (!target) return false;

    if (targetId === "tabletServerGuide") {
      target.open = true;
    } else {
      const updateButton = [...document.querySelectorAll(".update-menu-btn")]
        .find((item) => String(item?.dataset?.updateTarget || "") === targetId);
      if (!updateButton || typeof updateButton.click !== "function") return false;
      updateButton.click();
    }

    const clickId = String(button?.dataset?.tabletClick || "");
    if (clickId) {
      if (!VALID_TABLET_CLICKS.has(clickId)) return false;
      const action = safeTarget(clickId);
      if (!action || typeof action.click !== "function") return false;
      setTimeout(() => action.click(), 80);
    }

    const status = document.getElementById("tabletManagerStatus");
    if (status) {
      const label = String(button?.querySelector?.("b")?.textContent || "관리 기능").trim();
      status.classList?.add?.("active");
      status.textContent = `✅ ${label} 화면을 열었습니다.`;
    }
    scrollTarget(target, 60);
    return true;
  }

  document.querySelectorAll(".tablet-manager-action").forEach((button) => {
    button.addEventListener("click", () => openTabletAction(button));
  });

  if (fab) {
    fab.addEventListener("click", (event) => {
      event.preventDefault();
      scrollTarget(nav);
      const openCategory = categories.find((item) => item.open) || categories[0];
      const summary = openCategory?.querySelector?.("summary");
      setTimeout(() => summary?.focus?.(), reducedMotionPreferred() ? 0 : 80);
    });
  }

  function ensureAppDockStyles() {
    if (document.getElementById("tcgAppDockStyles")) return;
    const style = document.createElement("style");
    style.id = "tcgAppDockStyles";
    style.textContent = `
      .app-bottom-dock{display:none}
      @media(max-width:1180px){
        body.has-app-bottom-dock .app{padding-bottom:calc(118px + env(safe-area-inset-bottom,0px))!important}
        body.has-app-bottom-dock .feature-category-fab{display:none!important}
        .app-bottom-dock{
          position:fixed;left:50%;bottom:calc(10px + env(safe-area-inset-bottom,0px));z-index:70;
          transform:translateX(-50%);display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
          width:min(calc(100% - 20px),620px);padding:7px;border:1px solid rgba(148,163,184,.34);
          border-radius:22px;background:rgba(255,255,255,.93);backdrop-filter:blur(18px) saturate(145%);
          box-shadow:0 16px 38px rgba(15,23,42,.22)
        }
        .app-bottom-dock a{
          min-width:0;min-height:58px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;
          border-radius:16px;color:#64748b;text-decoration:none;font-size:10px;font-weight:850;line-height:1.1;
          touch-action:manipulation;-webkit-tap-highlight-color:transparent
        }
        .app-bottom-dock a:active{transform:scale(.96)}
        .app-bottom-dock a.app-bottom-dock-primary{
          width:62px;height:62px;min-height:62px;justify-self:center;align-self:end;margin-top:-20px;
          border-radius:50%;background:linear-gradient(145deg,#2563eb,#1d4ed8);color:#fff;
          border:4px solid rgba(255,255,255,.96);box-shadow:0 10px 24px rgba(37,99,235,.36)
        }
        .app-bottom-dock a.app-bottom-dock-primary .app-bottom-dock-icon{font-size:31px;font-weight:500;transform:translateY(-1px)}
        .app-bottom-dock a.app-bottom-dock-primary .app-bottom-dock-label{font-size:9px;color:#eff6ff}
        .app-bottom-dock a[aria-current="location"]{background:#eff6ff;color:#1d4ed8;box-shadow:inset 0 0 0 1px #dbeafe}
        .app-bottom-dock a.app-bottom-dock-primary[aria-current="location"]{background:linear-gradient(145deg,#1d4ed8,#1e40af);color:#fff;box-shadow:0 10px 24px rgba(37,99,235,.40)}
        .app-bottom-dock-icon{font-size:22px;line-height:1}
        .app-bottom-dock-label{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
        .app-bottom-dock a:focus-visible{outline:3px solid #2563eb;outline-offset:1px}
      }
      @media(max-width:360px){
        .app-bottom-dock{width:calc(100% - 12px);bottom:calc(6px + env(safe-area-inset-bottom,0px));padding:5px;border-radius:18px}
        .app-bottom-dock a{min-height:54px;border-radius:13px;font-size:9px}
        .app-bottom-dock-icon{font-size:20px}
      }
      @media(prefers-color-scheme:dark) and (max-width:1180px){
        .app-bottom-dock{background:rgba(15,23,42,.94);border-color:#334155;box-shadow:0 16px 38px rgba(0,0,0,.38)}
        .app-bottom-dock a{color:#cbd5e1}
        .app-bottom-dock a[aria-current="location"]{background:#172554;color:#bfdbfe;box-shadow:inset 0 0 0 1px #1e3a8a}
      }
      @media(prefers-reduced-motion:reduce){.app-bottom-dock a{transition:none!important}}
      @media(forced-colors:active){.app-bottom-dock{border:1px solid CanvasText}.app-bottom-dock a[aria-current="location"]{outline:2px solid Highlight}}
    `;
    document.head.append(style);
  }

  function adaptiveDockPlan(featureKeys = []) {
    const requested = Array.isArray(featureKeys) ? featureKeys.map(String) : [];
    const chosen = [];
    const usedTargets = new Set([FIXED_DOCK_MENU.target, FIXED_DOCK_PRIMARY.target]);
    const consider = [...requested, ...DEFAULT_DOCK_FEATURES];
    for (const key of consider) {
      const item = ADAPTIVE_DOCK_FEATURES[key];
      if (!item || usedTargets.has(item.target) || !safeTarget(item.target)) continue;
      chosen.push(item);
      usedTargets.add(item.target);
      if (chosen.length === 3) break;
    }
    // Fail closed: if three verified existing targets are not available, keep
    // the legacy dock untouched rather than creating incomplete navigation.
    if (chosen.length !== 3 || !safeTarget(FIXED_DOCK_MENU.target) || !safeTarget(FIXED_DOCK_PRIMARY.target)) return null;
    return Object.freeze([FIXED_DOCK_MENU, chosen[0], FIXED_DOCK_PRIMARY, chosen[1], chosen[2]]);
  }

  function renderAppDock(items) {
    if (!Array.isArray(items) || items.length !== 5) return false;
    ensureAppDockStyles();
    let dock = document.getElementById("tcgAppBottomDock");
    if (!dock) {
      dock = document.createElement("nav");
      dock.id = "tcgAppBottomDock";
      dock.className = "app-bottom-dock";
      dock.setAttribute("aria-label", "주요 기능 빠른 이동");
      document.body.append(dock);
      document.body.classList.add("has-app-bottom-dock");
    }
    dock.dataset.uiVersion = "v407-video-neural-dock";
    dock.dataset.adaptive = "verified-screen-neural";
    dock.replaceChildren();

    function setActive(key) {
      dock.querySelectorAll("a[data-dock-key]").forEach((link) => {
        const active = link.dataset.dockKey === key;
        if (active) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
    }

    for (const item of items) {
      const target = safeTarget(item.target);
      if (!target) return false;
      const link = document.createElement("a");
      link.href = "#" + item.target;
      link.dataset.dockKey = item.key;
      link.dataset.dockTarget = item.target;
      link.setAttribute("aria-label", item.label + " 화면으로 이동");
      link.setAttribute("aria-controls", item.target);
      if (item.primary === true) link.classList.add("app-bottom-dock-primary");

      const icon = document.createElement("span");
      icon.className = "app-bottom-dock-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = item.icon;
      const label = document.createElement("span");
      label.className = "app-bottom-dock-label";
      label.textContent = item.label;
      link.append(icon, label);

      link.addEventListener("click", (event) => {
        event.preventDefault();
        const verifiedTarget = safeTarget(item.target);
        if (!verifiedTarget) return;
        if (item.key === "menu") {
          categories.forEach((category) => { category.open = false; });
          updateCategoryStatus(null);
          setCategoryContent(null);
          setActive(item.key);
          scrollTarget(nav);
        } else {
          const dockCategory = categoryByKey(DOCK_CATEGORY_BY_KEY[item.key]) || targetCategories.get(verifiedTarget);
          if (dockCategory) selectCategory(dockCategory);
          showManagedTarget(verifiedTarget);
          if (item.panel) activateTopPanel(item.panel);
          setActive(item.key);
          scrollTarget(verifiedTarget, item.panel ? 50 : 0);
        }
        if (item.key === "menu") {
          const openCategory = categories.find((category) => category.open) || categories[0];
          setTimeout(() => openCategory?.querySelector?.("summary")?.focus?.(), reducedMotionPreferred() ? 0 : 80);
        }
      });
      dock.append(link);
    }
    const home = dock.querySelector('a[data-dock-key="menu"]');
    home?.setAttribute("aria-current", "location");
    return true;
  }

  function applyAdaptiveDock(featureKeys = []) {
    const plan = adaptiveDockPlan(featureKeys);
    if (!plan) return false;
    return renderAppDock(plan);
  }

  function createAppDock() {
    return applyAdaptiveDock([]);
  }

  function requestServiceWorkerRefresh() {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return false;
    navigator.serviceWorker.getRegistration()
      .then((registration) => registration?.update?.())
      .catch(() => {});
    return true;
  }

  createAppDock();
  requestServiceWorkerRefresh();

  window.TCGFeatureCategoryNav = Object.freeze({
    version: "v30-tablet-manager-hub",
    uiVersion: "v407-video-neural-dock",
    categoryInteractionVersion: "v470-single-feature-view",
    activateTopPanel,
    navigateShortcut,
    openTabletAction,
    selectCategory,
    setCategoryContent,
    showManagedTarget,
    returnToCategory,
    closeFeatureView,
    createAppDock,
    applyAdaptiveDock,
    requestServiceWorkerRefresh,
    reducedMotionPreferred,
    targetExists: (id) => Boolean(safeTarget(id)),
  });
})();

/* V485: Screenshot-informed, evidence-only market home.  Existing navigation,
   collector and grading contracts remain authoritative. */
(() => {
  "use strict";
  const root = document.getElementById("featureCategories");
  const grid = root?.querySelector(".feature-category-grid");
  if (!root || !grid || document.getElementById("tcgMarketHome")) return;
  const GAMES = Object.freeze([
    {id:"ALL", label:"전체"}, {id:"Pokémon", label:"⚡ 포켓몬"},
    {id:"ONE PIECE", label:"🏴‍☠️ 원피스"}, {id:"NARUTO", label:"🥷 나루토"}
  ]);
  const REGION = Object.freeze({KR:"한국판",JP:"일본판",US:"미국판"});
  const state = {game:"ALL", entries:[], images:{}, updated:"", ready:false};
  const el = (tag, cls, value) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (value !== undefined) n.textContent = value;
    return n;
  };
  const safeUrl = (value) => {
    try {
      const url = new URL(String(value || ""));
      return url.protocol === "https:" && url.hostname ? url.href : "";
    } catch (_) { return ""; }
  };
  const validDate = (value) => {
    const s = String(value || "");
    return /^20\d{2}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s+"T00:00:00Z")) ? s : "";
  };
  const clean = (value) => String(value || "").normalize("NFKC").trim().toLocaleLowerCase("ko-KR");
  const home = el("section", "tcg-market-home");
  home.id = "tcgMarketHome";
  home.setAttribute("aria-labelledby", "tcgMarketHomeTitle");
  const head = el("div", "tcg-market-home-head");
  const heading = el("div", "");
  const title = el("h3", "", "카드 시장 한눈에");
  title.id = "tcgMarketHomeTitle";
  heading.append(title, el("p", "", "실제 저장자료의 카드·BOX 가격을 게임별로 빠르게 확인합니다."));
  const refresh = el("button", "tcg-market-refresh", "새로 확인");
  refresh.type = "button";
  head.append(heading, refresh);
  const tabs = el("div", "tcg-market-game-tabs");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "카드게임 가격 선택");
  const buttons = [];
  GAMES.forEach(game => {
    const button = el("button", "tcg-market-game", game.label);
    button.type = "button";
    button.dataset.game = game.id;
    button.setAttribute("aria-pressed", String(game.id === state.game));
    button.addEventListener("click", () => {
      state.game = game.id;
      buttons.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.game === state.game)));
      render();
      if (!state.ready) void load();
    });
    tabs.append(button);
    buttons.push(button);
  });
  const meta = el("p", "tcg-market-home-meta", "공개 참고가격 · 과거 자료는 실시간 가격이 아닙니다.");
  meta.setAttribute("role", "status");
  meta.setAttribute("aria-live", "polite");
  const two = el("div", "tcg-market-home-sections");
  const sections = {};
  [["HIT","🎴 카드 시세","실제 거래·판매가 근거가 있는 카드"],["BOX","📦 인기 BOX 참고","BOX 공개 가격·상품정보"]].forEach(([key,name,subtitle]) => {
    const wrap = el("section", "tcg-market-home-section");
    const row = el("div", "tcg-market-section-heading");
    const left = el("div", "");
    left.append(el("h4", "", name),el("small", "", subtitle));
    const more = el("button", "tcg-market-more", "전체 검색 ›");
    more.type="button";
    more.addEventListener("click", () => openExistingSearch(null, key));
    row.append(left, more);
    const cards = el("div", "tcg-market-home-cards");
    cards.setAttribute("aria-label", name + " 목록");
    wrap.append(row,cards);
    two.append(wrap);
    sections[key] = cards;
  });
  const warning = el("p", "tcg-market-home-warning",
    "↗ 급등률·가격 그래프는 동일 카드·판본의 날짜별 거래기록이 확인된 경우에만 표시해야 합니다. 근거 없는 상승률은 생성하지 않습니다.");
  home.append(head,tabs,meta,two,warning);
  grid.parentNode.insertBefore(home,grid);

  function openExistingSearch(row, asset) {
    const market = document.getElementById("market12");
    const type = document.getElementById("asset12");
    const game = document.getElementById("v12Game");
    const query = document.getElementById("query12");
    if (market) market.value = row?.region || "ALL";
    if (type) type.value = asset || "ALL";
    if (game) game.value = row?.game && row.game !== "UNKNOWN" ? row.game : state.game;
    if (query) query.value = row?.name || "";
    const link = document.querySelector('.feature-shortcut[data-feature-key="market-search"]');
    if (link) link.click();
    else document.getElementById("market12section")?.scrollIntoView({block:"start"});
    if (row) document.getElementById("search12")?.click();
  }
  function openPurchase(row) {
    const selector = document.getElementById("purchaseGame");
    const query = document.getElementById("purchaseQuery");
    const mapping = {"Pokémon":"Pokemon","ONE PIECE":"ONE PIECE","NARUTO":"NARUTO"};
    if (selector && mapping[row.game]) selector.value=mapping[row.game];
    if (query) query.value=row.name;
    document.querySelector('.feature-shortcut[data-feature-key="purchase-finder"]')?.click();
  }
  function card(row) {
    const article = el("article", "tcg-market-tile");
    const visual = el("div", "tcg-market-tile-visual");
    const image = state.images[row.name];
    const imageUrl = image && image.region === row.region ? safeUrl(image.url) : "";
    if (row.asset === "BOX" && imageUrl) {
      const img = el("img", "");
      img.src=imageUrl;
      img.alt=row.name+" BOX 상품 참고 이미지";
      img.loading="lazy";
      img.decoding="async";
      img.addEventListener("error", () => {
        img.remove();
        visual.append(el("span", "tcg-market-art-empty", "이미지 확인 필요"));
      }, {once:true});
      visual.append(img);
    } else {
      visual.append(el("span", "tcg-market-art-empty", row.asset === "BOX" ? "BOX 이미지 확인 필요" : "카드 이미지 확인 필요"));
    }
    const label = el("div", "tcg-market-tile-label", (REGION[row.region] || "국가 미확인")+" · "+(row.game === "UNKNOWN" ? "게임 확인 필요" : row.game));
    const name = el("strong", "tcg-market-tile-name", row.name);
    name.title=row.name;
    const price = el("b", "tcg-market-tile-price", row.display);
    const kind = el("small", "tcg-market-tile-kind", row.kind || "참고시세 유형 확인 필요");
    const dated = el("small", "tcg-market-tile-date", row.source_date ? "자료일 "+row.source_date : "거래·관측일 미확인");
    const actions = el("div", "tcg-market-tile-actions");
    const detail = el("button", "", "시세 상세");
    detail.type="button";
    detail.addEventListener("click",()=>openExistingSearch(row,row.asset));
    actions.append(detail);
    const href = safeUrl(row.source);
    if (href) {
      const source = el("a", "", "가격 출처 ↗");
      source.href=href;
      source.target="_blank";
      source.rel="noopener noreferrer";
      source.setAttribute("aria-label",row.name+" 가격 출처 열기");
      actions.append(source);
    }
    if (row.game !== "UNKNOWN") {
      const seller = el("button", "tcg-market-tile-shop", "판매처 찾기");
      seller.type="button";
      seller.addEventListener("click",()=>openPurchase(row));
      actions.append(seller);
    }
    article.append(visual,label,name,price,kind,dated,actions);
    return article;
  }
  function render() {
    const filtered=state.entries.filter(row=>state.game==="ALL" || row.game===state.game);
    for(const asset of ["HIT","BOX"]) {
      const rows=filtered.filter(row=>row.asset===asset).slice(0,6);
      sections[asset].replaceChildren();
      if(!rows.length) sections[asset].append(el("p","tcg-market-home-empty",
        state.ready ? "확인 가능한 "+(asset==="BOX"?"BOX":"카드")+" 저장자료가 없습니다. 전체 검색에서 확인하세요." : "자료를 확인 중입니다."));
      else rows.forEach(row=>sections[asset].append(card(row)));
    }
    if(state.ready) {
      const date = state.updated ? "저장 파일 갱신: "+state.updated : "파일 갱신일 확인 필요";
      meta.textContent=date+" · 개별 관측일은 상품마다 다릅니다 · 실시간 체결 아님";
    }
  }
  let pending=null;
  async function load() {
    if(pending) return pending;
    refresh.disabled=true;
    meta.textContent="저장된 카드 시세를 읽는 중입니다…";
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),9000);
    pending=(async()=>{
      try {
        const results=await Promise.all([
          fetch("market_prices.json",{cache:"no-store",signal:controller.signal}).then(r=>{if(!r.ok)throw Error("market");return r.json()}),
          fetch("market_watch.json",{cache:"no-store",signal:controller.signal}).then(r=>r.ok?r.json():{items:[]}).catch(()=>({items:[]})),
          fetch("catalog_image_manifest.json",{cache:"no-store",signal:controller.signal}).then(r=>r.ok?r.json():{items:{}}).catch(()=>({items:{}}))
        ]);
        const [market,watch,images]=results;
        if(!market || !market.entries || typeof market.entries!=="object" || Array.isArray(market.entries)) throw Error("schema");
        const known=new Map();
        for(const item of Array.isArray(watch?.items)?watch.items:[]) {
          if(item && ["HIT","BOX"].includes(item.asset) && GAMES.some(g=>g.id===item.game))
            known.set([item.region,clean(item.name),item.asset].join("|"),item.game);
        }
        const rows=[];
        for(const [key,value] of Object.entries(market.entries).slice(0,1500)) {
          const parts=key.split("|");
          if(parts.length!==3 || !REGION[parts[0]] || !["HIT","BOX"].includes(parts[2]))continue;
          if(!value || typeof value!=="object" || typeof value.display!=="string" || !value.display.trim())continue;
          const game=GAMES.some(g=>g.id===value.game && g.id!=="ALL") ? value.game
            : known.get([parts[0],clean(parts[1]),parts[2]].join("|")) || "UNKNOWN";
          rows.push({region:parts[0],name:parts[1],asset:parts[2],game,
            display:value.display.slice(0,95),kind:String(value.kind||"").slice(0,130),
            source_date:validDate(value.source_date),source:value.source||""});
        }
        rows.sort((a,b)=>b.source_date.localeCompare(a.source_date)||a.name.localeCompare(b.name,"ko"));
        state.entries=rows;
        state.images=images && images.items && typeof images.items==="object" && !Array.isArray(images.items) ? images.items : {};
        state.updated=String(market.updated_at||"").slice(0,10);
        state.ready=true;
        render();
      } catch (_) {
        meta.textContent="시세자료를 읽지 못했습니다. 네트워크 또는 저장파일 상태를 확인하고 새로 확인을 눌러주세요.";
        meta.dataset.error="true";
        if (!state.ready) render();
      } finally {
        clearTimeout(timer);
        refresh.disabled=false;
        pending=null;
      }
    })();
    return pending;
  }
  refresh.addEventListener("click",()=>{delete meta.dataset.error;void load()});
  render();
  if("IntersectionObserver" in window) {
    const observer=new IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting)) {observer.disconnect();void load();}
    },{rootMargin:"160px"});
    observer.observe(home);
  } else void load();
  window.TCGMarketHome=Object.freeze({version:"v485-evidence-only",refresh:load});
})();
