"""Real Git cache boundaries, not an exemption from source/fixture checks."""
import os
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
