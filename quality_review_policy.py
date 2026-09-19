#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "quality_review_policy_v2.json"
REQUIRED_GROUP_TERMS = ("통역사", "회장", "프로그래머", "시니어 개발자", "SRE", "TCG", "Android", "감사")
REQUIRED_GATES = {"architecture", "implementation_correctness", "security", "sre_recovery", "performance", "release_qa"}
REQUIRED_ORDER = ["targeted_tests", "full_regression", "actual_output_validation"]
REQUIRED_RCA = ["failure_hypotheses", "reproduction", "call_path", "state_changes", "failure_point", "root_cause"]
REQUIRED_PREP_WORKFLOW = [
    "DISCOVER", "FETCH", "PARSE", "NORMALIZE", "DEDUP", "TYPO_IDENTITY_CHECK",
    "FRESHNESS_CHECK", "SOURCE_INDEPENDENCE_CHECK", "CROSSCHECK",
    "CONTRARY_EVIDENCE_CHECK", "CONFLICT_CHECK", "GAP_ANALYSIS",
    "SUPPLEMENTAL_COLLECTION", "PREPARED_DATASET",
]
REQUIRED_PIPELINE = [
    "100_senior_data_prep",
    "1000_expert_multi_lens_review",
    "targeted_tests",
    "full_regression",
    "actual_output_validation",
    "release_or_hold",
]
FALSE_SAFETY = {
    "direct_main_push_allowed",
    "force_push_allowed",
    "unsafe_reset_clean_allowed",
    "bypass_403_429_allowed",
    "arbitrary_allowlist_expansion_allowed",
    "learned_text_executable",
    "automatic_source_rewrite",
    "degraded_may_be_reported_as_success",
    "unverified_data_auto_promotion",
    "blocker_can_be_outvoted",
}
TRUE_TABLET = {
    "single_main_entrypoint",
    "policy_validation_fail_closed",
    "prep_policy_validation_fail_closed",
    "candidate_preflight_required",
    "ff_only_update_required",
    "final_verification_required",
}
REQUIRED_PREP_TRUE_RULES = {
    "supplement_missing_data_from_independent_paths",
    "correct_typos_against_source",
    "cross_validate_all_material_facts",
    "preserve_provenance",
    "preserve_freshness",
    "unresolved_conflict_must_hold",
}
REQUIRED_PREP_FALSE_RULES = {
    "same_origin_reposts_count_as_independent_sources",
    "bypass_blocked_sources_allowed",
    "degraded_may_be_reported_as_success",
}


def validate(path: Path = POLICY) -> dict:
    errors: list[str] = []
    if path.is_symlink():
        return {"ok": False, "errors": ["policy_symlink_forbidden"]}
    if not path.is_file():
        return {"ok": False, "errors": ["policy_missing"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"ok": False, "errors": ["policy_unreadable"]}

    prep = data.get("preparation_stage") if isinstance(data.get("preparation_stage"), dict) else {}
    prep_rules = prep.get("rules") if isinstance(prep.get("rules"), dict) else {}
    groups = data.get("expert_groups") if isinstance(data.get("expert_groups"), list) else []
    lenses = data.get("review_lenses") if isinstance(data.get("review_lenses"), list) else []
    group_ids = [x.get("id") for x in groups if isinstance(x, dict)]
    lens_ids = [x.get("id") for x in lenses if isinstance(x, dict)]
    names = " ".join(str(x.get("name", "")) for x in groups if isinstance(x, dict))

    if data.get("schema_version") != 2: errors.append("schema_version")

    if prep.get("independent_senior_perspectives") != 100: errors.append("prep_senior_count")
    if prep.get("separate_from_expert_review") is not True: errors.append("prep_separation")
    if prep.get("must_run_before_expert_review") is not True: errors.append("prep_order_contract")
    if prep.get("final_judgment_authority") is not False: errors.append("prep_final_authority")
    if prep.get("claim_external_human_team") is not False: errors.append("prep_truthful_claim")
    if prep.get("workflow") != REQUIRED_PREP_WORKFLOW: errors.append("prep_workflow")
    if any(prep_rules.get(k) is not True for k in REQUIRED_PREP_TRUE_RULES): errors.append("prep_rules")
    if any(prep_rules.get(k) is not False for k in REQUIRED_PREP_FALSE_RULES): errors.append("prep_rules")
    if data.get("quality_pipeline") != REQUIRED_PIPELINE: errors.append("quality_pipeline")

    if data.get("expert_group_count") != 25 or len(groups) != 25: errors.append("expert_group_count")
    if data.get("review_lens_count") != 40 or len(lenses) != 40: errors.append("review_lens_count")
    if group_ids != list(range(1, 26)) or len(set(group_ids)) != 25: errors.append("expert_group_ids")
    if lens_ids != list(range(1, 41)) or len(set(lens_ids)) != 40: errors.append("review_lens_ids")
    cells = len(groups) * len(lenses)
    if data.get("expected_review_cells") != 1000 or cells != 1000: errors.append("review_cells")
    if any(term not in names for term in REQUIRED_GROUP_TERMS): errors.append("required_expert_domains")
    if set(data.get("required_gates") or []) != REQUIRED_GATES: errors.append("required_gates")
    if data.get("verification_order") != REQUIRED_ORDER: errors.append("verification_order")
    if data.get("rca_order") != REQUIRED_RCA: errors.append("rca_order")

    safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}
    if any(safety.get(k) is not False for k in FALSE_SAFETY): errors.append("safety_contract")
    tablet = data.get("tablet") if isinstance(data.get("tablet"), dict) else {}
    if any(tablet.get(k) is not True for k in TRUE_TABLET): errors.append("tablet_contract")
    if tablet.get("claim_parallel_1000_external_reviewers") is not False: errors.append("truthful_claim")
    if tablet.get("claim_parallel_100_external_collectors") is not False: errors.append("prep_truthful_claim")

    return {
        "ok": not errors,
        "schema_version": data.get("schema_version"),
        "preparation_senior_perspectives": prep.get("independent_senior_perspectives", 0),
        "preparation_before_expert_review": prep.get("must_run_before_expert_review") is True,
        "expert_groups": len(groups),
        "review_lenses": len(lenses),
        "review_cells": cells,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--policy", type=Path, default=POLICY)
    args = parser.parse_args()
    result = validate(args.policy)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
