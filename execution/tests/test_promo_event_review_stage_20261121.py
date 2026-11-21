"""Offline fail-closed contract for separate, explicit review-only staging."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution import promo_event_review_stage as staging
from execution.promo_event_readonly_preflight import read_stable_snapshot


DATA = staging.SNAPSHOT


class StageCandidateTests(unittest.TestCase):
    def setUp(self):
        self.original = DATA.read_bytes()
        self.snapshot = json.loads(self.original.decode("utf-8"))

    def test_validated_stage_separates_products_without_overwriting_original(self):
        with tempfile.TemporaryDirectory(prefix="tcg-stage-") as folder:
            stage = Path(folder) / "candidate.json"
            report = staging.stage_candidate(DATA, stage)
            out = stage.read_bytes()
            saved = json.loads(out)
            self.assertEqual(self.original, DATA.read_bytes())
            self.assertEqual(staging.STATUS, report["status"])
            self.assertEqual(3, report["manual_review_queue_rows"])
            self.assertEqual(3, len(saved["product_release_review_queue"]))
            self.assertEqual(89, len(saved["items"]) + len(saved["archive_items"]))
            self.assertEqual(self.snapshot["updated_at"], saved["updated_at"])
            self.assertEqual(self.snapshot["updated_at"], report["source_updated_at"])
            self.assertEqual(hashlib.sha256(out).hexdigest(), report["stage_sha256"])
            self.assertEqual(hashlib.sha256(self.original).hexdigest(), report["input_sha256"])
            self.assertIs(report["publish_allowed"], False)
            self.assertIs(report["device_install_allowed"], False)
            self.assertIs(report["source_refresh_performed"], False)

    def test_unapproved_event_does_not_create_stage_or_modify_source(self):
        bad = deepcopy(self.snapshot)
        bad["items"].append({
            "game": "원피스 카드", "region": "US", "category": "promo",
            "name_ko": "검증되지 않은 이벤트", "start_date": "2026-11-21",
            "end_date": "2026-11-21", "source": "https://unapproved.invalid/event",
        })
        with tempfile.TemporaryDirectory(prefix="tcg-stage-invalid-") as folder:
            original = Path(folder) / "input.json"
            original.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            copy = original.read_bytes()
            target = Path(folder) / "stage.json"
            with self.assertRaises(ValueError):
                staging.stage_candidate(original, target)
            self.assertFalse(target.exists())
            self.assertEqual(copy, original.read_bytes())

    def test_existing_stage_never_overwritten_and_source_cannot_be_destination(self):
        with tempfile.TemporaryDirectory(prefix="tcg-stage-exclusive-") as folder:
            stage = Path(folder) / "stage.json"
            stage.write_bytes(b"EXISTING_REVIEW")
            with self.assertRaises(FileExistsError):
                staging.stage_candidate(DATA, stage)
            self.assertEqual(b"EXISTING_REVIEW", stage.read_bytes())
            with self.assertRaisesRegex(ValueError, "STAGE_CANNOT_REPLACE_SOURCE"):
                staging.stage_candidate(DATA, DATA)
            self.assertEqual(self.original, DATA.read_bytes())

    def test_changed_input_before_stage_creation_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="tcg-stage-stale-") as folder:
            target = Path(folder) / "stage.json"
            with patch.object(staging, "read_stable_snapshot", side_effect=[
                (self.original, deepcopy(self.snapshot)),
                (self.original + b"x", deepcopy(self.snapshot)),
            ]):
                with self.assertRaisesRegex(ValueError, "STAGE_SOURCE_CHANGED_BEFORE_WRITE"):
                    staging.stage_candidate(DATA, target)
            self.assertFalse(target.exists())
            self.assertEqual(self.original, DATA.read_bytes())

    def test_collector_is_invoked_with_explicit_write_false_only(self):
        import update_promo_events
        original = update_promo_events.refresh_auxiliary_coverage_metadata
        with tempfile.TemporaryDirectory(prefix="tcg-stage-nosync-") as folder:
            target = Path(folder) / "stage.json"
            with patch.object(
                update_promo_events, "refresh_auxiliary_coverage_metadata",
                wraps=original,
            ) as spy:
                staging.stage_candidate(DATA, target)
                self.assertEqual(1, spy.call_count)
                self.assertIs(spy.call_args.kwargs["write"], False)
                self.assertNotEqual(id(self.snapshot), id(spy.call_args.args[0]))
            self.assertEqual(self.original, DATA.read_bytes())

    def test_symlink_stage_and_symlink_parent_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="tcg-stage-symlink-") as folder:
            root = Path(folder)
            target = root / "alias.json"
            alias_dir = root / "dir_alias"
            try:
                target.symlink_to(DATA)
                alias_dir.symlink_to(DATA.parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unsupported")
            with self.assertRaisesRegex(ValueError, "STAGE_TARGET_SYMLINK"):
                staging.stage_candidate(DATA, target)
            with self.assertRaisesRegex(ValueError, "STAGE_PARENT_SYMLINK"):
                staging.stage_candidate(DATA, alias_dir / "candidate.json")
            self.assertEqual(self.original, DATA.read_bytes())

    def test_explicit_cli_stages_only_a_new_file_and_prints_nonpublish_status(self):
        import io
        with tempfile.TemporaryDirectory(prefix="tcg-stage-cli-") as folder:
            output = Path(folder) / "candidate.json"
            with patch("sys.stdout", new_callable=io.StringIO) as stream:
                result = staging.main(["--output", str(output)])
            self.assertEqual(0, result)
            message = json.loads(stream.getvalue())
            self.assertEqual(staging.STATUS, message["status"])
            self.assertTrue(message["review_required"])
            self.assertIs(message["publish_allowed"], False)
            self.assertIs(message["device_install_allowed"], False)
            self.assertTrue(output.exists())
            self.assertEqual(self.original, DATA.read_bytes())


if __name__ == "__main__":
    unittest.main()
