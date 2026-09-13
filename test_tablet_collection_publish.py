import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tablet_collection_publish as p


class TabletPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in p.OUTPUTS:
            (self.root / name).write_text('{}')
        self.receipt = {'schema_version': 1, 'repository': p.REPO,
                        'base_sha': 'abc', 'source_sha': 'abc',
                        'collected_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                        'sha256': p.hashes(self.root)}

    def save(self):
        (self.root / p.RECEIPT).write_text(json.dumps(self.receipt))

    def test_valid_snapshot_runs_real_gate_entrypoint(self):
        self.save()
        with patch.object(p, 'git', return_value=p.RECEIPT), patch.object(p, 'gates') as gates:
            p.verify_receipt(self.root, 'abc')
        gates.assert_called_once_with(self.root)

    def test_tampering_code_and_stale_base_block_before_gates(self):
        for failure in ('hash', 'code', 'base', 'source', 'age'):
            with self.subTest(failure=failure):
                receipt = dict(self.receipt)
                if failure == 'hash': receipt['sha256'] = {}
                if failure == 'base': receipt['base_sha'] = 'different'
                if failure == 'source': receipt['source_sha'] = 'different'
                if failure == 'age': receipt['collected_at'] = '2000-01-01T00:00:00+00:00'
                (self.root / p.RECEIPT).write_text(json.dumps(receipt))
                changed = p.RECEIPT + ('\nauto_update_all.py' if failure == 'code' else '')
                with patch.object(p, 'git', return_value=changed), patch.object(p, 'gates') as gates:
                    with self.assertRaises(ValueError): p.verify_receipt(self.root, 'abc')
                    gates.assert_not_called()

    def test_symlink_not_uploaded(self):
        path = self.root / p.OUTPUTS[0]
        path.unlink()
        path.symlink_to(self.root / p.OUTPUTS[1])
        with self.assertRaises(ValueError): p.hashes(self.root)

    def test_failed_collection_gate_never_pushes(self):
        commands = []
        def fake_git(root, *args):
            commands.append(args)
            if args[:3] == ('remote', 'get-url', 'origin'): return f'https://github.com/{p.REPO}.git'
            return 'abc'
        with patch.object(p, 'git', side_effect=fake_git), patch.object(p, 'run'), \
             patch.object(p, 'gates', side_effect=ValueError('PSA blocked')):
            with self.assertRaises(ValueError): p.collect(self.root, True)
        self.assertFalse(any('push' in cmd or 'add' == cmd[0] for cmd in commands))


if __name__ == '__main__':
    unittest.main()
