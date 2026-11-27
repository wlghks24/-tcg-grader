from execution.tests.test_successor_git_reads_20261122 import _write_fixture_object
import hashlib, subprocess,tempfile,unittest, zlib
from pathlib import Path
from unittest.mock import patch, Mock
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


class BatchIntegrityTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.root=Path(t.name)
        self.git('init','-q'); self.git('config','user.name','Fixture'); self.git('config','user.email','test@example.invalid')
        (self.root/'a').write_bytes(b'first'); self.git('add','a'); self.git('commit','-qm','first')
        self.a=self.git('rev-parse','HEAD').strip().decode(); self.oid=self.git('rev-parse','HEAD:a').strip().decode()
        (self.root/'a').write_bytes(b'other'); self.git('commit','-qam','second'); self.b=self.git('rev-parse','HEAD').strip().decode()
        self.oid2=self.git('rev-parse','HEAD:a').strip().decode()
    def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.PIPE)
    def batch(self):return m.batch_digests(self.a,self.b,['a'],cwd=self.root)
    def corrupt(self):
        _write_fixture_object(self.root/'.git/objects'/self.oid[:2]/self.oid[2:],zlib.compress(b'blob 5\0wrong'))
        self.assertEqual(self.git('show',self.a+':a'),b'wrong')
    def test_corrupt_blob_rejected(self):
        self.corrupt()
        with self.assertRaises(m.BatchRejected):self.batch()
    def test_corruption_does_not_trigger_legacy_fallback(self):
        self.corrupt(); fallback=Mock(return_value={'a':('forged','forged')})
        with self.assertRaises(m.BatchRejected):m.digests_with_fallback(self.a,self.b,['a'],cwd=self.root,legacy=fallback)
        fallback.assert_not_called()
    def test_blob_replace_rejected(self):
        self.git('replace',self.oid,self.oid2);self.assertEqual(self.git('show',self.a+':a'),b'other')
        with self.assertRaises(m.BatchRejected):self.batch()
    def test_mismatched_frame_content_rejected(self):
        with self.assertRaises(m.BatchRejected):m._read_rows(self.oid.encode()+b' blob 5\nwrong\n',[(self.oid.encode(),5)])
    def test_valid_frame(self):
        self.assertEqual(m._read_rows(self.oid.encode()+b' blob 5\nfirst\n',[(self.oid.encode(),5)]),[hashlib.sha256(b'first').hexdigest()])
    def test_clean_batch_parity(self):self.assertEqual(self.batch(),m.legacy_digests(self.a,self.b,['a'],cwd=self.root))
    def test_commit_replace_parity(self):
        self.git('replace',self.a,self.b); self.assertEqual(self.batch(),m.legacy_digests(self.a,self.b,['a'],cwd=self.root))

class MissingEvidenceTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        (self.root/'sub').mkdir();(self.root/'sub'/'a').write_bytes(b'first');(self.root/'[x]').write_bytes(b'lit')
        self.git('add','.');self.git('commit','-qm','base');self.a=self.git('rev-parse','HEAD').decode().strip()
        (self.root/'sub'/'a').write_bytes(b'other');self.git('commit','-qam','next');self.b=self.git('rev-parse','HEAD').decode().strip()
    def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.PIPE)
    def delete(self,ref):
        oid=self.git('rev-parse',ref).decode().strip();(self.root/'.git/objects'/oid[:2]/oid[2:]).unlink()
    def batch(self,paths,base=None):return m.batch_digests(base or self.a,self.b,paths,cwd=self.root)
    def fallback(self,paths,base=None,**kw):return m.digests_with_fallback(base or self.a,self.b,paths,cwd=self.root,**kw)
    def test_absent_path(self):self.assertEqual(self.batch(['missing']),{'missing':(None,None)})
    def test_literal_glob_path(self):self.assertEqual(self.batch(['[x]'])['[x]'],(hashlib.sha256(b'lit').hexdigest(),)*2)
    def test_missing_blob_batch(self):
        self.delete(self.a+':sub/a')
        with self.assertRaises(m.BatchIntegrityError):self.batch(['sub/a'])
    def test_missing_blob_fallback(self):
        self.delete(self.a+':sub/a')
        with self.assertRaises(m.BatchIntegrityError):self.fallback(['sub/a'])
    def test_missing_blob_direct_legacy(self):
        self.delete(self.a+':sub/a')
        with self.assertRaises(m.BatchIntegrityError):m.legacy_digests(self.a,self.b,['sub/a'],cwd=self.root)
    def test_missing_commit(self):
        self.delete(self.a)
        with self.assertRaises(m.BatchIntegrityError):self.fallback(['missing'])
    def test_missing_tree(self):
        self.delete(self.a+':sub')
        with self.assertRaises(m.BatchIntegrityError):self.fallback(['sub/a'])
    def test_custom_fallback_cannot_hide_missing_blob(self):
        self.delete(self.a+':sub/a')
        with patch.object(m,'batch_digests',side_effect=m.BatchRejected('fallback test')):
            with self.assertRaises(m.BatchIntegrityError):self.fallback(['sub/a'],legacy=lambda:{'sub/a':(None,'x')})
    def test_custom_fallback_preserves_real_absence(self):
        with patch.object(m,'batch_digests',side_effect=m.BatchRejected('fallback test')):
            self.assertEqual(self.fallback(['missing'],legacy=lambda:{'missing':(None,None)}),{'missing':(None,None)})
    def test_nonliteral_missing_name(self):
        # Git show treats this operand differently; retain the existing fallback contract.
        with self.assertRaises(m.BatchRejected):self.batch(['*'])
    def test_grouped_absence_uses_two_tree_queries(self):
        names=['missing-one','missing-two','sub/missing-three']
        with patch.object(subprocess,'run',wraps=subprocess.run) as run:
            self.assertEqual(self.batch(names),dict.fromkeys(names,(None,None)))
        calls=[c.args[0] for c in run.call_args_list if 'ls-tree' in c.args[0]]
        self.assertEqual(len(calls),2)
        self.assertTrue(all(set(names).issubset(c) for c in calls))
    def test_grouped_absence_does_not_hide_missing_blob(self):
        self.delete(self.a+':sub/a')
        with self.assertRaises(m.BatchIntegrityError):self.batch(['missing','sub/a'])
class FallbackIdentityTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        (self.root/'sub').mkdir();(self.root/'sub'/'a').write_bytes(b'first');self.git('add','.');self.git('commit','-qm','base');self.a=self.git('rev-parse','HEAD').decode().strip();self.oid=self.git('rev-parse','HEAD:sub/a').decode().strip()
        (self.root/'sub'/'a').write_bytes(b'other');self.git('commit','-qam','next');self.b=self.git('rev-parse','HEAD').decode().strip();self.oid2=self.git('rev-parse','HEAD:sub/a').decode().strip()
    def git(self,*a):return subprocess.check_output(['git',*a],cwd=self.root,stderr=subprocess.PIPE)
    def legacy(self,paths=('sub/a',)):return m.legacy_digests(self.a,self.b,list(paths),cwd=self.root)
    def fallback(self,**kw):return m.digests_with_fallback(self.a,self.b,['sub/a'],cwd=self.root,**kw)
    def corrupt(self):
        _write_fixture_object(self.root/'.git/objects'/self.oid[:2]/self.oid[2:],zlib.compress(b'blob 5\0wrong'))
        self.assertEqual(self.git('show',self.a+':sub/a'),b'wrong')
    def force(self):return patch.object(m,'batch_digests',side_effect=m.BatchRejected('forced legacy'))
    def test_direct_legacy_corruption(self):
        self.corrupt()
        with self.assertRaises(m.BatchIntegrityError):self.legacy()
    def test_oversize_fallback_corruption(self):
        self.corrupt()
        with patch.object(m,'MAX_BLOB',1),self.assertRaises(m.BatchIntegrityError):self.fallback()
    def test_generic_failure_fallback_corruption(self):
        self.corrupt()
        with self.force(),self.assertRaises(m.BatchIntegrityError):self.fallback()
    def test_direct_replacement(self):
        self.git('replace',self.oid,self.oid2)
        with self.assertRaises(m.BatchIntegrityError):self.legacy()
    def test_custom_fallback_forged_digest(self):
        with self.force(),self.assertRaises(m.BatchIntegrityError):self.fallback(legacy=lambda:{'sub/a':('0'*64,'1'*64)})
    def test_custom_fallback_old_valid_digest_after_corruption(self):
        valid=self.legacy();self.corrupt()
        with self.force(),self.assertRaises(m.BatchIntegrityError):self.fallback(legacy=lambda:valid)
    def test_custom_fallback_extra_path(self):
        valid=self.legacy();valid['extra']=(None,None)
        with self.force(),self.assertRaises(m.BatchIntegrityError):self.fallback(legacy=lambda:valid)
    def test_normal_oversize(self):
        expected=m.batch_digests(self.a,self.b,['sub/a'],cwd=self.root)
        with patch.object(m,'MAX_BLOB',1):self.assertEqual(self.fallback(),expected)
    def test_normal_custom_fallback(self):
        expected=self.legacy()
        with self.force():self.assertEqual(self.fallback(legacy=lambda:expected),expected)
    def test_commit_replace_parity(self):
        self.git('replace',self.a,self.b);self.assertEqual(self.legacy(),m.batch_digests(self.a,self.b,['sub/a'],cwd=self.root))
    def test_tree_legacy_parity(self):
        expected=tuple(hashlib.sha256(self.git('show',r+':sub')).hexdigest() for r in (self.a,self.b))
        self.assertEqual(self.legacy(('sub',)),{'sub':expected})
    def test_missing_legacy_parity(self):self.assertEqual(self.legacy(('absent',)),{'absent':(None,None)})
class FallbackMetadataTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.root=Path(d.name)
        self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        self.names=['space name','한글','line\nbreak','empty','binary']
        for name in self.names:(self.root/name).write_bytes(b'' if name=='empty' else b'\x00\xff'+name.encode())
        self.git('add','.');self.git('commit','-qm','first');self.a=self.git('rev-parse','HEAD').decode().strip()
        (self.root/'space name').write_bytes(b'other');self.git('commit','-qam','second');self.b=self.git('rev-parse','HEAD').decode().strip()
    def git(self,*a):return subprocess.check_output(['git',*a],cwd=self.root,stderr=subprocess.PIPE)
    def legacy(self,paths):return m.legacy_digests(self.a,self.b,paths,cwd=self.root)
    def native(self,paths):return {p:tuple(hashlib.sha256(self.git('show',r+':'+p)).hexdigest() for r in (self.a,self.b)) for p in paths}
    def test_safe_paths_two_processes_per_ref(self):
        paths=['space name','한글','empty','binary']; expected=self.native(paths)
        with patch.object(subprocess,'run',wraps=subprocess.run) as run:
            self.assertEqual(self.legacy(paths),expected)
        self.assertEqual(len(run.call_args_list),2*2*len(paths))
    def test_newline_path_keeps_argv_lookup(self):
        expected=self.native(['line\nbreak'])
        with patch.object(subprocess,'run',wraps=subprocess.run) as run:
            self.assertEqual(self.legacy(['line\nbreak']),expected)
        self.assertEqual(len(run.call_args_list),6)
        self.assertFalse(any('--batch-check' in c.args[0] for c in run.call_args_list))
    def test_batch_size_limit_fallback(self):
        expected=self.native(['space name'])
        with patch.object(m,'MAX_BLOB',1):self.assertEqual(m.digests_with_fallback(self.a,self.b,['space name'],cwd=self.root),expected)
    def test_corrupt_blob_rejected(self):
        oid=self.git('rev-parse',self.a+':space name').decode().strip();p=self.root/'.git/objects'/oid[:2]/oid[2:]
        _write_fixture_object(p,zlib.compress(b'blob 5\0wrong'))
        self.assertEqual(self.git('show',self.a+':space name'),b'wrong')
        with self.assertRaises(m.BatchIntegrityError):self.legacy(['space name'])
    def test_deleted_after_show(self):
        oid=self.git('rev-parse',self.a+':space name').decode().strip();p=self.root/'.git/objects'/oid[:2]/oid[2:];real=subprocess.run
        def mutate(cmd,*a,**kw):
            out=real(cmd,*a,**kw)
            if cmd[:2]==['git','show'] and cmd[2]==self.a+':space name':p.unlink()
            return out
        with patch.object(subprocess,'run',side_effect=mutate),self.assertRaises(m.BatchIntegrityError):self.legacy(['space name'])
    def test_metadata_diagnostic_rejected(self):self.check_bad_metadata('diagnostic')
    def test_metadata_size_mismatch_rejected(self):self.check_bad_metadata('size')
    def test_metadata_extra_row_rejected(self):self.check_bad_metadata('extra')
    def check_bad_metadata(self,mode):
        real=subprocess.run;seen=[]
        def mutate(cmd,*a,**kw):
            out=real(cmd,*a,**kw)
            if '--batch-check' in cmd:
                seen.append(True)
                if mode=='diagnostic':out.stderr=b'warning'
                elif mode=='size':out.stdout=out.stdout.rsplit(b' ',1)[0]+b' 99999\n'
                else:out.stdout+=out.stdout
            return out
        with patch.object(subprocess,'run',side_effect=mutate),self.assertRaises(m.BatchIntegrityError):self.legacy(['space name'])
        self.assertTrue(seen)
    def test_direct_blob_replace_rejected(self):
        a=self.git('rev-parse',self.a+':space name').decode().strip();b=self.git('rev-parse',self.b+':space name').decode().strip();self.git('replace',a,b)
        with self.assertRaises(m.BatchIntegrityError):self.legacy(['space name'])
    def test_nonpinned_path_unchanged(self):self.assertEqual(m.legacy_digests('HEAD','HEAD',['binary'],cwd=self.root)['binary'],(hashlib.sha256(self.git('show','HEAD:binary')).hexdigest(),)*2)

if __name__=='__main__':unittest.main()
