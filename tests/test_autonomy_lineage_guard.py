"""Fail-closed regression for autonomous version drift without web/device I/O."""
import tempfile
import unittest
from pathlib import Path
from execution.autonomy_lineage_guard import WORKFLOW, FAMILIES, audit


class AutonomyLineageGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        flow = self.root / WORKFLOW
        flow.parent.mkdir(parents=True)
        self.flow = flow
        path_lines = ''.join("      - '" + name + "'\n"
                             for prefix, _ in FAMILIES
                             for name in (prefix + '*.py', 'test_' + prefix + '*.py'))
        self.flow.write_text(
            'on:\n  schedule:\n  workflow_dispatch:\n  pull_request:\n    paths:\n'
            + path_lines + '  push:\n    branches: [main]\n    paths:\n'
            + path_lines + 'permissions:\n  contents: read\njobs:\n  verify:\n    steps:\n',
            encoding='utf-8')
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


    def test_missing_pr_future_version_trigger_is_hold(self):
        before = self.flow.read_text(encoding='utf-8')
        after = before.replace("      - 'tablet_autonomous_evolution_v*.py'\n", '', 1)
        self.assertNotEqual(before, after)
        self.flow.write_text(after, encoding='utf-8')
        self.assertIn('MISSING_VERSION_WILDCARD:pull_request:tablet_autonomous_evolution_v*.py',
                      audit(self.root)['issues'])

    def test_missing_push_future_version_trigger_is_hold(self):
        before = self.flow.read_text(encoding='utf-8')
        after = before.replace(
            "  push:\n    branches: [main]\n    paths:\n      - 'tablet_autonomous_evolution_v*.py'\n",
            "  push:\n    branches: [main]\n    paths:\n")
        self.assertNotEqual(before, after)
        self.flow.write_text(after, encoding='utf-8')
        self.assertIn('MISSING_VERSION_WILDCARD:push:tablet_autonomous_evolution_v*.py',
                      audit(self.root)['issues'])

    def test_commented_out_ci_does_not_count_as_coverage(self):
        self.write_version('tablet_autonomous_evolution_v', 401, covered=False)
        with self.flow.open('a', encoding='utf-8') as handle:
            handle.write('      # python tablet_autonomous_evolution_v401.py --self-test\n')
            handle.write('      # python -m unittest -v test_tablet_autonomous_evolution_v401.py\n')
        problems = audit(self.root)['issues']
        self.assertTrue(any('CI_SELF_TEST_MISSING' in issue for issue in problems))
        self.assertTrue(any('CI_UNIT_TEST_MISSING' in issue for issue in problems))

    def test_nested_write_permission_is_hold(self):
        with self.flow.open('a', encoding='utf-8') as handle:
            handle.write('      permissions:\n        contents: write\n')
        self.assertIn('WRITABLE_GITHUB_PERMISSIONS', audit(self.root)['issues'])



if __name__ == '__main__':
    unittest.main()
