#!/usr/bin/env python3
"""Offline capability triage for third-party research/trading/browser designs.

Scope: TCG_GRADER. This is an advisory gate, not a product feature or security
sandbox. No third-party code, network calls, browser, broker or LLM executes.
"""
from __future__ import annotations

import argparse
import json

PROJECT = "TCG_GRADER"
UPSTREAM = {
    "fincept": {"url": "https://github.com/Fincept-Corporation/FinceptTerminal",
                "license": "AGPL-3.0-or-later", "verified_code_installed": False},
    "vibe": {"url": "https://github.com/HKUDS/Vibe-Trading",
             "license": "MIT", "verified_code_installed": False},
    "camofox": {"url": "https://github.com/jo-inc/camofox-browser",
                "license": "MIT", "verified_code_installed": False},
}
BLOCKED = {
    "live_trade", "broker_order", "automatic_buy_sell", "bypass_access_controls",
    "evade_bot_protection", "import_browser_cookies", "steal_credentials",
    "copy_upstream_source", "unattended_system_patch", "cloud_training",
}
# Use only the concepts that actually belong to this domain; finance is not
# transplanted into the car or card-grading business.
ALLOWABLE = {
    "TCG_GRADER": {
        "fincept": {"evidence_dashboard_pattern", "source_provenance_layout"},
        "vibe": {"independent_review_pattern", "offline_scenario_comparison"},
        "camofox": {"owned_local_ui_snapshot"},
    },
    "VEHICLE_AIO": {
        "fincept": set(),
        "vibe": set(),
        "camofox": {"owned_local_ui_snapshot"},
    },
}


def assess(tool: str, capability: str, *, source: str, requires_payment: bool = False) -> dict:
    """Fail closed; concepts are never executable permissions."""
    if not isinstance(tool, str) or not isinstance(capability, str) or not isinstance(source, str):
        raise ValueError("invalid_field_type")
    if type(requires_payment) is not bool:
        raise ValueError("invalid_cost_flag")
    if tool not in UPSTREAM or not capability or len(capability) > 80:
        raise ValueError("unknown_tool_or_capability")
    item = UPSTREAM[tool]
    if source != item["url"]:
        state, reason = "HOLD", "unverified_source_url"
    elif capability in BLOCKED:
        state, reason = "BLOCK", "not_permitted_by_project_contract"
    elif requires_payment:
        state, reason = "HOLD", "free_only_boundary"
    elif capability in ALLOWABLE[PROJECT][tool]:
        state, reason = "CONCEPT_ONLY", "pattern_only_not_installed"
    else:
        state, reason = "HOLD", "not_supported_in_this_project"
    return {
        "schema": "third_party_capability_triage_v1",
        "project": PROJECT,
        "tool": tool,
        "license": item["license"],
        "capability": capability,
        "decision": state,
        "reason": reason,
        "upstream_code_installed": False,
        "runtime_verified": False,
        "requires_human_review": True,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tool", required=True, choices=sorted(UPSTREAM))
    p.add_argument("--capability", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--requires-payment", action="store_true")
    args = p.parse_args()
    print(json.dumps(assess(args.tool, args.capability, source=args.source,
                            requires_payment=args.requires_payment),
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
