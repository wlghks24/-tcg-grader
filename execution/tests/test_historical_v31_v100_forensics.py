"""Deterministic W001 historical forensic source and report checks."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v31_v100_forensics as forensic

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class V31V100HistoricalForensicsTests(unittest.TestCase):
    def test_pinned_original_git_evidence_not_synthetic_release_approval(self):
        result = forensic.inspect(ROOT)
        self.assertEqual(8, result["original_root_file_count"])
        self.assertEqual(forensic.ROOT_COMMIT, result["original_root"])
        self.assertFalse(result["full_v1_v100_code_review"])
        self.assertIsNone(result["quality_score"])
        self.assertFalse(result["device_verified"])
        self.assertFalse(result["v31"]["current_runtime_regression_proven"])

    def test_v31_original_serviceworker_icon_paths_are_absent_from_root_tree(self):
        r = forensic.inspect(ROOT)["v31"]
        self.assertEqual(
            ["icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png"],
            r["missing_in_first_commit_icons"],
        )
        self.assertEqual(
            ["icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png"],
            r["missing_in_first_commit_serviceworker_precache"],
        )
        self.assertTrue(r["serviceworker_precache_uses_add_all"])
        self.assertTrue(r["report_claims_icon_fix"])

    def test_v31_missing_icon_is_repaired_by_exact_early_commit(self):
        fixed = forensic.inspect(ROOT)["v31_early_icon_fix"]
        self.assertEqual(forensic.EARLY_ICON_FIX_COMMIT, fixed["fix_commit"])
        self.assertTrue(fixed["icon_blob_verified"])
        self.assertEqual(["icon.svg"], fixed["manifest_icon_references"])
        self.assertTrue(fixed["serviceworker_precache_includes_icon"])
        self.assertTrue(fixed["all_early_precache_paths_in_commit"])
        self.assertFalse(fixed["actual_browser_install_verified"])

    def test_early_icon_source_is_git_blob_pinned(self):
        with self.assertRaisesRegex(ValueError, "pinned_historical_blob_changed"):
            forensic.checked_object(
                ROOT, forensic.EARLY_ICON_FIX_COMMIT, "icon.svg", "0" * 40
            )

    def test_icon_parser_rejects_malformed_input(self):
        with self.assertRaisesRegex(ValueError, "malformed_root_manifest"):
            forensic.icon_references({}, "const CORE=['./']; cache.addAll(CORE)")
        with self.assertRaisesRegex(ValueError, "unrecognized_original_serviceworker"):
            forensic.icon_references({"icons": [{"src": "icon.svg"}]}, "nothing")

    def test_present_icon_does_not_create_false_missing_asset(self):
        manifest={"icons":[{"src":"icons/icon-192.png"}]}
        sw="const CORE=['./','./icons/icon-192.png'];cache.addAll(CORE)"
        icons, core=forensic.icon_references(manifest, sw)
        self.assertEqual(["icons/icon-192.png"], icons)
        self.assertIn("icons/icon-192.png", core)
        self.assertEqual(set(), set(icons)-{"icons/icon-192.png"})

    def test_v99_root_history_is_not_original_release_accuracy_proof(self):
        r=forensic.inspect(ROOT)["v99"]
        self.assertTrue(r["original_skipped_missing_channel"])
        self.assertEqual(forensic.ORIGINAL_V99_IMPORT, r["first_pinned_source_seen_at"])
        self.assertEqual(forensic.V291_REPAIR_COMMIT, r["later_v291_repair_commit"])
        self.assertFalse(r["complete_current_grading_review"])

    def test_v100_historical_report_metadata_mismatch_and_synthetic_limits(self):
        data=forensic.inspect(ROOT)["v100"]
        self.assertEqual("MISMATCH", data["build_label_vs_metadata"])
        self.assertEqual(1, data["metadata_version"])
        self.assertIn("v100", data["build_label"])
        self.assertEqual(6, data["historical_record_passes"])
        self.assertEqual(12, data["synthetic_positive_labels"])
        self.assertEqual(24, data["synthetic_negative_labels"])
        self.assertFalse(data["calibration_adopted"])
        self.assertTrue(data["explicit_real_photo_limitation"])
        self.assertFalse(data["real_photo_accuracy_verified"])

    def test_v100_rejects_forged_negative_counts_and_inconsistent_passes(self):
        d={"build":"TCG_v100", "version":100, "ok":True, "successful_passes":1,
           "final_full_verification_passes":[{}],
           "vision_self_learning":{"metrics":{"counts":{"tp":-1,"tn":24,"fp":0,"fn":0}}},
           "limitations":["synthetic result is not real evidence"]}
        with self.assertRaisesRegex(ValueError, "invalid_v100_count"):
            forensic.report_semantics(d)
        d["vision_self_learning"]["metrics"]["counts"]["tp"]=12
        d["successful_passes"]=2
        with self.assertRaisesRegex(ValueError, "internal_pass_count_mismatch"):
            forensic.report_semantics(d)

    def test_v100_rejects_missing_or_nonlist_pass_evidence(self):
        d={"build":"TCG_v100","version":100,"ok":True,"successful_passes":0,
           "final_full_verification_passes":[],
           "vision_self_learning":{"metrics":{"counts":{"tp":0,"tn":0,"fp":0,"fn":0}}},
           "limitations":["synthetic is not real"]}
        for bad in (None, "not-a-list", {}, 7):
            with self.subTest(bad=bad):
                d["final_full_verification_passes"]=bad
                with self.assertRaisesRegex(ValueError, "internal_pass_count_mismatch"):
                    forensic.report_semantics(d)
        d["final_full_verification_passes"]=[]
        for bad in (None, True, "0", -1):
            with self.subTest(successful=bad):
                d["successful_passes"]=bad
                with self.assertRaisesRegex(ValueError, "internal_pass_count_mismatch"):
                    forensic.report_semantics(d)

    def test_v100_pass_entries_must_be_real_ordered_success_records(self):
        record = {"pass": 1, "ok": True, "tail": "historical pass log"}
        data = {
            "build": "TCG_Grader_v100", "version": 1, "ok": True,
            "successful_passes": 1, "failed_passes": 0,
            "final_full_verification_passes": [record],
            "vision_self_learning": {"metrics": {
                "counts": {"tp": 12, "tn": 24, "fp": 0, "fn": 0}}},
            "limitations": ["synthetic result is not real photo proof"],
        }
        self.assertEqual(1, forensic.report_semantics(data)["historical_record_passes"])
        for bad in ({}, {"pass": True, "ok": True, "tail": "x"},
                    {"pass": 2, "ok": True, "tail": "x"},
                    {"pass": 1, "ok": False, "tail": "x"},
                    {"pass": 1, "ok": True, "tail": ""}):
            with self.subTest(bad=bad):
                data["final_full_verification_passes"] = [bad]
                with self.assertRaisesRegex(ValueError, "pass_record_malformed"):
                    forensic.report_semantics(data)
        data["final_full_verification_passes"] = [record]
        for bad in (True, 1, -1, None):
            with self.subTest(failed_passes=bad):
                data["failed_passes"] = bad
                with self.assertRaisesRegex(ValueError, "failed_pass_count_inconsistent"):
                    forensic.report_semantics(data)

    def test_v100_six_repeated_pass_logs_are_not_six_independent_receipts(self):
        record = forensic.inspect(ROOT)["v100"]
        self.assertEqual(6, record["historical_record_passes"])
        self.assertEqual(1, record["distinct_pass_log_texts"])
        self.assertTrue(record["repeated_pass_log_texts"])
        self.assertFalse(record["independent_run_receipts_verified"])

    def test_v100_report_rejects_false_success_flag(self):
        row = {"pass": 1, "ok": True, "tail": "test evidence"}
        payload = {
            "build": "TCG_Grader_v100", "version": 1,
            "ok": False, "successful_passes": 1, "failed_passes": 0,
            "final_full_verification_passes": [row],
            "vision_self_learning": {"metrics": {
                "counts": {"tp": 12, "tn": 24, "fp": 0, "fn": 0}}},
            "limitations": ["synthetic is not real photo evidence"],
        }
        for value in (False, None, 1, "true"):
            with self.subTest(ok=value):
                payload["ok"] = value
                with self.assertRaisesRegex(ValueError, "success_flag_inconsistent"):
                    forensic.report_semantics(payload)
        payload["ok"] = True
        out = forensic.report_semantics(payload)
        self.assertEqual(1, out["distinct_pass_log_texts"])
        self.assertFalse(out["repeated_pass_log_texts"])
        self.assertFalse(out["independent_run_receipts_verified"])

    def test_pinned_original_server_mutating_get_is_not_current_device_claim(self):
        out = forensic.inspect(ROOT)["v31_original_server"]
        self.assertTrue(out["historical_get_update_calls_collector"])
        self.assertTrue(out["historical_collector_writes_database"])
        self.assertTrue(out["historical_post_apply_writes_database"])
        self.assertFalse(out["historical_post_origin_guard_present"])
        self.assertTrue(out["historical_server_binds_all_interfaces"])
        self.assertFalse(out["current_runtime_vulnerable_proven"])
        self.assertFalse(out["live_network_origin_replay_performed"])

    def test_original_server_parser_rejects_comment_only_spoof(self):
        forged = (
            "def collect(): pass\n"
            "class Handler:\n"
            "    def do_GET(self):\n"
            "        # if path == '/api/update': return self.json(collect())\n"
            "        return None\n"
            "    def do_POST(self):\n"
            "        # save_db(data) on '/api/apply'\n"
            "        return None\n"
            "server = ThreadingHTTPServer(('0.0.0.0', 8765), Handler)\n"
        )
        with self.assertRaisesRegex(ValueError, "unrecognized_historical_server_flow"):
            forensic.original_server_semantics(forged)

    def test_original_server_parser_rejects_broken_syntax(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_server_source"):
            forensic.original_server_semantics("def foo(")

    def test_original_index_static_dom_and_legacy_route_gaps_are_evidenced(self):
        data = forensic.inspect(ROOT)["v31_original_index"]
        self.assertEqual(21, data["historical_inline_scripts"])
        self.assertEqual(
            ["v18out", "v18status", "v18update",
             "v19apply", "v19collect", "v19out"],
            data["literal_referenced_ids_absent_from_static_markup"],
        )
        self.assertEqual(
            ["/api/최신자료수집", "/api/상태"],
            data["unsupported_original_server_route_leads"],
        )
        self.assertFalse(data["dynamic_dom_absence_proven"])
        self.assertFalse(data["current_runtime_regression_proven"])

    def test_index_parser_ignores_id_markup_inside_script_strings(self):
        original = forensic.checked_object(
            ROOT, forensic.ROOT_COMMIT, "index.html",
            forensic.ROOT_INDEX_BLOB,
        ).decode("utf-8")
        # Inject a fake HTML-looking ID into an existing inline script only.
        altered = original.replace(
            "</script>", "const decoy = `<div id='v18out'></div>`;\\n</script>", 1
        )
        result = forensic.original_index_dom_semantics(altered)
        self.assertIn(
            "v18out", result["literal_referenced_ids_absent_from_static_markup"]
        )
        self.assertFalse(result["dynamic_dom_absence_proven"])

    def test_early_learning_store_migration_preserves_v99_verified_labels(self):
        import migrate_old_data as migration
        old_grade = {
            "official_result": True, "company": "PSA", "actual": 9,
            "raw_pred": 9.5, "certification_id": "OLD-0001", "card_id": "old-card"
        }
        another_grade = {
            "official_result": True, "company": "PSA", "actual": 9,
            "raw_pred": 9.5, "certification_id": "OLD-0002", "card_id": "second-card"
        }
        new_grade = {
            "official_result": True, "company": "BGS", "actual": 9.5,
            "raw_pred": 10, "certification_id": "NEW-0003", "card_id": "new-card"
        }
        old = {"version": 2, "v30_validation": [], "v11_validation": [],
               "v99_validation": [old_grade, another_grade],
               "legacy_verified_metadata": {"source": "old"}}
        new = {"version": 2, "v30_validation": [], "v11_validation": [],
               "v99_validation": [another_grade, new_grade],
               "future_learning_metadata": {"source": "new"}}
        result = migration.merge_learning(new, old)
        self.assertEqual(2, result["version"])
        self.assertEqual(
            ["OLD-0001", "OLD-0002", "NEW-0003"],
            [row["certification_id"] for row in result["v99_validation"]],
        )
        self.assertEqual({"source": "old"}, result["legacy_verified_metadata"])
        self.assertEqual({"source": "new"}, result["future_learning_metadata"])
        self.assertEqual(3, len(migration.merge_learning(result, old)["v99_validation"]))

    def test_migration_keeps_conflicting_official_certifications_for_quarantine(self):
        import migrate_old_data as migration
        import grading_accuracy_v99 as grading
        old_row = {"company": "PSA", "official_result": True, "actual": 9,
                   "raw_pred": 9.5, "certification_id": "CONFLICT-01"}
        new_row = {**old_row, "actual": 10}
        merged = migration.merge_learning(
            {"v99_validation": [new_row]}, {"v99_validation": [old_row]}
        )
        self.assertEqual(2, len(merged["v99_validation"]))
        self.assertEqual([], grading.sanitize_rows(merged))

    def test_migration_rejects_nonlist_v99_inputs_without_discarding_good_rows(self):
        import migrate_old_data as migration
        original = [{"company": "PSA", "official_result": True,
                     "actual": 10, "raw_pred": 10, "certification_id": "GOOD-0001"}]
        result = migration.merge_learning(
            {"version": "2", "v99_validation": {"invalid": True}},
            {"version": 2, "v99_validation": original}
        )
        self.assertEqual(original, result["v99_validation"])
        self.assertEqual(2, result["version"])

    def test_learning_migration_replay_preserves_v99_and_prechange_backup(self):
        import tempfile
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-migrate-") as tmp:
            old_dir, new_dir = Path(tmp) / "old", Path(tmp) / "new"
            old_dir.mkdir()
            new_dir.mkdir()
            for directory in (old_dir, new_dir):
                (directory / "tcg_updater.py").write_text(
                    "# empty fixture only; never executed\\n", encoding="utf-8"
                )
            legacy_row = {
                "official_result": True, "company": "PSA",
                "actual": 9, "raw_pred": 9.5,
                "certification_id": "LEGACY-0001",
            }
            new_row = {
                "official_result": True, "company": "BGS",
                "actual": 9.5, "raw_pred": 10,
                "certification_id": "CURRENT-0002",
            }
            old_payload = {"version": 2, "v99_validation": [legacy_row]}
            new_payload = {"version": 2, "v99_validation": [new_row]}
            (old_dir / "learning_store.json").write_text(
                json.dumps(old_payload), encoding="utf-8"
            )
            (new_dir / "learning_store.json").write_text(
                json.dumps(new_payload), encoding="utf-8"
            )
            backup = migration.migrate(old_dir, new_dir)
            saved = json.loads(
                (new_dir / "learning_store.json").read_text(encoding="utf-8")
            )
            original_new = json.loads(
                (backup / "learning_store.json").read_text(encoding="utf-8")
            )
            original_old = json.loads(
                (old_dir / "learning_store.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["LEGACY-0001", "CURRENT-0002"],
                [r["certification_id"] for r in saved["v99_validation"]],
            )
            self.assertEqual(new_payload, original_new)
            self.assertEqual(old_payload, original_old)

    def test_scope_gaps_are_not_equated_with_absent_or_certified_releases(self):
        out=forensic.inspect(ROOT)
        self.assertEqual("HISTORICAL_SOURCE_DISCREPANCY_REPRODUCED_REVIEW_PENDING", out["status"])
        self.assertNotIn("accuracy_score", out["v100"])
        self.assertIsNone(out["quality_score"])


if __name__ == "__main__":
    unittest.main()
