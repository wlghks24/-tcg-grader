import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_repair import stage,RepairHold
class RepairTests(unittest.TestCase):
 def test_candidate_preserves_original(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.py';p.write_bytes(b'x=1\n')
   r=stage(p,b'x=1\n',{'code':'x=2\n','explanation':'change','tests_needed':'check x'},Path(td)/'out',Path('a.py'),'fixture')
   self.assertEqual(b'x=1\n',p.read_bytes());self.assertEqual('NOT_RUN',r['behavioral_tests'])
   self.assertIn('+x=2',(Path(td)/'out/proposal.patch').read_text())
 def test_bad_syntax_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.py';p.write_bytes(b'x=1\n')
   with self.assertRaises(SyntaxError):stage(p,p.read_bytes(),{'code':'def :','explanation':'','tests_needed':''},Path(td)/'out',Path('a.py'),'fixture')
   self.assertFalse((Path(td)/'out').exists())
 def test_changed_source_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.py';p.write_bytes(b'x=3\n')
   with self.assertRaises(RepairHold):stage(p,b'x=1\n',{'code':'x=2','explanation':'','tests_needed':''},Path(td)/'out',Path('a.py'),'fixture')
