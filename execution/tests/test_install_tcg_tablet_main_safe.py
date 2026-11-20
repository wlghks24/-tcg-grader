"""Fail-closed local GitHub-main tablet staging checks; no actual tablet access."""
from pathlib import Path
import subprocess
import tempfile
import unittest

INSTALL = Path(__file__).resolve().parents[1] / 'INSTALL_TCG_TABLET_MAIN_SAFE.sh'


class MainTabletInstallStageTests(unittest.TestCase):
    def test_bash_syntax(self):
        subprocess.run(['bash', '-n', str(INSTALL)], check=True)

    def test_non_termux_cannot_install_or_touch_existing_data(self):
        with tempfile.TemporaryDirectory() as temp:
            output = subprocess.run(
                ['bash', str(INSTALL), '--install'],
                cwd=temp, capture_output=True, text=True, timeout=10,
                env={'HOME': temp, 'PATH': '/usr/bin:/bin', 'PREFIX': '/usr'},
            )
            self.assertEqual(2, output.returncode)
            self.assertIn('[HOLD]', output.stderr)
            self.assertEqual([], list(Path(temp).iterdir()))

    def test_only_official_pinned_main_and_verified_fresh_directory(self):
        source = INSTALL.read_text(encoding='utf-8')
        for required in (
            'https://github.com/wlghks24/-tcg-grader.git',
            '"$ACTUAL" = "$PIN"',
            '"$TRACKED" = "$PIN"',
            '"$ORIGIN" = "$OFFICIAL"',
            'VERIFY_TABLET_FINAL.sh',
            'tablet_main_ci_gate.py',
            'if [ "$MODE" = \'--install\' ] && [ -z "$PIN" ]; then',
            '[[ "$PIN" =~ ^[0-9a-f]{40}$ ]]',
            "python -c 'from PIL import Image'",
            '[STAGED_OK]',
            'git clone --branch main --single-branch',
        ):
            self.assertIn(required, source)
        for forbidden in (
            'reset --hard', 'git checkout -f', 'rm -rf',
            'curl | bash', 'wget | bash',
            'ANDROID_AUTO_START_INSTALL.sh',
            'python -m pip install',
        ):
            self.assertNotIn(forbidden, source)

    def test_install_missing_approval_fails_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = subprocess.run(
                ['bash', str(INSTALL), '--install'],
                cwd=temp, capture_output=True, text=True, timeout=10,
                env={'HOME': temp, 'PATH': '/usr/bin:/bin', 'PREFIX': '/usr'},
            )
            self.assertEqual(2, output.returncode)
            self.assertIn('explicitly reviewed', output.stderr)
            self.assertEqual([], list(Path(temp).iterdir()))

    def test_malformed_main_sha_fails_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = subprocess.run(
                ['bash', str(INSTALL), '--install', '../bad'],
                cwd=temp, capture_output=True, text=True, timeout=10,
                env={'HOME': temp, 'PATH': '/usr/bin:/bin', 'PREFIX': '/usr'},
            )
            self.assertEqual(2, output.returncode)
            self.assertIn('Invalid approved main SHA', output.stderr)
            self.assertEqual([], list(Path(temp).iterdir()))


if __name__ == '__main__':
    unittest.main()
