"""Read-only contract checks for the Lenovo Termux installation entrypoint."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]
INSTALL=ROOT/"scripts/TCG_LENOVO_INSTALL.sh"

class LenovoTermuxInstallerTests(unittest.TestCase):
    def test_bash_syntax(self):
        self.assertEqual(0, subprocess.run(["bash","-n",str(INSTALL)],check=False).returncode)

    def test_help_does_not_mutate_files(self):
        result=subprocess.run(["bash",str(INSTALL),"--help"],cwd=ROOT,
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertIn("--install",result.stdout)
        self.assertIn("--verify",result.stdout)

    def test_install_is_explicit_official_main_and_no_destructive_reset(self):
        body=INSTALL.read_text(encoding="utf-8")
        self.assertIn("https://github.com/wlghks24/-tcg-grader.git",body)
        self.assertIn("git clone --branch main --single-branch",body)
        self.assertIn("git -C \"$PROJECT\" remote get-url origin",body)
        self.assertIn("bash ANDROID_UPDATE_AND_START.sh",body)
        self.assertIn("tablet_runtime_manifest.py --check --compile",body)
        self.assertIn("tablet_runtime_probe.py",body)
        self.assertIn("--require-health",body)
        self.assertIn("--require-runtime-contract",body)
        for forbidden in ("git reset --hard", "git clean -fd", "rm -rf", "curl | bash", "wget | bash"):
            self.assertNotIn(forbidden,body)
        self.assertTrue(body.index("case \"$MODE\"") < body.index("pkg install -y git python"))

    def test_untrusted_modes_do_not_start_installer(self):
        result=subprocess.run(["bash",str(INSTALL),"--unsupported"],cwd=ROOT,
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(2,result.returncode)
        self.assertIn("--install",result.stderr)

if __name__=="__main__":
    unittest.main()
