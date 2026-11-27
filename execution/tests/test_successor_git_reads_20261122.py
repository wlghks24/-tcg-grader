import zlib
"""Real Git cache boundaries, not an exemption from source/fixture checks."""
import os
import hashlib
import copy
from contextlib import ExitStack
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import successor_git_reads_20261122 as reads
from execution import git_validation_cache as cache
from execution.git_validation_cache import head_validation_request


def _write_fixture_object(path, payload):
    """Git loose objects are read-only for ordinary Unix/Termux users."""
    path.chmod(0o600)
    path.write_bytes(payload)


class SuccessorGitReadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.repo=Path(self.temp.name)
        self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        (self.repo/'sample.txt').write_text('first')
        self.git('add','sample.txt');self.git('commit','-qm','first')
        self.first=self.git('rev-parse','HEAD').decode().strip()
        reads.metadata.cache_clear()
    def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.repo,stderr=subprocess.DEVNULL)
    def advance(self):
        (self.repo/'sample.txt').write_text('second');self.git('commit','-qam','second')
    def test_fixed_object_metadata_is_reused(self):
        args=('ls-tree','-z',self.first,'--','sample.txt')
        first=reads.read(self.repo,*args);before=reads.metadata.cache_info()
        self.assertEqual(reads.read(self.repo,*args),first)
        self.assertEqual(reads.metadata.cache_info().hits,before.hits+1)
    def test_symbolic_head_metadata_is_keyed_by_fresh_commit(self):
        args=('ls-tree','-z','HEAD','--','sample.txt')
        old=reads.read(self.repo,*args);self.advance()
        self.assertNotEqual(reads.read(self.repo,*args),old)
        self.assertEqual(reads.metadata.cache_info().currsize,2)
    def test_head_source_changes_between_requests_are_observed(self):
        @head_validation_request()
        def read():return reads.read(self.repo,'show','HEAD:sample.txt')
        self.assertEqual(read(),b'first');self.advance();self.assertEqual(read(),b'second')
    def test_fixed_history_stays_fixed_after_head_advance(self):
        args=('ls-tree','-z',self.first,'--','sample.txt')
        old=reads.read(self.repo,*args);self.advance();self.assertEqual(reads.read(self.repo,*args),old)
    def test_injected_executor_is_not_masked_by_warm_cache(self):
        args=('ls-tree','-z',self.first,'--','sample.txt');reads.read(self.repo,*args)
        with patch.object(subprocess,'check_output',return_value=b'tampered'):
            self.assertEqual(reads.read(self.repo,*args),b'tampered')
    def test_changed_environment_separates_metadata_cache(self):
        args=('ls-tree','-z',self.first,'--','sample.txt')
        with patch.dict(os.environ,{'GIT_OPTIONAL_LOCKS':'1'}):
            reads.read(self.repo,*args)
            before=reads.metadata.cache_info().misses
            with patch.dict(os.environ,{'GIT_OPTIONAL_LOCKS':'0'}):reads.read(self.repo,*args)
            self.assertEqual(reads.metadata.cache_info().misses,before+1)
    def test_changed_repository_separates_metadata_cache(self):
        args=('ls-tree','-z',self.first,'--','sample.txt');reads.read(self.repo,*args)
        with tempfile.TemporaryDirectory() as folder:
            other=Path(folder)/'repo'
            # No hardlinks: repository isolation test must not change source object ctime.
            subprocess.run(['git','clone','-q','--no-hardlinks',str(self.repo),str(other)],check=True)
            self.assertEqual(reads.read(other,*args),reads.read(self.repo,*args))
            self.assertEqual(reads.metadata.cache_info().currsize,2)

    def check_replaced_read(self,args):
        self.advance();second=self.git('rev-parse','HEAD').decode().strip()
        before=self.git(*args);self.assertEqual(before,reads.read(self.repo,*args))
        self.git('replace',self.first,second)
        after=self.git(*args);self.assertNotEqual(before,after)
        self.assertEqual(after,reads.read(self.repo,*args))
    def test_revparse_replace_after_warmup(self):
        self.check_replaced_read(('rev-parse',self.first+':sample.txt'))
    def test_tree_replace_after_warmup(self):
        self.check_replaced_read(('ls-tree','-z',self.first,'--','sample.txt'))
    def test_diff_replace_after_warmup(self):
        self.advance();second=self.git('rev-parse','HEAD').decode().strip()
        args=('diff','--no-renames','--name-only','-z',self.first,second)
        before=self.git(*args);self.assertEqual(before,reads.read(self.repo,*args))
        self.git('replace',self.first,second)
        after=self.git(*args);self.assertNotEqual(before,after)
        self.assertEqual(after,reads.read(self.repo,*args))
    def test_diff_live_attribute_after_warmup(self):
        self.advance();second=self.git('rev-parse','HEAD').decode().strip()
        attrs=self.repo/'.gitattributes';attrs.write_text('sample.txt reviewed\n')
        args=('diff','--no-renames','--name-only','-z',self.first,second,'--',':(attr:reviewed)sample.txt')
        before=self.git(*args);self.assertEqual(before,reads.read(self.repo,*args))
        attrs.write_text('sample.txt -reviewed\n');after=self.git(*args)
        self.assertNotEqual(before,after);self.assertEqual(after,reads.read(self.repo,*args))
    def test_diff_live_orderfile_after_warmup(self):
        self.advance();(self.repo/'other.txt').write_text('other');self.git('add','other.txt');self.git('commit','-qm','other')
        second=self.git('rev-parse','HEAD').decode().strip();order=self.repo/'order'
        order.write_text('sample.txt\n*.txt\n');self.git('config','diff.orderFile',str(order))
        args=('diff','--no-renames','--name-only','-z',self.first,second)
        before=self.git(*args);self.assertEqual(before,reads.read(self.repo,*args))
        order.write_text('other.txt\n*.txt\n');after=self.git(*args)
        self.assertNotEqual(before,after);self.assertEqual(after,reads.read(self.repo,*args))


    def test_head_changed_during_public_request_is_rejected(self):
        @head_validation_request()
        def verify():
            self.assertEqual(b'first',reads.read(self.repo,'show','HEAD:sample.txt'))
            self.advance()
            return reads.read(self.repo,'show','HEAD:sample.txt')
        with self.assertRaisesRegex(AssertionError,'HEAD changed'):
            verify()
        self.assertEqual(b'second',reads.read(self.repo,'show','HEAD:sample.txt'))

    def test_nested_head_change_is_rejected_at_outer_boundary(self):
        @head_validation_request()
        def inner():return reads.read(self.repo,'ls-tree','-z','HEAD','--','sample.txt')
        @head_validation_request()
        def outer():
            previous=inner();self.advance();self.assertEqual(previous,inner());return True
        with self.assertRaisesRegex(AssertionError,'HEAD changed'):outer()

    def test_ancestry_head_change_is_rejected(self):
        @head_validation_request()
        def verify():
            result=cache.git_validation_run(['git','merge-base','--is-ancestor',self.first,'HEAD'],cwd=self.repo,capture_output=True)
            self.assertEqual(0,result.returncode);self.advance();return True
        with self.assertRaisesRegex(AssertionError,'HEAD changed'):verify()

    def test_head_deleted_before_return_is_rejected(self):
        @head_validation_request()
        def verify():
            reads.read(self.repo,'rev-parse','HEAD');self.git('update-ref','-d','HEAD');return True
        with self.assertRaises((AssertionError,subprocess.CalledProcessError)):verify()

    def test_stable_nested_head_request(self):
        @head_validation_request()
        def inner():return reads.read(self.repo,'show','HEAD:sample.txt')
        @head_validation_request()
        def outer():return inner(),inner()
        self.assertEqual((b'first',b'first'),outer())

    def test_original_exception_is_preserved_and_snapshot_reset(self):
        @head_validation_request()
        def verify():
            reads.read(self.repo,'rev-parse','HEAD');self.advance();raise ValueError('original')
        with self.assertRaisesRegex(ValueError,'original'):verify()
        self.assertEqual(b'second',reads.read(self.repo,'show','HEAD:sample.txt'))

    def test_fixed_object_request_does_not_require_head(self):
        @head_validation_request()
        def verify():return reads.read(self.repo,'show',self.first+':sample.txt')
        self.git('update-ref','-d','HEAD')
        self.assertEqual(b'first',verify())

    def test_git_environment_change_is_rejected(self):
        @head_validation_request()
        def verify():
            reads.read(self.repo,'rev-parse','HEAD');os.environ['GIT_OPTIONAL_LOCKS']='0';return True
        with patch.dict(os.environ,{'GIT_OPTIONAL_LOCKS':'1'}):
            with self.assertRaisesRegex(AssertionError,'environment changed'):verify()

    def test_existing_custom_loader_contract_without_opt_in(self):
        values=iter(['a'*40,'b'*40]);calls=[]
        def load():
            value=next(values);calls.append(value);return value
        @head_validation_request()
        def verify():
            first=cache.resolve_validation_head(self.repo,load)
            self.assertEqual(first,cache.resolve_validation_head(self.repo,load));return first
        self.assertEqual('a'*40,verify());self.assertEqual('b'*40,verify());self.assertEqual(2,len(calls))


