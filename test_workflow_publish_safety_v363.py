import re
import unittest
from pathlib import Path


WORKFLOW_DIR = Path('.github/workflows')
HELPER = Path('scripts/publish_candidate_pr.sh')

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
            if 'scripts/publish_candidate_pr.sh' not in text:
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


if __name__ == '__main__':
    unittest.main()
