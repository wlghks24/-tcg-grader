"""Real Git cache boundaries, not an exemption from source/fixture checks."""
import os
import hashlib
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import successor_git_reads_20261122 as reads
from execution.git_validation_cache import head_validation_request


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
            subprocess.run(['git','clone','-q',str(self.repo),str(other)],check=True)
            self.assertEqual(reads.read(other,*args),reads.read(self.repo,*args))
            self.assertEqual(reads.metadata.cache_info().currsize,2)


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
        self.assertEqual({'sample.txt':b'second'},self.evidence())
        before=reads._source_evidence.cache_info()
        self.assertEqual(self.evidence(),{'sample.txt':b'second'})
        self.assertEqual(before.hits+1,reads._source_evidence.cache_info().hits)
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
