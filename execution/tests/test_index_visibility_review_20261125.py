"""Regression checks for hidden index flags in the actual installer."""
from execution.tests import test_tablet_preserved_update as fixture

class IndexVisibilityTests(fixture.unittest.TestCase):
    setUp = fixture.PreservedUpdateTests.setUp
    g = fixture.PreservedUpdateTests.g
    dirty = fixture.PreservedUpdateTests.dirty
    apply = fixture.PreservedUpdateTests.apply

    def test_hidden_index_flags_hold(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                name = 'learning_store.json'
                self.g('update-index', flag, name)
                try:
                    data = b'{"live":true}\n'
                    (self.repo / name).write_bytes(data)
                    with self.assertRaisesRegex(fixture.m.Hold, 'HIDDEN_INDEX_STATE'):
                        self.apply()
                    self.assertEqual((self.repo / name).read_bytes(), data)
                    self.assertEqual(self.g('rev-parse', 'HEAD').strip(), self.base)
                finally:
                    self.g('update-index', '--no-assume-unchanged', '--no-skip-worktree', name)
                    self.g('restore', '--', name)

    def test_flag_after_backup_holds_before_mutation(self):
        self.dirty()
        original = fixture.m.receipt
        def inject(path, value):
            original(path, value)
            if value['status'] == 'BACKED_UP':
                self.g('update-index', '--assume-unchanged', 'tcg_updater.py')
        with fixture.mock.patch.object(fixture.m, 'receipt', side_effect=inject):
            out = self.apply()
        self.assertEqual(out['status'], 'HOLD', out)
        self.assertEqual(out['reason'], 'HIDDEN_INDEX_STATE_REQUIRES_REVIEW')
        self.assertEqual(self.g('rev-parse', 'HEAD').strip(), self.base)
        self.assertEqual((self.repo / 'tcg_updater.py').read_text(), 'unstaged local code\n')
