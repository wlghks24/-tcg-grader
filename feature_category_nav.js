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

  categories.forEach((category) => {
    const targets = new Set();
    category.querySelectorAll(".feature-shortcut[href^='#']").forEach((link) => {
      const id = String(link.getAttribute("href") || "").slice(1);
      if (!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(id)) return;
      const target = document.getElementById(id);
      if (!target) return;
      targets.add(target);
      managedTargets.add(target);
    });
    categoryTargets.set(category, targets);
  });

  function setCategoryContent(category) {
    managedTargets.forEach((target) => { target.hidden = true; });
    if (!category || !categories.includes(category)) {
      document.body.removeAttribute("data-feature-category-active");
      nav?.removeAttribute("data-active-category");
      return true;
    }
    (categoryTargets.get(category) || new Set()).forEach((target) => { target.hidden = false; });
    const key = String(category.dataset.categoryKey || "");
    document.body.setAttribute("data-feature-category-active", key || "selected");
    nav?.setAttribute("data-active-category", key || "selected");
    return true;
  }

  function showManagedTarget(target) {
    if (!target || !managedTargets.has(target)) return false;
    managedTargets.forEach((item) => { item.hidden = item !== target; });
    target.hidden = false;
    return true;
  }

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

  function updateCategoryStatus(category) {
    if (!selectedStatus) return;
    if (!category) {
      selectedStatus.classList?.remove?.("active");
      selectedStatus.textContent = "카테고리를 선택하면 해당 기능 목록만 표시됩니다.";
      return;
    }
    selectedStatus.classList?.add?.("active");
    selectedStatus.textContent = `✅ ${categoryLabel(category)} · 아래 기능 목록에서 원하는 항목을 선택하세요.`;
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
    showManagedTarget(target);

    const panelId = String(link?.dataset?.featureOpenPanel || "");
    if (panelId) activateTopPanel(panelId);

    if (selectedStatus) {
      selectedStatus.classList?.add?.("active");
      selectedStatus.textContent = "✅ 기능 화면으로 이동했습니다. 아래 앱 메뉴 또는 오른쪽 아래 메뉴 버튼으로 주요 기능에 바로 이동할 수 있습니다.";
    }

    scrollTarget(target, panelId ? 50 : 0);
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
    activateTopPanel,
    navigateShortcut,
    openTabletAction,
    selectCategory,
    setCategoryContent,
    showManagedTarget,
    createAppDock,
    applyAdaptiveDock,
    requestServiceWorkerRefresh,
    reducedMotionPreferred,
    targetExists: (id) => Boolean(safeTarget(id)),
  });
})();