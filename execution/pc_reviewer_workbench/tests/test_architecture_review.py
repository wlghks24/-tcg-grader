import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_review import analyze, write_outputs, branch_inventory
from local_review import review

BODY=b'def calculate(x):\n    y=x+1\n    z=y*2\n    return z\n'
class ArchitectureTests(unittest.TestCase):
    def test_duplicate_body_different_names(self):
        r=analyze([('a.py',BODY),('b.py',BODY.replace(b'calculate',b'other'))],[])
        self.assertEqual(1,len(r['duplicate_functions']))
        self.assertEqual('REVIEW_NOT_SAFE_TO_MERGE',r['duplicate_functions'][0]['state'])
    def test_different_constants_not_clone(self):
        self.assertFalse(analyze([('a.py',BODY),('b.py',BODY.replace(b'+1',b'+9'))],[])['duplicate_functions'])
    def test_trivial_pass_not_duplicate(self):
        self.assertFalse(analyze([('a.py',b'def a(): pass\ndef b(): pass\n')],[])['duplicate_functions'])
    def test_nested_scopes_named(self):
        r=analyze([('a.py',b'class A:\n def f(self):\n  def g():\n   return h()\n  return g()\n')],[])
        fs={x['name']:x for x in r['modules'][0]['functions']}
        self.assertEqual(['g'],fs['A.f']['calls'])
        self.assertEqual(['h'],fs['A.f.g']['calls'])
    def test_transitive_impact_cycle(self):
        r=analyze([('a.py',b'import b\n'),('b.py',b'import c\n'),('c.py',b'import a\n')],[])
        self.assertEqual(['a.py','b.py'],r['reverse_import_impact']['c.py'])
    def test_invalid_encoding_and_syntax(self):
        r=analyze([('a.py',b'\xff'),('b.py',b'def :')],[])
        self.assertTrue(all(m['state']=='PARSE_FAILED' for m in r['modules']))
    def test_priority_and_protected(self):
        r=analyze([], [{'path':'a.py','line':1,'state':'REVIEW_REQUIRED','rule':'PY_SYNTAX','detail':'bad'}],{'a.py'})
        self.assertEqual('P0',r['tasks'][0]['priority']);self.assertTrue(r['tasks'][0]['protected'])
    def test_html_escapes_code(self):
        with tempfile.TemporaryDirectory() as td:
            r=analyze([('<script>.py',BODY)],[])
            write_outputs(Path(td),r)
            self.assertIn('&lt;script&gt;.py',Path(td,'architecture.html').read_text())
    def test_integrated_review_preserves_source(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td,'src');src.mkdir();Path(src,'a.py').write_bytes(BODY)
            out=Path(td,'out');r=review(src,out)
            self.assertEqual(BODY,Path(src,'a.py').read_bytes())
            self.assertTrue((out/'architecture.json').is_file())
            self.assertTrue((out/'REPAIR_PLAN.md').is_file())
            self.assertEqual(1,r['architecture_summary']['functions'])
    def test_non_git_marked_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual('UNAVAILABLE',branch_inventory(Path(td))['state'])

    def test_relative_import_not_claimed_absolute(self):
        r=analyze([('a.py',b'from .b import f\n'),('b.py',BODY)],[])
        self.assertEqual([],r['import_edges'])

    def test_unmerged_local_branch_is_reported_without_checkout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=src,stderr=subprocess.DEVNULL)
            git('init');git('config','user.email','test@example.invalid');git('config','user.name','Fixture')
            (src/'a.py').write_bytes(BODY);git('add','.');git('commit','-m','base')
            base=git('rev-parse','HEAD').decode().strip()
            git('checkout','-b','pending');(src/'b.py').write_bytes(BODY)
            git('add','.');git('commit','-m','pending');git('checkout','--detach',base)
            before=git('rev-parse','HEAD')
            result=branch_inventory(src)
            self.assertEqual('LOCAL_REFS_CHECKED',result['state'])
            self.assertEqual(1,result['unmerged_refs'][0]['ref_only_commits'])
            self.assertEqual(before,git('rev-parse','HEAD'))
