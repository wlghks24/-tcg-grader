"""Unit tests for PR814 source-proof schema and fail-closed behavior."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pr814_source_preflight_v665 as m


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '.github/tablet-autonomy').mkdir(parents=True)
        self.path = self.root / m.PROOF_PATH
        self.path.write_text(json.dumps(m.EXPECTED), encoding='utf-8')

    def test_valid_frozen_schema(self):
        self.assertEqual(m.load(self.root), m.EXPECTED)

    def test_refuses_changed_candidate(self):
        p = dict(m.EXPECTED, candidate_commit='a' * 40)
        self.path.write_text(json.dumps(p))
        with self.assertRaisesRegex(m.Hold, 'contract_not_pinned'):
            m.load(self.root)

    def test_refuses_unauthorized_device_claim(self):
        p = dict(m.EXPECTED, deployment_allowed=True)
        self.path.write_text(json.dumps(p))
        with self.assertRaisesRegex(m.Hold, 'contract_not_pinned'):
            m.load(self.root)

    def test_duplicate_keys_rejected(self):
        self.path.write_text('{"schema": 1, "schema": 2}')
        with self.assertRaisesRegex(m.Hold, 'duplicate_json_key'):
            m.load(self.root)

    def test_bad_sha_rejected(self):
        p = json.loads(json.dumps(m.EXPECTED))
        p['reviewed_sha256']['update_promo_events.py']['after'] = '0'*64
        self.path.write_text(json.dumps(p))
        with self.assertRaisesRegex(m.Hold, 'contract_not_pinned'):
            m.load(self.root)

    def test_symlink_contract_rejected(self):
        self.path.unlink()
        self.path.symlink_to(self.root / 'elsewhere.json')
        with self.assertRaisesRegex(m.Hold, 'invalid_contract_path'):
            m.load(self.root)

    def test_oversized_contract_rejected(self):
        self.path.write_bytes(b' ' * 8193)
        with self.assertRaisesRegex(m.Hold, 'invalid_contract_path'):
            m.load(self.root)

    def test_forged_proof_argument_rejected(self):
        with self.assertRaisesRegex(m.Hold, 'contract_not_pinned'):
            m.verify(self.root, dict(m.EXPECTED, physical_tablet_verified=True))

    def test_wrong_checkout_rejected(self):
        with patch.object(m, 'git', return_value=b'/other/repo\n'):
            with self.assertRaisesRegex(m.Hold, 'wrong_repository_root'):
                m.verify(self.root, m.EXPECTED)

    def test_source_change_after_candidate_rejected(self):
        def fake_git(root, *args):
            if args[:2] == ('rev-parse', '--show-toplevel'):
                return (str(root.resolve()) + '\n').encode()
            if args[:3] == ('diff', '--name-only', '--no-renames'):
                return ('\n'.join(m.CHANGED)+'\n').encode()
            if args[:3] == ('diff', '--name-only', m.CANDIDATE):
                return b'update_promo_events.py\n'
            return b''
        with patch.object(m, 'git', side_effect=fake_git):
            with self.assertRaisesRegex(m.Hold, 'unreviewed_descendant_source'):
                m.verify(self.root, m.EXPECTED)

    def test_changed_scope_not_exact(self):
        def fake_git(root, *args):
            if args[:2] == ('rev-parse', '--show-toplevel'):
                return (str(root.resolve()) + '\n').encode()
            return b''
        with patch.object(m, 'git', side_effect=fake_git):
            with self.assertRaisesRegex(m.Hold, 'changed_scope_not_exact'):
                m.verify(self.root, m.EXPECTED)


if __name__ == '__main__':
    unittest.main()
