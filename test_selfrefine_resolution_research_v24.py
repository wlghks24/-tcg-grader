#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import selfrefine_resolution_research as research
import verified_code_repair_rules as repairs


class SelfrefineResolutionResearchV24Tests(unittest.TestCase):
    def _issue(self) -> dict:
        return {
            "error_signature": "a" * 20,
            "error_code": "SELFREFINE.PYTHON_SYNTAX",
            "stage": "PYTHON_SYNTAX",
            "path": "broken.py",
            "root_cause": "SyntaxError",
            "evidence": "unexpected token at line 1",
            "state": "open",
        }

    def _repo(self, root: Path) -> None:
        (root / "broken.py").write_text("x = (\n", encoding="utf-8")
        (root / "consumer.py").write_text("import broken\n", encoding="utf-8")
        (root / "test_broken.py").write_text(
            "import broken\n# broken.py regression\n", encoding="utf-8"
        )
        (root / "top.py").write_text("import consumer\n", encoding="utf-8")
        (root / "unrelated.py").write_text("value = 1\n", encoding="utf-8")

    def _repair_issue(self) -> dict:
        return {
            "error_signature": "b" * 20,
            "error_code": "SELFREFINE.RESOURCE_HANDLE_LEAK_RISK",
            "stage": "RESOURCE_HANDLE_LEAK_RISK",
            "path": repairs.RESOURCE_GUARD_PATH,
            "root_cause": "unclosed literal text read",
            "evidence": "open(...).read() can leave a file handle",
            "state": "open",
        }

    def _prepare_verified_repair(
        self,
        root: Path,
        state: Path,
        report: Path,
        *,
        rollback_outcome: str = "verified_kept",
    ):
        target = root / repairs.RESOURCE_GUARD_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "from pathlib import Path\n"
            "x = Path('a.js').read_text(encoding='utf-8')\n",
            encoding="utf-8",
        )
        issue = self._repair_issue()
        research.observe_errors(
            [issue],
            root=root,
            state_path=state,
            report_path=report,
            network_research=False,
        )
        applied = {
            "error_signature": issue["error_signature"],
            "rule_id": repairs.RESOURCE_RULE_ID,
            "rule_fingerprint": repairs.rule_fingerprint(repairs.RESOURCE_RULE_ID),
            "path": repairs.RESOURCE_GUARD_PATH,
            "stage": "RESOURCE_HANDLE_LEAK_RISK",
            "before_hash": research._text_hash("old content"),
            "after_hash": research._text_hash(target.read_text(encoding="utf-8")),
            "rollback_outcome": rollback_outcome,
        }
        return issue, applied, target

    def test_new_error_scans_repository_and_builds_official_research_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            result = research.observe_errors(
                [self._issue()], root=root, state_path=state, report_path=report,
                network_research=False,
            )
            self.assertEqual(result["new_error_count"], 1)
            self.assertTrue(result["full_repository_scan"])
            self.assertGreaterEqual(result["repository_files_scanned"], 4)
            row = result["errors"][0]
            impacted = {
                item["path"] for item in row["impact_analysis"]["impacted_files"]
            }
            self.assertTrue(
                {"broken.py", "consumer.py", "test_broken.py", "top.py"}.issubset(
                    impacted
                ),
                impacted,
            )
            top = next(
                item
                for item in row["impact_analysis"]["impacted_files"]
                if item["path"] == "top.py"
            )
            self.assertIn("transitive_python_dependency", top["reasons"])
            self.assertEqual(top["dependency_depth"], 2)
            self.assertTrue(
                row["impact_analysis"]["python_transitive_dependency_analysis"]
            )
            self.assertEqual(row["research"]["research_family"], "python")
            self.assertTrue(all(
                source.startswith("https://")
                for source in row["research"]["preferred_sources"]
            ))
            self.assertFalse(row["research"]["research_text_executable"])
            self.assertFalse(row["research"]["patch_from_search_text_allowed"])

    def test_research_does_not_learn_before_full_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            staged = research.stage_repairs([applied], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 1)
            self.assertEqual(staged["skipped_unverified_repairs"], 0)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["lessons"], {})
            pending = payload["pending_verifications"][issue["error_signature"]]
            self.assertEqual(
                pending["verification_status"], "pending_full_regression"
            )
            self.assertEqual(pending["after_hash"], applied["after_hash"])
            self.assertEqual(
                payload["issues"][issue["error_signature"]]["status"],
                "pending_full_regression",
            )

    def test_successful_full_regression_becomes_reusable_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            staged = research.stage_repairs([applied], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 1)

            result = research.finalize_pending(
                True, state_path=state, root=root
            )
            self.assertEqual(result["verified_resolution_lessons"], 1)
            self.assertEqual(result["binding_rejected_resolutions"], 0)

            payload = json.loads(state.read_text(encoding="utf-8"))
            lesson = payload["lessons"][issue["error_signature"]]
            self.assertTrue(lesson["regression_pass"])
            self.assertEqual(
                lesson["verification_result"], "full_regression_passed"
            )
            self.assertEqual(
                lesson["fix_pattern"],
                f"verified_code_rule:{repairs.RESOURCE_RULE_ID}",
            )

            observed = research.observe_errors(
                [issue], root=root, state_path=state, report_path=report,
                network_research=False,
            )
            self.assertTrue(
                observed["errors"][0]["known_verified_resolution"]
            )
            self.assertEqual(
                observed["errors"][0]["preferred_verified_fix_pattern"],
                f"verified_code_rule:{repairs.RESOURCE_RULE_ID}",
            )

    def test_failed_full_regression_is_not_promoted_to_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            staged = research.stage_repairs([applied], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 1)
            result = research.finalize_pending(
                False, state_path=state, root=root
            )
            self.assertEqual(result["verified_resolution_lessons"], 0)
            self.assertEqual(result["rejected_unverified_resolutions"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertNotIn(issue["error_signature"], payload["lessons"])
            self.assertEqual(
                payload["issues"][issue["error_signature"]]["status"],
                "full_regression_not_passed",
            )

    def test_official_lookup_dns_failure_is_deferred_not_fatal(self):
        plan = research.research_plan(self._issue())
        with mock.patch.object(
            research,
            "require_public_https",
            side_effect=urllib.error.URLError("offline"),
        ):
            result = research.search_official_sources(plan, request_limit=1)
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["successful"], 0)
        self.assertEqual(result["status"], "deferred")
        self.assertEqual(result["results"][0]["error_type"], "URLError")
        self.assertFalse(result["content_used_for_patch"])
        self.assertFalse(result["search_result_patch_generation"])
        self.assertFalse(result["raw_body_persisted"])

    def test_network_research_runs_only_for_first_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            fake = {
                "attempted": 1,
                "successful": 1,
                "status": "researched",
                "results": [{
                    "host": "docs.python.org",
                    "http_status": 200,
                    "title": "Python Documentation",
                    "content_type": "text/html",
                    "bytes_sampled": 128,
                    "status": "reachable",
                }],
                "content_used_for_patch": False,
                "search_result_patch_generation": False,
                "raw_body_persisted": False,
            }
            with mock.patch.object(
                research, "search_official_sources", return_value=fake
            ) as lookup:
                first = research.observe_errors(
                    [self._issue()],
                    root=root,
                    state_path=state,
                    report_path=report,
                    network_research=True,
                )
                second = research.observe_errors(
                    [self._issue()],
                    root=root,
                    state_path=state,
                    report_path=report,
                    network_research=True,
                )
            self.assertEqual(lookup.call_count, 1)
            self.assertEqual(first["network_research_attempted"], 1)
            self.assertEqual(second["network_research_attempted"], 0)
            self.assertEqual(
                second["errors"][0]["network_research"]["status"],
                "not_required",
            )
            self.assertEqual(second["errors"][0]["recurrence_count"], 2)

    def test_rolled_back_repair_is_never_staged_for_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root,
                state,
                report,
                rollback_outcome="restored_after_failed_verification",
            )
            staged = research.stage_repairs([applied], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 0)
            self.assertEqual(staged["skipped_unverified_repairs"], 1)
            self.assertEqual(
                staged["skip_reasons"]["repair_not_locally_verified"], 1
            )
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertNotIn(
                issue["error_signature"], payload["pending_verifications"]
            )

    def test_changed_target_hash_cannot_be_promoted_by_later_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, target = self._prepare_verified_repair(
                root, state, report
            )
            research.stage_repairs([applied], state_path=state)
            target.write_text("changed after staging\n", encoding="utf-8")
            result = research.finalize_pending(
                True, state_path=state, root=root
            )
            self.assertEqual(result["verified_resolution_lessons"], 0)
            self.assertEqual(result["binding_rejected_resolutions"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertNotIn(issue["error_signature"], payload["lessons"])
            self.assertEqual(
                payload["issues"][issue["error_signature"]][
                    "last_verification_rejection"
                ],
                "repair_target_hash_changed",
            )

    def test_expired_pending_resolution_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            research.stage_repairs([applied], state_path=state)
            payload = json.loads(state.read_text(encoding="utf-8"))
            payload["pending_verifications"][issue["error_signature"]][
                "staged_at"
            ] = "2020-01-01T00:00:00+00:00"
            state.write_text(json.dumps(payload), encoding="utf-8")
            result = research.finalize_pending(
                True, state_path=state, root=root
            )
            self.assertEqual(result["verified_resolution_lessons"], 0)
            self.assertEqual(result["binding_rejected_resolutions"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["issues"][issue["error_signature"]][
                    "last_verification_rejection"
                ],
                "pending_verification_expired",
            )

    def test_clean_run_skips_redundant_impact_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            with mock.patch.object(
                research,
                "build_repository_index",
                side_effect=AssertionError("impact index must be skipped"),
            ):
                result = research.observe_errors(
                    [],
                    root=root,
                    state_path=state,
                    report_path=report,
                    network_research=False,
                )
            self.assertEqual(result["error_count"], 0)
            self.assertEqual(result["repository_files_scanned"], 0)
            self.assertFalse(result["impact_scan_required"])
            self.assertTrue(result["impact_scan_skipped_no_open_errors"])

    def test_incomplete_impact_analysis_cannot_enter_learning_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            payload = json.loads(state.read_text(encoding="utf-8"))
            payload["issues"][issue["error_signature"]]["impact_analysis"][
                "full_repository_scan"
            ] = False
            state.write_text(json.dumps(payload), encoding="utf-8")
            staged = research.stage_repairs([applied], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 0)
            self.assertEqual(
                staged["skip_reasons"]["impact_analysis_incomplete"], 1
            )

    def test_noop_hash_cannot_enter_learning_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            _issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            applied["before_hash"] = applied["after_hash"]
            staged = research.stage_repairs([applied], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 0)
            self.assertEqual(
                staged["skip_reasons"]["repair_did_not_change_target"], 1
            )

    def test_unrelated_full_regression_failure_does_not_poison_verified_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue, applied, _target = self._prepare_verified_repair(
                root, state, report
            )
            research.stage_repairs([applied], state_path=state)
            first = research.finalize_pending(
                True, state_path=state, root=root
            )
            self.assertEqual(first["verified_resolution_lessons"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            original_lesson = dict(payload["lessons"][issue["error_signature"]])

            research.observe_errors(
                [issue], root=root, state_path=state, report_path=report,
                network_research=False,
            )
            _issue2, applied2, _target2 = self._prepare_verified_repair(
                root, state, report
            )
            research.stage_repairs([applied2], state_path=state)
            second = research.finalize_pending(
                False, state_path=state, root=root
            )
            self.assertEqual(second["rejected_unverified_resolutions"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            current_lesson = payload["lessons"][issue["error_signature"]]
            self.assertEqual(
                current_lesson["verified_successes"],
                original_lesson["verified_successes"],
            )
            self.assertEqual(
                current_lesson["verified_failures"],
                original_lesson["verified_failures"],
            )
            self.assertEqual(
                current_lesson["confidence_level"],
                original_lesson["confidence_level"],
            )
            self.assertEqual(
                payload["issues"][issue["error_signature"]]["status"],
                "full_regression_not_passed",
            )

    def test_policy_keeps_search_text_non_executable(self):
        policy = json.loads(
            (Path(__file__).resolve().parent / "selfrefine_domain_policy.json")
            .read_text(encoding="utf-8")
        )
        rules = policy["rules"]
        self.assertTrue(rules["new_error_full_repository_analysis"])
        self.assertTrue(rules["new_error_official_source_research"])
        self.assertTrue(rules["new_error_bounded_official_network_research"])
        self.assertTrue(rules["research_network_allowlist_only"])
        self.assertFalse(rules["research_raw_body_persisted"])
        self.assertFalse(rules["research_network_failure_blocks_selfrefine"])
        self.assertFalse(rules["research_text_executable"])
        self.assertFalse(rules["search_result_patch_generation"])
        self.assertTrue(rules["full_regression_before_resolution_learning"])
        self.assertTrue(rules["pending_resolution_rule_binding_required"])
        self.assertTrue(rules["pending_resolution_after_hash_required"])
        self.assertTrue(rules["stale_pending_resolution_not_promoted"])
        self.assertTrue(rules["rolled_back_repair_not_staged_for_learning"])
        self.assertTrue(rules["clean_run_skips_redundant_impact_scan"])
        self.assertTrue(rules["transitive_dependency_impact_analysis"])
        self.assertTrue(rules["complete_impact_analysis_required_for_learning"])
        self.assertTrue(rules["full_regression_failure_does_not_poison_verified_lesson"])
        self.assertFalse(rules["unknown_error_auto_repair"])


if __name__ == "__main__":
    unittest.main()