class ImmutableSourceEvidenceTests(unittest.TestCase):
    git=SuccessorGitReadTests.git
    advance=SuccessorGitReadTests.advance

    def setUp(self):
        SuccessorGitReadTests.setUp(self)
        reads._source_evidence.cache_clear()
        before=self.pin(self.first)
        self.advance()
        self.candidate=self.git('rev-parse','HEAD').decode().strip()
        self.proof={'baseline_commit':self.first,'candidate_commit':self.candidate,
                    'baseline':{'sample.txt':before},'files':{'sample.txt':self.pin(self.candidate)}}
        self.reader=lambda *args:reads.read(self.repo,*args)
        self.pinning=self.checked_pin
    def pin(self,ref):
        raw=self.git('show',ref+':sample.txt')
        return {'blob':self.git('rev-parse',ref+':sample.txt').decode().strip(),
                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    def checked_pin(self,ref,name,pin):
        raw=self.reader('show',ref+':'+name)
        self.assertEqual(self.reader('ls-tree','-z',ref,'--',name),
                         ('100644 blob '+pin['blob']+'\t'+name+'\0').encode())
        self.assertEqual(pin['bytes'],len(raw))
        self.assertEqual(pin['sha256'],hashlib.sha256(raw).hexdigest())
        return raw
    def evidence(self,proof=None):
        return reads.immutable_source_evidence(self.repo,proof or self.proof,self.reader,self.pinning)
    def test_only_fixed_source_evidence_is_reused(self):
        # Reuse immutable objects, not a previous composite approval.
        self.assertEqual({'sample.txt':b'second'},self.evidence())
        before=reads._source_evidence.cache_info()
        metadata_before=reads.metadata.cache_info().hits
        self.assertEqual(self.evidence(),{'sample.txt':b'second'})
        self.assertEqual(before.hits,reads._source_evidence.cache_info().hits)
        self.assertEqual(before.misses+1,reads._source_evidence.cache_info().misses)
        self.assertEqual(0,reads._source_evidence.cache_info().currsize)
        self.assertGreater(reads.metadata.cache_info().hits,metadata_before)
        # Same reader and pins; replacement after warmup must invalidate evidence.
        self.git('replace',self.first,self.candidate)
        with self.assertRaises((AssertionError,subprocess.CalledProcessError)):
            self.evidence()
    def test_valid_compressed_object_with_wrong_identity_rejected_by_existing_pin(self):
        self.assertEqual({'sample.txt':b'second'},self.evidence())
        oid=self.proof['files']['sample.txt']['blob']
        obj=self.repo/'.git/objects'/oid[:2]/oid[2:]
        _write_fixture_object(obj,zlib.compress(b'blob 6\0forged'))
        self.assertEqual(b'forged',self.git('show',self.candidate+':sample.txt'))
        with self.assertRaises(AssertionError):self.evidence()
        result=subprocess.run(['git','fsck','--full','--strict'],cwd=self.repo,capture_output=True)
        self.assertNotEqual(0,result.returncode)

    def test_changed_pin_cannot_reuse_verified_evidence(self):
        self.evidence(); forged=copy.deepcopy(self.proof)
        forged['files']['sample.txt']['sha256']='0'*64
        for _ in range(2):
            with self.assertRaises(AssertionError):self.evidence(forged)
    def test_new_reader_and_environment_separate_evidence(self):
        self.evidence();before=reads._source_evidence.cache_info().misses
        with patch.dict(os.environ,{'GIT_OPTIONAL_LOCKS':'0'}):self.evidence()
        self.assertEqual(before+1,reads._source_evidence.cache_info().misses)
        old=self.reader
        self.reader=lambda *args:b'extra.py\0' if args[0]=='diff' else old(*args)
        with self.assertRaises(AssertionError):self.evidence()
    def test_symbolic_source_and_failed_checks_are_not_cached(self):
        forged=copy.deepcopy(self.proof);forged['candidate_commit']='HEAD'
        before=reads._source_evidence.cache_info().currsize
        with self.assertRaises(AssertionError):self.evidence(forged)
        self.assertEqual(before,reads._source_evidence.cache_info().currsize)


class ObjectStoreCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.git('init','-q'); self.git('config','user.name','Fixture'); self.git('config','user.email','fixture@example.invalid')
        self.commit('first'); self.first=self.git('rev-parse','HEAD').strip().decode()
        self.commit('second'); self.second=self.git('rev-parse','HEAD').strip().decode()
        self.blob=self.git('rev-parse',self.first+':sample.txt').strip().decode()
        self.objects=self.root/'.git/objects'
        cache._cached_object_read.cache_clear();cache._cached_status_read.cache_clear();reads.metadata.cache_clear()
    def git(self,*a):return subprocess.check_output(['git',*a],cwd=self.root,stderr=subprocess.PIPE)
    def commit(self,s):
        (self.root/'sample.txt').write_text(s);self.git('add','.');self.git('commit','-qm',s)
    def loose(self,oid):return self.objects/oid[:2]/oid[2:]
    def show(self):return ['git','show',self.first+':sample.txt']
    def output(self,cmd):return cache.git_validation_output(cmd,cwd=self.root)
    def native_fails(self,cmd):self.assertNotEqual(0,subprocess.run(cmd,cwd=self.root,capture_output=True).returncode)
    def test_loose_blob_deleted_output(self):
        cmd=self.show();self.assertEqual(b'first',self.output(cmd));self.loose(self.blob).unlink();self.native_fails(cmd)
        with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)
    def test_loose_blob_deleted_run(self):
        cmd=self.show();self.assertEqual(b'first',cache.git_validation_run(cmd,cwd=self.root,capture_output=True).stdout);self.loose(self.blob).unlink();self.native_fails(cmd)
        self.assertNotEqual(0,cache.git_validation_run(cmd,cwd=self.root,capture_output=True).returncode)
    def test_loose_blob_corrupted_same_size_mtime(self):
        cmd=self.show();self.output(cmd);p=self.loose(self.blob);st=p.stat();_write_fixture_object(p,b'x'*st.st_size);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns));self.native_fails(cmd)
        with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)
    def test_tree_deleted(self):
        args=('ls-tree','-z',self.first,'--','sample.txt');reads.read(self.root,*args);tree=self.git('rev-parse',self.first+'^{tree}').strip().decode();self.loose(tree).unlink();self.native_fails(['git',*args])
        with self.assertRaises(subprocess.CalledProcessError):reads.read(self.root,*args)
    def test_revparse_tree_deleted(self):
        cmd=['git','rev-parse',self.first+':sample.txt'];self.output(cmd);tree=self.git('rev-parse',self.first+'^{tree}').strip().decode();self.loose(tree).unlink();self.native_fails(cmd)
        with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)
    def test_ancestry_commit_deleted(self):
        cmd=['git','merge-base','--is-ancestor',self.first,self.second];self.output(cmd);self.loose(self.first).unlink();self.native_fails(cmd)
        with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)
    def test_pack_deleted(self):
        self.git('gc','--prune=now');cmd=self.show();self.output(cmd);packs=list((self.objects/'pack').glob('*.pack'));self.assertTrue(packs)
        for p in packs:p.unlink()
        self.native_fails(cmd)
        with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)
    def test_pack_index_deleted(self):
        self.git('gc','--prune=now');cmd=self.show();self.output(cmd);indexes=list((self.objects/'pack').glob('*.idx'));self.assertTrue(indexes)
        for p in indexes:p.unlink()
        self.native_fails(cmd)
        with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)
    def test_normal_loose_cache_hit(self):
        cmd=self.show();self.output(cmd);before=cache._cached_object_read.cache_info().hits;self.assertEqual(b'first',self.output(cmd));self.assertGreater(cache._cached_object_read.cache_info().hits,before)
    def test_normal_packed_cache_hit(self):
        self.git('gc','--prune=now');cmd=self.show();self.output(cmd);before=cache._cached_object_read.cache_info().hits;self.assertEqual(b'first',self.output(cmd));self.assertGreater(cache._cached_object_read.cache_info().hits,before)
    def test_repack_preserves_parity(self):
        cmd=self.show();self.output(cmd);self.git('gc','--prune=now');self.assertEqual(self.git(*cmd[1:]),self.output(cmd))
    def test_bounded_inventory_fallback(self):
        cmd=self.show();self.output(cmd)
        with patch.object(cache,'MAX_OBJECT_STORE_ENTRIES',1):
            before=cache._cached_object_read.cache_info().hits;self.assertEqual(b'first',self.output(cmd));self.assertEqual(before,cache._cached_object_read.cache_info().hits)
            self.loose(self.blob).unlink()
            with self.assertRaises(subprocess.CalledProcessError):self.output(cmd)


class CacheBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.git('init','-q'); self.git('config','user.name','Fixture'); self.git('config','user.email','fixture@example.invalid')
        self.commit('first'); self.a=self.git('rev-parse','HEAD').strip().decode(); self.commit('second'); self.b=self.git('rev-parse','HEAD').strip().decode()
        self.blob=self.git('rev-parse',self.a+':sample.txt').strip().decode(); self.objects=self.root/'.git/objects'; self.path=self.objects/self.blob[:2]/self.blob[2:]
        self.cmd=['git','show',self.a+':sample.txt']; cache._cached_object_read.cache_clear(); cache._cached_status_read.cache_clear(); reads.metadata.cache_clear()
    def git(self,*a):return subprocess.check_output(['git',*a],cwd=self.root,stderr=subprocess.PIPE)
    def commit(self,s):
        (self.root/'sample.txt').write_text(s);self.git('add','.');self.git('commit','-qm',s)
    def output(self):return cache.git_validation_output(self.cmd,cwd=self.root)
    def run_read(self):return cache.git_validation_run(self.cmd,cwd=self.root,capture_output=True,check=True).stdout
    def mutate_after(self,module,name,call,mutate):
        original=getattr(module,name)
        def boundary(*a,**kw):
            result=original(*a,**kw);mutate();return result
        with patch.object(module,name,side_effect=boundary):
            with self.assertRaisesRegex(AssertionError,'Git cache context changed'):call()
    def test_warm_output_deleted_after_lookup(self):
        self.assertEqual(b'first',self.output());self.mutate_after(cache,'_cached_read',self.output,self.path.unlink)
    def test_cold_output_deleted_after_lookup(self):
        self.mutate_after(cache,'_cached_read',self.output,self.path.unlink)
    def test_warm_run_deleted_after_lookup(self):
        self.assertEqual(b'first',self.run_read());self.mutate_after(cache,'_cached_read',self.run_read,self.path.unlink)
    def test_replace_after_lookup(self):
        self.output();self.mutate_after(cache,'_cached_read',self.output,lambda:self.git('replace',self.a,self.b))
        self.assertEqual(b'second',self.output())
    def test_metadata_tree_deleted_after_lookup(self):
        args=('ls-tree','-z',self.a,'--','sample.txt');call=lambda:reads.read(self.root,*args);call()
        tree=self.git('rev-parse',self.a+'^{tree}').strip().decode();p=self.objects/tree[:2]/tree[2:]
        self.mutate_after(reads,'metadata',call,p.unlink)
    def test_ancestry_mutated_after_lookup(self):
        cmd=['git','merge-base','--is-ancestor',self.a,self.b];call=lambda:cache.git_validation_output(cmd,cwd=self.root);call()
        p=self.objects/self.a[:2]/self.a[2:];self.mutate_after(cache,'_cached_read',call,p.unlink)
    def test_environment_changed_after_lookup(self):
        self.output()
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('GIT_OPTIONAL_LOCKS',None)
            self.mutate_after(cache,'_cached_read',self.output,lambda:os.environ.__setitem__('GIT_OPTIONAL_LOCKS','0'))
    def test_request_end_object_deleted(self):
        @cache.head_validation_request()
        def verify():
            self.assertEqual(b'first',self.output());self.path.unlink();return True
        with self.assertRaisesRegex(AssertionError,'Git cache context changed'):verify()
    def test_request_end_replace_created(self):
        @cache.head_validation_request()
        def verify():
            self.output();self.git('replace',self.a,self.b);return True
        with self.assertRaisesRegex(AssertionError,'Git cache context changed'):verify()
    def test_stable_cache_hit(self):
        self.output();before=cache._cached_object_read.cache_info().hits;self.assertEqual(b'first',self.output());self.assertGreater(cache._cached_object_read.cache_info().hits,before)
    def test_stable_outer_request(self):
        @cache.head_validation_request()
        def verify():return self.output(),self.run_read()
        self.assertEqual((b'first',b'first'),verify())
    def test_hash_pin_detects_valid_zlib_wrong_object(self):
        # Native Git may read a valid compressed blob whose content does not
        # match its filename. Existing explicit content pins still reject it.
        expected=hashlib.sha256(self.output()).digest(); _write_fixture_object(self.path,zlib.compress(b'blob 5\0wrong'))
        actual=self.git('show',self.a+':sample.txt');self.assertEqual(b'wrong',actual)
        self.assertNotEqual(expected,hashlib.sha256(self.output()).digest())
        result=subprocess.run(['git','fsck','--full','--strict'],cwd=self.root,capture_output=True)
        self.assertNotEqual(0,result.returncode)


