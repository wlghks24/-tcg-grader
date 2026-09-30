import re
import unittest
from pathlib import Path


WORKFLOW_DIR = Path('.github/workflows')
HELPER = Path('scripts/publish_candidate_pr.sh')

# Direct updates of main from Actions are forbidden. Keep the patterns focused
# on git push destinations so comments and documentation do not create noise.
FORBIDDEN = (
    re.compile(r'git\s+push[^\n]*(?:HEAD:main|HEAD:refs/heads/main)'),
    re.compile(r'git\s+push[^\n]*origin\s+main(?:\s|$)'),
    re.compile(r'git\s+push[^\n]*refs/heads/main'),
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

    def test_candidate_publishers_have_pr_permission(self):
        publishers = []
        missing = []
        for path in sorted(WORKFLOW_DIR.glob('*.yml')):
            text = path.read_text(encoding='utf-8')
            if 'scripts/publish_candidate_pr.sh' not in text:
                continue
            publishers.append(str(path))
            if 'pull-requests: write' not in text or 'contents: write' not in text:
                missing.append(str(path))
        self.assertGreater(len(publishers), 0)
        self.assertEqual([], missing, f'missing publish permissions: {missing}')

    def test_shared_publisher_never_updates_main_or_forces_refs(self):
        text = HELPER.read_text(encoding='utf-8')
        self.assertIn('BASE_ADVANCED', text)
        self.assertIn('refs/heads/${candidate_branch}', text)
        self.assertIn('gh pr create', text)
        self.assertNotIn('HEAD:main', text)
        self.assertNotIn('refs/heads/main"', text.replace('refs/heads/main:refs/remotes/origin/main', ''))
        self.assertNotRegex(text, r'git\s+(?:push|reset)[^\n]*--force')
        self.assertNotIn('--admin', text)


if __name__ == '__main__':
    unittest.main()
