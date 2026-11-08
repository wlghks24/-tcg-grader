"""V976 offline real-Git tests: never install or signal a tablet."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import tablet_release_install_v976 as release


class ReleaseInstallV976Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tcg-v976-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.live = root / "live"
        self.stage = root / "stage"
        self.live.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "TCG fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.live / "execution").mkdir()
        (self.live / "execution" / "runtime.py").write_text("V=1\n")
        (self.live / "v31_최종검증보고서.json").write_text('{"report":"original"}\n')
        (self.live / "labels.json").write_text('{"labels":[1]}\n')
        (self.live / "integrity_manifest.json").write_text('{"files":{}}\n')
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture baseline")
        self.base = self.git("rev-parse", "HEAD")
        archive = self.live / release.ARCHIVED_REPORT
        archive.parent.mkdir(parents=True)
        shutil.move(self.live / release.OLD_REPORT, archive)
        (self.live / "execution" / "runtime.py").write_text("V=975\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture V975")
        self.v975 = self.git("rev-parse", "HEAD")
        self.installer_bytes = Path(release.__file__).read_bytes()
        self.test_bytes = Path(__file__).read_bytes()
        (self.live / release.SELF).write_bytes(self.installer_bytes)
        (self.live / release.TEST).parent.mkdir(parents=True, exist_ok=True)
        (self.live / release.TEST).write_bytes(self.test_bytes)
        (self.live / release.WORKFLOW).parent.mkdir(parents=True, exist_ok=True)
        (self.live / release.WORKFLOW).write_bytes((Path(__file__).resolve().parents[2] / release.WORKFLOW).read_bytes())
        manifest = {"files": {
            release.SELF: {"sha256": hashlib.sha256(self.installer_bytes).hexdigest(),
                           "bytes": len(self.installer_bytes)},
            release.TEST: {"sha256": hashlib.sha256(self.test_bytes).hexdigest(),
                           "bytes": len(self.test_bytes)}}}
        (self.live / "integrity_manifest.json").write_text(json.dumps(manifest) + "\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture exact V976 child")
        self.target = self.git("rev-parse", "HEAD")
        self.git("worktree", "add", "--detach", "-q", str(self.stage), self.target)
        self.git("switch", "-q", "--detach", self.base)
        self.source_file = self.stage / release.SELF
        self.p1 = patch.object(release, "V927", self.base)
        self.p2 = patch.object(release, "V975", self.v975)
        self.p3 = patch.object(release, "V976_BASE", self.v975)
        self.p1.start()
        self.p2.start()
        self.p3.start()
        self.addCleanup(self.p1.stop)
        self.addCleanup(self.p2.stop)
        self.addCleanup(self.p3.stop)

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.live), *args],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, (args, p.stderr))
        return p.stdout.strip()

    def inspect(self):
        return release.inspect(self.live, self.base, self.target,
                               source_file=self.source_file)

    def test_readonly_preflight_and_historical_report_copy(self):
        before = (self.git("status", "--porcelain"), self.git("rev-parse", "HEAD"),
                  (self.live / "labels.json").read_bytes())
        r = self.inspect()
        after = (self.git("status", "--porcelain"), self.git("rev-parse", "HEAD"),
                 (self.live / "labels.json").read_bytes())
        self.assertEqual(before, after)
        self.assertEqual(r["status"], "READY_FOR_EXPLICIT_DEVICE_APPLY")
        self.assertTrue(r["historical_report_preserved"])
        self.assertFalse(r["installation_completed"])

    def test_mutable_json_is_not_overwritten(self):
        (self.live / "labels.json").write_text('{"labels":[1,2,3]}\n')
        self.assertEqual(self.inspect()["local_mutable_root_json_count"], 1)
        self.assertEqual((self.live / "labels.json").read_text(), '{"labels":[1,2,3]}\n')

    def test_changed_historical_report_is_hard_hold(self):
        (self.live / release.OLD_REPORT).write_text('{"report":"private edit"}\n')
        with self.assertRaisesRegex(release.ReleaseHold, "OVERLAPPING_LOCAL_EDITS"):
            self.inspect()

    def test_untracked_and_ignored_candidate_collisions_hold(self):
        path = self.live / release.SELF
        path.write_text("private collision")
        with self.assertRaisesRegex(release.ReleaseHold, "UNTRACKED_COLLISION"):
            self.inspect()
        (self.live / ".git" / "info" / "exclude").write_text(release.SELF + "\n")
        with self.assertRaisesRegex(release.ReleaseHold, "IGNORED_COLLISION"):
            self.inspect()

    def test_source_tamper_and_unreviewed_extra_target_rejected(self):
        self.source_file.write_bytes(self.installer_bytes + b"\n# tamper")
        with self.assertRaisesRegex(release.ReleaseHold, "STAGED_INSTALLER_BYTES_CHANGED"):
            self.inspect()
        self.source_file.write_bytes(self.installer_bytes)
        self.git("switch", "-q", "--detach", self.target)
        (self.live / "index.html").write_text("<script>unreviewed</script>")
        self.git("add", "-A")
        self.git("commit", "-qm", "unreviewed target extension")
        extra = self.git("rev-parse", "HEAD")
        self.git("switch", "-q", "--detach", self.base)
        with self.assertRaisesRegex(release.ReleaseHold, "TARGET_NOT_EXACT_REVIEWED_V976_PATCH_CHILD"):
            release.inspect(self.live, self.base, extra, source_file=self.source_file)

    def test_staged_edit_and_stale_base_hold(self):
        (self.live / "labels.json").write_text('{"labels":[99]}\n')
        self.git("add", "labels.json")
        with self.assertRaisesRegex(release.ReleaseHold, "STAGED_DEVICE_EDITS"):
            self.inspect()
        with self.assertRaisesRegex(release.ReleaseHold, "LIVE_HEAD_CHANGED"):
            release.inspect(self.live, self.target, self.target,
                            source_file=self.source_file)

    def test_backup_verifies_every_root_json_without_extraction(self):
        with tempfile.TemporaryDirectory(dir=self.live.parent) as path:
            backup = Path(path)
            import tarfile
            with tarfile.open(backup / "runtime-json.tar.gz", "w:gz") as archive:
                for p in sorted(self.live.glob("*.json")):
                    archive.add(p, arcname=p.name, recursive=False)
            (backup / "BASE_SHA.txt").write_text(self.base)
            release.verify_backup(self.live, backup)
            (self.live / "labels.json").write_text('{"labels":[8]}\n')
            with self.assertRaisesRegex(release.ReleaseHold, "BACKUP_MISMATCH"):
                release.verify_backup(self.live, backup)

    def test_no_apply_or_stop_in_default_cli(self):
        with patch.object(release, "inspect", return_value={"status": "READY_FOR_EXPLICIT_DEVICE_APPLY"}):
            with patch.object(release, "apply") as action:
                code = release.main(["--repo", str(self.live), "--expected-base", self.base,
                                     "--target-sha", self.target])
                self.assertEqual(code, 0)
                action.assert_not_called()
                code = release.main(["--repo", str(self.live), "--expected-base", self.base,
                                     "--target-sha", self.target, "--apply"])
                self.assertEqual(code, 2)
                action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
