"""V636: prevent noncritical schedule overlap from preempting active TCG jobs.

The static refresh keeps cancel-in-progress=true intentionally: the existing
repository health guard requires newer collector runs to cancel obsolete work.
Grading-company watch and Drive packaging can preserve running work instead.
This does NOT fix Actions PR-permission HTTP 403, GitHub pending queue eviction,
or stale/mismatched integrity manifests.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
TARGETS = {
    ".github/workflows/tcg-static-data-refresh.yml": (
        "tcg-static-data-refresh-main",
        "status=PENDING_EXTERNAL_PR",
        "true",  # stale-main protection required by repository_health_guard.py
    ),
    ".github/workflows/grading-company-watch.yml": (
        "grading-company-watch-main",
        "status=PENDING_EXTERNAL_PR",
        "false",
    ),
    ".github/workflows/gpt-tcg-drive-package.yml": (
        "gpt-tcg-drive-package-",
        "tablet_gdrive_publish.py --output-dir",
        "false",
    ),
}


class ScheduledWorkflowNoPreemptionV636Tests(unittest.TestCase):
    def test_schedule_manual_overlap_policy_preserves_required_guards(self):
        for name, (group, _, cancel) in TARGETS.items():
            with self.subTest(workflow=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                concurrency = re.search(
                    r"(?ms)^concurrency:\n(.*?)(?=^jobs:\n)", source
                )
                self.assertIsNotNone(concurrency, "concurrency stanza missing")
                self.assertIn("group: " + group, concurrency.group(1))
                self.assertRegex(
                    concurrency.group(1),
                    rf"(?m)^  cancel-in-progress: {cancel}\s*$",
                )
                self.assertEqual(
                    1, len(re.findall(r"(?m)^  cancel-in-progress:", source)),
                    "unexpected duplicate or nested cancellation policy",
                )
                self.assertIn("workflow_dispatch:", source)
                self.assertIn("schedule:", source)
                self.assertRegex(source, r"(?m)^    timeout-minutes: [1-9]\d*\s*$")

    def test_preemption_fix_does_not_relax_fail_closed_publish(self):
        for name, (_, guard, _) in TARGETS.items():
            with self.subTest(workflow=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn(guard, source)
                self.assertNotIn("git push origin HEAD:main", source)
                self.assertIn("if: always()", source)
        for name in list(TARGETS)[:2]:
            with self.subTest(candidate=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("Allow GitHub Actions to create and approve pull requests", source)
                self.assertIn("gh api --method POST", source)
                self.assertIn("exit 1", source)


if __name__ == "__main__":
    unittest.main()
