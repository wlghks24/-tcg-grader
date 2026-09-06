"use strict";
(() => {
  const VALID_TOP_PANELS = new Set(["releasePanel", "promoPanel", "purchasePanel"]);
  const categories = [...document.querySelectorAll(".feature-category")];
  const selectedStatus = document.getElementById("featureCategorySelected");
  const nav = document.getElementById("featureCategories");
  const fab = document.getElementById("featureCategoryFab");
  let syncing = false;

  function safeTarget(id) {
    const value = String(id || "");
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,80}$/.test(value)) return null;
    return document.getElementById(value);
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

    const panelId = String(link?.dataset?.featureOpenPanel || "");
    if (panelId) activateTopPanel(panelId);

    if (selectedStatus) {
      selectedStatus.classList?.add?.("active");
      selectedStatus.textContent = "✅ 기능 화면으로 이동했습니다. 오른쪽 아래 ‘☰ 메뉴’를 누르면 기능 메뉴로 돌아올 수 있습니다.";
    }

    setTimeout(() => {
      try {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (_) {
        target.scrollIntoView();
      }
    }, panelId ? 50 : 0);
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

  if (fab) {
    fab.addEventListener("click", (event) => {
      event.preventDefault();
      try {
        nav?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (_) {
        nav?.scrollIntoView?.();
      }
      const openCategory = categories.find((item) => item.open) || categories[0];
      const summary = openCategory?.querySelector?.("summary");
      setTimeout(() => summary?.focus?.(), 80);
    });
  }

  window.TCGFeatureCategoryNav = Object.freeze({
    version: "v28-clear-home",
    activateTopPanel,
    navigateShortcut,
    selectCategory,
    targetExists: (id) => Boolean(safeTarget(id)),
  });
})();
