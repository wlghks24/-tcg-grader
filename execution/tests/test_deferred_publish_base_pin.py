"""A candidate must not silently launder a corrupt baseline data pin."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from execution.deferred_publish_tree import verify_git_candidate


class BasePinTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.name = 'grading_company_updates.json'
        self.path = self.root / self.name
        self.manifest = self.root / 'integrity_manifest.json'

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE, timeout=10)

    def commit(self):
        self.git('add', '--all')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD').decode().strip()

    def write(self, raw, *, pin=None):
        self.path.write_bytes(raw)
        row = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.manifest.write_text(json.dumps({'version':2, 'engine':'v', 'generated_at':'fixture', 'files':{self.name: row if pin is None else pin}, 'mutable_json':{}, 'policy':{}}))

    def transition(self, raw=b'{"v":1}', pin=None):
        self.write(raw, pin=pin)
        base = self.commit()
        self.write(b'{"v":2}')
        head = self.commit()
        return verify_git_candidate(self.root, 'grading', base, head, [self.name, 'integrity_manifest.json'])

    def test_good_transition(self):
        self.assertEqual('TREE_PASS', self.transition()['verdict'])

    def test_wrong_base_digest(self):
        with self.assertRaisesRegex(ValueError, 'base data hash mismatch'):
            self.transition(pin={'bytes':7, 'sha256':'0'*64})

    def test_wrong_base_size(self):
        with self.assertRaisesRegex(ValueError, 'base data hash mismatch'):
            self.transition(pin={'bytes':99, 'sha256':hashlib.sha256(b'{"v":1}').hexdigest()})

    def test_bool_base_size(self):
        with self.assertRaisesRegex(ValueError, 'invalid base manifest row'):
            self.transition(pin={'bytes':True, 'sha256':hashlib.sha256(b'{"v":1}').hexdigest()})

    def test_malformed_base_json(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            self.transition(raw=b'{"v":1,"v":3}')

    def test_scalar_base_json(self):
        with self.assertRaisesRegex(ValueError, 'base data JSON root'):
            self.transition(raw=b'123')

    def test_missing_base_pin_field(self):
        with self.assertRaisesRegex(ValueError, 'invalid base manifest row'):
            self.transition(pin={'sha256':'0'*64})


if __name__ == '__main__':
    unittest.main()
