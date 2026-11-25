"""Temporary Git tests; never write to the actual source repository."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from execution import deferred_publish_base_successor as p


class DeferredBaseSuccessorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.path = self.root / p.NAME
        self.path.parent.mkdir()
        self.path.write_bytes(b'old\n')
        self.base = self.commit()
        self.path.write_bytes(b'new\n')
        for name in p.PATHS[1:]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture\n')
        self.head = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE, timeout=10)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD').decode().strip()

    @staticmethod
    def pin(raw):
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def verify(self, previous=b'old\n', **overrides):
        kwargs = dict(base=self.base, candidate=self.head, old=self.pin(b'old\n'), new=self.pin(b'new\n'))
        kwargs.update(overrides)
        return p.verify(self.root, previous, **kwargs)

    def test_exact_transition(self):
        self.assertEqual(b'new\n', self.verify())

    def test_unrelated_later_commit(self):
        (self.root/'other').write_text('ok')
        self.commit()
        self.assertEqual(b'new\n', self.verify())

    def test_wrong_predecessor(self):
        with self.assertRaises(AssertionError): self.verify(b'wrong')

    def test_wrong_parent(self):
        with self.assertRaises(AssertionError): self.verify(base=self.head)

    def test_wrong_pin(self):
        with self.assertRaises(AssertionError): self.verify(new=self.pin(b'wrong'))

    def test_unexpected_path_set(self):
        with self.assertRaises(AssertionError): self.verify(paths=(p.NAME,))

    def test_live_drift(self):
        self.path.write_bytes(b'changed')
        with self.assertRaises(AssertionError): self.verify()

    def test_committed_drift(self):
        self.path.write_bytes(b'changed')
        self.commit()
        with self.assertRaises(AssertionError): self.verify()

    def test_symlink(self):
        target = self.root/'other'
        target.write_bytes(b'new\n')
        self.path.unlink()
        self.path.symlink_to(target)
        with self.assertRaises(AssertionError): self.verify()

    def test_unreachable_successor(self):
        self.git('checkout', '--detach', self.base)
        with self.assertRaises(subprocess.CalledProcessError): self.verify()


if __name__ == '__main__': unittest.main()
