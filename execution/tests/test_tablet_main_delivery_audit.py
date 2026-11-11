"""The source-only CI report must never certify a Lenovo installation."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from execution.tablet_main_delivery_audit import RULES, inspect


class MainAutoPickupContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, rules in RULES.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(rules.values()) + "\n", encoding="utf-8")

    def report(self, sha="a" * 40, ref="refs/heads/main"):
        return inspect(self.root, sha=sha, git_ref=ref)

    def test_main_contract_pass_is_not_device_install(self):
        r = self.report()
        self.assertTrue(r["static_auto_pickup_contract_pass"])
        self.assertTrue(r["code_ready_on_main"])
        self.assertIs(r["physical_tablet_verified"], False)
        self.assertIsNone(r["installed_sha"])
        self.assertIsNone(r["running_server_sha"])
        self.assertIs(r["reboot_verified"], False)

    def test_pr_commit_is_not_deployable_main(self):
        r = self.report(ref="refs/pull/123/merge")
        self.assertTrue(r["static_auto_pickup_contract_pass"])
        self.assertFalse(r["code_ready_on_main"])
        self.assertEqual(r["source_scope"], "review_candidate")

    def test_removed_scheduler_or_handoff_contract_fails(self):
        for name, marker in (
            ("TABLET_SCHEDULED_UPDATE.sh", RULES["TABLET_SCHEDULED_UPDATE.sh"]["canonical_fetch"]),
            ("execution/tablet_local_automation.py", RULES["execution/tablet_local_automation.py"]["running_sha_identity"]),
            ("ANDROID_UPDATE_AND_START.sh", RULES["ANDROID_UPDATE_AND_START.sh"]["safe_fast_forward"]),
        ):
            p = self.root / name
            source = p.read_text(encoding="utf-8")
            p.write_text(source.replace(marker, "BROKEN"), encoding="utf-8")
            with self.subTest(name=name):
                self.assertFalse(self.report()["static_auto_pickup_contract_pass"])
            p.write_text(source, encoding="utf-8")

    def test_unsafe_force_update_fails(self):
        p = self.root / "ANDROID_UPDATE_AND_START.sh"
        p.write_text(p.read_text(encoding="utf-8") + "\ngit reset --hard\n", encoding="utf-8")
        self.assertFalse(self.report()["static_auto_pickup_contract_pass"])

    def test_missing_or_symlinked_source_fails(self):
        p = self.root / "main"
        p.unlink()
        self.assertFalse(self.report()["static_auto_pickup_contract_pass"])
        p.symlink_to("TABLET_SCHEDULED_UPDATE.sh")
        self.assertFalse(self.report()["static_auto_pickup_contract_pass"])

    def test_invalid_sha_cannot_pass(self):
        r = self.report(sha="unavailable")
        self.assertFalse(r["static_auto_pickup_contract_pass"])
        self.assertIsNone(r["source_sha"])


if __name__ == "__main__":
    unittest.main()
