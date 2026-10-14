"""V636: overlapping schedule/manual triggers must not preempt running TCG jobs.

GitHub Actions concurrency with cancel-in-progress: true may cancel an active
collection or package upload when another run starts. This test covers only
workflow self-preemption; it does NOT assert that GitHub queueing never skips
pending runs, or that GitHub Actions has permissions to create pull requests.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
TARGETS = {
    ".github/workflows/tcg-static-data-refresh.yml": (
        "tcg-static-data-refresh-main",
        "status=PENDING_EXTERNAL_PR",
    ),
    ".github/workflows/grading-company-watch.yml": (
        "grading-company-watch-main",
        "status=PENDING_EXTERNAL_PR",
    ),
    ".github/workflows/gpt-tcg-drive-package.yml": (
        "gpt-tcg-drive-package-",
        "tablet_gdrive_publish.py --output-dir",
    ),
}


class ScheduledWorkflowNoPreemptionV636Tests(unittest.TestCase):
    def test_schedule_and_manual_dispatch_preserve_running_jobs(self):
        for name, (group, _) in TARGETS.items():
            with self.subTest(workflow=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                concurrency = re.search(
                    r"(?ms)^concurrency:\n(.*?)(?=^jobs:\n)", source
                )
                self.assertIsNotNone(concurrency, "concurrency stanza missing")
                self.assertIn("group: " + group, concurrency.group(1))
                self.assertRegex(
                    concurrency.group(1),
                    r"(?m)^  cancel-in-progress: false\s*$",
                )
                self.assertEqual(
                    1, len(re.findall(r"(?m)^  cancel-in-progress:", source)),
                    "unexpected duplicate or nested cancellation policy",
                )
                self.assertIn("workflow_dispatch:", source)
                self.assertIn("schedule:", source)
                self.assertRegex(source, r"(?m)^    timeout-minutes: [1-9]\d*\s*$")

    def test_preemption_fix_does_not_relax_fail_closed_publish(self):
        for name, (_, guard) in TARGETS.items():
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
