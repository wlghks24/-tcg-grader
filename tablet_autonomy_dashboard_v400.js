(() => {
  "use strict";

  const VERSION = "v400";
  const REPORT_URL = "./tablet_autonomy_v400_report.json";
  let refreshMs = 45000;
  let timer = null;

  const labels = {
    ui: "UI · PWA",
    card_measurement: "카드 측정 · 등급",
    card_market: "카드 시세",
    collab_event: "콜라보 · 이벤트",
  };

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

  function mount() {
    const manager = document.getElementById("tabletManagerHub");
    if (!manager || document.getElementById("tabletAutonomyV400")) return null;

    const panel = node("section", "tablet-autonomy-v400");
    panel.id = "tabletAutonomyV400";
    panel.setAttribute("aria-labelledby", "tabletAutonomyV400Title");

    const head = node("div", "tablet-autonomy-head");
    const intro = node("div", "tablet-autonomy-intro");
    intro.append(
      node("span", "tablet-autonomy-kicker", "AI SELF-EVOLUTION · " + VERSION),
      node("h4", "", "🧠 태블릿 AI 영역별 자율진화 상태판"),
      node("p", "", "UI · 카드측정 · 카드시세 · 콜라보/이벤트를 실제 검증 신호로 비교해 다음 보완 목표를 선택합니다.")
    );
    intro.querySelector("h4").id = "tabletAutonomyV400Title";

    const refresh = node("button", "tablet-autonomy-refresh", "상태 새로고침");
    refresh.type = "button";
    refresh.setAttribute("aria-label", "태블릿 AI V400 상태 새로고침");
    head.append(intro, refresh);

    const status = node("div", "tablet-autonomy-status", "최신 V400 보고서를 확인하는 중…");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const flow = node("div", "tablet-autonomy-flow");
    ["영역 진단", "증거 신뢰도", "목표 선택", "선언형 기능후보", "Canary", "성과측정", "승격/롤백"].forEach((name) => {
      flow.append(node("span", "tablet-autonomy-flow-step", name));
    });

    const grid = node("div", "tablet-autonomy-grid");
    const defs = {
      focus: "현재 최우선 영역",
      urgency: "보완 긴급도",
      canary: "V400 Canary",
      rollback: "Rollback",
      source: "보호 PR 후보",
      gate: "안전 게이트",
    };
    const values = {};
    Object.entries(defs).forEach(([key, label]) => {
      const item = metric(label);
      values[key] = item.value;
      grid.append(item.box);
    });

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
      node("span", "", "✓ 선언형 기능만 자동 적용"),
      node("span", "", "✓ 코드 새 기능은 보호 PR/CI 후보"),
      node("span", "", "✓ 가격·등급·행사 사실 발명 금지")
    );

    panel.append(head, status, flow, grid, surfaces, footer);
    const managerHead = manager.querySelector(".tablet-manager-head");
    if (managerHead && managerHead.nextSibling) manager.insertBefore(panel, managerHead.nextSibling);
    else manager.append(panel);

    return {panel, refresh, status, values, surfaceNodes};
  }

  function surfaceMeta(row) {
    const ev = row && row.evidence && typeof row.evidence === "object" ? row.evidence : {};
    if (row.surface === "ui") {
      return "구성 " + asText(ev.passed, "0") + "/" + asText(ev.total, "0") +
        " · critical " + asText(ev.critical_failed, "0");
    }
    if (row.surface === "card_measurement") {
      const age = ev.verification_age_days === null || ev.verification_age_days === undefined
        ? "미확인"
        : Math.round(Number(ev.verification_age_days)) + "일";
      return "측정자산 " + asText(ev.present_assets, "0") + "/" + asText(ev.required_assets, "0") +
        " · 검증자료 " + age;
    }
    if (row.surface === "card_market") {
      return "시세 " + asText(ev.entry_count, "0") + "건 · " +
        (Array.isArray(ev.regions) ? ev.regions.join("/") : "지역 미확인") +
        " · 최신성 " + pct(ev.freshness);
    }
    if (row.surface === "collab_event") {
      return "행사 " + asText(ev.item_count, "0") + "건 · 콜라보 " +
        asText(ev.collaboration_count, "0") + "건 · 감시 " + pct(ev.watched_game_region_ratio);
    }
    return "검증 신호 확인 중";
  }

  function render(ui, report) {
    const data = report && report.v400_ui && typeof report.v400_ui === "object" ? report.v400_ui : {};
    const rows = Array.isArray(data.surfaces) ? data.surfaces : [];
    const bySurface = Object.fromEntries(rows.filter(Boolean).map((row) => [row.surface, row]));

    ui.values.focus.textContent = labels[data.selected_surface] || asText(data.selected_surface, "대기");
    ui.values.urgency.textContent = pct(data.selected_urgency);
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
      target.fill.style.width = Number.isFinite(score)
        ? Math.round(Math.max(0, Math.min(1, score)) * 100) + "%"
        : "0%";
    });

    const hold = asText(data.upstream_gate_status, "").includes("HOLD");
    const attention = rows.some((row) => row && row.status === "attention");
    ui.status.dataset.state = hold ? "hold" : "ok";
    ui.status.textContent = hold
      ? "상위 안전 게이트가 변경 실행을 보류했습니다. 기존 검증 상태는 유지됩니다."
      : data.rollback_required
        ? "성과 저하가 감지되어 V400 선언형 기능을 정확히 롤백하도록 표시되었습니다."
        : attention
          ? "검증 신호가 약한 영역을 AI가 최우선 보완 대상으로 선택했습니다."
          : "V400 연결됨 · UI/측정/시세/이벤트 영역이 검증 기준 안에서 자율진화 중입니다.";

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
        cache: "no-store",
        headers: {"Accept": "application/json"},
      });
      if (!response.ok) throw new Error("HTTP_" + response.status);
      render(ui, await response.json());
    } catch (_error) {
      ui.status.dataset.state = "idle";
      ui.status.textContent = "아직 V400 실행 보고서가 없습니다. 태블릿에서 bash main evolve 실행 후 표시됩니다.";
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
    load(ui).finally(() => schedule(ui));
    window.TCGTabletAutonomyV400 = Object.freeze({
      version: VERSION,
      reportUrl: REPORT_URL,
      refresh: () => load(ui),
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }
})();