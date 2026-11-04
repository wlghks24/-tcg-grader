"use strict";
(() => {
  function boot() {
    const config = JSON.parse(document.getElementById("tcg903-config").textContent);
    const node = id => document.getElementById("tcg903-" + id), body = document.body;
    const drawer = node("drawer"), toggle = node("toggle"), desktop = () => window.matchMedia("(min-width:1100px)").matches;
    const targets = new Set(config.targets), report = text => { node("status").textContent = text; };
    const rows = Array.from(node("cards").content.querySelectorAll("article")).map(element => ({element, text:element.textContent.toLowerCase()}));
    let visible = [], page = 0, country = "", returnFocus = toggle, dispatchingOriginal = false, selectedCard = null;
    const pageSize = 24;
    function menu(open) {
      const modal = open && !desktop(), wasOpen = body.dataset.tcg903Menu === "open";
      if (modal && !wasOpen) returnFocus = document.activeElement;
      body.dataset.tcg903Menu = open ? "open" : "closed";
      toggle.setAttribute("aria-expanded", String(open));
      node("backdrop").hidden = !modal; drawer.inert = !open && !desktop();
      if (modal) { drawer.setAttribute("role", "dialog"); drawer.setAttribute("aria-modal", "true"); node("close").focus(); }
      else {
        drawer.removeAttribute("role"); drawer.removeAttribute("aria-modal");
        if (!open && wasOpen && returnFocus?.isConnected) returnFocus.focus();
      }
    }
    function setView(view, title) {
      if (body.dataset.tcg903View === "tool" && view !== "tool") window.tcgCameraRuntime?.stop?.();
      body.dataset.tcg903View = view;
      node("home").hidden = view !== "home"; node("events").hidden = view !== "events";
      node("title").textContent = title; report(""); menu(false);
      document.querySelectorAll("#tcg903-drawer a").forEach(a => a.removeAttribute("aria-current"));
      window.dispatchEvent(new Event("resize"));
    }
    function renderPage() {
      page = Math.max(0, Math.min(page, Math.max(0, Math.ceil(visible.length/pageSize)-1)));
      node("grid").replaceChildren(...visible.slice(page*pageSize, (page+1)*pageSize).map(r => r.element));
      node("count").textContent = config.viewState === "UNAVAILABLE" ? "자료 읽기 보류 · 0건으로 판정하지 않았습니다." : visible.length + "개 자료 · 공개 수집 도감 · 사진 수는 보유 수량이 아닙니다.";
      node("page").textContent = (visible.length ? page+1 : 0) + " / " + Math.ceil(visible.length/pageSize);
      node("prev").disabled = page === 0; node("next").disabled = (page+1)*pageSize >= visible.length;
    }
    function filter() {
      const query = node("query").value.trim().toLowerCase(), game = node("game").value, kind = node("kind").value;
      visible = rows.filter(row => {
        const d = row.element.dataset, card = ["CARD","PROMO"].includes(d.kind);
        return (!country || (country === "CN" ? ["CN-S","CN-T"].includes(d.region) : country === d.region)) &&
          (!game || game === d.game) && (!kind || (kind === "CARD" ? card : !card)) && (!query || row.text.includes(query));
      });
      page = 0; renderPage();
    }
    function selectSurface(id, label) {
      const target = document.getElementById(id), app = target?.closest("main.app");
      const heading = document.getElementById("tcg904-workspace-title");
      if (heading) heading.textContent = String(label || "카드 작업").replace(/^[^가-힣A-Za-z0-9]+/, "");
      const context = document.getElementById("tcg904-selected-card");
      if (context) context.textContent = selectedCard ? "선택한 카드: " + selectedCard.name + " · " + selectedCard.code : "";
      if (!app) return;
      Array.from(app.children).forEach(child => child.removeAttribute("data-tcg904-surface"));
      const mark = element => {
        let owner = element;
        while (owner && owner.parentElement !== app) owner = owner.parentElement;
        owner?.setAttribute("data-tcg904-surface", "true");
      };
      mark(target);
      // Result nodes retain their own hidden/style gates; marking only reserves
      // their layout slot after the original measurement code produces a result.
      const related = {simpleGradeV32:["simpleGradeResult"],gradeStart:["out"],precisionHub:["out"]}[id] || [];
      related.forEach(key => { const result = document.getElementById(key); if (result) mark(result); });
      if (selectedCard && ["pokemon","onepiece","naruto"].includes(selectedCard.game)) {
        app.querySelector('button[data-simple-game="'+selectedCard.game+'"]')?.click();
      }
    }
    function openTool(id) {
      const owner = {simpleGradeResult:"simpleGradeV32",out:"precisionHub"}[id];
      if (owner) { const ok = openTool(owner); if (ok) report("측정을 완료하면 결과가 표시됩니다. 기존 결과 표시 조건을 유지합니다."); return ok; }
      const target = document.getElementById(id);
      if (!target) return false;
      if (id === "featureCategories" || target.closest("#featureCategories")) { setView("home","홈"); menu(true); return true; }
      setView("tool", target.querySelector("h2,h3,summary")?.textContent || "세부 기능");
      let parent = target, opened = false;
      while (parent && parent !== body) {
        if (parent.id && window.TCGFeatureCategoryNav?.openTarget?.(parent.id)) { opened = true; break; }
        parent = parent.parentElement;
      }
      if (!opened) window.TCGFeatureCategoryNav?.closeFeatureView?.();
      parent = target;
      while (parent && parent !== body) { if (parent.tagName === "DETAILS") parent.open = true; parent = parent.parentElement; }
      selectSurface(id, target.querySelector("h2,h3,summary")?.textContent || "카드 작업");
      requestAnimationFrame(() => target.scrollIntoView({block:"start"})); return true;
    }
    function route(url, push = true) {
      const params = url.searchParams, key = params.get("feature"), target = params.get("target");
      let ok = false;
      const inline = {"market-search":"home","trading-catalog":"home","box-knowledge":"home","release-info":"events","promo-event-info":"events"};
      if (key && Object.hasOwn(inline,key)) {
        const pane = inline[key];
        setView(pane, pane === "home" ? (key === "box-knowledge" ? "BOX · 팩 도감" : "시세 · 카드정보") : "행사 · 출시 · 프로모");
        if (pane === "home") {
          node("kind").value = key === "box-knowledge" ? "PRODUCT" : "";
          if (selectedCard && key !== "box-knowledge") node("query").value = selectedCard.code;
          filter();
        }
        ok = true;
      } else if (key && Object.hasOwn(config.features,key)) {
        const original = Array.from(document.querySelectorAll(".feature-shortcut[data-feature-key]")).find(a => a.dataset.featureKey === key);
        if (original && document.getElementById(config.features[key])) {
          window.tcgCameraRuntime?.stop?.(); setView("tool", original.childNodes[0]?.textContent || "선택한 기능");
          dispatchingOriginal = true; try { original.click(); } finally { dispatchingOriginal = false; }
          selectSurface(config.features[key], original.childNodes[0]?.textContent || "카드 작업"); ok = true;
        }
      } else if (target && targets.has(target)) { window.tcgCameraRuntime?.stop?.(); ok = openTool(target); }
      else if (!key && !target) {
        const hash = url.hash.slice(1);
        if (hash && (targets.has(hash) || Object.values(config.features).includes(hash))) ok = openTool(hash);
        else if (!hash) {
          const pane = params.get("pane") || (url.pathname === "/tablet-events-all" ? "events" : "home");
          if (["home","library","events"].includes(pane)) {
            const home = pane !== "events";
            setView(home ? "home" : "events", home ? "홈 · 카드와 이미지" : "행사 · 콜라보 · 영화 · 프로모");
            if (home) { node("kind").value = ["CARD","PRODUCT"].includes(params.get("kind")) ? params.get("kind") : ""; filter(); }
            ok = true;
          }
        }
      }
      if (!ok && config.compatibility && (key || target)) { location.assign(url.href); return true; }
      if (!ok) { report("메뉴 대상을 찾지 못했습니다. 전체 메뉴에서 기능을 다시 선택하세요."); menu(true); return false; }
      if (push) history.pushState(null,"",url.pathname+url.search+url.hash);
      const active = Array.from(document.querySelectorAll("#tcg903-drawer a")).find(a => a.getAttribute("href") === url.pathname+url.search);
      active?.setAttribute("aria-current","page"); return true;
    }
    ["query","game","kind"].forEach(id => node(id).addEventListener(id === "query" ? "input" : "change", filter));
    node("countries").addEventListener("click", event => {
      const button = event.target.closest("[data-tcg903-country]"); if (!button) return;
      country = button.dataset.tcg903Country;
      node("countries").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b === button))); filter();
    });
    node("prev").addEventListener("click", () => { page--; renderPage(); });
    node("next").addEventListener("click", () => { page++; renderPage(); });
    [["collect","/api/local-card-images/auto-start"],["refresh","/api/run-auto-update"]].forEach(([id,endpoint]) => node(id).addEventListener("click", async () => {
      const button = node(id); button.disabled = true;
      try { const response = await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}); const result = await response.json(); if (!response.ok || result.ok === false) throw Error("요청 실패 · 서버 상태를 확인하세요"); node("job").textContent = "작업 요청 접수 · 완료 후 새로고침하여 결과를 확인하세요."; }
      catch(error) { node("job").textContent = error.message; } finally { button.disabled = false; }
    }));
    toggle.addEventListener("click", () => menu(body.dataset.tcg903Menu !== "open"));
    node("close").addEventListener("click", () => menu(false)); node("backdrop").addEventListener("click", () => menu(false));
    document.addEventListener("keydown", event => {
      if (body.dataset.tcg903Menu !== "open" || desktop()) return;
      if (event.key === "Escape") { event.preventDefault(); menu(false); }
      if (event.key === "Tab") {
        const focus = Array.from(drawer.querySelectorAll("a[href],button,summary")).filter(e => e.getClientRects().length);
        const first = focus[0], last = focus[focus.length-1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    });
    document.addEventListener("click", event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (event.target.closest(".app-feature-back,.app-feature-collapse")) { event.preventDefault(); event.stopImmediatePropagation(); setView("home","홈"); menu(true); return; }
      const anchor = event.target.closest("a[href]"); if (!anchor || anchor.target === "_blank") return;
      if (anchor.classList.contains("feature-shortcut")) {
        if (dispatchingOriginal) return;
        const key = anchor.dataset.featureKey;
        if (Object.hasOwn(config.features,key)) {
          event.preventDefault(); event.stopImmediatePropagation();
          route(new URL("/index.html?feature="+encodeURIComponent(key),location.href));
        }
        return;
      }
      const card = anchor.closest("article[data-card-code]");
      if (card) selectedCard = {code:card.dataset.cardCode,game:card.dataset.game,name:card.querySelector("h2")?.textContent || card.dataset.cardCode};
      const url = new URL(anchor.href,location.href); if (url.origin !== location.origin) return;
      if (anchor.getAttribute("href").startsWith("#")) { const id = url.hash.slice(1); if (!targets.has(id) && !Object.values(config.features).includes(id)) return; url.search = ""; }
      if (["/","/index.html","/tablet-unified","/tablet-events-all","/tablet-features"].includes(url.pathname)) {
        event.preventDefault(); event.stopImmediatePropagation();
        if (url.pathname === "/tablet-features") { setView("home","홈"); node("advanced").open = true; menu(true); } else route(url);
      }
    },true);
    document.addEventListener("error", event => {
      const img = event.target; if (!(img instanceof HTMLImageElement) || !img.closest("#tcg903-grid") || !img.dataset.original) return;
      if (!img.dataset.originalTried) { img.dataset.originalTried = "1"; img.src = img.dataset.original; }
      else { img.hidden = true; if (img.nextElementSibling) img.nextElementSibling.textContent = "사진 표시 확인 필요 · 원본 확대에서 확인하세요"; }
    },true);
    window.addEventListener("popstate", () => route(new URL(location.href),false));
    window.addEventListener("resize", () => { if (desktop()) { drawer.inert = false; drawer.removeAttribute("role"); drawer.removeAttribute("aria-modal"); node("backdrop").hidden = true; } else drawer.inert = body.dataset.tcg903Menu !== "open"; });
    filter(); menu(false);
    if (config.compatibility) setView("tool","기존 통합 도구");
    else { route(new URL(location.href),false); if (config.initial === "features") { node("advanced").open = true; menu(true); } }
    window.TCGMenuShellV903 = Object.freeze({route,menu,version:903});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",boot,{once:true}); else boot();
})();
