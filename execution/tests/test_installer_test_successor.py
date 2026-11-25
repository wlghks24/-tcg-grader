"""Real Git fixtures for the V645 historical regression lineage proof."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import installer_test_successor as m


class InstallerTestSuccessorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        self.path = self.root / m.NAME; self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'original test\n'); self.historical = self.commit()
        self.pins = [self.pin()]
        (self.root/'unrelated').write_text('base'); self.base = self.commit()
        (self.root/'unrelated').write_text('parent1'); p1 = self.commit()
        self.path.write_bytes(b'reviewed test\n'); c1 = self.commit(); self.pins.append(self.pin())
        (self.root/'unrelated').write_text('parent2'); p2 = self.commit()
        self.path.write_bytes(b'security corrected test\n'); (self.root/m.MANIFEST).write_text('{}\n')
        c2 = self.commit(); self.pins.append(self.pin())
        self.steps = [(p1,c1,(m.NAME,)),(p2,c2,(m.NAME,m.MANIFEST))]
        self.final = self.path.read_bytes()

    def git(self, *args):
        return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git('add','-A'); self.git('commit','-qm','fixture'); return self.git('rev-parse','HEAD')

    def pin(self):
        raw = self.path.read_bytes()
        return hashlib.sha256(raw).hexdigest(),len(raw),self.git('hash-object',str(self.path))

    def verify(self):
        return m._verify(self.root,self.historical,self.base,self.steps,self.pins)

    def extend_recovery_chain(self):
        for contents in (b'recovery HEAD regression\n', b'lock cleanup regression\n'):
            (self.root/'unrelated').write_bytes(contents)
            parent = self.commit()
            self.path.write_bytes(contents)
            candidate = self.commit()
            self.steps.append((parent, candidate, (m.NAME,)))
            self.pins.append(self.pin())
        self.final = self.path.read_bytes()

    def test_four_transition_recovery_chain(self):
        self.extend_recovery_chain()
        self.assertEqual(m.NAME, self.verify())
        self.assertEqual(['other.py'], self.scope())

    def test_recovery_chain_wrong_new_pin(self):
        self.extend_recovery_chain()
        self.pins[3] = ('0'*64, *self.pins[3][1:])
        self.assertRaises(AssertionError, self.verify)

    def test_recovery_chain_missing_transition(self):
        self.extend_recovery_chain()
        self.steps.pop(2)
        self.pins.pop(3)
        self.assertRaises(AssertionError, self.verify)

    def test_recovery_chain_live_tampering(self):
        self.extend_recovery_chain()
        self.verify()
        self.path.write_bytes(b'tamper')
        self.assertRaises(AssertionError, self.verify)
        self.assertIn(m.NAME, self.scope())

    def test_graphify_single_transition_and_live_tampering(self):
        target = self.root / m.GRAPHIFY_NAME
        target.write_bytes(b'original graphify fixture\n')
        historical = self.commit()
        def pin():
            raw = target.read_bytes()
            return hashlib.sha256(raw).hexdigest(), len(raw), self.git('hash-object', str(target))
        old = pin()
        target.write_bytes(b'reviewed graphify fixture\n')
        candidate = self.commit()
        transitions = [(historical, candidate, (m.GRAPHIFY_NAME,))]
        pins = [old, pin()]
        def verify():
            return m._verify(self.root, historical, historical, transitions,
                             pins, name=m.GRAPHIFY_NAME)
        self.assertEqual(m.GRAPHIFY_NAME, verify())
        target.write_bytes(b'tamper')
        self.assertRaises(AssertionError, verify)

    def test_graphify_rejects_wrong_public_pin(self):
        with patch.object(m, '_verify') as proof:
            self.assertRaises(AssertionError, m.validate_graphify_test_successor, '0'*64)
            proof.assert_not_called()

    def test_exact_chain(self): self.assertEqual(m.NAME,self.verify())
    def test_unrelated_later_commit(self):
        (self.root/'other').write_text('later metadata');self.commit();self.assertEqual(m.NAME,self.verify())
    def test_live_tampering_after_success(self):
        self.verify();self.path.write_bytes(b'tamper');self.assertRaises(AssertionError,self.verify)
    def test_committed_drift_with_restored_worktree(self):
        self.path.write_bytes(b'tamper');self.commit();self.path.write_bytes(self.final);self.assertRaises(AssertionError,self.verify)
    def test_wrong_intermediate_digest(self):
        self.pins[1] = ('0'*64,*self.pins[1][1:]);self.assertRaises(AssertionError,self.verify)
    def test_wrong_original_blob(self):
        self.pins[0] = (*self.pins[0][:2],'0'*40);self.assertRaises(AssertionError,self.verify)
    def test_wrong_parent(self):
        _,c2,paths=self.steps[1];self.steps[1]=(self.steps[0][1],c2,paths);self.assertRaises(AssertionError,self.verify)
    def test_extra_path(self):
        (self.root/'extra').write_text('unexpected');self.git('add','extra');self.git('commit','--amend','--no-edit','-q')
        p2,_,paths=self.steps[1];self.steps[1]=(p2,self.git('rev-parse','HEAD'),paths);self.assertRaises(AssertionError,self.verify)
    def test_mode_change(self):
        self.git('update-index','--chmod=+x',m.NAME);self.git('commit','-qm','mode');self.assertRaises(AssertionError,self.verify)
    def test_symlink(self):
        target=self.root/'copy';target.write_bytes(self.final);self.path.unlink();self.path.symlink_to(target);self.assertRaises(AssertionError,self.verify)
    def test_symbolic_ref(self):
        self.base='HEAD';self.assertRaises(AssertionError,self.verify)
    def test_wrong_public_pin(self):
        with patch.object(m,'_verify') as proof:
            self.assertRaises(AssertionError,m.validate_installer_test_successor,'0'*64);proof.assert_not_called()
    def test_unrelated_history(self):
        self.git('switch','--orphan','elsewhere');(self.root/'other').write_text('different');self.commit()
        self.assertRaises(subprocess.CalledProcessError,self.verify)


    def scope(self, source=None, head='HEAD', prior_head=None):
        return m._scope([m.NAME, 'other.py'], self.base if source is None else source,
                        head, prior_head, self.root, self.historical, self.base, self.steps, self.pins)

    def test_scope_exact_source(self): self.assertEqual(['other.py'], self.scope())
    def test_scope_original_source(self): self.assertEqual(['other.py'], self.scope(self.historical))
    def test_scope_non_head(self): self.assertIn(m.NAME, self.scope(head=self.base))
    def test_scope_prior_boundary(self): self.assertIn(m.NAME, self.scope(prior_head=self.base))
    def test_scope_symbolic_source(self): self.assertIn(m.NAME, self.scope('HEAD'))
    def test_scope_later_source(self): self.assertIn(m.NAME, self.scope(self.steps[0][1]))
    def test_scope_tamper_after_success(self):
        self.assertEqual(['other.py'], self.scope())
        self.path.write_bytes(b'tamper'); self.assertIn(m.NAME, self.scope())
    def test_scope_wrong_pin(self):
        self.pins[1] = ('0'*64,*self.pins[1][1:]); self.assertIn(m.NAME,self.scope())
    def test_scope_unrelated_source(self):
        self.git('switch','--orphan','elsewhere'); (self.root/'other').write_text('different'); other=self.commit()
        self.assertIn(m.NAME,self.scope(other))


if __name__ == '__main__': unittest.main()
