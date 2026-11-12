"""V1011 non-destructive runtime JSON update, real Git FF smoke tests."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "ANDROID_UPDATE_AND_START.sh"
OFFICIAL = "https://github.com/wlghks24/-tcg-grader.git"


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


class SafeRuntimeFastForwardV1011(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="v1011-git-")
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        self.remote, self.device = home / "remote", home / "device"
        self.remote.mkdir()
        git("init", "-b", "main", cwd=self.remote)
        git("config", "user.name", "V1011 Test", cwd=self.remote)
        git("config", "user.email", "test@example.invalid", cwd=self.remote)
        (self.remote / "ANDROID_UPDATE_AND_START.sh").write_bytes(UPDATER.read_bytes())
        (self.remote / "VERIFY_TABLET_FINAL.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.remote / "START_TCG_UPDATER_ANDROID.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.remote / "learning_store.json").write_text('{"learned":0}\n')
        (self.remote / "code.txt").write_text("v1\n")
        git("add", ".", cwd=self.remote)
        git("commit", "-m", "base", cwd=self.remote)
        git("clone", str(self.remote), str(self.device))
        git("config", "user.name", "V1011 Local", cwd=self.device)
        git("config", "user.email", "local@example.invalid", cwd=self.device)
        self.real_git = shutil.which("git")
        self.bin = home / "bin"
        self.bin.mkdir()
        shim = self.bin / "git"
        shim.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = remote ] && [ "$2" = get-url ]; then\n'
            '  echo "https://github.com/wlghks24/-tcg-grader.git"\n'
            '  exit 0\n'
            'fi\n'
            'if [ "$1" = fetch ] && [ "$2" = "https://github.com/wlghks24/-tcg-grader.git" ]; then\n'
            '  shift; shift\n'
            '  exec "$REAL_GIT" fetch "$TEST_REMOTE" "$@"\n'
            'fi\n'
            'exec "$REAL_GIT" "$@"\n'
        )
        shim.chmod(0o755)
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            REAL_GIT=self.real_git,
            TEST_REMOTE=str(self.remote),
            TCG_UPDATE_ONLY="1",
            TMPDIR=str(home),
        )

    def remote_commit(self, filename: str, value: str):
        (self.remote / filename).write_text(value)
        git("add", ".", cwd=self.remote)
        git("commit", "-m", "remote-update", cwd=self.remote)
        return git("rev-parse", "HEAD", cwd=self.remote)

    def run_update(self) -> str:
        result = subprocess.run(["bash", "ANDROID_UPDATE_AND_START.sh"],
                                cwd=self.device, env=self.env,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_code_only_fast_forward_preserves_dirty_learning_bytes(self):
        original = b'{"learned":321,"manual_grade":"keep"}\n'
        (self.device / "learning_store.json").write_bytes(original)
        new = self.remote_commit("code.txt", "v2\n")
        out = self.run_update()
        self.assertEqual(new, git("rev-parse", "HEAD", cwd=self.device), out)
        self.assertEqual(original, (self.device / "learning_store.json").read_bytes())
        self.assertNotIn("normalize_runtime", out)
        self.assertFalse((self.device / ".tcg_runtime_preserved").exists())

    def test_incoming_changes_to_dirty_runtime_json_hold_before_checkout(self):
        original = b'{"learned":321}\n'
        (self.device / "learning_store.json").write_bytes(original)
        before = git("rev-parse", "HEAD", cwd=self.device)
        self.remote_commit("learning_store.json", '{"learned":0,"schema":2}\n')
        out = self.run_update()
        self.assertIn("데이터 마이그레이션", out)
        self.assertEqual(before, git("rev-parse", "HEAD", cwd=self.device))
        self.assertEqual(original, (self.device / "learning_store.json").read_bytes())

    def test_detached_head_is_not_auto_rebound(self):
        git("checkout", "--detach", cwd=self.device)
        self.remote_commit("code.txt", "v2\n")
        before = git("rev-parse", "HEAD", cwd=self.device)
        out = self.run_update()
        self.assertIn("detached", out)
        self.assertEqual(before, git("rev-parse", "HEAD", cwd=self.device))
        self.assertEqual("", git("branch", "--show-current", cwd=self.device))

    def test_diverged_main_fails_closed(self):
        (self.device / "local-note.txt").write_text("valuable local commit\n")
        git("add", ".", cwd=self.device)
        git("commit", "-m", "local-only", cwd=self.device)
        before = git("rev-parse", "HEAD", cwd=self.device)
        self.remote_commit("code.txt", "v2\n")
        out = self.run_update()
        self.assertIn("fast-forward", out)
        self.assertEqual(before, git("rev-parse", "HEAD", cwd=self.device))
        self.assertEqual("valuable local commit\n", (self.device / "local-note.txt").read_text())

    def test_dirty_source_code_blocks_automatic_update(self):
        (self.device / "code.txt").write_text("local code change\n")
        before = git("rev-parse", "HEAD", cwd=self.device)
        self.remote_commit("code.txt", "v2\n")
        out = self.run_update()
        self.assertIn("코드/설정 추적파일", out)
        self.assertEqual(before, git("rev-parse", "HEAD", cwd=self.device))
        self.assertEqual("local code change\n", (self.device / "code.txt").read_text())

    def test_runtime_symlink_blocks_update(self):
        (self.device / "learning_store.json").unlink()
        target = self.device / "device_learning_keep.json"
        target.write_text('{"keep":true}\n')
        (self.device / "learning_store.json").symlink_to(target.name)
        before = git("rev-parse", "HEAD", cwd=self.device)
        self.remote_commit("code.txt", "v2\n")
        out = self.run_update()
        self.assertIn("심볼릭 링크", out)
        self.assertEqual(before, git("rev-parse", "HEAD", cwd=self.device))
        self.assertTrue((self.device / "learning_store.json").is_symlink())
        self.assertEqual('{"keep":true}\n', target.read_text())

    def test_no_live_normalization_in_update_flow(self):
        source = UPDATER.read_text()
        self.assertIn('git diff --quiet "$local_head" "$merge_head" -- "$changed"', source)
        self.assertIn('git merge-base --is-ancestor "$local_head" "$merge_head"', source)
        self.assertNotIn('if ! backup_and_normalize_runtime "$runtime_dirty_paths"', source)
        self.assertNotIn('git reset --hard', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
