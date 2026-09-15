import tempfile
import unittest
from pathlib import Path

import repository_health_guard as health


class RepositoryHealthGuardTests(unittest.TestCase):
    def test_current_repository_has_no_blocking_health_drift(self):
        report = health.audit(Path(__file__).resolve().parent)
        self.assertEqual("PASS", report["status"], report["blockers"])
        self.assertEqual(0, report["summary"]["blockers"])
        self.assertEqual(8, report["checks"]["collection_jobs"]["count"])
        self.assertTrue(report["checks"]["legacy_7step_removed"])

    def test_legacy_7step_mutator_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/apply-android-7step-display.yml").write_text("legacy\n", encoding="utf-8")
            (root / ".github/workflows/tcg-static-data-refresh.yml").write_text(
                "concurrency:\n  group: x\n  cancel-in-progress: true\n"
                "jobs:\n  x:\n    timeout-minutes: 1\n"
                "# main advanced during collection; discard this snapshot\n"
                "# git diff --cached --quiet\n",
                encoding="utf-8",
            )
            (root / "auto_update_all.py").write_text(
                "JOBS = (\n" + "".join(
                    f"    ('job{i}', 'module{i}', 'out{i}.json'),\n" for i in range(8)
                ) + ")\n\n"
                "def _worker_count(n): return 1\n"
                "def _job_timeout(name, stats): return 30\n"
                "def _run_managed_process(*a, **k): return None\n"
                "# ThreadPoolExecutor\n# atomic_write_json\n",
                encoding="utf-8",
            )
            report = health.audit(root)
            self.assertEqual("BLOCKED", report["status"])
            self.assertIn(
                "LEGACY_7STEP_MUTATOR_PRESENT",
                {row["code"] for row in report["blockers"]},
            )

    def test_write_capable_apply_workflow_is_warning_not_automatic_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_dir = root / ".github/workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "apply-old-feature.yml").write_text(
                "on: workflow_dispatch\npermissions:\n  contents: write\n"
                "jobs:\n  x:\n    steps:\n      - run: git push origin main\n",
                encoding="utf-8",
            )
            debt = health._workflow_debt(root)
            self.assertEqual(1, len(debt))
            self.assertEqual(".github/workflows/apply-old-feature.yml", debt[0]["path"])


if __name__ == "__main__":
    unittest.main()
