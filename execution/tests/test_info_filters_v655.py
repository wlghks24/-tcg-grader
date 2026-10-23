import base64
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[2]
class InformationFilterTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_real_inline_filter_behavior(self):
        result=subprocess.run(['node','execution/tests/verify_info_filters_v655.js'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
    def test_every_inline_script_has_exact_csp_hash(self):
        html=(ROOT/'index.html').read_text()
        policy=re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"',html).group(1)
        for attributes,script in re.findall(r'<script([^>]*)>(.*?)</script>',html,re.S):
            if re.search(r'\bsrc\s*=',attributes) or not script.strip():continue
            digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
            self.assertIn("'sha256-"+digest+"'",policy)
        self.assertNotIn("'unsafe-inline'",policy.split('script-src ',1)[1].split(';',1)[0])
