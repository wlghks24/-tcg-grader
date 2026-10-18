"""Fail-closed regression for autonomous version drift without web/device I/O."""
import tempfile
import unittest
from pathlib import Path
from execution.autonomy_lineage_guard import WORKFLOW, audit


class AutonomyLineageGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        flow = self.root / WORKFLOW
        flow.parent.mkdir(parents=True)
        self.flow = flow
        self.flow.write_text('on:\n  schedule:\n  workflow_dispatch:\npermissions:\n  contents: read\n'
                             'jobs:\n  verify:\n    steps:\n', encoding='utf-8')
        self.write_version('tablet_autonomous_evolution_v', 398)
        self.write_version('tablet_autonomous_evolution_v', 399)
        self.write_version('tablet_autonomous_evolution_v', 400)
        self.write_version('tcg_grader_autonomous_evolution_v', 397)

    def write_version(self, prefix, version, *, covered=True, with_test=True):
        filename = f'{prefix}{version}.py'
        test_name = f'test_{prefix}{version}.py'
        (self.root / filename).write_text('# controller\n', encoding='utf-8')
        if with_test:
            (self.root / test_name).write_text('# test\n', encoding='utf-8')
        if covered:
            with self.flow.open('a', encoding='utf-8') as handle:
                handle.write('      - run: python ' + filename + ' --self-test\n')
                handle.write('      - run: python -m unittest -v ' + test_name + '\n')

    def test_all_current_version_pairs_wired(self):
        result = audit(self.root)
        self.assertEqual('PASS', result['status'])
        self.assertFalse(result['source_code_modified'])
        self.assertFalse(result['physical_tablet_verified'])
        self.assertEqual([398, 399, 400], result['families']['tablet_autonomous_evolution_v']['latest_required_in_existing_workflow'])

    def test_new_version_missing_ci_is_hold(self):
        self.write_version('tablet_autonomous_evolution_v', 401, covered=False)
        result = audit(self.root)
        self.assertEqual('HOLD', result['status'])
        self.assertTrue(any('CI_SELF_TEST_MISSING' in issue for issue in result['issues']))

    def test_version_missing_test_is_hold(self):
        self.write_version('tablet_autonomous_evolution_v', 401, covered=True, with_test=False)
        result = audit(self.root)
        self.assertEqual('HOLD', result['status'])
        self.assertTrue(any('NO_TEST' in issue for issue in result['issues']))

    def test_missing_source_permissions_is_hold(self):
        source = self.flow.read_text(encoding='utf-8').replace('contents: read', 'contents: write')
        self.flow.write_text(source, encoding='utf-8')
        result = audit(self.root)
        self.assertIn('MISSING_READ_ONLY_GITHUB_PERMISSIONS', result['issues'])

    def test_historical_versions_preserved(self):
        self.write_version('tablet_autonomous_evolution_v', 371, covered=False)
        result = audit(self.root)
        self.assertEqual('PASS', result['status'])
        self.assertIn(371, result['families']['tablet_autonomous_evolution_v']['module_versions'])


if __name__ == '__main__':
    unittest.main()
