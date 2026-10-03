(() => {
  "use strict";

  const VERSION = "v400-adaptive";
  const REPORT_URL = "./tablet_autonomy_v400_report.json";
  const LAYOUT_PREF_KEY = "tcgAdaptiveLayoutV400";
  const CATEGORY_KEYS = Object.freeze(["grade","market","box","news","purchase","learning","tablet","code"]);
  const categoryLabels = Object.freeze({
    grade:"카드 분석 · 등급", market:"카드 시세", box:"BOX · HIT", news:"출시 · 프로모 · 행사",
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
  let sessionLayoutPreference = null;

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

  function categoryContainer() {
    return document.getElementById("featureCategories");
  }

  function categoryNodes() {
    const container = categoryContainer();
    if (!container) return [];
    return [...container.querySelectorAll(".feature-category[data-category-key]")];
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
    return CATEGORY_KEYS.every((key) => allowed.has(key) && order.includes(key));
  }

  function clearRanks() {
    categoryNodes().forEach((item) => {
      delete item.dataset.aiRank;
      item.removeAttribute("aria-description");
    });
  }

  function restoreOriginalOrder() {
    const container = categoryContainer();
    if (!container) return false;
    const byKey = Object.fromEntries(categoryNodes().map((item) => [String(item.dataset.categoryKey || ""), item]));
    captureOriginalOrder().forEach((key) => { if (byKey[key]) container.append(byKey[key]); });
    clearRanks();
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
    return true;
  }

  function mount() {
    const manager = document.getElementById("tabletManagerHub");
    if (!manager || document.getElementById("tabletAutonomyV400")) return null;
    captureOriginalOrder();

    const panel = node("section", "tablet-autonomy-v400");
    panel.id = "tabletAutonomyV400";
    panel.setAttribute("aria-labelledby", "tabletAutonomyV400Title");

    const head = node("div", "tablet-autonomy-head");
    const intro = node("div", "tablet-autonomy-intro");
    intro.append(
      node("span", "tablet-autonomy-kicker", "AI SELF-EVOLUTION · ADAPTIVE UI"),
      node("h4", "", "🧠 태블릿 AI 자율진화 · 화면 최적화"),
      node("p", "", "UI · 카드분석 · 시세 · 발급/출시 · 콜라보/행사 · 구매처 · 태블릿 운영을 검증하고, 필요한 기능이 위로 오도록 화면 순서를 안전하게 조정합니다.")
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
    ["영역 진단","증거 신뢰도","시장활동","목표 선택","UI 재배치","Canary","성과/롤백"].forEach((name) => {
      flow.append(node("span", "tablet-autonomy-flow-step", name));
    });

    const grid = node("div", "tablet-autonomy-grid");
    const defs = {
      focus:"현재 최우선 영역", urgency:"보완 긴급도", layout:"AI 화면 정렬",
      top:"화면 1순위", canary:"V400 Canary", rollback:"Rollback",
      source:"보호 PR 후보", gate:"안전 게이트",
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
      node("span", "", "검증된 부족 영역과 최근 출시·행사·거래 활동만으로 메뉴 순서를 조정합니다.")
    );
    const layoutToggle = node("button", "tablet-autonomy-layout-toggle", "");
    layoutToggle.type = "button";
    layoutToggle.setAttribute("aria-pressed", layoutEnabled() ? "true" : "false");
    layoutHead.append(layoutText, layoutToggle);
    const layoutRank = node("div", "tablet-autonomy-layout-rank");
    layoutBox.append(layoutHead, layoutRank);

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
      node("span", "", "✓ AI 화면 정렬은 언제든 원래 순서로 복원"),
      node("span", "", "✓ 선언형 기능만 자동 적용 · 코드 자가수정 금지"),
      node("span", "", "✓ 가격·등급·재고·출시·행사 사실 발명 금지")
    );

    panel.append(head, status, flow, grid, layoutBox, surfaces, footer);
    const managerHead = manager.querySelector(".tablet-manager-head");
    if (managerHead && managerHead.nextSibling) manager.insertBefore(panel, managerHead.nextSibling);
    else manager.append(panel);

    return {panel, refresh, status, values, surfaceNodes, layoutToggle, layoutRank};
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

    const hold = asText(data.upstream_gate_status, "").includes("HOLD");
    const attention = rows.some((row) => row && row.status === "attention");
    ui.status.dataset.state = hold ? "hold" : "ok";
    ui.status.textContent = hold
      ? "상위 안전 게이트가 변경 실행을 보류했습니다. 화면은 검증된 기존 순서를 유지합니다."
      : attention
        ? "검증 신호가 약한 영역을 AI가 우선 보완 대상으로 선택했고, 허용된 메뉴만 재배치합니다."
        : "연결됨 · 분석/시세/발급/행사/구매/태블릿 운영을 함께 비교해 화면 우선순위를 조정합니다.";
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
    load(ui).finally(() => schedule(ui));
    window.TCGTabletAutonomyV400 = Object.freeze({
      version:VERSION,
      reportUrl:REPORT_URL,
      refresh:() => load(ui),
      adaptiveLayoutEnabled:layoutEnabled,
      restoreOriginalOrder,
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();