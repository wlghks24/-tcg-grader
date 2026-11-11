"""Fail-closed Lenovo/Termux installation entrypoint contract tests."""
from pathlib import Path
import os
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT/'INSTALL_LENOVO_TCG_V1004.sh'

class LenovoInstallV1004Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SCRIPT.read_text(encoding='utf-8')

    def test_shell_parses_and_help_is_read_only(self):
        subprocess.run(['bash','-n',str(SCRIPT)],check=True)
        result=subprocess.run(['bash',str(SCRIPT),'--help'],capture_output=True,text=True,check=True)
        self.assertIn('http://127.0.0.1:8765/index.html',result.stdout)

    def test_non_termux_install_fails_closed(self):
        env=dict(os.environ)
        env.pop('PREFIX',None)
        for action in ('--check','--install','--status'):
            with self.subTest(action=action):
                result=subprocess.run(['bash',str(SCRIPT),action],env=env,capture_output=True,text=True)
                self.assertEqual(2,result.returncode)
                self.assertIn('Termux',result.stderr)

    def test_existing_source_and_data_preserved(self):
        for unsafe in ('git reset --hard','git clean -fd','rm -rf','curl | bash','wget -O-','pkg upgrade -y'):
            self.assertNotIn(unsafe,self.source)
        for required in ('origin_is_official','branch', 'diff --cached --name-only',
                         'tablet_runtime_manifest.py --check --compile',
                         'bash VERIFY_TABLET_FINAL.sh','bash main auto-install',
                         'tablet_runtime_probe.py --require-health --require-runtime-contract'):
            self.assertIn(required,self.source)

    def test_app_and_device_proof_not_forged(self):
        self.assertIn('Chrome 홈 화면 설치 및 재부팅 후 자동실행은 실제 태블릿에서 별도로 확인',self.source)
        self.assertNotIn('physical_tablet_verified=true',self.source)

if __name__=='__main__':unittest.main()
