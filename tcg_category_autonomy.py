#!/usr/bin/env python3
"""Evidence-bounded autonomous category controller for the tablet runtime.

This controller can review the declarative TCG registry and produce a bounded
action plan for the tablet UI. It never predicts profit, invents market
direction, generates source code, or activates grading for a newly discovered
game. Registry promotion remains gated by verified evidence in
tcg_game_registry.py; neural components are routing-only until the independent
label gate is satisfied.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from tcg_game_registry import load_registry, review_registry, validate_registry


VERSION = "v424"
ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "tcg_category_autonomy_v424_report.json"
MIN_INDEPENDENT_LABELS = 1000
ACTIVE_STATES = {"core", "promoted"}
WATCH_STATE = "watch"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime | None = None) -> str:
    value = (moment or _now()).astimezone(dt.timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _fresh(value: Any, now: dt.datetime, review_days: int) -> bool:
    stamp = _parse_time(value)
    if stamp is None:
        return False
    age = (now - stamp).total_seconds()
    return 0 <= age <= max(1, review_days) * 86400


def _review_map(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = review.get("reviewed", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("canonical")): row
        for row in rows
        if isinstance(row, dict) and row.get("canonical")
    }


def _signal_count(reviewed: dict[str, Any], row: dict[str, Any]) -> int:
    signals = reviewed.get("signals")
    if isinstance(signals, list):
        return len({str(item) for item in signals if str(item).strip()})
    value = reviewed.get("signal_count")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    evidence = row.get("evidence", {})
    gate = evidence.get("verified_activation_gate", {}) if isinstance(evidence, dict) else {}
    value = gate.get("signal_count")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _gate_summary(
    row: dict[str, Any],
    reviewed: dict[str, Any],
    *,
    registry: dict[str, Any],
    now: dt.datetime,
) -> dict[str, Any]:
    policy = registry.get("policy", {})
    evidence = row.get("evidence", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    gate = evidence.get("verified_activation_gate", {})
    gate = gate if isinstance(gate, dict) else {}
    min_catalog = int(policy.get("min_marketplace_catalog_count") or 500)
    min_signals = int(policy.get("min_independent_signal_types") or 2)
    review_days = int(policy.get("review_window_days") or 30)
    catalog_count = evidence.get("marketplace_catalog_count")
    official_ok = gate.get("official_ok") is True or evidence.get("official_live") is True
    market_ok = gate.get("market_ok") is True or "marketplace_depth" in (
        reviewed.get("signals") if isinstance(reviewed.get("signals"), list) else []
    )
    catalog_ok = gate.get("catalog_ok") is True or (
        isinstance(catalog_count, int)
        and not isinstance(catalog_count, bool)
        and catalog_count >= min_catalog
    )
    signal_count = _signal_count(reviewed, row)
    fresh = _fresh(
        evidence.get("last_verified_at") or evidence.get("marketplace_catalog_checked_at"),
        now,
        review_days,
    )
    missing: list[str] = []
    if not official_ok:
        missing.append("official_source")
    if not market_ok:
        missing.append("independent_market_depth")
    if not catalog_ok:
        missing.append("marketplace_catalog_depth")
    if signal_count < min_signals:
        missing.append("independent_signal_types")
    if not fresh:
        missing.append("fresh_verification")
    return {
        "official_ok": bool(official_ok),
        "market_ok": bool(market_ok),
        "catalog_ok": bool(catalog_ok),
        "signal_count": signal_count,
        "min_signal_count": min_signals,
        "fresh": bool(fresh),
        "missing": missing,
    }


def _effective_state(row: dict[str, Any], reviewed: dict[str, Any]) -> str:
    candidate = str(reviewed.get("state") or row.get("state") or WATCH_STATE)
    return candidate if candidate in ACTIVE_STATES | {WATCH_STATE} else WATCH_STATE


def build_action_plan(
    registry: dict[str, Any],
    review: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    moment = now or _now()
    reviewed_by_game = _review_map(review)
    rows = registry.get("games", [])
    active: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    refresh: list[dict[str, Any]] = []

    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        canonical = str(row.get("canonical") or row.get("id") or "")
        reviewed = reviewed_by_game.get(canonical, {})
        state = _effective_state(row, reviewed)
        capabilities = row.get("capabilities", {})
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        gate = _gate_summary(row, reviewed, registry=registry, now=moment)
        payload = {
            "id": row.get("id"),
            "canonical": canonical,
            "label_ko": row.get("label_ko") or canonical,
            "state": state,
            "activation_score": reviewed.get(
                "evidence_activation_score", row.get("activation_score", 0.0)
            ),
            "regions": list(row.get("regions", [])),
            "capabilities": {
                key: bool(capabilities.get(key))
                for key in ("market", "release", "promo", "purchase", "grading")
            },
            "gate": gate,
        }
        if state in ACTIVE_STATES:
            payload["action"] = "serve"
            active.append(payload)
            if not gate["fresh"] and state != "core":
                refresh.append({
                    "canonical": canonical,
                    "reason": "stale_verified_evidence",
                    "action": "revalidate",
                })
        else:
            payload["action"] = "observe"
            watch.append(payload)
            if gate["missing"]:
                refresh.append({
                    "canonical": canonical,
                    "reason": "missing_verified_gate",
                    "missing": gate["missing"],
                    "action": "collect_evidence",
                })

    active.sort(key=lambda item: (item["state"] != "core", -float(item["activation_score"] or 0)))
    watch.sort(key=lambda item: -float(item["activation_score"] or 0))
    refresh.sort(key=lambda item: str(item.get("canonical") or ""))

    return {
        "mode": "autonomous_declarative_review",
        "active": active,
        "watch": watch,
        "refresh_queue": refresh,
        "self_extension": {
            "allowed": True,
            "scope": "registry-backed category labels, aliases, regions, and evidence queues",
            "source_code_generation": False,
            "unverified_category_activation": False,
        },
    }


def build_report(
    root: Path = ROOT,
    *,
    persist_registry: bool = False,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    moment = now or _now()
    registry = load_registry(root)
    review = review_registry(root, now=moment, persist=persist_registry)
    if persist_registry:
        registry = load_registry(root)
    if not validate_registry(registry):
        raise ValueError("TCG_GAME_REGISTRY_INVALID")

    policy = registry["policy"]
    plan = build_action_plan(registry, review, now=moment)
    enabled = plan["active"]
    watch = plan["watch"]
    safety = {
        "registry_valid": True,
        "profit_guarantee_disabled": policy.get("profit_guarantee") is False,
        "investment_return_prediction_disabled": (
            policy.get("investment_return_prediction") is False
        ),
        "market_direction_prediction_disabled": (
            policy.get("market_direction_prediction") is False
        ),
        "source_code_auto_generation": policy.get("source_code_auto_generation") is False,
        "user_behavior_tracking_disabled": policy.get("user_behavior_tracking") is False,
        "grading_auto_enabled_for_new_games": (
            policy.get("grading_required_for_new_games") is True
        ),
        "registry_only_mutation": True,
        "physical_tablet_runtime_verified": False,
    }
    safety["all_gates_pass"] = all(
        value is True
        for key, value in safety.items()
        if key not in {"grading_auto_enabled_for_new_games"}
    )

    return {
        "schema_version": 1,
        "controller_version": VERSION,
        "observed_at": _iso(moment),
        "status": "ready" if safety["all_gates_pass"] else "blocked",
        "registry_updated_at": registry.get("updated_at"),
        "enabled_market_games": [
            item["canonical"]
            for item in enabled
            if item["capabilities"].get("market") is True
        ],
        "enabled_purchase_games": [
            item["canonical"]
            for item in enabled
            if item["capabilities"].get("purchase") is True
        ],
        "watch_games": [item["canonical"] for item in watch],
        "active_count": len(enabled),
        "watch_count": len(watch),
        "action_plan": plan,
        "review_summary": {
            "reviewed_count": len(review.get("reviewed", [])),
            "unknown_candidates": len(review.get("unknown_candidates", [])),
            "auto_watch_created_games": list(review.get("auto_watch_created_games", [])),
            "retired_auto_watch_games": list(review.get("retired_auto_watch_games", [])),
            "activation_score_uses_verified_evidence": (
                review.get("activation_score_uses_verified_evidence") is True
            ),
            "activation_score_uses_price_direction": (
                review.get("activation_score_uses_price_direction") is True
            ),
            "activation_score_uses_profit_prediction": (
                review.get("activation_score_uses_profit_prediction") is True
            ),
        },
        "neural_controller": {
            "active": False,
            "mode": "routing_only",
            "minimum_independent_labels": MIN_INDEPENDENT_LABELS,
            "promotion_allowed": False,
            "reason": (
                "독립 라벨 게이트가 충족되기 전에는 신경망이 카테고리 "
                "활성화·수익·가격 방향을 결정하지 않습니다."
            ),
        },
        "safety_gates": safety,
        "physical_device_note": (
            "이 보고서는 코드·레지스트리 검증 결과입니다. 실제 Lenovo/Termux "
            "태블릿 화면·설치·부팅은 별도 현장 검증이 필요합니다."
        ),
    }


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tablet TCG category autonomy controller")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("status", "review", "verify"),
        default="status",
    )
    parser.add_argument(
        "--persist-registry",
        action="store_true",
        help="검증된 review 결과로 registry JSON의 상태만 갱신",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="검토 보고서를 tcg_category_autonomy_v424_report.json에 저장",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_report(ROOT, persist_registry=args.persist_registry)
    except Exception as exc:  # fail closed for the tablet command surface
        error = {
            "schema_version": 1,
            "controller_version": VERSION,
            "status": "blocked",
            "error": type(exc).__name__,
            "message": str(exc),
            "source_code_modified": False,
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 2

    if args.write_report:
        write_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ready" else 2 if args.command == "verify" else 0


if __name__ == "__main__":
    sys.exit(main())
