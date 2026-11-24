"""Exact two-route protection successor, real disposable Git history."""
import hashlib
from pathlib import Path
import subprocess
import unittest
from execution import installer_lock_successor as m
from execution.tests import test_installer_lock_successor as fixtures


class InstallerIgnoreSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.InstallerSuccessorTests('test_exact_transition')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        # Use the exact first lock edit and include the real merge token.
        self.f.git('checkout', '--detach', self.f.historical)
        self.f.original += b"        git(repo, 'merge', '--ff-only', target, timeout=180)\n"
        self.f.path.write_bytes(self.f.original)
        self.shell = self.f.root / m.ANDROID
        self.shell_original = b'if git merge --ff-only "$TARGET_MAIN_SHA"; then\n  :\nelif git merge --ff-only origin/main; then\n  :\nfi\n'
        self.shell.write_bytes(self.shell_original)
        self.f.commit('historical updater files')
        self.f.historical = self.f.sha()
        self.f.digest = hashlib.sha256(self.f.original).hexdigest()
        (self.f.root/'unrelated').write_text('review base')
        self.f.commit('base'); self.f.base=self.f.sha()
        self.f.fixed=m.exact_change(self.f.original)
        self.f.path.write_bytes(self.f.fixed)
        self.f.commit('lock fix'); self.f.candidate=self.f.sha()
        (self.f.root/'unrelated').write_text('later review')
        self.f.commit('ignore base'); self.base=self.f.sha()
        self.fixed={m.ANDROID:m.guarded_bytes(m.ANDROID,self.shell_original),m.INSTALLER:m.guarded_bytes(m.INSTALLER,self.f.fixed)}
        for path,data in self.fixed.items(): (self.f.root/path).write_bytes(data)
        self.f.commit('ignore protection');self.candidate=self.f.sha()
        self.shell_digest=hashlib.sha256(self.shell_original).hexdigest()
    def transition(self): return (self.base,self.candidate,self.f.historical,self.shell_digest,len(self.shell_original))
    def verify(self): return m._verify(self.f.root,self.f.historical,self.f.base,self.f.candidate,self.f.digest,len(self.f.original),self.transition())
    def scope(self,source=None): return m._scope([m.INSTALLER,'other.py'],self.f.historical if source is None else source,'HEAD',None,self.f.root,self.f.historical,self.f.base,self.f.candidate,self.f.digest,len(self.f.original),self.transition())
    def test_exact_both_routes(self): self.assertEqual(self.f.original,self.verify()); self.assertEqual(['other.py'],self.scope())
    def test_no_other_bytes_changed(self):
        for path,old in ((m.ANDROID,self.shell_original),(m.INSTALLER,self.f.fixed)):
            self.assertEqual(old,self.fixed[path].replace(b' --no-overwrite-ignore',b'').replace(b", '--no-overwrite-ignore'",b''))
    def test_shell_tamper_after_success(self):
        self.verify();self.shell.write_bytes(self.fixed[m.ANDROID]+b'# tamper\n')
        with self.assertRaises(AssertionError): self.verify()
        self.assertIn(m.INSTALLER,self.scope())
    def test_python_tamper_after_success(self):
        self.verify();self.f.path.write_bytes(self.fixed[m.INSTALLER]+b'# tamper\n')
        with self.assertRaises(AssertionError): self.verify()
    def test_wrong_shell_digest(self):
        self.shell_digest='0'*64
        with self.assertRaises(AssertionError): self.verify()
    def test_extra_path_rejected(self):
        (self.f.root/'extra').write_text('x');self.f.git('add','extra');self.f.git('commit','--amend','--no-edit','-q');self.candidate=self.f.sha()
        with self.assertRaises(AssertionError):self.verify()
    def test_wrong_parent_rejected(self):
        self.f.git('commit','--allow-empty','-qm','extra');self.candidate=self.f.sha()
        with self.assertRaises(AssertionError):self.verify()
    def test_committed_shell_revert_with_restored_worktree(self):
        self.shell.write_bytes(self.shell_original);self.f.commit('revert');self.shell.write_bytes(self.fixed[m.ANDROID])
        with self.assertRaises(AssertionError):self.verify()
    def test_shell_symlink_rejected(self):
        copy=self.f.root/'copy';copy.write_bytes(self.fixed[m.ANDROID]);self.shell.unlink();self.shell.symlink_to(copy)
        with self.assertRaises(AssertionError):self.verify()
    def test_shell_mode_rejected(self):
        self.f.git('update-index','--chmod=+x',m.ANDROID);self.f.git('commit','-qm','mode')
        with self.assertRaises(AssertionError):self.verify()
    def test_earlier_change_remains_visible(self):self.assertIn(m.INSTALLER,self.scope(self.f.older))
    def test_duplicate_merge_token_rejected(self):
        with self.assertRaises(AssertionError):m.guarded_bytes(m.ANDROID,self.shell_original*2)
    def test_wrong_v1011_pin_rejected(self):
        with self.assertRaises(AssertionError):m.validate_android_ignore_successor('0'*64)

if __name__=='__main__':unittest.main()
