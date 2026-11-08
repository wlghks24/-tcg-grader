"""V972 release-scope preflight exercises real isolated Git histories."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from execution.tablet_release_preflight_v972 import (
    PreflightHold, inspect, _changes, _paths,
)


class TabletReleasePreflightV972Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tcg-v972-release-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'TCG test reviewer')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / 'execution').mkdir()
        (self.root / 'execution' / 'runtime.py').write_text('CODE = 1\n')
        (self.root / 'learning_store.json').write_text('{}\n')
        (self.root / 'integrity_manifest.json').write_text('{}\n')
        self.git('add', '--all')
        self.git('commit', '-qm', 'stable V927 fixture base')
        self.base = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        p = subprocess.run(
            ['git', '-C', str(self.root), *args],
            capture_output=True, text=True, timeout=12, check=False)
        self.assertEqual(p.returncode, 0, (args, p.stderr))
        return p.stdout.strip()

    def candidate(self, changes, *, deletes=(), symlinks=()):
        self.git('checkout', '-q', '--detach', self.base)
        for name, data in changes.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding='utf-8')
        for name, target in symlinks:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
        for name in deletes:
            self.git('rm', '-q', '--', name)
        self.git('add', '--all')
        self.git('commit', '-qm', 'new reviewed-source candidate')
        target = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', '--detach', self.base)
        return target

    def test_exact_v927_like_scope_protects_local_learning_bytes(self):
        target = self.candidate({
            'execution/runtime.py': 'CODE = 2\n',
            'execution/tablet_new.py': 'SAFE = True\n',
            '.github/workflows/v972-review.yml': 'name: audit\n',
            '.github/tablet-autonomy/v954.json': '{"proof": true}\n',
            'sync_v376_successor_test_support.py': '# review only\n',
            'integrity_manifest.json': '{"version": 2}\n',
        })
        data = self.root / 'learning_store.json'
        data.write_bytes(b'{"private_learning":[1,2,3]}\n')
        before = (self.git('rev-parse', 'HEAD'),
                  self.git('status', '--porcelain'),
                  data.read_bytes(),
                  self.git('show-ref'))
        r = inspect(self.root, self.base, target)
        after = (self.git('rev-parse', 'HEAD'),
                 self.git('status', '--porcelain'),
                 data.read_bytes(),
                 self.git('show-ref'))
        self.assertEqual(before, after)
        self.assertEqual(r['status'], 'HOLD_RELEASE_INTEGRATION')
        self.assertEqual(r['tracked_change_count'], 6)
        self.assertEqual(r['excluded_scope_count'], 3)
        self.assertEqual(r['modified_tracked_json_count'], 1)
        self.assertEqual(r['mutated_candidate_json_paths'],
                         ['.github/tablet-autonomy/v954.json'])
        self.assertIn('CHANGED_JSON_EVIDENCE_OR_RUNTIME', r['blocking'])
        self.assertIn('OUT_OF_V897_SCOPE', r['blocking'])
        self.assertFalse(r['installation_permitted'])
        self.assertFalse(r['network_used'])

    def test_scope_only_pass_never_means_device_install_is_permitted(self):
        target = self.candidate({'execution/runtime.py': 'CODE = 7\n'})
        report = inspect(self.root, self.base, target)
        self.assertEqual(report['status'], 'SCOPE_ONLY_REVIEW_PASSED')
        self.assertEqual(report['blocking'], [])
        self.assertFalse(report['installation_permitted'])
        self.assertFalse(report['device_restarted'])

    def test_candidate_change_to_mutable_root_json_is_hard_hold(self):
        target = self.candidate({'learning_store.json': '{"erased": true}\n'})
        r = inspect(self.root, self.base, target)
        self.assertIn('CHANGED_JSON_EVIDENCE_OR_RUNTIME', r['blocking'])
        self.assertFalse(r['installation_permitted'])

    def test_deleting_existing_feature_never_passes(self):
        target = self.candidate({}, deletes=('execution/runtime.py',))
        r = inspect(self.root, self.base, target)
        self.assertEqual(r['deleted_paths'], ['execution/runtime.py'])
        self.assertIn('REMOVED_SOURCE_FILE', r['blocking'])

    def test_symlink_in_candidate_is_not_regular_runtime_code(self):
        target = self.candidate({}, symlinks=(('execution/safe_link.py', '/tmp/elsewhere'),))
        r = inspect(self.root, self.base, target)
        self.assertEqual(r['unsafe_target_tree_modes'], ['execution/safe_link.py'])
        self.assertIn('SYMLINK_OR_UNSUPPORTED_GIT_MODE', r['blocking'])

    def test_staged_or_overlapping_changes_prevent_claiming_clean_scope(self):
        target = self.candidate({'execution/runtime.py': 'CODE = 9\n'})
        (self.root / 'execution/runtime.py').write_text('LOCAL = 999\n')
        self.git('add', '--', 'execution/runtime.py')
        r = inspect(self.root, self.base, target)
        self.assertIn('STAGED_DEVICE_EDITS', r['blocking'])
        self.assertIn('OVERLAPPING_LOCAL_CHANGES', r['blocking'])
        self.assertIn('UNEXPECTED_LOCAL_SOURCE_DIRTY', r['blocking'])

    def test_no_target_change_is_not_an_install_plan(self):
        with self.assertRaisesRegex(PreflightHold, 'SOURCE_TARGET_IDENTICAL'):
            inspect(self.root, self.base, self.base)

    def test_untested_abbreviated_or_forged_commits_refused(self):
        target = self.candidate({'execution/runtime.py': 'CODE = 8\n'})
        for b, t in ((self.base[:8], target),
                     (self.base, target[:8]),
                     ('0' * 40, target)):
            with self.assertRaises(PreflightHold):
                inspect(self.root, b, t)

    def test_stale_expected_device_head_fails_closed(self):
        target = self.candidate({'execution/runtime.py': 'CODE = 3\n'})
        self.git('checkout', '-q', '--detach', target)
        with self.assertRaisesRegex(PreflightHold, 'DEVICE_HEAD_CHANGED'):
            inspect(self.root, self.base, target)

    def test_divergent_git_target_must_not_be_promoted(self):
        target = self.candidate({'execution/runtime.py': 'CODE = 4\n'})
        self.git('checkout', '-q', '--detach', self.base)
        (self.root / 'execution/runtime.py').write_text('CODE = 55\n')
        self.git('add', '--all')
        self.git('commit', '-qm', 'other user descendant')
        divergent_base = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(PreflightHold, 'TARGET_NOT_DESCENDANT'):
            inspect(self.root, divergent_base, target)

    def test_path_parser_preserves_valid_whitespace_names(self):
        self.assertEqual(_paths(b'execution/ leading.py\0'), ['execution/ leading.py'])
        self.assertEqual(_paths(b'execution/trailing .py\0'), ['execution/trailing .py'])

    def test_untracked_candidate_overlap_is_blocked_without_mutation(self):
        target = self.candidate({'execution/new_feature.py': 'FEATURE = 1\n'})
        local = self.root / 'execution/new_feature.py'
        local.write_text('LOCAL DATA\n')
        before = local.read_bytes()
        report = inspect(self.root, self.base, target)
        self.assertIn('OVERLAPPING_UNTRACKED_FILES', report['blocking'])
        self.assertEqual(report['untracked_overlap_paths'], ['execution/new_feature.py'])
        self.assertEqual(local.read_bytes(), before)
        self.assertFalse(report['installation_permitted'])

    def test_ignored_candidate_overlap_is_blocked_without_mutation(self):
        target = self.candidate({'execution/ignored_feature.py': 'FEATURE = 1\n'})
        (self.root / '.gitignore').write_text('execution/ignored_feature.py\n')
        local = self.root / 'execution/ignored_feature.py'
        local.write_text('PRIVATE LOCAL DATA\n')
        before = local.read_bytes()
        report = inspect(self.root, self.base, target)
        self.assertIn('OVERLAPPING_IGNORED_FILES', report['blocking'])
        self.assertEqual(report['ignored_overlap_paths'], ['execution/ignored_feature.py'])
        self.assertEqual(local.read_bytes(), before)
        self.assertFalse(report['installation_permitted'])

    def test_mode_parser_preserves_valid_whitespace_names(self):
        target = self.candidate({'execution/ leading.py': 'CODE = 2\n'})
        report = inspect(self.root, self.base, target)
        self.assertEqual(report['status'], 'SCOPE_ONLY_REVIEW_PASSED')
        self.assertFalse(report['installation_permitted'])

    def test_path_parser_rejects_unsafe_git_names(self):
        for raw in (b'/absolute\0', b'execution/../evil\0',
                    b'execution//bad\0', b'bad\\name\0', b'bad\xff\0'):
            with self.assertRaises(PreflightHold):
                _paths(raw)
        with self.assertRaises(PreflightHold):
            _changes(b'M\0unpaired')
        with self.assertRaises(PreflightHold):
            _changes(b'R100\0file\0')


if __name__ == '__main__':
    unittest.main()
