import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v379 as v379


def ready_quality():
    return {
        "ok": True,
        "status": "QUALITY_100_1000_READY",
        "preparation_senior_perspectives": 100,
        "review_cells": 1000,
    }


def lesson(lesson_id, *, fix="use verified alternate parser", scope="both", verified=True):
    return {
        "lesson_id": lesson_id,
        "subsystem": "source_parser",
        "issue_class": "empty_parse",
        "trigger_condition": "HTTP 200 but zero usable rows",
        "symptom_summary": "verified summary only",
        "root_cause_class": "dynamic_page_shell",
        "fix_pattern": fix,
        "prevention_rule_id": f"RULE-{lesson_id}",
        "verification_result": "passed" if verified else "review",
        "regression_pass": bool(verified),
        "recurrence_count": 1,
        "applicable_scope": scope,
        "confidence_level": "high",
    }


def write_exchange(root: Path, main_rows, peer_rows):
    exchange = root / "crosscheck_exchange"
    exchange.mkdir(parents=True, exist_ok=True)
    (exchange / "runtime-main-learning.json").write_text(
        json.dumps({"domain": "main", "kind": "learning_summary", "lessons": main_rows}),
        encoding="utf-8",
    )
    (exchange / "runtime-instagram-learning.json").write_text(
        json.dumps({"domain": "instagram_content", "kind": "learning_summary", "lessons": peer_rows}),
        encoding="utf-8",
    )


def core_result(status="V376_EXECUTED"):
    return {
        "controller_version": "v378",
        "v378_status": status,
        "execution": {"status": status, "executed": status == "V376_EXECUTED"},
        "quality_governance": ready_quality(),
        "neural_council": {
            "advisory_only": True,
            "members": [
                {"id": "query_strategy", "score": 0.9, "verified_runtime_signal": True},
                {"id": "meta_neural_reliability", "score": 0.8, "verified_runtime_signal": True},
            ],
            "confidence": 0.85,
            "agreement": 0.9,
            "readiness": "HIGH",
        },
        "adaptive_mode": {"mode": "STEADY_VERIFIED_EVOLUTION", "market_direction_inferred": False},
        "improvement_queue": [],
        "evolution_contract": {
            "runtime_self_added_functions": "allowlisted_declarative_capabilities_only",
            "source_level_new_functions": "proposal_only_pr_ci_required",
            "market_direction_prediction": False,
        },
    }


