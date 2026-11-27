"""Temporary Git history regression for the exact runtime-safety successor."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from execution import installer_runtime_successor as m


class RuntimeSuccessorTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.git('init', '-q'); self.git('config', 'user.name', 'CI'); self.git('config', 'user.email', 'ci@example.invalid')
        self.path = self.root / m.NAME; self.path.parent.mkdir()
        self.old = b'old installer\n'; self.new = b'new reviewed installer\n'
        self.path.write_bytes(self.old); self.previous = self.commit()
        (self.root/'other').write_text('base metadata'); self.base = self.commit()
        self.path.write_bytes(self.new); self.candidate = self.commit()
        self.old_pin = self.pin(self.old); self.new_pin = self.pin(self.new)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git('add', '-A'); self.git('commit', '-qm', 'fixture'); return self.git('rev-parse', 'HEAD')

    def pin(self, data): return hashlib.sha256(data).hexdigest(), len(data)

    def verify(self):
        return m._verify(self.root, self.previous, self.old, self.base, self.candidate, self.old_pin, self.new_pin)

    def test_exact_second_successor_and_tamper(self):
        (self.root/'metadata').write_text('successor base')
        next_base = self.commit()
        final = b'index visibility successor\n'
        self.path.write_bytes(final)
        next_candidate = self.commit()
        args = (self.root, self.previous, self.old, self.base,
                self.candidate, self.old_pin, self.new_pin,
                (next_base, next_candidate, self.pin(final)))
        self.assertEqual(self.old, m._verify(*args))
        self.path.write_bytes(b'live tamper')
        self.assertRaises(AssertionError, m._verify, *args)
        self.path.write_bytes(self.new)
        self.commit()
        self.path.write_bytes(final)
        self.assertRaises(AssertionError, m._verify, *args)

    def test_exact_transition(self): self.assertEqual(self.old, self.verify())
    def test_later_unrelated_metadata_allowed(self):
        (self.root/'metadata').write_text('later proof'); self.commit(); self.assertEqual(self.old, self.verify())
    def test_live_tamper(self):
        self.path.write_bytes(b'live tamper'); self.assertRaises(AssertionError, self.verify)
    def test_committed_revert_with_restored_worktree(self):
        self.path.write_bytes(self.old); self.commit(); self.path.write_bytes(self.new); self.assertRaises(AssertionError, self.verify)
    def test_wrong_old_pin(self): self.old_pin = ('0'*64, len(self.old)); self.assertRaises(AssertionError, self.verify)
    def test_wrong_new_pin(self): self.new_pin = ('0'*64, len(self.new)); self.assertRaises(AssertionError, self.verify)
    def test_wrong_parent(self):
        self.git('commit', '--allow-empty', '-qm', 'extra'); self.candidate = self.git('rev-parse','HEAD'); self.assertRaises(AssertionError, self.verify)
    def test_extra_path(self):
        (self.root/'extra').write_text('unexpected'); self.git('add','extra'); self.git('commit','--amend','--no-edit','-q'); self.candidate=self.git('rev-parse','HEAD'); self.assertRaises(AssertionError,self.verify)
    def test_mode_change(self):
        self.git('update-index','--chmod=+x',m.NAME); self.git('commit','-qm','mode'); self.assertRaises(AssertionError,self.verify)
    def test_symlink_live(self):
        target=self.root/'copy'; target.write_bytes(self.new); self.path.unlink(); self.path.symlink_to(target); self.assertRaises(AssertionError,self.verify)
    def test_symbolic_revision(self): self.base='HEAD'; self.assertRaises(AssertionError,self.verify)
    def test_wrong_previous_bytes(self): self.old=b'wrong predecessor'; self.assertRaises(AssertionError,self.verify)


if __name__ == '__main__': unittest.main()