"""Step 14: real Git invalidation and complete historical bridge entrypoints."""
import json

import sync_v376_successor_test_support as sync
from execution import git_validation_cache as cache
from execution.git_batch_evidence import BatchIntegrityError


class RevalidatedEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.quotePath', 'false')
        self.name = '한글.txt'
        (self.root / self.name).write_bytes(b'first')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.a = self.git('rev-parse', 'HEAD').decode().strip()
        self.oid = self.git('rev-parse', self.a + ':' + self.name).decode().strip()
        (self.root / self.name).write_bytes(b'other')
        self.git('commit', '-qam', 'candidate')
        self.b = self.git('rev-parse', 'HEAD').decode().strip()
        self.old = hashlib.sha256(b'first').hexdigest()
        self.new = hashlib.sha256(b'other').hexdigest()
        patched = patch.object(sync, 'ROOT', self.root)
        patched.start()
        self.addCleanup(patched.stop)
        self.clear()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE)

    def clear(self):
        for name in ('_v645_immutable_commit_evidence', '_v646_immutable_commit_evidence', '_v989_exact_immutable_git_at_head',
                     '_v993_immutable_hot_evidence', '_v994_immutable_neural_git',
                     '_v995_immutable_post_evidence', '_immutable_review_document_digest'):
            getattr(sync, name).cache_clear()
        cache._cached_status_read.cache_clear()
        cache._cached_object_read.cache_clear()

    def aggregate(self):
        return sync._v646_immutable_commit_evidence(self.a, self.b, (self.name,))

    def test_reuse_has_real_hits_without_retaining_callers_mutations(self):
        expected = copy.deepcopy(self.aggregate())
        first = sync._v646_immutable_commit_evidence.cache_info()
        ancestor, changed, rows = self.aggregate()
        changed.clear()
        rows.clear()
        self.assertEqual(expected, self.aggregate())
        after = sync._v646_immutable_commit_evidence.cache_info()
        self.assertEqual(first.misses, after.misses)
        self.assertGreater(after.hits, first.hits)

    def test_diff_config_is_replayed_on_a_warm_result(self):
        self.git('config', 'core.quotePath', 'true')
        before = self.aggregate()[1]
        self.git('config', 'core.quotePath', 'false')
        after = self.aggregate()[1]
        self.assertNotEqual(before, after)
        self.assertEqual(set(self.git('diff', '--no-renames', '--name-only', self.a, self.b).decode().splitlines()), after)

    def test_same_order_file_path_with_changed_contents_is_not_hidden(self):
        (self.root / 'z.txt').write_bytes(b'new')
        self.git('add', '.')
        self.git('commit', '-qm', 'two paths')
        newer = self.git('rev-parse', 'HEAD').decode().strip()
        order = self.root / 'order'
        order.write_text('z.txt\n*\n')
        self.git('config', 'diff.orderFile', str(order))
        p = {'base_commit': self.a, 'candidate_commit': newer,
             'reviewed_paths': ['z.txt', self.name],
             'reviewed_sha256': {'z.txt': hashlib.sha256(b'new').hexdigest(), self.name: self.new},
             'reviewed_bytes': {'z.txt': 3, self.name: 5}}
        key = json.dumps(p, sort_keys=True)
        reader = sync._v995_immutable_post_evidence
        self.assertTrue(reader(newer, key, (subprocess.run, subprocess.check_output)))
        order.write_text(self.name + '\nz.txt\n')
        with self.assertRaises(AssertionError):
            reader(newer, key, (subprocess.run, subprocess.check_output))

    def test_commit_replace_is_observed_after_warmup(self):
        self.aggregate()
        self.git('replace', self.a, self.b)
        self.assertEqual(sync._v646_immutable_commit_evidence.__wrapped__(self.a, self.b, (self.name,)), self.aggregate())

    def test_blob_replace_rejects_stale_digest(self):
        self.aggregate()
        other = self.git('rev-parse', self.b + ':' + self.name).decode().strip()
        self.git('replace', self.oid, other)
        with self.assertRaises(BatchIntegrityError):
            self.aggregate()

    def test_object_corruption_rejects_stale_digest(self):
        self.aggregate()
        obj = self.root / '.git/objects' / self.oid[:2] / self.oid[2:]
        obj.chmod(0o600)
        obj.write_bytes(zlib.compress(b'blob 5\0wrong'))
        with self.assertRaises(BatchIntegrityError):
            self.aggregate()

    def test_deleted_object_is_not_a_cached_success(self):
        self.aggregate()
        (self.root / '.git/objects' / self.oid[:2] / self.oid[2:]).unlink()
        with self.assertRaises(BatchIntegrityError):
            self.aggregate()

    def test_unknown_large_store_uses_original_reader(self):
        self.aggregate()
        with patch.object(cache, 'MAX_OBJECT_STORE_ENTRIES', 0):
            before = sync._v646_immutable_commit_evidence.cache_info()
            self.assertEqual(sync._v646_immutable_commit_evidence.__wrapped__(self.a, self.b, (self.name,)), self.aggregate())
            self.assertEqual(before, sync._v646_immutable_commit_evidence.cache_info())

    def test_injected_high_level_reader_is_live(self):
        self.aggregate()
        original = sync._git_validation_output
        def changed(args, **kwargs):
            return 'unreviewed\n' if args[1] == 'diff' else original(args, **kwargs)
        with patch.object(sync, '_git_validation_output', changed):
            self.assertEqual({'unreviewed'}, self.aggregate()[1])

    def test_hot_successor_rechecks_changed_history(self):
        p = {'baseline_commit': self.a, 'candidate_commit': self.b, 'path': self.name,
             'baseline_sha256': self.old, 'reviewed_sha256': self.new}
        key = json.dumps(p, sort_keys=True)
        read = lambda: sync._v993_immutable_hot_evidence(self.b, key, (subprocess.run, subprocess.check_output))
        self.assertTrue(read())
        self.git('replace', self.a, self.b)
        with self.assertRaises(AssertionError):
            read()

    def test_post_successor_rechecks_changed_history(self):
        p = {'base_commit': self.a, 'candidate_commit': self.b, 'reviewed_paths': [self.name],
             'reviewed_sha256': {self.name: self.new}, 'reviewed_bytes': {self.name: 5}}
        key = json.dumps(p, sort_keys=True)
        read = lambda: sync._v995_immutable_post_evidence(self.b, key, (subprocess.run, subprocess.check_output))
        self.assertTrue(read())
        self.git('replace', self.a, self.b)
        with self.assertRaises(AssertionError):
            read()

    def test_neural_successor_rechecks_changed_history(self):
        p = {'historical_source_commit': self.a, 'base_commit': self.a,
             'candidate_commit': self.b, 'reviewed_paths': [self.name],
             'baseline_sha256': {self.name: self.old}, 'reviewed_sha256': {self.name: self.new}}
        with patch.object(sync, 'V994_NEURAL_PROOF', p):
            self.assertTrue(sync._v994_immutable_neural_git(self.b))
            self.git('replace', self.a, self.b)
            self.assertFalse(sync._v994_immutable_neural_git(self.b))

    def test_tablet_image_successor_rechecks_changed_history(self):
        p = {'base_commit': self.a, 'candidate_commit': self.b,
             'baseline_sha256': {self.name: self.old}, 'reviewed_sha256': {self.name: self.new}}
        with patch.multiple(sync, V989_REVIEW_FILES=(('fixture', 'V645_FEATURE_PROOF'),),
                            V989_TABLET_SCOPED_PATHS=frozenset({self.name}),
                            V989_LATEST_REVIEW={}, V645_FEATURE_PROOF=p):
            self.assertTrue(sync._v989_exact_immutable_git_at_head(self.b))
            self.git('replace', self.a, self.b)
            self.assertFalse(sync._v989_exact_immutable_git_at_head(self.b))

    def test_global_neural_proof_is_a_complete_cache_input(self):
        p = {'historical_source_commit': self.a, 'base_commit': self.a,
             'candidate_commit': self.b, 'reviewed_paths': [self.name],
             'baseline_sha256': {self.name: self.old}, 'reviewed_sha256': {self.name: self.new}}
        with patch.object(sync, 'V994_NEURAL_PROOF', p):
            self.assertTrue(sync._v994_immutable_neural_git(self.b))
            p['reviewed_sha256'][self.name] = '0' * 64
            self.assertFalse(sync._v994_immutable_neural_git(self.b))

    def test_archived_document_injected_reader_cannot_reuse_previous_digest(self):
        def output(args, **kwargs):
            return output.value
        output.value = b'original'
        with patch.object(sync, '_git_validation_output', output):
            self.assertEqual(hashlib.sha256(b'original').hexdigest(), sync._immutable_review_document_digest('review.md'))
            output.value = b'changed'
            self.assertEqual(hashlib.sha256(b'changed').hexdigest(), sync._immutable_review_document_digest('review.md'))

    def test_literal_range_reuse_observes_effective_quote_config(self):
        (self.root / 'sub').mkdir()
        (self.root / 'sub' / self.name).write_bytes(b'new')
        self.git('add', '.')
        self.git('commit', '-qm', 'nested unicode path')
        newer = self.git('rev-parse', 'HEAD').decode().strip()
        command = ['git', 'diff', '--no-renames', '--name-only', self.a + '..' + newer, '--', 'sub']
        self.git('config', 'core.quotePath', 'true')
        before = cache.git_validation_output(command, cwd=self.root)
        misses = cache._cached_object_read.cache_info().misses
        self.assertEqual(before, cache.git_validation_output(command, cwd=self.root))
        self.assertEqual(misses, cache._cached_object_read.cache_info().misses)
        self.git('config', 'core.quotePath', 'false')
        after = cache.git_validation_output(command, cwd=self.root)
        self.assertNotEqual(before, after)
        self.assertEqual(self.git(*command[1:]), after)

    def test_literal_range_with_external_orderfile_stays_live(self):
        for name in ('x.txt', 'z.txt'):
            (self.root / name).write_bytes(b'new')
        self.git('add', '.')
        self.git('commit', '-qm', 'two ASCII paths')
        newer = self.git('rev-parse', 'HEAD').decode().strip()
        order = self.root / 'order'
        self.git('config', 'diff.orderFile', str(order))
        command = ['git', 'diff', '--no-renames', '--name-only', self.a + '..' + newer, '--', 'x.txt', 'z.txt']
        order.write_text('z.txt\nx.txt\n')
        before = cache.git_validation_output(command, cwd=self.root)
        info = cache._cached_object_read.cache_info()
        order.write_text('x.txt\nz.txt\n')
        after = cache.git_validation_output(command, cwd=self.root)
        self.assertNotEqual(before, after)
        self.assertEqual(info, cache._cached_object_read.cache_info())
        self.assertEqual(self.git(*command[1:]), after)

    def test_empty_git_maintenance_lock_creation_does_not_change_object_evidence(self):
        command = ['git', 'show', self.a + ':' + self.name]
        self.assertEqual(b'first', cache.git_validation_output(command, cwd=self.root))
        lock = self.root / '.git/objects/maintenance.lock'
        original = cache._cached_object_read
        def create(*args):
            value = original(*args)
            lock.touch()
            return value
        with patch.object(cache, '_cached_object_read', create):
            self.assertEqual(b'first', cache.git_validation_output(command, cwd=self.root))

    def test_empty_git_maintenance_lock_removal_does_not_change_object_evidence(self):
        command = ['git', 'show', self.a + ':' + self.name]
        lock = self.root / '.git/objects/maintenance.lock'
        lock.touch()
        self.assertEqual(b'first', cache.git_validation_output(command, cwd=self.root))
        original = cache._cached_object_read
        def remove(*args):
            value = original(*args)
            lock.unlink()
            return value
        with patch.object(cache, '_cached_object_read', remove):
            self.assertEqual(b'first', cache.git_validation_output(command, cwd=self.root))

    def test_unknown_nonempty_maintenance_lock_still_invalidates_evidence(self):
        command = ['git', 'show', self.a + ':' + self.name]
        self.assertEqual(b'first', cache.git_validation_output(command, cwd=self.root))
        original = cache._cached_object_read
        def change(*args):
            value = original(*args)
            (self.root / '.git/objects/maintenance.lock').write_bytes(b'unknown')
            return value
        with patch.object(cache, '_cached_object_read', change):
            with self.assertRaisesRegex(AssertionError, 'cache context changed'):
                cache.git_validation_output(command, cwd=self.root)

    def test_stable_native_aggregate_reuses_fixed_dependencies_under_object_guard(self):
        expected = self.aggregate()
        with patch.object(cache, '_cached_status_read', wraps=cache._cached_status_read) as lower:
            self.assertEqual(expected, self.aggregate())
        self.assertEqual(0, lower.call_count)

    def test_return_boundary_rejects_object_deleted_after_aggregate_reuse(self):
        self.aggregate()
        original = cache._confirm_cache_context
        def remove(cwd, expected, **kwargs):
            (self.root / '.git/objects' / self.oid[:2] / self.oid[2:]).unlink()
            return original(cwd, expected, **kwargs)
        with patch.object(cache, '_confirm_cache_context', remove):
            with self.assertRaisesRegex(AssertionError, 'cache context changed'):
                self.aggregate()

    def _populate_normal_loose_store(self):
        for index in range(48):
            subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=self.root,
                           input=('fixture-object-' + str(index)).encode(),
                           check=True, capture_output=True)
        count = len(list((self.root / '.git/objects').rglob('*')))
        self.assertGreater(count, 64)
        self.assertLess(count, cache.MAX_OBJECT_STORE_ENTRIES)

    def test_normal_full_checkout_budget_keeps_real_cache_reuse(self):
        self._populate_normal_loose_store()
        self.assertIsNotNone(cache._cache_context(str(self.root)))
        expected = self.aggregate()
        before = sync._v646_immutable_commit_evidence.cache_info()
        self.assertEqual(expected, self.aggregate())
        self.assertGreater(sync._v646_immutable_commit_evidence.cache_info().hits, before.hits)

    def test_larger_inventory_still_rejects_corrupted_pinned_object(self):
        self._populate_normal_loose_store()
        self.test_object_corruption_rejects_stale_digest()


