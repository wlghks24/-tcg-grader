from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/gpt-tcg-drive-package.yml"


class GptTcgDrivePackageRecoveryTests(unittest.TestCase):
    def test_freshness_only_recovery_covers_all_known_stale_sources_without_weakening_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for code in (
            "STALE_AUTO_UPDATE_REPORT",
            "STALE_SOCIAL_SNAPSHOT",
            "STALE_SUPPLEMENTARY_SNAPSHOT",
        ):
            self.assertIn(code, workflow)
        self.assertIn("critical and critical <= recoverable", workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-refresh')", workflow)
        self.assertIn("python tablet_gdrive_publish.py --output-dir .tcg_drive_outbox", workflow)
        self.assertIn('echo "ready=true"', workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_RETRY", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertIn("never widen freshness gates", workflow)
        self.assertIn("Stale inputs are never uploaded", workflow)
        self.assertNotIn("publish_allowed = true", workflow)
        self.assertNotIn("actions: write", workflow)

    def test_stale_topic_matrix_drift_requires_independent_stale_evidence(self):
        import json
        import subprocess
        import sys
        import tempfile
        import textwrap

        workflow = WORKFLOW.read_text(encoding="utf-8")
        block = workflow.split("static_stale_only() {", 1)[1].split("transient_degraded_only() {", 1)[0]
        script = textwrap.dedent(block.split("python - <<'PY'", 1)[1].split("          PY", 1)[0])
        scenarios = (
            ([], False),
            (["STALE_AUTO_UPDATE_REPORT"], True),
            (["STALE_SOCIAL_SNAPSHOT", "TOPIC_EXPECTED_CELL_MISMATCH",
              "SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH"], True),
            (["TOPIC_EXPECTED_CELL_MISMATCH", "SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH"], False),
            (["STALE_SUPPLEMENTARY_SNAPSHOT", "INVALID_PUBLIC_OUTPUT"], False),
            (["STALE_AUTO_UPDATE_REPORT", "TOPIC_COLLECTION_NOT_FULLY_ATTEMPTED"], False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "STATIC_DATA_PUBLISH_REPORT.json"
            for codes, expected in scenarios:
                with self.subTest(codes=codes):
                    report.write_text(json.dumps({"findings": [
                        {"severity": "critical", "code": code} for code in codes
                    ]}), encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, "-c", script], cwd=tmp,
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode == 0, expected, result.stderr)
        self.assertIn("topic_contract_drift", workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_RETRY", workflow)
        self.assertIn("python tablet_gdrive_publish.py --output-dir .tcg_drive_outbox", workflow)

    def test_transient_degraded_recovery_is_bounded_and_fail_closed(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("transient_degraded_only()", workflow)
        self.assertIn('row.get("code") != "DEGRADED_COLLECTION_OUTPUT"', workflow)
        self.assertIn("if not high or len(high) > 4", workflow)
        self.assertIn("allowed_targets = {job[2] for job in auto_update_all.JOBS}", workflow)
        self.assertIn("code not in {408, 425} and not 500 <= code <= 599", workflow)
        self.assertIn('"retry-after" in lowered', workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-transient-recovery')", workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_PLUS_TRANSIENT_RETRY", workflow)
        self.assertIn("TRANSIENT_DEGRADED_COLLECTION_RETRY", workflow)
        self.assertIn("print_failure_diagnostics", workflow)
        self.assertIn("without changing any gate", workflow)
        self.assertIn("package remains blocked", workflow)
        self.assertNotIn("--max-health-age-seconds 3600", workflow)
        self.assertNotIn("fail-on-degraded=false", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
