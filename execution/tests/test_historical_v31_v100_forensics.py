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
        old_sample = {"company": "PSA", "verified": True, "actual_grade": 9,
                      "raw_pred": 9.5, "cert_no": "OLD-CONFIRMED-1"}
        new_sample = {"company": "BGS", "verified": True, "actual_grade": 9.5,
                      "raw_pred": 10, "cert_no": "NEW-CONFIRMED-2"}
        old = {"version": 2, "v30_validation": [], "v11_validation": [],
               "v99_validation": [old_grade, another_grade],
               "confirmed_samples": [old_sample],
               "legacy_verified_metadata": {"source": "old"}}
        new = {"version": 2, "v30_validation": [], "v11_validation": [],
               "v99_validation": [another_grade, new_grade],
               "confirmed_samples": [new_sample],
               "future_learning_metadata": {"source": "new"}}
        result = migration.merge_learning(new, old)
        self.assertEqual(2, result["version"])
        self.assertEqual(
            ["OLD-0001", "OLD-0002", "NEW-0003"],
            [row["certification_id"] for row in result["v99_validation"]],
        )
        self.assertEqual([old_sample, new_sample], result["confirmed_samples"])
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
            old_sample = {"company": "PSA", "verified": True,
                          "actual_grade": 9, "raw_pred": 9.5,
                          "cert_no": "LEGACY-CONFIRMED"}
            new_sample = {"company": "BGS", "verified": True,
                          "actual_grade": 9.5, "raw_pred": 10,
                          "cert_no": "CURRENT-CONFIRMED"}
            old_payload = {"version": 2, "v99_validation": [legacy_row],
                           "confirmed_samples": [old_sample]}
            new_payload = {"version": 2, "v99_validation": [new_row],
                           "confirmed_samples": [new_sample]}
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
            self.assertEqual([old_sample, new_sample], saved["confirmed_samples"])
            self.assertEqual(new_payload, original_new)
            self.assertEqual(old_payload, original_old)

    def test_v40_confirmed_certificate_conflict_fails_closed(self):
        import migrate_old_data as migration
        import grading_self_learning as learner
        old = {"company": "PSA", "verified": True, "actual_grade": 9,
               "raw_pred": 9.5, "cert_no": "CERT-CONFLICT-004"}
        new = {**old, "actual_grade": 10}
        with self.assertRaisesRegex(ValueError, "confirmed_sample_cert_grade_conflict"):
            migration.merge_learning(
                {"confirmed_samples": [new]},
                {"confirmed_samples": [old]},
            )
        with self.assertRaisesRegex(ValueError, "confirmed_sample_cert_grade_conflict"):
            migration.merge_learning(
                {"confirmed_samples": [old, new]}, {},
            )
        # Equal official grades represented with different number types do not
        # cause a false quarantine; the reader still handles model rebuilding.
        allowed = migration.merge_learning(
            {"confirmed_samples": [{**new, "actual_grade": "9.0"}]},
            {"confirmed_samples": [old]},
        )
        self.assertEqual(2, len(allowed["confirmed_samples"]))
        self.assertEqual(
            1,
            len(learner.rebuild_store(allowed)["confirmed_samples"]),
        )

    def test_conflicting_confirmed_certificate_does_not_replace_migration_files(self):
        import tempfile
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-confirmed-conflict-") as tmp:
            old, new = Path(tmp) / "old", Path(tmp) / "new"
            old.mkdir()
            new.mkdir()
            for directory in (old,new):
                (directory / "tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            historical = {"version": 2, "confirmed_samples": [{
                "company": "BGS", "actual_grade": 9, "verified": True,
                "raw_pred": 9.5, "cert_no": "CONFLICT-CERT-20"
            }]}
            current = {"version": 2, "confirmed_samples": [{
                "company": "BGS", "actual_grade": 10, "verified": True,
                "raw_pred": 9.5, "cert_no": "CONFLICT-CERT-20"
            }]}
            for directory,data in ((old,historical),(new,current)):
                (directory / "learning_store.json").write_text(
                    json.dumps(data), encoding="utf-8"
                )
            (new / "verification_history.json").write_text(
                '{"runs":[]}', encoding="utf-8"
            )
            original_learning=(new / "learning_store.json").read_bytes()
            original_history=(new / "verification_history.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "confirmed_sample_cert_grade_conflict"):
                migration.migrate(old,new)
            self.assertEqual(original_learning,(new / "learning_store.json").read_bytes())
            self.assertEqual(original_history,(new / "verification_history.json").read_bytes())
            self.assertEqual(historical, json.loads((old / "learning_store.json").read_text()))

    def test_migration_rejects_overflow_without_silent_training_label_loss(self):
        import migrate_old_data as migration
        rows = [
            {"official_result": True, "company": "PSA", "actual": 9,
             "raw_pred": 9.5, "certification_id": f"CAP-{i:04d}"}
            for i in range(3)
        ]
        with self.assertRaisesRegex(ValueError, "learning_evidence_capacity_exceeded"):
            migration.merge_v99_rows([rows[2]], rows[:2], limit=2)
        with self.assertRaisesRegex(ValueError, "learning_evidence_capacity_exceeded"):
            migration.merge_confirmed_rows([rows[2]], rows[:2], limit=2)
        self.assertEqual(rows, migration.merge_v99_rows([rows[2]], rows[:2], limit=3))

    def test_migration_v99_overflow_refuses_disk_write_and_keeps_old_input(self):
        import tempfile
        import migrate_old_data as migration
        rows = [{"official_result": True, "company": "PSA", "actual": 9,
                 "raw_pred": 9.5, "certification_id": f"CAP-{i:04d}"}
                for i in range(1001)]
        with tempfile.TemporaryDirectory(prefix="tcg-w001-capacity-") as tmp:
            old, new = Path(tmp) / "old", Path(tmp) / "new"
            old.mkdir()
            new.mkdir()
            for directory in (old, new):
                (directory / "tcg_updater.py").write_text("# fixture\\n", encoding="utf-8")
            original_old = json.dumps({"version": 2, "v99_validation": rows})
            original_new = json.dumps({"version": 2, "v99_validation": []})
            (old / "learning_store.json").write_text(original_old, encoding="utf-8")
            (new / "learning_store.json").write_text(original_new, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "learning_evidence_capacity_exceeded"):
                migration.migrate(old,new)
            self.assertEqual(original_old,(old / "learning_store.json").read_text())
            self.assertEqual(original_new,(new / "learning_store.json").read_text())

    def test_migration_preflights_later_invalid_json_before_any_write(self):
        import tempfile
        import migrate_old_data as migration
        for bad_source in ("old", "new"):
            with self.subTest(bad_source=bad_source), tempfile.TemporaryDirectory(
                    prefix="tcg-w001-invalid-json-") as tmp:
                old,new=Path(tmp)/"old",Path(tmp)/"new"
                old.mkdir()
                new.mkdir()
                for folder in (old,new):
                    (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
                prior={"version":2,"v99_validation":[{
                    "company":"PSA","actual":9,"raw_pred":9.5,
                    "certification_id":"PREVIOUS-GOOD-001"
                }]}
                (new/"learning_store.json").write_text(
                    json.dumps(prior),encoding="utf-8")
                (old/"learning_store.json").write_text(
                    json.dumps({"version":2,"v99_validation":[]}),encoding="utf-8")
                (new/"verification_history.json").write_text(
                    '{"version":2,"runs":[]}',encoding="utf-8")
                ( (old if bad_source=="old" else new) /
                  "auto_repair_memory.json").write_text("{bad-json",encoding="utf-8")
                before={
                    p.name:p.read_bytes() for p in new.iterdir() if p.is_file()
                }
                with self.assertRaisesRegex(
                        ValueError,"migration_source_unreadable_or_invalid_json"):
                    migration.migrate(old,new)
                after={
                    p.name:p.read_bytes() for p in new.iterdir() if p.is_file()
                }
                self.assertEqual(before,after)
                self.assertFalse((new/"MIGRATION_BACKUP").exists())

    def test_migration_preflights_nonobject_json_and_blocks_symlink(self):
        import tempfile
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-json-type-") as tmp:
            new=Path(tmp)/"new"
            old=Path(tmp)/"old"
            old.mkdir()
            new.mkdir()
            for folder in (old,new):
                (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            (old/"verification_history.json").write_text(
                "[]",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"migration_source_must_be_object"):
                migration.migrate(old,new)
            self.assertFalse((new/"learning_store.json").exists())
            (old/"verification_history.json").unlink()
            real=(old/"real.json")
            real.write_text("{}",encoding="utf-8")
            link=old/"learning_store.json"
            try:
                link.symlink_to(real)
            except (OSError,NotImplementedError):
                self.skipTest("filesystem cannot create symlinks")
            with self.assertRaisesRegex(ValueError,"migration_source_symlink_blocked"):
                migration.migrate(old,new)
            self.assertFalse((new/"learning_store.json").exists())

    def test_legacy_v30_rows_keep_distinct_cards_with_same_grade_and_time(self):
        import migrate_old_data as migration
        base={"company":"PSA","time":"2026-08-21T00:00:00Z",
              "actual":9,"pred":9}
        old={**base,"certification_id":"CERT-V30-OLD","card_id":"card-a"}
        new={**base,"certification_id":"CERT-V30-NEW","card_id":"card-b"}
        merged=migration.merge_learning(
            {"v30_validation":[new],"v11_validation":[new]},
            {"v30_validation":[old],"v11_validation":[old]},
        )
        self.assertEqual(
            ["CERT-V30-OLD","CERT-V30-NEW"],
            [x["certification_id"] for x in merged["v30_validation"]],
        )
        self.assertEqual(2,len(merged["v11_validation"]))
        # Replaying the same migration never multiplies identical rows.
        again=migration.merge_learning(merged,{"v30_validation":[old]})
        self.assertEqual(2,len(again["v30_validation"]))

    def test_legacy_v30_overcapacity_refuses_to_discard_older_cards(self):
        import migrate_old_data as migration
        records=[
            {"company":"PSA","actual":9,"pred":9,
             "certification_id":f"OLD-CERT-{i:04d}"}
            for i in range(501)
        ]
        with self.assertRaisesRegex(ValueError,"learning_evidence_capacity_exceeded"):
            migration.merge_learning({"v30_validation":[]},
                                     {"v30_validation":records})
        self.assertEqual(
            2,len(migration.rows_merged(
                [{"company":"PSA","actual":9,"pred":9,"card_id":"b"}],
                [{"company":"PSA","actual":9,"pred":9,"card_id":"a"}],
                limit=2,
            ))
        )

    def test_migration_refuses_last_good_symlinks_before_rewriting_learning(self):
        import tempfile
        import migrate_old_data as migration

        # A malformed legacy snapshot must not cause a *partial* migration.
        # The original bug rejected a link only after overwriting four files.
        for location in ("old-root", "old-nested", "new-root"):
            with self.subTest(location=location), tempfile.TemporaryDirectory(
                    prefix="tcg-w001-migration-symlink-") as tmp:
                old, new = Path(tmp) / "old", Path(tmp) / "new"
                old.mkdir()
                new.mkdir()
                for d in (old, new):
                    (d / "tcg_updater.py").write_text("# fixture\n", encoding="utf-8")
                before = {
                    "version": 2,
                    "v99_validation": [{
                        "company": "PSA", "official_result": True,
                        "actual": 10, "raw_pred": 10,
                        "certification_id": "NEW-SAFE-0001",
                    }],
                }
                (new / "learning_store.json").write_text(
                    json.dumps(before), encoding="utf-8")
                outside = Path(tmp) / "outside.json"
                outside.write_text('{"untouched":true}', encoding="utf-8")
                if location == "old-root":
                    (old / ".tcg_last_good").symlink_to(outside)
                elif location == "new-root":
                    (new / ".tcg_last_good").symlink_to(outside)
                else:
                    tree = old / ".tcg_last_good"
                    tree.mkdir()
                    (tree / "escape").symlink_to(outside)
                with self.assertRaisesRegex(ValueError, "심볼릭 링크"):
                    migration.migrate(old, new)
                self.assertEqual(
                    before,
                    json.loads((new / "learning_store.json").read_text(
                        encoding="utf-8")),
                )
                self.assertEqual('{"untouched":true}', outside.read_text(
                    encoding="utf-8"))
                self.assertFalse((new / "MIGRATION_BACKUP").exists())

    def test_migration_rolls_back_json_when_writer_fails_after_replace(self):
        import tempfile
        from unittest import mock
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-write-rollback-") as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            old.mkdir();new.mkdir()
            for folder in (old,new):
                (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            initial={
                "learning_store.json": b'{"version":2,"v99_validation":[{"certification_id":"KEEP"}]}',
                "verification_history.json": b'{"version":2,"runs":[]}',
            }
            for name,data in initial.items():
                (new/name).write_bytes(data)
            (old/"learning_store.json").write_text(
                '{"version":2,"v99_validation":[{"certification_id":"OLD"}]}',
                encoding="utf-8")
            old_bytes=(old/"learning_store.json").read_bytes()
            original_write=migration.write_json
            calls=[0]
            def failing_writer(path,data):
                calls[0]+=1
                original_write(path,data)
                if calls[0]==2:
                    raise OSError("injected-after-rename")
            with mock.patch.object(migration,"write_json",side_effect=failing_writer):
                with self.assertRaisesRegex(OSError,"injected-after-rename"):
                    migration.migrate(old,new)
            self.assertEqual(2,calls[0])
            for name,data in initial.items():
                self.assertEqual(data,(new/name).read_bytes())
            for name in set(migration.FILES)-set(initial):
                self.assertFalse((new/name).exists())
            self.assertEqual(old_bytes,(old/"learning_store.json").read_bytes())
            backups=list((new/"MIGRATION_BACKUP").iterdir())
            self.assertEqual(1,len(backups))
            for name,data in initial.items():
                self.assertEqual(data,(backups[0]/name).read_bytes())

    def test_migration_rolls_back_json_and_new_snapshot_on_snapshot_copy_error(self):
        import tempfile
        from unittest import mock
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-snapshot-rollback-") as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            old.mkdir();new.mkdir()
            for folder in (old,new):
                (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            original=b'{"version":2,"v99_validation":[{"certification_id":"KEEP"}]}'
            (new/"learning_store.json").write_bytes(original)
            good=old/".tcg_last_good";good.mkdir()
            (good/"previous.json").write_text('{"last_good":true}',encoding="utf-8")
            original_copy=migration.copy_safe_file
            def failing_copy(source,destination):
                original_copy(source,destination)
                if destination.parent.name==".tcg_last_good":
                    raise OSError("injected-snapshot-copy")
            with mock.patch.object(migration,"copy_safe_file",side_effect=failing_copy):
                with self.assertRaisesRegex(OSError,"injected-snapshot-copy"):
                    migration.migrate(old,new)
            self.assertEqual(original,(new/"learning_store.json").read_bytes())
            for name in set(migration.FILES)-{"learning_store.json"}:
                self.assertFalse((new/name).exists())
            self.assertFalse((new/".tcg_last_good").exists())
            self.assertEqual('{"last_good":true}',(good/"previous.json").read_text())

    def test_migration_refuses_symlinked_backup_root_without_writing(self):
        import tempfile
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-backup-link-") as tmp:
            old,new,outside=[Path(tmp)/name for name in ("old","new","outside")]
            for folder in (old,new,outside):
                folder.mkdir()
            for folder in (old,new):
                (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            original=b'{"version":2,"v99_validation":[]}'
            (new/"learning_store.json").write_bytes(original)
            try:
                (new/"MIGRATION_BACKUP").symlink_to(outside,target_is_directory=True)
            except (OSError,NotImplementedError):
                self.skipTest("filesystem cannot create symlinks")
            with self.assertRaisesRegex(ValueError,"migration_backup_directory_unsafe"):
                migration.migrate(old,new)
            self.assertEqual(original,(new/"learning_store.json").read_bytes())
            self.assertEqual([],list(outside.iterdir()))


    def test_migration_lock_refuses_unsafe_owner_without_mutation(self):
        import tempfile
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-migration-lock-") as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            old.mkdir();new.mkdir()
            for folder in (old,new):
                (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            before=b'{"version":2,"v99_validation":[{"certification_id":"KEEP"}]}'
            (new/"learning_store.json").write_bytes(before)
            bad_lock=new/".tcg_migration.lock"
            bad_lock.mkdir()  # A directory cannot masquerade as a regular lock.
            with self.assertRaisesRegex(ValueError,"unsafe lock target"):
                migration.migrate(old,new)
            self.assertEqual(before,(new/"learning_store.json").read_bytes())
            self.assertFalse((new/"MIGRATION_BACKUP").exists())
            bad_lock.rmdir()
            migration.migrate(old,new)
            self.assertFalse(bad_lock.exists())
            self.assertEqual(
                before, (next((new/"MIGRATION_BACKUP").iterdir())/
                         "learning_store.json").read_bytes()
            )

    def test_two_quick_migrations_preserve_separate_backups_and_old_labels(self):
        import tempfile
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix="tcg-w001-double-migration-") as tmp:
            old,new=Path(tmp)/"old",Path(tmp)/"new"
            old.mkdir();new.mkdir()
            for folder in (old,new):
                (folder/"tcg_updater.py").write_text("# fixture\\n",encoding="utf-8")
            existing={"version":2,"v99_validation":[{"company":"PSA",
                       "official_result":True,"actual":9,"raw_pred":9.5,
                       "certification_id":"CURRENT-CERT-001"}]}
            older={"version":2,"v99_validation":[{"company":"PSA",
                       "official_result":True,"actual":10,"raw_pred":10,
                       "certification_id":"OLDER-CERT-002"}]}
            (old/"learning_store.json").write_text(json.dumps(older),encoding="utf-8")
            (new/"learning_store.json").write_text(json.dumps(existing),encoding="utf-8")
            migration.migrate(old,new)
            after_first=(new/"learning_store.json").read_bytes()
            migration.migrate(old,new)
            after_second=json.loads((new/"learning_store.json").read_text(encoding="utf-8"))
            self.assertEqual(2,len(after_second["v99_validation"]))
            self.assertEqual(2,len(list((new/"MIGRATION_BACKUP").iterdir())))
            self.assertFalse((new/".tcg_migration.lock").exists())
            self.assertEqual(2,len(json.loads(after_first)["v99_validation"]))
    def test_protected_main_learning_post_discards_confirmed_evidence_on_save(self):
        """Static original-main evidence, NOT a live Lenovo or HTTP replay."""
        import ast
        code = forensic.checked_object(
            ROOT, forensic.PROTECTED_MAIN, "tcg_updater.py",
            "b48f86fe4cf60531ffb36e1f5340d5354980590c",
        ).decode("utf-8")
        tree = ast.parse(code)
        handlers = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not isinstance(test, ast.Compare):
                continue
            if not (isinstance(test.left, ast.Name) and
                    test.left.id == "post_path"):
                continue
            if not (len(test.comparators) == 1 and
                    isinstance(test.comparators[0], ast.Constant) and
                    test.comparators[0].value == "/api/learning-store"):
                continue
            handlers.append(node)
        self.assertEqual(1, len(handlers))
        target = handlers[0]
        assignments = [
            n for n in ast.walk(target)
            if isinstance(n, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id == "data" for t in n.targets)
            and isinstance(n.value, ast.Dict)
        ]
        self.assertEqual(1, len(assignments))
        keys = {
            k.value for k in assignments[0].value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        self.assertTrue({"v99_validation", "v30_validation", "v11_validation"} <= keys)
        self.assertNotIn("confirmed_samples", keys)
        saves = [
            n for n in ast.walk(target)
            if isinstance(n, ast.Call) and
            isinstance(n.func, ast.Name) and
            n.func.id == "save_json_atomic" and
            len(n.args) >= 2 and isinstance(n.args[0], ast.Name) and
            n.args[0].id == "LEARNING_STORE" and
            isinstance(n.args[1], ast.Name) and n.args[1].id == "data"
        ]
        self.assertEqual(1, len(saves))
        # This is a confirmed source-path overwrite risk, not a claim that
        # a real user's confirmed_samples have already been lost.

    def test_original_first_21_history_has_four_noop_git_commits(self):
        # An upload commit with unchanged tree cannot be counted as a
        # separately tested application release or new source version.
        noops = (
            ("53be359779a2c973be207d9ae6962b61f9df54f4",
             "a36fee19c11b6873ce09a0010e326846f16f6930"),
            ("aad00f455563964a8eb1b11508c8777a7581b57f",
             "a36fee19c11b6873ce09a0010e326846f16f6930"),
            ("736202295dbaae5877a74b00e1570cd61cb73d4a",
             "3bf7038754513a13abcc0654e653421f665d38bc"),
            ("01103e9a7bd265c8fca3133ae82b34a87b2b03ab",
             "445e02d64627afea02908ddcd8df8b13cbcb21bf"),
        )
        for commit, expected_tree in noops:
            with self.subTest(commit=commit):
                own_tree = forensic.git(ROOT, "rev-parse",
                                        commit + "^{tree}").decode().strip()
                parent = forensic.git(ROOT, "rev-parse",
                                      commit + "^").decode().strip()
                parent_tree = forensic.git(ROOT, "rev-parse",
                                           parent + "^{tree}").decode().strip()
                self.assertEqual(expected_tree, own_tree)
                self.assertEqual(expected_tree, parent_tree)
                self.assertEqual(b"", forensic.git(ROOT, "diff", "--name-only",
                                                     parent, commit))
        # Only this early historical subrange is assessed; do not assert that
        # all V1-V100 releases or the remaining 41-commit files were tested.

    def test_v31_android_launcher_failure_was_not_startup_blocking(self):
        # Pin the earliest Termux launcher without executing scripts.
        historical = forensic.checked_object(
            ROOT, "df9bf37ff7b5d6bb5dd802244aa6dc7356f96e6c",
            "START_TCG_UPDATER_ANDROID.sh",
            "8c887cf5f6d4a940ec709c65515560e437f334c3",
        ).decode("utf-8")
        current = forensic.checked_object(
            ROOT, forensic.PROTECTED_MAIN,
            "START_TCG_UPDATER_ANDROID.sh",
            "efd8ba0623f6459febb4f156c116b7a25cc41cfe",
        ).decode("utf-8")
        self.assertIn("python verify_all.py || echo", historical)
        self.assertEqual(
            "python tcg_updater.py",
            [line.strip() for line in historical.splitlines() if line.strip()][-1],
        )
        marker = "if ! python tablet_runtime_manifest.py --check --compile; then"
        self.assertIn(marker, current)
        guarded_block = current.split(marker, 1)[1].split("\nfi", 1)[0]
        self.assertIn("exit 1", guarded_block)
        self.assertNotIn("python verify_all.py || echo", current)
        # Current source guards do not establish Lenovo device execution.

    def test_migration_rejects_duplicate_and_nonfinite_json_without_any_writes(self):
        import tempfile
        import migrate_old_data as migration

        malformed = (
            '{"confirmed_samples":[{"cert_no":"KEEP"}],"confirmed_samples":[]}',
            '{"confirmed_samples":[{"features":{"surface_risk":9,"surface_risk":0}}]}',
            '{"confirmed_samples":[],"untrusted_score":NaN}',
            '{"confirmed_samples":[],"untrusted_score":Infinity}',
            '{"confirmed_samples":[],"untrusted_score":-Infinity}',
        )
        for target in ("old", "new"):
            for raw in malformed:
                with self.subTest(target=target, payload=raw), tempfile.TemporaryDirectory(
                        prefix="tcg-w001-strict-json-") as tmp:
                    old, new = Path(tmp) / "old", Path(tmp) / "new"
                    old.mkdir(); new.mkdir()
                    for folder in (old, new):
                        (folder / "tcg_updater.py").write_text("# fixture\n", encoding="utf-8")
                    clean = b'{"version":2,"confirmed_samples":[{"cert_no":"GOOD","company":"PSA","actual":9}]}'
                    (new / "learning_store.json").write_bytes(clean)
                    (old / "learning_store.json").write_text(
                        '{"version":2,"confirmed_samples":[]}', encoding="utf-8")
                    ((old if target == "old" else new) / "verification_history.json").write_text(
                        raw, encoding="utf-8")
                    old_before = (old / "learning_store.json").read_bytes()
                    with self.assertRaisesRegex(
                            ValueError, "migration_source_unreadable_or_invalid_json"):
                        migration.migrate(old, new)
                    self.assertEqual(clean, (new / "learning_store.json").read_bytes())
                    self.assertEqual(old_before, (old / "learning_store.json").read_bytes())
                    self.assertFalse((new / "MIGRATION_BACKUP").exists())
                    self.assertFalse((new / ".tcg_migration.lock").exists())

    def test_migration_strict_parser_accepts_valid_distinct_certificate_rows(self):
        import tempfile
        import migrate_old_data as migration

        with tempfile.TemporaryDirectory(prefix="tcg-w001-strict-valid-") as tmp:
            old, new = Path(tmp) / "old", Path(tmp) / "new"
            old.mkdir(); new.mkdir()
            for folder in (old, new):
                (folder / "tcg_updater.py").write_text("# fixture\n", encoding="utf-8")
            rows = [
                {"company":"PSA","cert_no":"CERT-ONE-01","actual":9,"verified":True},
                {"company":"PSA","cert_no":"CERT-TWO-02","actual":10,"verified":True},
            ]
            (old / "learning_store.json").write_text(
                json.dumps({"version":2,"confirmed_samples":rows}), encoding="utf-8")
            (new / "learning_store.json").write_text(
                '{"version":2,"confirmed_samples":[]}', encoding="utf-8")
            migration.migrate(old, new)
            saved = json.loads((new / "learning_store.json").read_text(encoding="utf-8"))
            self.assertEqual(rows, saved["confirmed_samples"])
            self.assertEqual(1, len(list((new / "MIGRATION_BACKUP").iterdir())))

    def test_scope_gaps_are_not_equated_with_absent_or_certified_releases(self):
        out=forensic.inspect(ROOT)
        self.assertEqual("HISTORICAL_SOURCE_DISCREPANCY_REPRODUCED_REVIEW_PENDING", out["status"])
        self.assertNotIn("accuracy_score", out["v100"])
        self.assertIsNone(out["quality_score"])


if __name__ == "__main__":
    unittest.main()