class ReadonlyObjectRequestTests(unittest.TestCase):
    setUp = RevalidatedEvidenceTests.setUp
    git = RevalidatedEvidenceTests.git
    clear = RevalidatedEvidenceTests.clear
    def read(self):
        return cache.git_validation_output(['git', 'show', self.a + ':' + self.name], cwd=self.root)
    def test_opt_in_inventory_is_checked_at_both_public_boundaries(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            return self.read(), self.read(), self.read()
        with patch.object(cache, '_object_store_signature', wraps=cache._object_store_signature) as inventory:
            self.assertEqual((b'first',) * 3, verify())
        self.assertEqual(2, inventory.call_count)
    def test_default_api_keeps_per_lookup_inventory(self):
        @cache.head_validation_request()
        def verify():
            return self.read(), self.read()
        with patch.object(cache, '_object_store_signature', wraps=cache._object_store_signature) as inventory:
            self.assertEqual((b'first', b'first'), verify())
        self.assertGreater(inventory.call_count, 2)
    def test_deleted_object_prevents_public_approval(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            self.assertEqual(b'first', self.read())
            (self.root / '.git/objects' / self.oid[:2] / self.oid[2:]).unlink()
            return True
        with self.assertRaisesRegex(AssertionError, 'cache context changed'):
            verify()
    def test_corrupted_object_prevents_public_approval(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            self.read()
            _write_fixture_object(self.root / '.git/objects' / self.oid[:2] / self.oid[2:],
                                  zlib.compress(b'blob 5\0wrong'))
            return True
        with self.assertRaisesRegex(AssertionError, 'cache context changed'):
            verify()
    def test_override_created_mid_request_is_observed_immediately(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            self.read(); self.git('replace', self.a, self.b)
            return self.read()
        with self.assertRaisesRegex(AssertionError, 'cache context changed'):
            verify()
    def test_nested_readonly_calls_share_only_one_lifetime(self):
        @cache.head_validation_request(share_objects=True)
        def inner():
            return self.read()
        @cache.head_validation_request(share_objects=True)
        def outer():
            return inner(), inner()
        with patch.object(cache, '_object_store_signature', wraps=cache._object_store_signature) as inventory:
            self.assertEqual((b'first', b'first'), outer())
            self.assertEqual(2, inventory.call_count)
            self.assertEqual(b'first', inner())
            self.assertEqual(4, inventory.call_count)
    def test_original_error_is_preserved_and_scope_is_reset(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            self.read(); raise ValueError('original readonly failure')
        with self.assertRaisesRegex(ValueError, 'original readonly failure'):
            verify()
        self.assertIsNone(cache._OBJECT_REQUEST.get())
        self.assertEqual(b'first', self.read())
    def test_temporary_executor_change_cannot_be_hidden_by_restore(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            self.read()
            with patch.object(subprocess, 'check_output', return_value=b'forged'):
                self.assertEqual(b'forged', self.read())
            return True
        with self.assertRaisesRegex(AssertionError, 'environment changed'):
            verify()
    def test_caught_temporary_environment_change_still_blocks_approval(self):
        @cache.head_validation_request(share_objects=True)
        def verify():
            self.read()
            with patch.dict(os.environ, {'GIT_OPTIONAL_LOCKS': 'request-change'}):
                try:self.read()
                except AssertionError:
                    # Catching a rejected inner read must not bless the outer request.
                    pass
            return True
        with self.assertRaisesRegex(AssertionError, 'environment changed'):
            verify()


class V645RevalidatedEvidenceTests(unittest.TestCase):
    # Reuse the same real-Git fixtures and fault cases for V645's historical
    # three-field rows; no copy of the production verifier or old test edits.
    setUp = RevalidatedEvidenceTests.setUp
    git = RevalidatedEvidenceTests.git
    clear = RevalidatedEvidenceTests.clear
    def aggregate(self):
        return sync._v645_immutable_commit_evidence(self.a, self.b, (self.name,))
    test_config = RevalidatedEvidenceTests.test_diff_config_is_replayed_on_a_warm_result
    test_blob_replace = RevalidatedEvidenceTests.test_blob_replace_rejects_stale_digest
    test_corruption = RevalidatedEvidenceTests.test_object_corruption_rejects_stale_digest
    test_deletion = RevalidatedEvidenceTests.test_deleted_object_is_not_a_cached_success
    test_injected_reader = RevalidatedEvidenceTests.test_injected_high_level_reader_is_live
    test_return_boundary = RevalidatedEvidenceTests.test_return_boundary_rejects_object_deleted_after_aggregate_reuse
    def test_real_reuse_returns_independent_historical_rows(self):
        expected = copy.deepcopy(self.aggregate())
        before = sync._v645_immutable_commit_evidence.cache_info()
        _, changed, rows = self.aggregate()
        changed.clear(); rows.clear()
        self.assertEqual(expected, self.aggregate())
        after = sync._v645_immutable_commit_evidence.cache_info()
        self.assertEqual(before.misses, after.misses)
        self.assertGreater(after.hits, before.hits)
    def test_missing_baseline_preserves_original_code_and_stdout_digest(self):
        (self.root / 'added.txt').write_bytes(b'added')
        self.git('add', '.'); self.git('commit', '-qm', 'added')
        candidate = self.git('rev-parse', 'HEAD').decode().strip()
        args = self.a, candidate, (self.name, 'added.txt')
        expected = sync._v645_immutable_commit_evidence.__wrapped__(*args)
        self.assertEqual(expected, sync._v645_immutable_commit_evidence(*args))
        self.assertEqual(expected, sync._v645_immutable_commit_evidence(*args))
        self.assertEqual((hashlib.sha256(b'added').hexdigest(), 128,
                          hashlib.sha256(b'').hexdigest()), expected[2]['added.txt'])


class PinnedVectorMetadataTests(unittest.TestCase):
    setUp = SuccessorGitReadTests.setUp
    git = SuccessorGitReadTests.git
    advance = SuccessorGitReadTests.advance
    def command(self):
        self.advance()
        self.second = self.git('rev-parse', 'HEAD').decode().strip()
        return ['git', 'rev-parse', self.first + ':sample.txt', self.second + ':sample.txt']
    def test_native_pinned_vector_reuses_object_metadata(self):
        args = self.command()
        expected = self.git(*args[1:])
        self.assertEqual(expected, cache.git_validation_output(args, cwd=self.repo))
        before = cache._cached_object_read.cache_info()
        self.assertEqual(expected, cache.git_validation_output(args, cwd=self.repo))
        self.assertEqual(before.hits + 1, cache._cached_object_read.cache_info().hits)
    def test_vector_observes_commit_replace(self):
        args = self.command(); before = cache.git_validation_output(args, cwd=self.repo)
        self.git('replace', self.first, self.second)
        after = cache.git_validation_output(args, cwd=self.repo)
        self.assertNotEqual(before, after)
        self.assertEqual(self.git(*args[1:]), after)
    def test_vector_rejects_deleted_commit(self):
        args = self.command(); cache.git_validation_output(args, cwd=self.repo)
        (self.repo / '.git/objects' / self.first[:2] / self.first[2:]).unlink()
        with self.assertRaises(subprocess.CalledProcessError):
            cache.git_validation_output(args, cwd=self.repo)
    def test_vector_with_mutable_operand_stays_live(self):
        args = self.command(); args[-1] = 'HEAD:sample.txt'
        self.assertIsNone(cache._immutable_command(args, str(self.repo), subprocess.run, allow_head=True))
        before = cache.git_validation_output(args, cwd=self.repo)
        (self.repo / 'sample.txt').write_text('third'); self.git('commit', '-qam', 'third')
        after = cache.git_validation_output(args, cwd=self.repo)
        self.assertNotEqual(before, after)


class V881InitialProofTests(unittest.TestCase):
    def test_unvalidated_csp_proof_cannot_seed_future_live_acceptance(self):
        # Use the complete original historical source and validator. Give both
        # Path readers the same simulated file contents, including the forged
        # CSP proof that the V881-only live index does not otherwise exercise.
        root = sync.ROOT
        v881 = json.loads((root / '.github/tablet-autonomy/video_ui_successor_v881.json').read_text())
        original_files = {root / row['path']: subprocess.check_output(
            ['git', 'show', '40cca325b84e5eef04f3a5987aea371b111c86c0:' + row['path']], cwd=root)
            for row in v881['reviewed_files']}
        malicious = b'<html>unreviewed runtime</html>'
        proof_path = root / '.github/tablet-autonomy/csp_hash_successor_v882.json'
        forged = json.loads(proof_path.read_text())
        forged.update(reviewed_sha256=hashlib.sha256(malicious).hexdigest(), reviewed_bytes=len(malicious))
        proof_bytes = json.dumps(forged, sort_keys=True).encode()
        read_bytes, read_text = Path.read_bytes, Path.read_text
        current = [original_files[root / 'index.html']]
        def bytes_at(path):
            if path == root / 'index.html':
                return current[0]
            if path in original_files:
                return original_files[path]
            return proof_bytes if path == proof_path else read_bytes(path)
        def text_at(path, *args, **kwargs):
            return proof_bytes.decode() if path == proof_path else read_text(path, *args, **kwargs)
        sync._v881_immutable_review_at_head.cache_clear()
        with patch.object(Path, 'read_bytes', bytes_at), patch.object(Path, 'read_text', text_at):
            try:
                sync._v881_cached_immutable_live_verified()
            except AssertionError as exc:
                self.assertEqual('csp_hash_successor_v882.json', str(exc))
                return  # Reject the forged proof before accepting any live file.
            current[0] = malicious
            with self.assertRaises(AssertionError):
                sync._v881_cached_immutable_live_verified()


class HistoricalScopeEligibilityTests(unittest.TestCase):
    """Native ancestry/diff must establish removability before costly live scans."""
    setUp = RevalidatedEvidenceTests.setUp
    git = RevalidatedEvidenceTests.git
    clear = RevalidatedEvidenceTests.clear
    children = {
        645: (), 647: (),
        648: ('v1019_radar_scope', 'v993_hot_scope', 'v652_scope', 'v651_update_scope'),
        649: (), 650: (), 651: ('v652_scope',), 652: ('v653_scope',),
        653: ('v881_scope', 'v654_scope'), 654: ('v655_scope',),
        655: ('v656_scope',), 656: ('v657_scope', 'v1021_browser_scope'),
        657: ('v661_scope', 'v1021_browser_scope', 'v658_scope'),
        658: ('v995_ui_event_scope', 'v1021_browser_scope', 'v661_scope'),
        661: ('v662_scope',), 662: ('v663_scope',), 663: ('v664_scope',),
        664: ('v880_scope',), 880: ('v881_scope',),
    }

    def scope(self, version, base, source, *, blocked=False):
        suffix = {645: 'feature', 647: 'ci', 648: 'update', 649: 'update',
                  650: 'update', 651: 'update'}.get(version)
        stem = f'v{version}' + ('_' + suffix if suffix else '')
        with ExitStack() as stack:
            # Isolate this generation's eligibility from independently tested
            # later filters; the ancestry/diff commands below use real Git.
            for child in self.children[version]:
                stack.enter_context(patch.object(sync, 'preserve_reviewed_' + child,
                    lambda visible, *args, **kwargs: visible))
            stack.enter_context(patch.object(sync, stem.upper() + '_PROOF',
                {'base_commit': base, 'reviewed_sha256': {self.name: self.new}}))
            validator = stack.enter_context(patch.object(sync, 'assert_' + stem + '_successor',
                side_effect=AssertionError('unreviewed live bytes') if blocked else None))
            result = getattr(sync, 'preserve_reviewed_' + stem + '_scope')([self.name], source)
            return result, validator.call_count

    def test_earlier_change_remains_visible_without_unneeded_live_scan(self):
        for version in self.children:
            with self.subTest(version=version):
                self.assertEqual(([self.name], 0), self.scope(version, self.b, self.a))

    def test_removable_change_still_requires_full_live_validation(self):
        for version in self.children:
            with self.subTest(version=version):
                self.assertEqual(([], 1), self.scope(version, self.a, self.a))

    def test_failed_live_validation_never_removes_an_eligible_path(self):
        for version in self.children:
            with self.subTest(version=version):
                self.assertEqual(([self.name], 1), self.scope(version, self.a, self.a, blocked=True))

    def test_later_source_is_retained_without_unneeded_live_scan(self):
        for version in self.children:
            with self.subTest(version=version):
                self.assertEqual(([self.name], 0), self.scope(version, self.a, self.b))


class UIScopeEligibilityTests(unittest.TestCase):
    """Keep prior UI edits visible and require live proof for every removal."""
    def v881(self, source, *, blocked=False):
        reviewed = {'execution/tablet_market_hub_v881.html',
                    'execution/tests/test_tablet_market_hub_v881.py', 'index.html', 'sw.js',
                    'tablet_runtime_manifest.py', 'tcg_updater.py', 'verify_link_runtime.py',
                    'verify_v107_code_audit.py'}
        with patch.object(sync, 'preserve_reviewed_v995_ui_event_scope', side_effect=lambda v, *a: v), \
             patch.object(sync, 'preserve_reviewed_v1021_browser_scope', side_effect=lambda v, *a: v), \
             patch.object(sync, '_v881_cached_immutable_live_verified', return_value=sorted(reviewed),
                          side_effect=AssertionError('unreviewed UI') if blocked else None) as checked:
            result = sync.preserve_reviewed_v881_scope(['index.html'], source)
        return result, checked.call_count

    def v995(self, source, *, blocked=False):
        from execution.tests import test_ui_event_successor_v995 as proof
        with patch.object(sync, 'preserve_reviewed_v1001_scope', side_effect=lambda v, *a: v), \
             patch.object(sync, 'preserve_reviewed_v1003_ui_scope', side_effect=lambda v, *a: v), \
             patch.object(proof, 'validate_v995_successors', return_value=['index.html'],
                          side_effect=AssertionError('unreviewed UI') if blocked else None) as checked:
            result = sync.preserve_reviewed_v995_ui_event_scope(['index.html'], source)
        return result, checked.call_count

    def test_prior_ui_changes_do_not_invoke_unneeded_live_acceptance(self):
        for scope in (self.v881, self.v995):
            with self.subTest(scope=scope.__name__):
                self.assertEqual((['index.html'], 0), scope(sync.V525_GRADE_BASE))

    def test_ui_removal_still_requires_successful_full_live_validation(self):
        from execution.tests import test_ui_event_successor_v995 as proof
        for scope, base in ((self.v881, 'f538d136c033f838016e910cd24374a79dbc0b15'),
                            (self.v995, proof.EXPECTED['reviewed_files']['index.html']['baseline_commit'])):
            with self.subTest(scope=scope.__name__):
                self.assertEqual(([], 1), scope(base))
                self.assertEqual((['index.html'], 1), scope(base, blocked=True))


class NativeDirectProofHeadBoundaryTests(unittest.TestCase):
    """Changing a real ref after successful evidence must block public approval."""
    setUp = RevalidatedEvidenceTests.setUp
    git = RevalidatedEvidenceTests.git
    clear = RevalidatedEvidenceTests.clear

    def test_v993_ref_change_after_history_is_rejected(self):
        proof = copy.deepcopy(sync.V993_HOT_SUCCESSOR)
        proof.update(path=self.name, baseline_commit=self.a, candidate_commit=self.b,
                     baseline_sha256=self.old, reviewed_sha256=self.new)
        document = self.root / '.github/tablet-autonomy/hot_sale_successor_v993.json'
        document.parent.mkdir(parents=True)
        document.write_text(json.dumps(proof))
        history = sync._v993_immutable_hot_evidence
        def changed_head(*args, **kwargs):
            result = history(*args, **kwargs)
            self.git('update-ref', 'HEAD', self.a)
            return result
        try:
            with patch.object(sync, 'V993_HOT_SUCCESSOR', proof), \
                 patch.object(sync, '_v993_immutable_hot_evidence', changed_head):
                with self.assertRaisesRegex(AssertionError, 'HEAD changed'):
                    sync._v993_hot_live_verified()
        finally:
            self.git('update-ref', 'HEAD', self.b)
        self.assertIsNone(cache._HEAD_REQUEST.get())
        self.assertIsNone(cache._OBJECT_REQUEST.get())

    def test_direct_v652_ref_change_during_last_live_read_is_rejected(self):
        proof = copy.deepcopy(sync.V652_PROOF)
        proof.update(base_commit=self.a, candidate_commit=self.b,
                     baseline_sha256={self.name: self.old}, reviewed_sha256={self.name: self.new},
                     candidate_auxiliary_paths=[])
        document = self.root / '.github/tablet-autonomy/continuous_learning_image_ui_successor_v652.json'
        document.parent.mkdir(parents=True)
        document.write_text(json.dumps(proof))
        native_read = Path.read_bytes
        def changed_head(path):
            result = native_read(path)
            if path == self.root / self.name:
                self.git('update-ref', 'HEAD', self.a)
            return result
        try:
            with patch.object(sync, 'V652_PROOF', proof), \
                 patch.object(sync, 'V653_PROOF', {'reviewed_sha256': {}}), \
                 patch.object(sync, 'V654_PROOF', {'reviewed_sha256': {}}), \
                 patch.object(Path, 'read_bytes', changed_head):
                with self.assertRaisesRegex(AssertionError, 'HEAD changed'):
                    sync.assert_v652_successor(self)
        finally:
            self.git('update-ref', 'HEAD', self.b)
        self.assertIsNone(cache._HEAD_REQUEST.get())
        self.assertIsNone(cache._OBJECT_REQUEST.get())


class V881NativeHeadBoundaryTests(unittest.TestCase):
    def test_original_reviewed_bytes_do_not_mask_mid_request_head_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'repo'
            # An independent object store preserves the caller's metadata epoch.
            subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(sync.ROOT), str(root)],
                           check=True, capture_output=True)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root)
            before = git('rev-parse', 'HEAD').decode().strip()
            proof = json.loads((root / '.github/tablet-autonomy/video_ui_successor_v881.json').read_text())
            original_bytes = {root / row['path']: git('show', proof['candidate_commit'] + ':' + row['path'])
                              for row in proof['reviewed_files']}
            native_read = Path.read_bytes
            history = sync._v881_immutable_review_at_head
            def read(path):
                return original_bytes[path] if path in original_bytes else native_read(path)
            def changed_head(head):
                result = history(head)
                git('update-ref', 'HEAD', proof['baseline_commit'])
                return result
            try:
                with patch.object(sync, 'ROOT', root), patch.object(Path, 'read_bytes', read), \
                     patch.object(sync, '_v881_immutable_review_at_head', changed_head):
                    with self.assertRaisesRegex(AssertionError, 'HEAD changed'):
                        sync._v881_cached_immutable_live_verified()
            finally:
                git('update-ref', 'HEAD', before)
        self.assertIsNone(cache._HEAD_REQUEST.get())
        self.assertIsNone(cache._OBJECT_REQUEST.get())


def load_tests(loader, tests, pattern):
    # The existing root grading suite already loads this module. Include the
    # batch regressions here so current CI executes them without a new root.
    tests.addTests(loader.loadTestsFromName('execution.tests.test_git_batch_evidence_20261124'))
    # Installer Git/index and failure-cleanup regressions use the same existing
    # root entrypoint, including the formerly unregistered hidden-index cases.
    tests.addTests(loader.loadTestsFromName('execution.tests.test_index_visibility_review_20261125'))
    tests.addTests(loader.loadTestsFromName('execution.tests.test_installer_runtime_guard_20261125'))
    tests.addTests(loader.loadTestsFromName('execution.tests.test_installer_lock_runtime_20261124'))
    return tests