class TabletAutonomousEvolutionV379Tests(unittest.TestCase):
    def test_conflicting_exchange_blocks_mutation_before_v378(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v379.v378, "quality_governance", return_value=ready_quality()
        ), mock.patch.object(v379.v378, "run_cycle") as core:
            root = Path(td)
            write_exchange(
                root,
                [lesson("MAIN-C", fix="use parser A")],
                [lesson("PEER-C", fix="use parser B")],
            )
            result = v379.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=root, persist_outputs=False,
            )
            core.assert_not_called()
            self.assertEqual("EXCHANGE_CONFLICT_HOLD", result["v379_status"])
            self.assertFalse(result["execution"]["executed"])
            self.assertFalse(result["information_exchange_manager"]["mutation_allowed"])
            self.assertFalse(result["safety"]["peer_fix_auto_apply"])

    def test_invalid_exchange_extra_field_fails_closed(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v379.v378, "quality_governance", return_value=ready_quality()
        ), mock.patch.object(v379.v378, "run_cycle") as core:
            root = Path(td)
            write_exchange(root, [lesson("MAIN-X")], [lesson("PEER-X")])
            path = root / "crosscheck_exchange" / "runtime-main-learning.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["lessons"][0]["raw_log"] = "forbidden"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = v379.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=root, persist_outputs=False,
            )
            core.assert_not_called()
            self.assertEqual("EXCHANGE_INTEGRITY_HOLD", result["v379_status"])
            self.assertIn("EXCHANGE_LESSON_FIELDS_MISMATCH", result["information_exchange_manager"]["error_codes"])

    def test_single_system_evidence_requires_reproduction_but_local_autonomy_can_continue(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v379.v378, "quality_governance", return_value=ready_quality()
        ), mock.patch.object(v379.v378, "run_cycle", return_value=core_result()) as core:
            root = Path(td)
            write_exchange(root, [lesson("MAIN-ONLY")], [])
            result = v379.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=root, persist_outputs=False,
            )
            core.assert_called_once()
            manager = result["information_exchange_manager"]
            self.assertEqual("EXCHANGE_REPRODUCTION_REQUIRED", manager["status"])
            self.assertTrue(manager["mutation_allowed"])
            self.assertFalse(manager["peer_influence_allowed"])
            self.assertTrue(manager["safety"]["independent_reproduction_required"])
            self.assertFalse(manager["safety"]["peer_fix_auto_apply"])
            self.assertEqual("REPRODUCE_PEER_LESSONS_LOCALLY", result["improvement_queue"][0]["id"])

    def test_corroborated_exchange_enters_advisory_council_only(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v379.v378, "quality_governance", return_value=ready_quality()
        ), mock.patch.object(v379.v378, "run_cycle", return_value=core_result()) as core:
            root = Path(td)
            write_exchange(root, [lesson("MAIN-A")], [lesson("PEER-A")])
            result = v379.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=root, persist_outputs=False,
            )
            core.assert_called_once()
            manager = result["information_exchange_manager"]
            self.assertEqual("EXCHANGE_CORROBORATED", manager["status"])
            self.assertTrue(manager["peer_influence_allowed"])
            council = result["information_exchange_neural_council"]
            exchange_member = next(row for row in council["members"] if row["id"] == "information_exchange_governance")
            self.assertTrue(exchange_member["validated_exchange_signal"])
            self.assertFalse(exchange_member["verified_runtime_signal"])
            self.assertFalse(council["peer_content_direct_model_training"])
            self.assertFalse(result["evolution_contract"]["information_exchange_peer_fix_auto_apply"])

    def test_missing_exchange_uses_local_verified_only(self):
        with tempfile.TemporaryDirectory() as td:
            result = v379.information_exchange_manager(Path(td))
            self.assertEqual("EXCHANGE_UNAVAILABLE", result["status"])
            self.assertTrue(result["mutation_allowed"])
            self.assertFalse(result["peer_influence_allowed"])
            self.assertEqual("LOCAL_VERIFIED_ONLY", result["selected_management_action"])

    def test_exchange_change_during_decision_holds_before_core_mutation(self):
        first = {
            "status": "EXCHANGE_CORROBORATED",
            "mutation_allowed": True,
            "peer_influence_allowed": True,
            "selected_management_action": "OBSERVE_CORROBORATED_PATTERNS",
            "counts": {"corroborated": 1, "single-system-only": 0, "conflicting-fix": 0, "not-applicable": 0},
            "store_status": {"main": "loaded", "peer": "loaded"},
            "error_codes": [],
            "signal_score": 0.85,
            "input_digest": "a" * 64,
            "safety": {"peer_fix_auto_apply": False},
        }
        second = dict(first, input_digest="b" * 64)
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v379, "information_exchange_manager", side_effect=[first, second]
        ), mock.patch.object(
            v379.v378, "quality_governance", return_value=ready_quality()
        ), mock.patch.object(v379.v378, "run_cycle") as core:
            result = v379.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), persist_outputs=False,
            )
            core.assert_not_called()
            self.assertEqual("EXCHANGE_CHANGED_DURING_DECISION_HOLD", result["v379_status"])
            self.assertFalse(result["execution"]["executed"])

    def test_invalid_quality_still_uses_v378_quality_fail_closed(self):
        exchange = {
            "status": "EXCHANGE_UNAVAILABLE",
            "mutation_allowed": True,
            "peer_influence_allowed": False,
            "selected_management_action": "LOCAL_VERIFIED_ONLY",
            "counts": {"corroborated": 0, "single-system-only": 0, "conflicting-fix": 0, "not-applicable": 0},
            "store_status": {"main": "missing", "peer": "missing"},
            "error_codes": [],
            "signal_score": 0.3,
            "input_digest": "a" * 64,
            "safety": {"peer_fix_auto_apply": False},
        }
        quality = {"ok": False, "status": "QUALITY_GOVERNANCE_HOLD"}
        held = core_result("QUALITY_GOVERNANCE_HOLD")
        held["execution"] = {"status": "QUALITY_GOVERNANCE_HOLD", "executed": False}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            v379, "information_exchange_manager", return_value=exchange
        ), mock.patch.object(
            v379.v378, "quality_governance", return_value=quality
        ), mock.patch.object(v379.v378, "run_cycle", return_value=held) as core:
            result = v379.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), persist_outputs=False,
            )
            core.assert_called_once()
            self.assertEqual("QUALITY_GOVERNANCE_HOLD", result["v379_status"])

    def test_self_test_contract(self):
        v379.self_test()
        self.assertTrue(v379.SAFETY["information_exchange_manager_enabled"])
        self.assertTrue(v379.SAFETY["information_exchange_conflict_blocks_mutation"])
        self.assertFalse(v379.SAFETY["peer_fix_auto_apply"])
        self.assertFalse(v379.SAFETY["git_write"])
        self.assertFalse(v379.SAFETY["verification_bypass"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
