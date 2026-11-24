import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import installer_lock_successor as m


class InstallerSuccessorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.path = self.root / m.INSTALLER
        self.path.parent.mkdir()
        self.path.write_bytes(b'earlier implementation\n')
        self.commit('earlier')
        self.older = self.sha()
        self.original = b'def fixture():\n' + m.OLD + b'        pass\n    finally:\n        pass\n'
        self.path.write_bytes(self.original)
        self.commit('historical')
        self.historical = self.sha()
        (self.root / 'unrelated').write_text('base')
        self.commit('review base')
        self.base = self.sha()
        self.fixed = m.exact_change(self.original)
        self.path.write_bytes(self.fixed)
        self.commit('exact fix')
        self.candidate = self.sha()
        self.digest = hashlib.sha256(self.original).hexdigest()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE)
    def commit(self, msg):
        self.git('add', '.'); self.git('commit', '-qm', msg)
    def sha(self): return self.git('rev-parse', 'HEAD').decode().strip()
    def verify(self): return m._verify(self.root, self.historical, self.base, self.candidate, self.digest, len(self.original))
    def scope(self, source=None, head='HEAD', prior=None):
        return m._scope([m.INSTALLER, 'other.py'], self.historical if source is None else source, head, prior, self.root, self.historical, self.base, self.candidate, self.digest, len(self.original))
    def test_exact_transition(self): self.assertEqual(self.original, self.verify())
    def test_exact_scope_keeps_unrelated(self): self.assertEqual(['other.py'], self.scope())
    def test_earlier_change_visible(self): self.assertEqual([m.INSTALLER, 'other.py'], self.scope(self.older))
    def test_non_head_visible(self): self.assertIn(m.INSTALLER, self.scope(head=self.base))
    def test_symbolic_source_visible(self): self.assertIn(m.INSTALLER, self.scope('HEAD'))
    def test_earlier_boundary(self):
        self.assertEqual(['other.py'], self.scope(prior=self.base))
        self.assertIn(m.INSTALLER, self.scope(prior=self.older))
        self.assertIn(m.INSTALLER, self.scope(prior=self.candidate))
    def test_live_tamper_after_warmup(self):
        self.verify()
        self.path.write_bytes(self.fixed+b'# tamper\n')
        with self.assertRaises(AssertionError): self.verify()
        self.assertIn(m.INSTALLER, self.scope())
    def test_committed_tamper_restored_worktree(self):
        self.path.write_bytes(self.fixed+b'# tamper\n'); self.commit('tamper'); self.path.write_bytes(self.fixed)
        with self.assertRaises(AssertionError): self.verify()
    def test_candidate_reverted_to_old(self):
        self.path.write_bytes(self.original); self.commit('revert')
        with self.assertRaises(AssertionError): self.verify()
        self.assertIn(m.INSTALLER, self.scope())
    def test_extra_path(self):
        (self.root/'extra').write_text('x'); self.git('add','extra'); self.git('commit','--amend','--no-edit','-q'); self.candidate=self.sha()
        with self.assertRaises(AssertionError): self.verify()
    def test_wrong_parent(self):
        self.git('commit','--allow-empty','-qm','extra'); self.candidate=self.sha()
        with self.assertRaises(AssertionError): self.verify()
    def test_wrong_digest(self):
        self.digest='0'*64
        with self.assertRaises(AssertionError): self.verify()
    def test_symlink(self):
        outside=self.root/'copy'; outside.write_bytes(self.fixed); self.path.unlink(); self.path.symlink_to(outside)
        with self.assertRaises(AssertionError): self.verify()
    def test_mode_change(self):
        self.git('update-index','--chmod=+x',m.INSTALLER); self.git('commit','-qm','mode')
        with self.assertRaises(AssertionError): self.verify()
    def test_detached_before_candidate(self):
        self.git('checkout','--detach',self.base)
        with self.assertRaises(subprocess.CalledProcessError): self.verify()
        self.assertIn(m.INSTALLER, self.scope())
    def test_candidate_change_not_exact(self):
        self.path.write_bytes(self.fixed+b'# added\n'); self.git('commit','-qam','amend','--amend'); self.candidate=self.sha()
        with self.assertRaises(AssertionError): self.verify()
    def test_wrong_predecessor_pin(self):
        with self.assertRaises(AssertionError): m.validate_installer_lock_successor('0'*64)
    def test_duplicate_edit_token(self):
        with self.assertRaises(AssertionError): m.exact_change(m.OLD+m.OLD)
    def test_new_unrelated_commit_allowed(self):
        (self.root/'unrelated').write_text('new'); self.commit('later unrelated')
        self.assertEqual(self.original,self.verify())
    def test_forged_read(self):
        self.verify(); original=Path.read_bytes
        with patch.object(Path,'read_bytes',lambda p: original(p)+b' tamper' if p==self.path else original(p)):
            with self.assertRaises(AssertionError): self.verify()
            self.assertIn(m.INSTALLER,self.scope())

if __name__=='__main__': unittest.main()
