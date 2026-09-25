from __future__ import annotations

from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
WORKFLOW=ROOT/'.github'/'workflows'/'grading-company-watch.yml'


class GradingCompanyWatchProtectedPublishV320Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=WORKFLOW.read_text(encoding='utf-8')

    def test_no_direct_main_push_and_no_push_trigger(self):
        self.assertNotIn('git push origin HEAD:main',self.source)
        self.assertNotIn('git push origin main',self.source)
        trigger=self.source.split('\npermissions:',1)[0]
        self.assertIn('workflow_dispatch:',trigger)
        self.assertIn('schedule:',trigger)
        self.assertNotIn('\n  push:',trigger)
        self.assertIn("cron: '23 */3 * * *'",trigger)

    def test_candidate_branch_and_pr_only_publish(self):
        self.assertIn('candidate_branch="auto/grading-company-watch-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',self.source)
        self.assertIn('git push origin "HEAD:refs/heads/${candidate_branch}"',self.source)
        self.assertIn('gh api --method POST "repos/${REPO}/pulls"',self.source)
        self.assertIn('pull-requests: write',self.source)
        self.assertIn('actions: write',self.source)
        self.assertIn('checks: read',self.source)

    def test_exact_main_and_integrity_are_rechecked(self):
        self.assertGreaterEqual(self.source.count('git fetch origin main'),3)
        self.assertIn('if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then',self.source)
        self.assertIn('if [ "$(git rev-parse origin/main)" != "${base_sha}" ]; then',self.source)
        self.assertIn('if [ "$(git rev-parse origin/main)" != "${BASE_SHA}" ]; then',self.source)
        manifest=self.source.index('python fault_injection_healing.py --manifest')
        diagnose=self.source.index('python fault_injection_healing.py --diagnose',manifest)
        publish=self.source.index('git push origin "HEAD:refs/heads/${candidate_branch}"')
        self.assertLess(manifest,diagnose)
        self.assertLess(diagnose,publish)

    def test_all_protected_checks_gate_merge(self):
        checks={
            'Tablet GPT TCG Grader Main Alignment','Repository Integrity Guard','Main SELFREFINE',
            'Deep SELFREFINE Guard','Exhaustive SELFREFINE Guard','Tablet Termux Main Guard','Android Updater Guard',
        }
        for check in checks:
            with self.subTest(check=check): self.assertIn(check,self.source)
        self.assertIn('status=REQUIRED_CHECK_FAILED',self.source)
        self.assertIn('status=REQUIRED_CHECK_TIMEOUT',self.source)
        self.assertIn('merge_method=merge -f sha="${CANDIDATE_SHA}"',self.source)

    def test_provider_policy_remains_fail_closed(self):
        for text in ('official_sources_only','community_posts_are_leads_only','automatic_source_code_mutation','service_availability_status_only_no_price_promotion','price_facts_promoted'):
            with self.subTest(text=text): self.assertIn(text,self.source)


if __name__=='__main__':
    unittest.main(verbosity=2)
