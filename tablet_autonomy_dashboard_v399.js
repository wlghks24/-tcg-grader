(() => {
  "use strict";

  const VERSION = "v399";
  const REPORT_URL = "./tablet_autonomy_v399_report.json";
  let refreshMs = 45000;
  let timer = null;

  const asText = (value, fallback = "—") => {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  };

  const asPercent = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return Math.round(Math.max(0, Math.min(1, n)) * 100) + "%";
  };

  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function metric(label) {
    const box = node("div", "tablet-autonomy-metric");
    const key = node("span", "", label);
    const value = node("b", "", "—");
    box.append(key, value);
    return {box, value};
  }

  function mount() {
    const manager = document.getElementById("tabletManagerHub");
    if (!manager || document.getElementById("tabletAutonomyV399")) return null;

    const panel = node("section", "tablet-autonomy-v399");
    panel.id = "tabletAutonomyV399";
    panel.setAttribute("aria-labelledby", "tabletAutonomyV399Title");

    const head = node("div", "tablet-autonomy-head");
    const intro = node("div", "tablet-autonomy-intro");
    intro.append(
      node("span", "tablet-autonomy-kicker", "AI SELF-EVOLUTION · " + VERSION),
      node("h4", "", "🧠 태블릿 AI 자율진화 통합 상태판"),
      node(
        "p",
        "",
        "학습·판단·기능후보·canary·rollback과 UI/PWA/런타임 구성 상태를 함께 확인합니다."
      )
    );
    intro.querySelector("h4").id = "tabletAutonomyV399Title";

    const refresh = node("button", "tablet-autonomy-refresh", "상태 새로고침");
    refresh.type = "button";
    refresh.setAttribute("aria-label", "태블릿 AI 자율진화 상태 새로고침");
    head.append(intro, refresh);

    const status = node("div", "tablet-autonomy-status", "최신 V399 보고서를 확인하는 중…");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const flow = node("div", "tablet-autonomy-flow");
    ["진단", "목표 선택", "후보 생성", "검증 토너먼트", "Canary", "성과학습", "Rollback/재사용"].forEach((name) => {
      flow.append(node("span", "tablet-autonomy-flow-step", name));
    });

    const grid = node("div", "tablet-autonomy-grid");
    const defs = {
      surface: "UI 운용모드",
      mode: "시장·운용 모드",
      goal: "현재 목표",
      critic: "검증학습 샘플",
      candidate: "기능 후보",
      selected: "선택 기능",
      canary: "Canary 상태",
      rollback: "Rollback",
      uihealth: "UI/PWA 건강도",
      source: "UI 보완 후보",
      gate: "안전 게이트",
      physical: "실기기 확인",
    };
    const values = {};
    Object.entries(defs).forEach(([key, label]) => {
      const item = metric(label);
      item.box.dataset.metric = key;
      values[key] = item.value;
      grid.append(item.box);
    });

    const healthBlock = node("div", "tablet-autonomy-health");
    const healthHead = node("div", "tablet-autonomy-health-head");
    healthHead.append(
      node("b", "", "UI · PWA · 서버 · 런타임 구성"),
      node("span", "tablet-autonomy-health-score", "—")
    );
    const healthBar = node("div", "tablet-autonomy-health-bar");
    const healthFill = node("i", "");
    healthFill.style.width = "0%";
    healthBar.append(healthFill);
    const healthNote = node(
      "p",
      "",
      "반복되는 구성 결함은 자동 실행하지 않고 보호된 PR/CI 후보로 승격합니다."
    );
    healthBlock.append(healthHead, healthBar, healthNote);

    const footer = node("div", "tablet-autonomy-footer");
    footer.append(
      node("span", "", "✓ 선언형 기능만 자동 적용"),
      node("span", "", "✓ 코드 자동재작성 금지"),
      node("span", "", "✓ 시장방향·가격·등급 발명 금지")
    );

    panel.append(head, status, flow, grid, healthBlock, footer);

    const managerHead = manager.querySelector(".tablet-manager-head");
    if (managerHead && managerHead.nextSibling) {
      manager.insertBefore(panel, managerHead.nextSibling);
    } else {
      manager.append(panel);
    }

    return {panel, refresh, status, values, healthFill, healthScore: healthHead.querySelector("span")};
  }

  function render(ui, report) {
    const data = report && report.v399_ui && typeof report.v399_ui === "object"
      ? report.v399_ui
      : {};

    ui.values.surface.textContent = asText(data.surface_mode);
    ui.values.mode.textContent = asText(data.operating_mode);
    ui.values.goal.textContent = asText(data.primary_goal);
    ui.values.critic.textContent = asText(data.critic_samples, "0");
    ui.values.candidate.textContent = asText(data.candidate_count, "0") + "개";
    ui.values.selected.textContent = asText(data.selected_capability, "대기");
    ui.values.canary.textContent = asText(data.active_evaluation, "관찰 없음");
    ui.values.rollback.textContent = data.rollback_required ? "필요" : "불필요";
    ui.values.uihealth.textContent = asPercent(data.ui_health_score);
    ui.values.source.textContent = asText(data.ui_protected_pr_candidates, "0") + "개";
    ui.values.gate.textContent = asText(data.gate_status);
    ui.values.physical.textContent = data.physical_tablet_runtime_verified ? "확인됨" : "미확인";

    const score = Number(data.ui_health_score);
    const bounded = Number.isFinite(score) ? Math.max(0, Math.min(1, score)) : 0;
    ui.healthFill.style.width = Math.round(bounded * 100) + "%";
    ui.healthScore.textContent =
      asText(data.ui_checks_passed, "0") + "/" + asText(data.ui_checks_total, "0") + " PASS";

    const hold = asText(data.gate_status, "").includes("HOLD");
    const critical = Number(data.ui_critical_failed || 0) > 0;
    ui.status.dataset.state = hold || critical ? "hold" : "ok";
    ui.status.textContent = hold
      ? "안전 게이트가 변경 실행을 보류했습니다. 기존 검증 상태는 유지됩니다."
      : critical
        ? "UI/PWA 핵심 구성 결함이 감지되었습니다. 자동 실행 없이 보호 PR 후보로 관리합니다."
        : "V399 연결됨 · V398 자율학습과 UI/PWA 구성 감시가 정상입니다.";

    const seconds = Number(data.refresh_seconds);
    if (Number.isFinite(seconds) && seconds >= 20 && seconds <= 300) {
      refreshMs = seconds * 1000;
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
      const report = await response.json();
      render(ui, report);
    } catch (_error) {
      ui.status.dataset.state = "idle";
      ui.status.textContent =
        "아직 V399 실행 보고서가 없습니다. 태블릿에서 bash main evolve 실행 후 자동으로 표시됩니다.";
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
    window.TCGTabletAutonomyV399 = Object.freeze({
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
