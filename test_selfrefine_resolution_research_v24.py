#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import selfrefine_resolution_research as research


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
        (root / "unrelated.py").write_text("value = 1\n", encoding="utf-8")

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
                {"broken.py", "consumer.py", "test_broken.py"}.issubset(impacted),
                impacted,
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
            research.observe_errors(
                [self._issue()], root=root, state_path=state, report_path=report,
                network_research=False,
            )
            staged = research.stage_repairs([{
                "error_signature": "a" * 20,
                "rule_id": "safe-rule-v1",
                "rule_fingerprint": "f" * 24,
                "path": "broken.py",
                "stage": "PYTHON_SYNTAX",
            }], state_path=state)
            self.assertEqual(staged["pending_full_regression"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["lessons"], {})
            self.assertEqual(
                payload["pending_verifications"]["a" * 20]["verification_status"],
                "pending_full_regression",
            )

    def test_successful_full_regression_becomes_reusable_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            issue = self._issue()
            research.observe_errors(
                [issue], root=root, state_path=state, report_path=report,
                network_research=False,
            )
            research.stage_repairs([{
                "error_signature": "a" * 20,
                "rule_id": "safe-rule-v1",
                "rule_fingerprint": "f" * 24,
                "path": "broken.py",
                "stage": "PYTHON_SYNTAX",
            }], state_path=state)
            result = research.finalize_pending(True, state_path=state)
            self.assertEqual(result["verified_resolution_lessons"], 1)

            payload = json.loads(state.read_text(encoding="utf-8"))
            lesson = payload["lessons"]["a" * 20]
            self.assertTrue(lesson["regression_pass"])
            self.assertEqual(
                lesson["verification_result"], "full_regression_passed"
            )
            self.assertEqual(
                lesson["fix_pattern"], "verified_code_rule:safe-rule-v1"
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
                "verified_code_rule:safe-rule-v1",
            )

    def test_failed_full_regression_is_not_promoted_to_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            state = root / "state.json"
            report = root / "report.json"
            research.observe_errors(
                [self._issue()], root=root, state_path=state, report_path=report,
                network_research=False,
            )
            research.stage_repairs([{
                "error_signature": "a" * 20,
                "rule_id": "safe-rule-v1",
                "rule_fingerprint": "f" * 24,
                "path": "broken.py",
                "stage": "PYTHON_SYNTAX",
            }], state_path=state)
            result = research.finalize_pending(False, state_path=state)
            self.assertEqual(result["verified_resolution_lessons"], 0)
            self.assertEqual(result["rejected_unverified_resolutions"], 1)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertNotIn("a" * 20, payload["lessons"])
            self.assertEqual(
                payload["issues"]["a" * 20]["status"],
                "verification_failed",
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
        self.assertFalse(rules["unknown_error_auto_repair"])


if __name__ == "__main__":
    unittest.main()
