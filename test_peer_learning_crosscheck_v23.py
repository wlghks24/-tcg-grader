#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import daily_collection_instagram_accuracy as daily
import main_peer_learning_adoption as adoption
import peer_learning_crosscheck_gate as gate
from shared_self_learning.peer_learning import (
    PEER_LEARNING_FIELDS,
    compare_learning_sets,
    evaluate_main_peer_adoption,
    normalize_peer_lesson,
)


def lesson(
    lesson_id: str,
    *,
    fix: str = "switch to verified alternate source/parser",
    scope: str = "both",
    regression_pass: bool = True,
    verification_result: str = "passed",
) -> dict:
    return {
        "lesson_id": lesson_id,
        "subsystem": "source_parser",
        "issue_class": "empty_parse",
        "trigger_condition": "HTTP 200 but zero usable rows",
        "symptom_summary": "page shell parsed without card rows",
        "root_cause_class": "dynamic_page_shell",
        "fix_pattern": fix,
        "prevention_rule_id": f"RULE-{lesson_id}",
        "verification_result": verification_result,
        "regression_pass": regression_pass,
        "recurrence_count": 2,
        "applicable_scope": scope,
        "confidence_level": "high",
    }


class PeerLearningCrosscheckV23Tests(unittest.TestCase):
    def test_exact_learning_allowlist_only(self):
        row = normalize_peer_lesson("main", lesson("MAIN-1"))
        self.assertEqual(tuple(row), PEER_LEARNING_FIELDS)
        self.assertEqual(set(row), set(PEER_LEARNING_FIELDS))

    def test_raw_internal_state_is_rejected_fail_closed(self):
        forbidden = (
            "raw_log",
            "parser_state",
            "retry_queue",
            "source_health",
            "baseline",
            "ranking_weights",
            "confidence_tuning",
            "grading_raw",
            "grading_calibration",
            "pixel_features",
            "rendering_state",
            "upload_state",
            "delivery_state",
        )
        for field in forbidden:
            with self.subTest(field=field):
                row = lesson("MAIN-X")
                row[field] = {"secret": True}
                with self.assertRaises(ValueError):
                    normalize_peer_lesson("main", row)

    def test_four_crosscheck_statuses(self):
        main = lesson("MAIN-A")
        insta = lesson("IG-A")
        result = compare_learning_sets([main], [insta])
        self.assertEqual(result["counts"]["corroborated"], 1)

        result = compare_learning_sets([main], [lesson("IG-B", fix="quarantine and use alternate API")])
        self.assertEqual(result["counts"]["conflicting-fix"], 1)

        result = compare_learning_sets([lesson("MAIN-ONLY")], [])
        self.assertEqual(result["counts"]["single-system-only"], 1)

        design = lesson("IG-DESIGN", scope="instagram_content")
        design.update({
            "subsystem": "renderer",
            "issue_class": "text_clip",
            "trigger_condition": "mobile export",
            "root_cause_class": "layout_overflow",
            "fix_pattern": "reduce font size",
        })
        result = compare_learning_sets([], [design])
        self.assertEqual(result["counts"]["not-applicable"], 1)

    def test_peer_fix_never_auto_applies(self):
        result = compare_learning_sets([lesson("MAIN-A")], [lesson("IG-A")])
        row = result["comparisons"][0]
        self.assertFalse(row["peer_fix_auto_apply"])
        self.assertFalse(row["prevention_rule_shared"])
        self.assertFalse(row["raw_state_shared"])

    def test_main_adoption_requires_all_five_gates(self):
        peer = lesson("IG-A")
        names = (
            "reproduction_pass",
            "root_cause_reconfirmed",
            "minimal_scope_fix",
            "local_regression_pass",
            "full_regression_pass",
        )
        base = {name: True for name in names}
        for name in names:
            with self.subTest(name=name):
                flags = dict(base)
                flags[name] = False
                result = evaluate_main_peer_adoption(peer, **flags)
                self.assertFalse(result["adoption_allowed"])

        result = evaluate_main_peer_adoption(peer, **base)
        self.assertTrue(result["adoption_allowed"])
        rule = result["local_prevention_rule"]
        self.assertEqual(rule["learned_from_peer"], "IG-A")
        self.assertNotEqual(rule["prevention_rule_id"], peer["prevention_rule_id"])
        self.assertNotIn("peer_prevention_rule_id", rule)

    def test_conflicting_fix_requires_safer_local_selection(self):
        peer = lesson("IG-CONFLICT")
        flags = {
            "reproduction_pass": True,
            "root_cause_reconfirmed": True,
            "minimal_scope_fix": True,
            "local_regression_pass": True,
            "full_regression_pass": True,
            "crosscheck_status": "conflicting-fix",
        }
        self.assertFalse(evaluate_main_peer_adoption(peer, safer_fix_selected=False, **flags)["adoption_allowed"])
        self.assertTrue(evaluate_main_peer_adoption(peer, safer_fix_selected=True, **flags)["adoption_allowed"])

    def test_main_persistence_is_local_and_never_copies_peer_rule(self):
        peer = lesson("IG-PERSIST")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MARKET_ANALYSIS_PEER_PREVENTION_RULES.json"
            result = adoption.adopt_peer_lesson(
                peer,
                reproduction_pass=True,
                root_cause_reconfirmed=True,
                minimal_scope_fix=True,
                local_regression_pass=True,
                full_regression_pass=True,
                state_path=path,
            )
            self.assertTrue(result["adoption_allowed"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            rule = payload["rules"][0]
            self.assertEqual(rule["learned_from_peer"], "IG-PERSIST")
            self.assertNotEqual(rule["prevention_rule_id"], peer["prevention_rule_id"])
            self.assertNotIn("prevention_rule", rule)
            self.assertNotIn("raw_log", rule)

    def test_not_applicable_peer_can_never_be_adopted(self):
        peer = lesson("IG-NA", scope="both")
        result = evaluate_main_peer_adoption(
            peer,
            reproduction_pass=True,
            root_cause_reconfirmed=True,
            minimal_scope_fix=True,
            local_regression_pass=True,
            full_regression_pass=True,
            crosscheck_status="not-applicable",
        )
        self.assertFalse(result["adoption_allowed"])
        self.assertFalse(result["status_eligible"])
        self.assertIsNone(result["local_prevention_rule"])

    def test_conflicting_fix_requires_explicit_selected_fix_pattern(self):
        peer = lesson("IG-CONFLICT-EXPLICIT")
        flags = {
            "reproduction_pass": True,
            "root_cause_reconfirmed": True,
            "minimal_scope_fix": True,
            "local_regression_pass": True,
            "full_regression_pass": True,
            "crosscheck_status": "conflicting-fix",
            "safer_fix_selected": True,
        }
        blocked = evaluate_main_peer_adoption(peer, **flags)
        self.assertFalse(blocked["adoption_allowed"])
        self.assertFalse(blocked["selected_fix_explicit"])
        allowed = evaluate_main_peer_adoption(
            peer,
            selected_fix_pattern="locally validated alternate parser with fail-closed empty-row detection",
            **flags,
        )
        self.assertTrue(allowed["adoption_allowed"])
        self.assertTrue(allowed["selected_fix_explicit"])
        self.assertEqual(
            allowed["local_prevention_rule"]["fix_pattern"],
            "locally validated alternate parser with fail-closed empty-row detection",
        )

    def test_renderer_peer_lesson_is_not_applicable_to_main_even_when_scope_claims_both(self):
        peer = lesson("IG-RENDER", scope="both")
        peer.update({
            "subsystem": "renderer",
            "issue_class": "text_clip",
            "trigger_condition": "mobile export",
            "root_cause_class": "layout_overflow",
            "fix_pattern": "reduce font size",
        })
        result = evaluate_main_peer_adoption(
            peer,
            reproduction_pass=True,
            root_cause_reconfirmed=True,
            minimal_scope_fix=True,
            local_regression_pass=True,
            full_regression_pass=True,
        )
        self.assertFalse(result["applicable_to_main"])
        self.assertFalse(result["adoption_allowed"])

    def test_nested_container_cannot_leak_raw_state_through_summary_field(self):
        row = lesson("MAIN-NESTED")
        row["symptom_summary"] = {"raw_log": "secret full log"}
        with self.assertRaises(TypeError):
            normalize_peer_lesson("main", row)

    def test_snapshot_rejects_extra_learning_fields_fail_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as tmp:
            path = Path(tmp) / "runtime-main-learning.json"
            row = lesson("MAIN-EXTRA")
            row["created_at"] = "2026-09-05T00:00:00Z"
            path.write_text(
                json.dumps({"domain": "main", "kind": "learning_summary", "lessons": [row]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                gate._load_lessons(path, "main")

    def test_snapshot_rejects_extra_envelope_fields_fail_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as tmp:
            path = Path(tmp) / "runtime-main-learning.json"
            path.write_text(
                json.dumps({
                    "domain": "main",
                    "kind": "learning_summary",
                    "lessons": [lesson("MAIN-ENV")],
                    "source_health": {"hidden": True},
                }),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                gate._load_lessons(path, "main")

    def test_crosscheck_gate_rejects_wrong_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "learning.json"
            outside.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                gate._load_lessons(outside, "main")

    def test_daily_0600_report_includes_learning_crosscheck(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as tmp:
            root = Path(tmp)
            main_path = root / "runtime-main-learning.json"
            insta_path = root / "runtime-instagram-learning.json"
            main_path.write_text(
                json.dumps(
                    {"domain": "main", "kind": "learning_summary", "lessons": [lesson("MAIN-A")]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            insta_path.write_text(
                json.dumps(
                    {"domain": "instagram_content", "kind": "learning_summary", "lessons": [lesson("IG-A")]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = daily.audit_peer_learning(main_path, insta_path)
            self.assertEqual(result["status"], "crosschecked")
            self.assertEqual(result["counts"]["corroborated"], 1)
            self.assertFalse(result["peer_fix_auto_apply"])
            self.assertFalse(result["prevention_rule_shared"])
            self.assertFalse(result["raw_state_shared"])


if __name__ == "__main__":
    unittest.main()
