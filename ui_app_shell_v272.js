"use strict";
(() => {
  const VERSION = "v272-accessible-app-shell";
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

  window.TCGAppShellV272 = Object.freeze({
    version: VERSION,
    filterFeatures,
    clear: () => clearSearch(),
  });
})();
