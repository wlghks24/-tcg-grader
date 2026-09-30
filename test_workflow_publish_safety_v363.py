import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


WORKFLOW_DIR = Path('.github/workflows')
HELPER = Path('scripts/publish_candidate_pr.sh')
MANIFEST_RECONCILER = Path('scripts/manifest_semantic_reconcile.py')
SAFETY_WORKFLOW = WORKFLOW_DIR / 'workflow-publish-safety-v363.yml'

# Direct updates of protected main from Actions are forbidden.  Keep these
# patterns focused on git push destinations so comments/documentation do not
# create noise while common spelling variants remain covered.
FORBIDDEN = (
    re.compile(r'git\s+push[^\n]*(?:HEAD:main|HEAD:refs/heads/main)'),
    re.compile(r'git\s+push[^\n]*origin\s+main(?:\s|$)'),
    re.compile(r'git\s+push[^\n]*refs/heads/main'),
)
REQUIRED_PUBLISH_PERMISSIONS = (
    'contents: write',
    'pull-requests: write',
    'actions: write',
    'checks: read',
)
REQUIRED_CHECKS = (
    'Tablet GPT TCG Grader Main Alignment',
    'Repository Integrity Guard',
    'Main SELFREFINE',
    'Deep SELFREFINE Guard',
    'Exhaustive SELFREFINE Guard',
    'Tablet Termux Main Guard',
    'Android Updater Guard',
)


class WorkflowPublishSafetyV363Tests(unittest.TestCase):
    def test_no_workflow_directly_pushes_main(self):
        offenders = []
        for path in sorted(WORKFLOW_DIR.glob('*.yml')):
            text = path.read_text(encoding='utf-8')
            for pattern in FORBIDDEN:
                if pattern.search(text):
                    offenders.append(f'{path}:{pattern.pattern}')
                    break
        self.assertEqual([], offenders, '\n'.join(offenders))

    def test_candidate_publishers_have_complete_permissions(self):
        publishers = []
        missing = []
        for path in sorted(WORKFLOW_DIR.glob('*.yml')):
            text = path.read_text(encoding='utf-8')
            # Count only actual publisher invocations.  The safety workflow itself
            # references the helper path in triggers and `bash -n`, but it does not
            # publish a candidate and therefore must not be treated as one.
            if 'bash scripts/publish_candidate_pr.sh' not in text:
                continue
            publishers.append(str(path))
            absent = [value for value in REQUIRED_PUBLISH_PERMISSIONS if value not in text]
            if absent:
                missing.append(f'{path}:{absent}')
        self.assertGreater(len(publishers), 0)
        self.assertEqual([], missing, '\n'.join(missing))

    def test_shared_publisher_is_fail_closed_and_exact_check_gated(self):
        text = HELPER.read_text(encoding='utf-8')
        for marker in (
            'BASE_ADVANCED',
            'BASE_ADVANCED_BEFORE_MERGE',
            'REQUIRED_CHECK_FAILED',
            'REQUIRED_CHECK_TIMEOUT',
            'MERGE_REJECTED',
            'refs/heads/${candidate_branch}',
            'pulls/${pr_number}/merge',
            '-f merge_method=merge -f sha="${candidate_sha}"',
        ):
            self.assertIn(marker, text)
        for name in REQUIRED_CHECKS:
            self.assertIn(name, text)
        self.assertNotIn('HEAD:main', text)
        self.assertNotRegex(text, r'git\s+(?:push|reset)[^\n]*--force')
        self.assertNotIn('--admin', text)

    def test_publisher_rejects_noncurrent_or_empty_candidate(self):
        text = HELPER.read_text(encoding='utf-8')
        self.assertIn('run_base_sha', text)
        self.assertIn('current_main_sha', text)
        self.assertIn('NO_CANDIDATE_COMMIT', text)
        self.assertIn('git merge-base --is-ancestor', text)

    def test_safety_writer_has_no_pr_or_wildcard_write_trigger(self):
        text = SAFETY_WORKFLOW.read_text(encoding='utf-8')
        trigger = text.split('\npermissions:', 1)[0]
        self.assertNotIn('pull_request:', trigger)
        self.assertIn('fix/remove-direct-main-publishers-v363-final', trigger)
        self.assertNotIn("'fix/**'", trigger)
        self.assertNotIn('fix/**', trigger)
        self.assertIn("github.ref == 'refs/heads/fix/remove-direct-main-publishers-v363-final'", text)

    def test_manifest_reconciler_restores_timestamp_only_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / 'before.json'
            after = root / 'after.json'
            base = {
                'version': 2,
                'engine': 'test',
                'generated_at': '2026-09-30T00:00:00Z',
                'files': {'a.py': {'sha256': 'abc', 'bytes': 1}},
                'mutable_json': {},
                'policy': {'generated_code_auto_applied': False},
            }
            rebuilt = dict(base)
            rebuilt['generated_at'] = '2026-09-30T00:01:00Z'
            before.write_text(json.dumps(base), encoding='utf-8')
            after.write_text(json.dumps(rebuilt), encoding='utf-8')
            proc = subprocess.run(
                ['python', str(MANIFEST_RECONCILER), str(before), str(after)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertIn('MANIFEST_SEMANTIC_NOOP_RESTORED', proc.stdout)
            self.assertEqual(base, json.loads(after.read_text(encoding='utf-8')))

            changed = dict(rebuilt)
            changed['files'] = {'a.py': {'sha256': 'def', 'bytes': 1}}
            after.write_text(json.dumps(changed), encoding='utf-8')
            proc = subprocess.run(
                ['python', str(MANIFEST_RECONCILER), str(before), str(after)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertIn('MANIFEST_SEMANTIC_CHANGE_RETAINED', proc.stdout)
            self.assertEqual(changed, json.loads(after.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
