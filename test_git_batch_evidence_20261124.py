import hashlib, subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from execution import git_batch_evidence as m
class TestBatch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.cwd=self.tmp.name; self.root=Path(self.cwd)
        self.git('init','-q'); self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        self.names=['a.txt','space name.txt','한글.txt','empty','bin','sub/x']
        (self.root/'sub').mkdir()
        for i,p in enumerate(self.names): (self.root/p).write_bytes(b'' if p=='empty' else bytes([i,0,10,255])+p.encode())
        (self.root/'old').write_text('gone'); self.git('add','.');self.git('commit','-qm','old');self.a=self.git('rev-parse','HEAD').decode().strip()
        (self.root/'a.txt').write_text('new');(self.root/'old').unlink();(self.root/'new').write_text('added');self.git('add','-A');self.git('commit','-qm','new');self.b=self.git('rev-parse','HEAD').decode().strip()
    def git(self,*a):return subprocess.check_output(['git',*a],cwd=self.cwd)
    def batch(self,p):return m.batch_digests(self.a,self.b,p,cwd=self.cwd)
    def fallback(self,p):return m.digests_with_fallback(self.a,self.b,p,cwd=self.cwd)
    def legacy(self,p):return m.legacy_digests(self.a,self.b,p,cwd=self.cwd)
    def test_binary_unicode_empty_parity(self): self.assertEqual(self.batch(self.names),self.legacy(self.names))
    def test_changed_blob(self): self.assertNotEqual(*self.batch(['a.txt'])['a.txt'])
    def test_missing_added_deleted(self):
        for name in ['new','old','missing']:
            with self.subTest(name=name):
                self.assertEqual(self.batch([name]),self.legacy([name]))
                self.assertEqual(self.fallback([name]),self.legacy([name]))
    def test_mixed_existing_and_missing(self):
        names=self.names+['old','new','missing'];self.assertEqual(self.batch(names),self.legacy(names))
    def test_missing_status_drift(self):
        with self.assertRaises(m.BatchRejected):m._read_rows(b'x missing\n',[(b'y',None)])
    def test_tree_fallback(self):
        with self.assertRaises(m.BatchRejected):self.batch(['sub'])
        self.assertEqual(self.fallback(['sub']),self.legacy(['sub']))
    def test_replacement_parity(self):
        self.git('replace',self.a,self.b)
        self.assertEqual(self.batch(self.names),self.legacy(self.names))
    def test_invalid_paths(self):
        for p in ['../x','/a','a\nb','x\x00z','a//b','']:
            with self.subTest(p=p),self.assertRaises(m.BatchRejected):self.batch([p])
    def test_unpinned_ref(self):
        with self.assertRaises(m.BatchRejected):m.batch_digests('HEAD',self.b,['a.txt'],cwd=self.cwd)
    def test_duplicate(self):
        with self.assertRaises(m.BatchRejected):self.batch(['a.txt','a.txt'])
    def test_size_bound(self):
        with patch.object(m,'MAX_BLOB',1),self.assertRaises(m.BatchRejected):self.batch(['bin'])
    def test_frame_truncation(self):
        with self.assertRaises(m.BatchRejected):m._read_rows(b'a'*40+b' blob 4\nabc\n',[(b'a'*40,4)])
    def test_extra_bytes(self):
        with self.assertRaises(m.BatchRejected):m._read_rows(b'a'*40+b' blob 1\nx\nextra',[(b'a'*40,1)])
    def test_meta_drift(self):
        with self.assertRaises(m.BatchRejected):m._read_rows(b'b'*40+b' blob 1\nx\n',[(b'a'*40,1)])
    def test_git_failure_fallback(self):
        with patch.object(m,'batch_digests',side_effect=subprocess.CalledProcessError(1,'git')):
            self.assertEqual(m.digests_with_fallback(self.a,self.b,['a.txt'],cwd=self.cwd,legacy=lambda:'old'),'old')
    def test_no_result_cache_after_replace(self):
        old=self.batch(['a.txt']);self.git('replace',self.a,self.b);new=self.batch(['a.txt']);self.assertNotEqual(old,new)
    def test_symlink_blob(self):
        (self.root/'link').symlink_to('a.txt');self.git('add','link');self.git('commit','-qm','symlink');self.a=self.b=self.git('rev-parse','HEAD').decode().strip()
        self.assertEqual(self.batch(['link']),self.legacy(['link']))
if __name__=='__main__':unittest.main()
