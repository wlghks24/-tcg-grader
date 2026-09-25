from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "grading-company-watch.yml"


class GradingCompanyWatchProtectedPublishV319Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_direct_main_push_is_forbidden(self) -> None:
        self.assertNotIn("git push origin HEAD:main", self.source)
        self.assertNotIn("git push origin main", self.source)
        self.assertIn("candidate_branch=\"auto/grading-company-watch-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}\"", self.source)
        self.assertIn('git push origin "HEAD:refs/heads/${candidate_branch}"', self.source)

    def test_workflow_has_pr_and_check_permissions(self) -> None:
        self.assertIn("pull-requests: write", self.source)
        self.assertIn("actions: write", self.source)
        self.assertIn("checks: read", self.source)
        self.assertIn("contents: write", self.source)

    def test_candidate_is_built_from_exact_validated_main(self) -> None:
        self.assertGreaterEqual(self.source.count("git fetch origin main"), 3)
        self.assertIn('if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then', self.source)
        self.assertIn('base_sha="$(git rev-parse HEAD)"', self.source)
        self.assertIn('if [ "$(git rev-parse origin/main)" != "${base_sha}" ]; then', self.source)
        self.assertIn('if [ "$(git rev-parse origin/main)" != "${BASE_SHA}" ]; then', self.source)

    def test_integrity_is_regenerated_and_diagnosed_before_publish(self) -> None:
        manifest = self.source.index("python fault_injection_healing.py --manifest")
        diagnose = self.source.index("python fault_injection_healing.py --diagnose", manifest)
        branch_push = self.source.index('git push origin "HEAD:refs/heads/${candidate_branch}"')
        self.assertLess(manifest, diagnose)
        self.assertLess(diagnose, branch_push)
        self.assertIn("git add -- integrity_manifest.json", self.source)
        self.assertIn("git diff --cached --check", self.source)

    def test_pr_promotion_waits_for_all_protected_main_checks(self) -> None:
        self.assertIn('gh api --method POST "repos/${REPO}/pulls"', self.source)
        expected_workflows = {
            "tablet-gpt-tcg-grader-main-alignment.yml",
            "repository-integrity-guard.yml",
            "selfrefine-full-repo.yml",
            "deep-selfrefine-guard.yml",
            "exhaustive-selfrefine-guard.yml",
            "tablet-termux-main-guard.yml",
            "android-updater-guard.yml",
        }
        expected_checks = {
            "Tablet GPT TCG Grader Main Alignment",
            "Repository Integrity Guard",
            "Main SELFREFINE",
            "Deep SELFREFINE Guard",
            "Exhaustive SELFREFINE Guard",
            "Tablet Termux Main Guard",
            "Android Updater Guard",
        }
        for item in expected_workflows | expected_checks:
            with self.subTest(item=item):
                self.assertIn(item, self.source)
        self.assertIn("status=REQUIRED_CHECK_FAILED", self.source)
        self.assertIn("status=REQUIRED_CHECK_TIMEOUT", self.source)
        self.assertIn('merge_method=merge -f sha="${CANDIDATE_SHA}"', self.source)

    def test_provider_safety_contract_remains_fail_closed(self) -> None:
        self.assertIn("official_sources_only", self.source)
        self.assertIn("community_posts_are_leads_only", self.source)
        self.assertIn("automatic_source_code_mutation", self.source)
        self.assertIn("service_availability_status_only_no_price_promotion", self.source)
        self.assertIn("preserve last-good structured facts", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
