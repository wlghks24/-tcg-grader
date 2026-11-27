"""Temporary Git tests: reject unrelated transitions and live/committed drift."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from execution import retention_future_marker_successor_20261125 as proof


class RetentionFutureMarkerSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init','-q')
        self.git('config','user.name','TCG fixture')
        self.git('config','user.email','fixture@localhost')
        self.git('config','commit.gpgsign','false')
        self.path = self.root/proof.NAME
        self.path.parent.mkdir()
        self.path.write_bytes(b'old\n')
        self.old = self.commit('old')
        self.old_pin = self.pin(self.old)
        self.path.write_bytes(b'new\n')
        self.new = self.commit('new')
        self.new_pin = self.pin(self.new)

    def git(self,*args):
        return subprocess.check_output(['git','--no-replace-objects',*args],cwd=self.root,stderr=subprocess.PIPE,timeout=10)

    def commit(self,message):
        self.git('add','--all')
        self.git('commit','-qm',message)
        return self.git('rev-parse','HEAD').decode().strip()

    def pin(self,ref):
        raw=self.git('show',ref+':'+proof.NAME)
        blob=self.git('rev-parse',ref+':'+proof.NAME).decode().strip()
        return blob,hashlib.sha256(raw).hexdigest(),len(raw)

    def verify(self,*,previous=b'old\n',base=None,candidate=None,new_pin=None):
        return proof._verify(self.root,self.git,lambda name:(self.root/name).read_bytes(),previous,base or self.old,candidate or self.new,self.old_pin,new_pin or self.new_pin)

    def test_exact_transition_and_unrelated_later_commit(self):
        self.assertEqual(self.verify(),b'new\n')
        (self.root/'unrelated').write_text('safe')
        self.commit('unrelated')
        self.assertEqual(self.verify(),b'new\n')

    def test_wrong_predecessor(self):
        with self.assertRaises(AssertionError):self.verify(previous=b'wrong')

    def test_wrong_parent(self):
        with self.assertRaises(AssertionError):self.verify(base=self.new)

    def test_wrong_pin(self):
        with self.assertRaises(AssertionError):self.verify(new_pin=(self.new_pin[0],'0'*64,self.new_pin[2]))

    def test_live_drift(self):
        self.path.write_bytes(b'tampered')
        with self.assertRaises(AssertionError):self.verify()

    def test_committed_drift(self):
        self.path.write_bytes(b'tampered')
        self.commit('tampered')
        with self.assertRaises(AssertionError):self.verify()

    def test_symlink(self):
        target=self.root/'outside'
        target.write_bytes(b'new\n')
        self.path.unlink();self.path.symlink_to(target)
        with self.assertRaises(AssertionError):self.verify()

    def test_extra_transition_path(self):
        self.git('checkout','--detach',self.old)
        self.path.write_bytes(b'new\n')
        (self.root/'extra').write_text('extra')
        candidate=self.commit('extra')
        with self.assertRaises(AssertionError):self.verify(candidate=candidate,new_pin=self.pin(candidate))

    def test_unreachable_candidate(self):
        self.git('checkout','--detach',self.old)
        with self.assertRaises(subprocess.CalledProcessError):self.verify()


if __name__=='__main__':unittest.main()
