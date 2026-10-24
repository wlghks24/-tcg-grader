import base64
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[2]

class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.policy='';self.scripts=[];self.current=None
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if tag=='meta' and str(attributes.get('http-equiv','')).casefold()=='content-security-policy':
            self.policy=attributes.get('content','')
        if tag=='script':self.current=None if 'src' in attributes else []
    def handle_data(self,data):
        if self.current is not None:self.current.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.current is not None:
            self.scripts.append(''.join(self.current));self.current=None

class InformationFilterTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_real_inline_filter_behavior(self):
        result=subprocess.run(['node','execution/tests/verify_info_filters_v655.js'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
    def test_every_inline_script_has_exact_csp_hash(self):
        parser=InlineScripts();parser.feed((ROOT/'index.html').read_text());parser.close()
        policy=parser.policy
        self.assertTrue(policy);self.assertTrue(parser.scripts)
        for script in parser.scripts:
            if not script.strip():continue
            digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
            self.assertIn("'sha256-"+digest+"'",policy)
        self.assertNotIn("'unsafe-inline'",policy.split('script-src ',1)[1].split(';',1)[0])
    def test_parser_handles_case_whitespace_end_tags_and_external_src(self):
        parser=InlineScripts()
        parser.feed('<SCRIPT>one &amp; two</SCRIPT ><script SrC="/x.js">external</script ><ScRiPt>three</sCrIpT\t>')
        parser.close()
        self.assertEqual(['one &amp; two','three'],parser.scripts)
