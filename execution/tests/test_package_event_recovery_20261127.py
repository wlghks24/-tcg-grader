"""Exercise the actual workflow classifier; no collection or publication."""
import ast
import json
from pathlib import Path
import subprocess
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ".github/workflows/gpt-tcg-drive-package.yml"
BASE = "7f5adbc25f9967207edace9fa314bc0a646e19f2"


def classify(workflow, codes):
    block = workflow.split("          static_stale_only() {", 1)[1].split(
        "          transient_degraded_only()", 1)[0]
    source = block.split("python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    tree = ast.parse(textwrap.dedent(source))
    report = {"findings": [{"severity": "critical", "code": code} for code in codes]}
    with patch.object(Path, "read_text", return_value=json.dumps(report)):
        try:
            exec(compile(tree, PATH, "exec"), {"__name__": "__main__"})
        except SystemExit as exc:
            return exc.code
    raise AssertionError("classifier did not decide")


class PackageEventRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = (ROOT / PATH).read_text(encoding="utf-8")
        cls.before = subprocess.check_output(
            ["git", "show", BASE + ":" + PATH], cwd=ROOT, text=True)

    def test_actual_five_findings_reproduce_before_and_recover_after(self):
        codes = {"STALE_AUTO_UPDATE_REPORT", "STALE_SOCIAL_SNAPSHOT",
                 "STALE_SUPPLEMENTARY_SNAPSHOT", "STALE_EVENT_SNAPSHOT",
                 "ACTIVE_EVENT_ARCHIVE_OVERDUE"}
        self.assertEqual(1, classify(self.before, codes))
        self.assertEqual(0, classify(self.current, codes))

    def test_stale_event_has_the_existing_one_cycle_recovery(self):
        self.assertEqual(1, classify(self.before, {"STALE_EVENT_SNAPSHOT"}))
        self.assertEqual(0, classify(self.current, {"STALE_EVENT_SNAPSHOT"}))

    def test_unknown_and_structural_findings_remain_blocked(self):
        for code in ("UNKNOWN_CRITICAL", "INVALID_EVENT_DATE", "FUTURE_EVENT_SNAPSHOT"):
            with self.subTest(code=code):
                self.assertEqual(1, classify(self.current, {"STALE_EVENT_SNAPSHOT", code}))

    def test_archive_or_contract_drift_alone_never_authorizes_retry(self):
        for codes in (set(), {"ACTIVE_EVENT_ARCHIVE_OVERDUE"},
                      {"TOPIC_EXPECTED_CELL_MISMATCH"},
                      {"ACTIVE_EVENT_ARCHIVE_OVERDUE", "TOPIC_EXPECTED_CELL_MISMATCH"}):
            with self.subTest(codes=codes):
                self.assertEqual(1, classify(self.current, codes))

    def test_prior_freshness_and_contract_drift_recovery_is_preserved(self):
        for codes in ({"STALE_SOCIAL_SNAPSHOT"},
                      {"STALE_SUPPLEMENTARY_SNAPSHOT", "TOPIC_EXPECTED_CELL_MISMATCH"}):
            with self.subTest(codes=codes):
                self.assertEqual(classify(self.before, codes), classify(self.current, codes))

    def test_only_classifier_changes_and_existing_publish_gate_is_preserved(self):
        def without_classifier(source):
            first, rest = source.split("          static_stale_only() {", 1)
            tail = rest.split("          transient_degraded_only()", 1)[1]
            return first, tail
        self.assertEqual(without_classifier(self.before), without_classifier(self.current))
        collector = (ROOT / "update_promo_events.py").read_text(encoding="utf-8")
        self.assertIn("data = apply_retention(data, today=event_today())", collector)
