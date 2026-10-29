"""Adversarial real-Git checks: closed findings require pinned historical evidence."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_auditor"))
from audit import AuditError, git_inventory, load_findings


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True).stdout.decode().strip()


class HistoricalCloseGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tcg-closed-finding-guard-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        (self.repo / "V001_core.py").write_text("def core():\n    return True\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "baseline")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.blob = git(self.repo, "rev-parse", "HEAD:V001_core.py")
        evidence = self.repo / "execution" / "evidence"
        evidence.mkdir(parents=True)
        self.ledger = evidence / "version_review_findings_v001_v205.json"
        self.item = {
            "id": "W001-F014", "first_observed_version": 40,
            "severity": "P0", "state": "HISTORICAL_REPAIR_EVIDENCED",
            "summary": "Past repair evidence, not current release approval",
            "source_refs": [{"path": "V001_core.py", "blob": self.blob}],
            "code_history": [self.base],
        }
        self.record = {"schema": "tcg-version-scoped-findings/v1",
                       "baseline_main_sha": self.base, "findings": [self.item]}
        self._commit(self.record)

    def _commit(self, payload):
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "fixture update")

    def _read(self):
        return load_findings(self.repo, git_inventory(self.repo))[0]

    def test_valid_pinned_history_is_historical_not_release_approval(self):
        rows = self._read()
        self.assertEqual("HISTORICAL_REPAIR_EVIDENCED", rows[0]["state"])
        self.assertEqual("W001-F014", rows[0]["id"])

    def test_forged_or_missing_closure_evidence_fails_closed(self):
        variants = (
            (lambda d: d.pop("schema"), "unverified_historical_close_schema"),
            (lambda d: d.pop("baseline_main_sha"), "unverified_historical_close_baseline"),
            (lambda d: d["findings"][0].pop("source_refs"),
             "unverified_historical_close_missing_evidence"),
            (lambda d: d["findings"][0].pop("code_history"),
             "unverified_historical_close_missing_evidence"),
            (lambda d: d["findings"][0]["source_refs"][0].update(blob="0" * 40),
             "unverified_historical_close_blob_mismatch"),
            (lambda d: d["findings"][0]["source_refs"][0].update(path="missing.py"),
             "unverified_historical_close_source_missing"),
            (lambda d: d["findings"][0]["code_history"].append("1" * 40),
             "unverified_historical_close_commit_ancestry"),
        )
        for mutation, error in variants:
            with self.subTest(error=error):
                payload = json.loads(json.dumps(self.record))
                mutation(payload)
                self._commit(payload)
                with self.assertRaisesRegex(AuditError, error):
                    self._read()

    def test_bad_window_id_and_unknown_state_are_not_accepted(self):
        variants = (
            ("W101-F014", 40, "OPEN_SUCCESSOR_REQUIRED", "bad_findings_id_or_version_window"),
            ("W001-F014", 101, "OPEN_SUCCESSOR_REQUIRED", "bad_findings_id_or_version_window"),
            ("bad-id", 40, "OPEN_SUCCESSOR_REQUIRED", "bad_findings_id_or_version_window"),
            ("W001-F014", 40, "RESOLVED", "bad_findings_state"),
            ("W001-F014", 40, "NOT_AN_ACTUAL_STATE", "bad_findings_state"),
        )
        for bad_id, version, state, error in variants:
            with self.subTest(id=bad_id, state=state):
                payload = json.loads(json.dumps(self.record))
                payload["findings"][0].update(id=bad_id,
                                               first_observed_version=version,
                                               state=state)
                self._commit(payload)
                with self.assertRaisesRegex(AuditError, error):
                    self._read()

    def test_minimal_open_evidence_remains_supported(self):
        payload = {"findings": [{"id": "W001-F015", "first_observed_version": 40,
                                "severity": "P0", "state": "OPEN_SUCCESSOR_REQUIRED",
                                "summary": "Under review"}]}
        self._commit(payload)
        self.assertEqual("OPEN_SUCCESSOR_REQUIRED", self._read()[0]["state"])


if __name__ == "__main__":
    unittest.main()
