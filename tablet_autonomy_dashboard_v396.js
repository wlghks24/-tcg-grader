(() => {
  "use strict";

  const VERSION = "v396";
  const REPORT_URL = "./tablet_autonomy_v396_report.json";
  const REFRESH_MS = 45000;

  const text = (value, fallback = "—") => {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  };

  const percent = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return Math.round(Math.max(0, Math.min(1, number)) * 100) + "%";
  };

  function el(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function mount() {
    const manager = document.getElementById("tabletManagerHub");
    if (!manager || document.getElementById("tabletAutonomyV396")) return null;

    const panel = el("section", "tablet-autonomy-v396");
    panel.id = "tabletAutonomyV396";
    panel.setAttribute("aria-labelledby", "tabletAutonomyV396Title");

    const head = el("div", "tablet-autonomy-head");
    const titleWrap = el("div", "tablet-autonomy-title-wrap");
    const kicker = el("span", "tablet-autonomy-kicker", "AI SELF-EVOLUTION · " + VERSION);
    const title = el("h4", "", "🧠 태블릿 AI 자율진화 상태");
    title.id = "tabletAutonomyV396Title";
    const description = el(
      "p",
      "",
      "신경망 학습 · 목표 판단 · 기능 보완 · 시장상태 적응 · 자동 롤백 상태를 한 화면에서 확인합니다."
    );
    titleWrap.append(kicker, title, description);

    const refresh = el("button", "tablet-autonomy-refresh", "상태 새로고침");
    refresh.type = "button";
    refresh.setAttribute("aria-label", "태블릿 AI 자율진화 상태 새로고침");
    head.append(titleWrap, refresh);

    const status = el("div", "tablet-autonomy-status", "상태 보고서를 불러오는 중…");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const grid = el("div", "tablet-autonomy-grid");
    const metricDefs = [
      ["mode", "운용 모드"],
      ["goal", "현재 목표"],
      ["health", "운용 건강도"],
      ["critic", "검증학습 샘플"],
      ["action", "AI 추천 행동"],
      ["stage", "기능 승격 단계"],
      ["transition", "최근 진화"],
      ["gate", "안전 게이트"],
    ];
    const metricNodes = {};
    metricDefs.forEach(([key, label]) => {
      const card = el("div", "tablet-autonomy-metric");
      card.dataset.metric = key;
      card.append(el("span", "", label), el("b", "", "—"));
      metricNodes[key] = card.querySelector("b");
      grid.append(card);
    });

    const lifecycle = el("div", "tablet-autonomy-lifecycle");
    lifecycle.append(el("div", "tablet-autonomy-block-title", "기능 자동보완 수명주기"));
    const stages = ["SHADOW", "CANARY", "ACTIVE", "ROLLBACK"];
    const stageRow = el("div", "tablet-autonomy-stage-row");
    const stageNodes = {};
    stages.forEach((stage) => {
      const item = el("span", "tablet-autonomy-stage", stage);
      item.dataset.stage = stage.toLowerCase();
      stageNodes[stage.toLowerCase()] = item;
      stageRow.append(item);
    });
    const stageNote = el(
      "p",
      "tablet-autonomy-note",
      "검증되지 않은 새 기능은 바로 활성화하지 않고 Shadow → Canary → Active 순서로 승격하며, 성능 저하 시 Rollback으로 되돌립니다."
    );
    lifecycle.append(stageRow, stageNote);

    const detail = el("div", "tablet-autonomy-detail-grid");
    const sourceBox = el("div", "tablet-autonomy-detail");
    sourceBox.append(
      el("span", "", "코드 수준 기능 후보"),
      el("b", "tablet-autonomy-source-count", "—"),
      el("small", "", "보호 PR/CI 후보만 생성 · 런타임 자동 코드수정 없음")
    );
    const safetyBox = el("div", "tablet-autonomy-detail");
    safetyBox.append(
      el("span", "", "시장 적응 기준"),
      el("b", "", "운영상태 기반"),
      el("small", "", "신선도·커버리지·소스건강·드리프트·불확실성 기반 / 시장 방향 예측 없음")
    );
    detail.append(sourceBox, safetyBox);

    panel.append(head, status, grid, lifecycle, detail);

    const managerHead = manager.querySelector(".tablet-manager-head");
    if (managerHead && managerHead.nextSibling) {
      manager.insertBefore(panel, managerHead.nextSibling);
    } else {
      manager.append(panel);
    }

    return {panel, refresh, status, metricNodes, stageNodes, sourceCount: sourceBox.querySelector("b")};
  }

  function setStage(nodes, stage) {
    Object.values(nodes).forEach((node) => node.removeAttribute("data-active"));
    const key = text(stage, "").toLowerCase();
    if (nodes[key]) nodes[key].setAttribute("data-active", "true");
  }

  function render(ui, report) {
    const data = report && report.v396_ui && typeof report.v396_ui === "object"
      ? report.v396_ui
      : {};
    ui.metricNodes.mode.textContent = text(data.operating_mode);
    ui.metricNodes.goal.textContent = text(data.primary_goal);
    ui.metricNodes.health.textContent = percent(data.health_score);
    ui.metricNodes.critic.textContent = text(data.critic_samples, "0");
    ui.metricNodes.action.textContent = text(data.recommended_action);
    ui.metricNodes.stage.textContent = text(data.feature_stage, "관찰 중");
    ui.metricNodes.transition.textContent = text(data.feature_transition, "변화 없음");
    ui.metricNodes.gate.textContent = text(data.gate_status);
    ui.sourceCount.textContent = text(data.source_feature_candidates, "0") + "개";
    setStage(ui.stageNodes, data.feature_stage);

    const gate = text(data.gate_status, "");
    ui.status.dataset.state = gate.includes("HOLD") ? "hold" : "ok";
    ui.status.textContent = gate.includes("HOLD")
      ? "안전 게이트가 현재 변경 실행을 보류했습니다. 기존 기능은 유지됩니다."
      : "V396 보고서 연결됨 · 검증된 범위에서만 학습·기능 승격을 수행합니다.";
  }

  async function load(ui) {
    if (!ui) return;
    ui.refresh.disabled = true;
    ui.status.dataset.state = "loading";
    ui.status.textContent = "최신 자율진화 보고서를 확인하는 중…";
    try {
      const response = await fetch(REPORT_URL + "?v=" + Date.now(), {
        cache: "no-store",
        headers: {"Accept": "application/json"},
      });
      if (!response.ok) throw new Error("HTTP_" + response.status);
      const report = await response.json();
      render(ui, report);
    } catch (_error) {
      ui.status.dataset.state = "idle";
      ui.status.textContent =
        "아직 V396 실행 보고서가 없습니다. 태블릿에서 bash main evolve 실행 후 이 화면에 결과가 표시됩니다.";
    } finally {
      ui.refresh.disabled = false;
    }
  }

  function start() {
    const ui = mount();
    if (!ui) return;
    ui.refresh.addEventListener("click", () => load(ui));
    load(ui);
    window.setInterval(() => {
      if (document.visibilityState === "visible") load(ui);
    }, REFRESH_MS);
    window.TCGTabletAutonomyV396 = Object.freeze({
      version: VERSION,
      refresh: () => load(ui),
      reportUrl: REPORT_URL,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }
})();
