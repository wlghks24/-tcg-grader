"""Offline contract tests for exact-main install approval; no external network."""
from datetime import datetime, timedelta, timezone
import unittest

from execution import tablet_main_ci_gate as gate

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def fixture(overrides=None, missing=(), branch_sha=SHA):
    overrides = overrides or {}
    runs = []
    for number, name in enumerate(gate.REQUIRED_WORKFLOWS, start=1):
        if name in missing:
            continue
        run = dict(
            id=number, name=name, head_sha=SHA, head_branch="main",
            event="push", repository={"full_name": "wlghks24/-tcg-grader"},
            status="completed", conclusion="success",
            created_at=(NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
        run.update(overrides.get(name, {}))
        runs.append(run)

    def fetch(url):
        if url.endswith("/branches/main"):
            return {"commit": {"sha": branch_sha}}
        if "page=1" in url:
            return {"total_count": len(runs), "workflow_runs": runs}
        raise AssertionError("Unexpected network request")
    return fetch


class TabletMainCiGateTests(unittest.TestCase):
    def test_complete_exact_main_and_fresh_ci_is_approved(self):
        self.assertEqual([], gate.assess_main(SHA, fetch=fixture(), now=NOW))

    def test_nonmain_or_wrong_sha_is_never_approved(self):
        self.assertEqual(["MAIN_SHA_CHANGED"],
                         gate.assess_main(SHA, fetch=fixture(branch_sha="b"*40), now=NOW))
        self.assertEqual(["INVALID_SHA"],
                         gate.assess_main("../main", fetch=fixture(), now=NOW))
        overrides = {"CodeQL V438": {"head_branch": "feature"}}
        self.assertIn("MISSING:CodeQL V438",
                      gate.assess_main(SHA, fetch=fixture(overrides), now=NOW))

    def test_missing_or_cancelled_gates_fail_closed(self):
        problems = gate.assess_main(
            SHA, fetch=fixture(
                {"Tablet GPT TCG Grader Main Alignment": {
                    "status": "completed", "conclusion": "cancelled"}},
                missing=("GPT TCG Drive Package",)), now=NOW
        )
        self.assertIn("NOT_SUCCESS:Tablet GPT TCG Grader Main Alignment", problems)
        self.assertIn("MISSING:GPT TCG Drive Package", problems)

    def test_stale_data_and_failed_market_workflow_block_install(self):
        old = (NOW - timedelta(hours=80)).isoformat().replace("+00:00", "Z")
        overrides = {
            "TCG Static Data Refresh": {"created_at": old},
            "Grading Company Watch": {"conclusion": "failure"},
        }
        problems = gate.assess_main(SHA, fetch=fixture(overrides), now=NOW)
        self.assertIn("STALE:TCG Static Data Refresh", problems)
        self.assertIn("NOT_SUCCESS:Grading Company Watch", problems)

    def test_untrusted_repo_success_is_not_evidence(self):
        overrides = {
            "Repository Integrity Guard": {
                "repository": {"full_name": "untrusted/repo"}
            }
        }
        self.assertIn("MISSING:Repository Integrity Guard",
                      gate.assess_main(SHA, fetch=fixture(overrides), now=NOW))

    def test_latest_failed_run_overrides_earlier_success(self):
        data = []
        for i, name in enumerate(gate.REQUIRED_WORKFLOWS, 1):
            data.append(dict(id=i, name=name, head_sha=SHA, head_branch="main",
                event="push", repository={"full_name": "wlghks24/-tcg-grader"},
                status="completed", conclusion="success",
                created_at=(NOW-timedelta(hours=2)).isoformat()))
        data.append(dict(data[0], id=1000, conclusion="cancelled",
             created_at=(NOW-timedelta(hours=1)).isoformat()))

        def fetch(url):
            if url.endswith("/branches/main"): return {"commit": {"sha": SHA}}
            return {"total_count": len(data), "workflow_runs": data}
        self.assertIn("NOT_SUCCESS:Android Updater Guard",
                      gate.assess_main(SHA, fetch=fetch, now=NOW))


if __name__ == "__main__":
    unittest.main()
