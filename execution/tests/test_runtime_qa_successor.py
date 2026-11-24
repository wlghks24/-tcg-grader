"""Real temporary Git histories; original historical changes stay visible."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import runtime_qa_successor as m


class RuntimeQASuccessorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.path = self.root / m.NAME
        self.path.write_bytes(b'earlier QA\n')
        self.commit('earlier'); self.earlier = self.sha()
        self.old = b'UPDATER_MARKERS = (\n' + m.OLD + b')\n'
        self.path.write_bytes(self.old)
        self.commit('historical'); self.source = self.sha()
        (self.root / 'unrelated').write_text('base')
        self.commit('base'); self.base = self.sha()
        self.new = m.exact_change(self.old)
        self.path.write_bytes(self.new)
        for name in m.PATHS:
            if name != m.NAME:
                p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('reviewed other file')
        self.commit('reviewed QA'); self.candidate = self.sha()
        self.digest = hashlib.sha256(self.old).hexdigest()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE)
    def commit(self, msg):
        self.git('add', '.'); self.git('commit', '-qm', msg)
    def sha(self): return self.git('rev-parse', 'HEAD').decode().strip()
    def verify(self): return m.verify(self.root, self.base, self.candidate, self.digest, len(self.old))
    def scope(self, source=None, head='HEAD', prior=None):
        return m._scope([m.NAME, 'other.py'], self.source if source is None else source, head, prior, self.root, self.base, self.candidate, self.digest, len(self.old))
    def test_exact_transition(self): self.assertEqual(self.old, self.verify())
    def test_exact_scope(self): self.assertEqual(['other.py'], self.scope())
    def test_earlier_change(self): self.assertIn(m.NAME, self.scope(self.earlier))
    def test_explicit_head(self): self.assertIn(m.NAME, self.scope(head=self.candidate))
    def test_symbolic_source(self): self.assertIn(m.NAME, self.scope('HEAD'))
    def test_boundaries(self):
        self.assertEqual(['other.py'], self.scope(prior=self.base))
        self.assertIn(m.NAME, self.scope(prior=self.earlier))
        self.assertIn(m.NAME, self.scope(prior=self.candidate))
    def test_live_tamper(self):
        self.verify(); self.path.write_bytes(self.new+b'# tamper')
        with self.assertRaises(AssertionError): self.verify()
        self.assertIn(m.NAME, self.scope())
    def test_committed_tamper_with_restored_worktree(self):
        self.path.write_bytes(self.new+b'# tamper'); self.commit('tamper'); self.path.write_bytes(self.new)
        with self.assertRaises(AssertionError): self.verify()
    def test_revert(self):
        self.path.write_bytes(self.old); self.commit('revert')
        self.assertIn(m.NAME, self.scope())
    def test_mode(self):
        self.git('update-index','--chmod=+x',m.NAME); self.git('commit','-qm','mode')
        self.assertIn(m.NAME, self.scope())
    def test_symlink(self):
        p=self.root/'copy';p.write_bytes(self.new);self.path.unlink();self.path.symlink_to(p)
        self.assertIn(m.NAME, self.scope())
    def test_wrong_digest(self):
        self.digest='0'*64; self.assertIn(m.NAME, self.scope())
    def test_wrong_parent(self):
        self.git('commit','--allow-empty','-qm','later');self.candidate=self.sha()
        self.assertIn(m.NAME, self.scope())
    def test_extra_path(self):
        (self.root/'extra').write_text('x');self.git('add','extra');self.git('commit','--amend','--no-edit','-q');self.candidate=self.sha()
        self.assertIn(m.NAME, self.scope())
    def test_not_ancestor(self):
        self.git('checkout','--detach',self.base); self.assertIn(m.NAME, self.scope())
    def test_duplicate_marker(self):
        with self.assertRaises(AssertionError):m.exact_change(m.OLD*2)
    def test_live_read_rechecked(self):
        self.verify();orig=Path.read_bytes
        with patch.object(Path,'read_bytes',lambda p:orig(p)+b'# fake' if p==self.path else orig(p)):
            self.assertIn(m.NAME,self.scope())
    def test_unrelated_later_commit(self):
        (self.root/'unrelated').write_text('later');self.commit('later')
        self.assertEqual(['other.py'],self.scope())

if __name__ == '__main__': unittest.main()
