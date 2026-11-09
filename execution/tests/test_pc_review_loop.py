"""Adversarial tests of the PC controller using synthetic files only.

No TCG runtime, collector, model, device, network or real user evidence is run.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


CONTROLLER = Path(__file__).resolve().parents[1] / "pc_review_loop/runner.py"
WORKER = CONTROLLER.with_name("test_worker.py")
SPEC = importlib.util.spec_from_file_location("tcg_pc_review_test_controller", CONTROLLER)
R = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(R)


class SyntheticRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tcg-pc-support-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.local_git("init", "-q")
        self.put("update_promo_events.py", "VALUE = 1\n")
        self.put("test_historical.py", "# preserved\n")
        self.put("integrity_manifest.json", json.dumps({"files": {"update_promo_events.py": {
            "sha256": R.digest(b"VALUE = 1\n"), "bytes": 10}}}))
        self.local_git("add", "--", "update_promo_events.py", "test_historical.py", "integrity_manifest.json")
        self.local_git("-c", "user.name=PC Support Fixture", "-c", "user.email=fixture@example.invalid",
                       "-c", "core.hooksPath=" + str(self.base / "unused-hooks"), "commit", "-qm", "fixture")

    def local_git(self, *args):
        return subprocess.check_output(["git", "-c", "core.fsmonitor=false", *args], cwd=self.root,
                                       stderr=subprocess.PIPE, timeout=15).decode().strip()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def proposal(self, path="update_promo_events.py", content="VALUE = 2\n"):
        file = self.root / path
        return {"path": path, "old_sha256": R.digest(file.read_bytes()) if file.exists() else "NEW",
                "content": content}


class StrictJSONTests(unittest.TestCase):
    def test_valid_nested_value_preserved(self):
        self.assertEqual(R.strict_json('{"name":"원화","v":[1,null,true]}'),
                         {"name": "원화", "v": [1, None, True]})

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":{"v":1,"v":2}}',
                     '{"v":NaN}', '{"v":Infinity}', '{"v":-Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                R.strict_json(text)


class PathAndScopeTests(SyntheticRepository):
    def test_portable_valid_path(self):
        self.assertEqual(R.safe_path(self.root, "execution/pc_candidate_fx.py"),
                         self.root / "execution/pc_candidate_fx.py")

    def test_traversal_ads_reserved_and_ambiguous_paths_rejected(self):
        names = ["../outside.py", "/tmp/out.py", "a//b.py", "a/./b.py", "a/../b.py",
                 "a\\b.py", "update_promo_events.py:payload", "C:/x.py", "a/NUL.py", "COM1.txt",
                 "a./x.py", "a /x.py", "a?b.py", "a\x00b.py", "", "a\nb.py"]
        for name in names:
            with self.subTest(name=name), self.assertRaises(ValueError):
                R.safe_path(self.root, name)

    def test_case_alias_rejected(self):
        with self.assertRaises(ValueError):
            R.safe_path(self.root, "Update_promo_events.py")

    def test_symlink_component_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        try:
            (self.root / "escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("OS does not permit symlink fixtures")
        with self.assertRaises(ValueError):
            R.safe_path(self.root, "escape/x.py")

    def test_historical_tests_guards_data_policy_and_controller_protected(self):
        indexed = set(R.tracked(self.root)) | {"index.html", "execution/tablet_local_learning.py"}
        for name in ("test_historical.py", "repository_integrity_guard.py", "AGENTS.md", "CLAUDE.md",
                     "GEMINI.md", "market_prices.json", ".github/workflows/guard.py",
                     "execution/tablet_local_learning.py", "execution/pc_review_loop/runner.py"):
            with self.subTest(name=name):
                self.assertFalse(R.editable(name, indexed))

    def test_new_helpers_and_new_regressions_allowed_but_old_test_is_not(self):
        indexed = set(R.tracked(self.root))
        self.assertTrue(R.editable("update_promo_events.py", indexed))
        self.assertTrue(R.editable("execution/pc_candidate_fx.py", indexed))
        self.assertTrue(R.editable("execution/tests/test_pc_candidate_fx.py", indexed))
        self.assertFalse(R.editable("unreviewed_new_update_promo_events.py", indexed))


class ProposalTests(SyntheticRepository):
    def test_verified_candidate_changes_source_and_exact_manifest_entry(self):
        original_test = (self.root / "test_historical.py").read_bytes()
        changed = R.apply_proposal(self.root, [self.proposal()])
        self.assertEqual(changed, ["update_promo_events.py"])
        self.assertEqual((self.root / "update_promo_events.py").read_bytes(), b"VALUE = 2\n")
        payload = json.loads((self.root / "integrity_manifest.json").read_text())
        self.assertEqual(payload["files"]["update_promo_events.py"], {"sha256": R.digest(b"VALUE = 2\n"), "bytes": 10})
        self.assertEqual((self.root / "test_historical.py").read_bytes(), original_test)

    def test_all_rows_validated_before_any_source_write(self):
        original = (self.root / "update_promo_events.py").read_bytes()
        invalid = self.proposal("test_historical.py", "# weakened\n")
        with self.assertRaises(ValueError):
            R.apply_proposal(self.root, [self.proposal(), invalid])
        self.assertEqual((self.root / "update_promo_events.py").read_bytes(), original)

    def test_stale_source_hash_fails_without_source_write(self):
        proposal = self.proposal()
        self.put("update_promo_events.py", "VALUE = 3\n")
        with self.assertRaises(ValueError):
            R.apply_proposal(self.root, [proposal])
        self.assertEqual((self.root / "update_promo_events.py").read_text(), "VALUE = 3\n")

    def test_duplicate_empty_oversized_and_invalid_syntax_proposals_fail(self):
        cases = [[self.proposal(), self.proposal()], [],
                 [self.proposal(content="   ")], [self.proposal(content="x" * 1_000_001)],
                 [self.proposal(content="def broken(:\n")]]
        for value in cases:
            with self.subTest(size=len(value)), self.assertRaises((ValueError, SyntaxError)):
                R.apply_proposal(self.root, value)
        self.assertEqual((self.root / "update_promo_events.py").read_text(), "VALUE = 1\n")

    def test_new_regression_and_helper_supported_together(self):
        result = R.apply_proposal(self.root, [self.proposal("execution/pc_candidate_fx.py", "def fx(): return 1\n"),
                                            self.proposal("execution/tests/test_pc_candidate_fx.py", "# independent regression\n")])
        self.assertEqual(len(result), 2)

    def test_source_fingerprint_changes_only_on_tracked_content_changes(self):
        original = R.fingerprint(self.root)
        self.put("untracked.txt", "diagnostic")
        self.assertEqual(R.fingerprint(self.root), original)
        self.put("update_promo_events.py", "VALUE = 2\n")
        self.assertNotEqual(R.fingerprint(self.root), original)


class CarryTests(SyntheticRepository):
    def test_carry_preserves_tracked_ignored_files_and_new_indexed_candidates(self):
        self.put(".gitignore", "GRADE_TRAINING_INBOX/\n")
        self.put("GRADE_TRAINING_INBOX/tracked.json", '{"synthetic":true}\n')
        self.local_git("add", "--", ".gitignore")
        # Historical tracked ignored file; force is fixture setup only, never the
        # behavior under test or permission to add a user's ignored data.
        self.local_git("add", "-f", "--", "GRADE_TRAINING_INBOX/tracked.json")
        self.local_git("-c", "user.name=PC Support Fixture", "-c", "user.email=fixture@example.invalid",
                       "-c", "core.hooksPath=" + str(self.base / "unused-hooks"), "commit", "-qm", "tracked ignored fixture")
        base_head = self.local_git("rev-parse", "HEAD")
        destination = self.base / "destination"
        R.clone(str(self.root), destination, base_head)
        helper = "execution/pc_candidate_carry.py"
        regression = "execution/tests/test_pc_candidate_carry.py"
        self.put(helper, "def value(): return 2\n")
        self.put(regression, "# synthetic regression, not a runtime test\n")
        self.put("GRADE_TRAINING_INBOX/tracked.json", '{"synthetic":true,"revision":2}\n')
        self.local_git("add", "--", helper, regression)
        before = {p: (self.root / p).read_bytes() for p in R.tracked(self.root)}
        before_digest = R.fingerprint(self.root)
        R.carry(self.root, destination)
        self.assertEqual(R.fingerprint(destination), before_digest)
        self.assertEqual(R.fingerprint(self.root), before_digest)
        self.assertEqual(self.local_git("rev-parse", "HEAD"), base_head)
        self.assertEqual(set(R.tracked(destination)), set(before))
        for name, body in before.items():
            with self.subTest(path=name):
                self.assertEqual((self.root / name).read_bytes(), body)
                self.assertEqual((destination / name).read_bytes(), body)


class ProcessAndWorkerTests(SyntheticRepository):
    def test_argv_is_literal_and_utf8_receipt_is_preserved(self):
        argument = "원화 & $(touch injected) ^ !"
        result = R.command([sys.executable, "-c", "import sys; print(sys.argv[1])", argument], self.root,
                           log=self.base / "utf8.log")
        self.assertEqual(result["status"], "PASS")
        self.assertIn(argument, result["tail"])
        self.assertFalse((self.root / "injected").exists())

    def test_batch_wrappers_rejected(self):
        for name in ("codex.cmd", "x.BAT", "run.ps1"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                R.command([name], self.root)

    def test_windows_npm_wrapper_is_resolved_without_executing_cmd(self):
        install = self.base / "npm path & literal"
        install.mkdir()
        wrapper = install / "codex.cmd"
        wrapper.write_text("@echo do not run", encoding="ascii")
        entry = install / "node_modules/@openai/codex/bin/codex.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("// synthetic official entry", encoding="ascii")
        node = str(self.base / "node.exe")
        def which(name):
            return str(wrapper) if name == "codex" else node if name == "node.exe" else None
        with patch.dict(os.environ, {"TCG_CODEX_EXE": ""}), patch.object(R.shutil, "which", side_effect=which):
            self.assertEqual(R.codex_executable(), [node, str(entry)])

    def test_explicit_windows_batch_path_is_not_executed(self):
        wrapper = self.put("codex.cmd", "@echo forbidden")
        with patch.dict(os.environ, {"TCG_CODEX_EXE": str(wrapper)}):
            self.assertIsNone(R.codex_executable())

    def test_ai_environment_does_not_inherit_api_or_github_tokens(self):
        code = "import os; print(','.join(k for k in ['OPENAI_API_KEY','CODEX_API_KEY','GH_TOKEN','GITHUB_TOKEN'] if k in os.environ))"
        with patch.dict(os.environ, {k: "synthetic-private-value" for k in ("OPENAI_API_KEY", "CODEX_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")}):
            result = R.command([sys.executable, "-c", code], self.root, ai=True, log=self.base / "env.log")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["tail"].strip(), "")

    def test_candidate_environment_drops_arbitrary_credentials_and_uses_workspace_temp(self):
        work_temp = self.root / ".synthetic-tests-tmp"
        literal = "원화 · 환율 & ^ $(literal)"
        code = ("import json,os,sys,tempfile; from pathlib import Path; "
                "p=Path(tempfile.mkdtemp()); "
                "print(json.dumps({'credential_present':'PRIVATE_SERVICE_SECRET' in os.environ,"
                "'argv':sys.argv[1], 'tmp':os.environ.get('TMP'), 'temp':os.environ.get('TEMP'),"
                "'tmpdir':os.environ.get('TMPDIR'), 'created':str(p),"
                "'utf8':os.environ.get('PYTHONIOENCODING')}, ensure_ascii=False))")
        with patch.dict(os.environ, {"PRIVATE_SERVICE_SECRET": "synthetic-credential-not-a-real-secret"}):
            result = R.command([sys.executable, "-c", code, literal], self.root,
                               test_temp=work_temp, log=self.base / "candidate-env.log")
        self.assertEqual(result["status"], "PASS", result["tail"])
        receipt = json.loads(result["tail"])
        self.assertFalse(receipt["credential_present"])
        self.assertEqual(receipt["argv"], literal)
        self.assertEqual(receipt["utf8"], "utf-8")
        for name in ("tmp", "temp", "tmpdir"):
            self.assertEqual(Path(receipt[name]), work_temp)
        self.assertTrue(Path(receipt["created"]).is_relative_to(work_temp))

    def test_timeout_does_not_become_pass(self):
        result = R.command([sys.executable, "-c", "import time; time.sleep(10)"], self.root,
                           timeout=0.1, log=self.base / "timeout.log")
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertTrue(result["timed_out"])
        self.assertIsNotNone(result["exit_code"])

    def worker(self, source):
        self.put("test_synthetic.py", source)
        result = R.command([sys.executable, str(WORKER), str(self.root), "test_synthetic.py"],
                           self.root, log=self.base / "worker.log")
        matches = [x.split("=", 1)[1] for x in result["tail"].splitlines() if x.startswith("TCG_TEST_RECEIPT=")]
        self.assertEqual(len(matches), 1, result["tail"])
        return result, json.loads(matches[0])

    def test_worker_zero_tests_is_unverified(self):
        result, receipt = self.worker("VALUE = 1\n")
        self.assertEqual(receipt["collected"], 0)
        self.assertFalse(receipt["successful"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_worker_all_skipped_is_not_success(self):
        result, receipt = self.worker("import unittest\nclass Sample(unittest.TestCase):\n @unittest.skip('fixture')\n def test_one(self): pass\n")
        self.assertEqual(receipt["collected"], 1)
        self.assertEqual(receipt["skipped"], 1)
        self.assertFalse(receipt["successful"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_worker_real_assertion_is_counted_and_failure_is_recorded(self):
        result, receipt = self.worker("import unittest\nclass Sample(unittest.TestCase):\n def test_one(self): self.assertEqual(1, 2)\n")
        self.assertEqual(receipt["collected"], 1)
        self.assertEqual(receipt["failures"], 1)
        self.assertFalse(receipt["successful"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_worker_real_passing_test_has_positive_count(self):
        result, receipt = self.worker("import unittest\nclass Sample(unittest.TestCase):\n def test_one(self): self.assertEqual(1 + 1, 2)\n")
        self.assertEqual(receipt["collected"], 1)
        self.assertTrue(receipt["successful"])
        self.assertEqual(result["exit_code"], 0)

    def test_worker_expected_failures_only_cannot_count_as_a_passing_run(self):
        result, receipt = self.worker("import unittest\nclass Sample(unittest.TestCase):\n @unittest.expectedFailure\n def test_one(self): self.assertEqual(1, 2)\n")
        self.assertEqual(receipt["collected"], 1)
        self.assertEqual(receipt["expected_failures"], 1)
        self.assertEqual(receipt["passed"], 0)
        self.assertFalse(receipt["successful"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_worker_rejects_inside_repository_symlink_before_resolution(self):
        self.put("test_real.py", "raise SystemExit('must not execute')\n")
        try:
            (self.root / "test_alias.py").symlink_to(self.root / "test_real.py")
        except OSError:
            self.skipTest("OS does not permit symlink fixtures")
        result = R.command([sys.executable, str(WORKER), str(self.root), "test_alias.py"],
                           self.root, log=self.base / "link-worker.log")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertNotIn("must not execute", result["tail"])
        self.assertIn("link/reparse", result["tail"])


class SandboxProfileTests(SyntheticRepository):
    def test_missing_sandbox_executable_holds_without_executing_tests(self):
        with patch.object(R, "command") as execute:
            result = R.sandbox_probe(None, self.root, self.base)
        self.assertEqual(result["status"], "HOLD_SANDBOX_REQUIRED")
        execute.assert_not_called()

    def test_missing_sandbox_cannot_run_project_tests(self):
        with patch.object(R, "command") as execute:
            result = R.run_tests(self.root, self.base / "tests", {"test_files": ["test_historical.py"]},
                                 deadline=time.monotonic() + 5, stop=self.base / "STOP", sandbox=None)
        self.assertEqual(result["status"], "HOLD_SANDBOX_REQUIRED")
        self.assertEqual(result["rows"], [])
        execute.assert_not_called()

    def test_profile_has_network_disabled_and_no_user_home_read_grant(self):
        prefix = R.sandbox_prefix(["codex-executable"], self.root)
        self.assertIn("permissions.tcg_pc_tests.network.enabled=false", prefix)
        self.assertIn("--include-managed-config", prefix)
        self.assertIn("--permission-profile", prefix)
        self.assertEqual(prefix[prefix.index("--permission-profile") + 1], "tcg_pc_tests")
        filesystem = next(v for v in prefix if v.startswith("permissions.tcg_pc_tests.filesystem="))
        self.assertIn('\":minimal\" = \"read\"', filesystem)
        self.assertIn('\":workspace_roots\" = \"write\"', filesystem)
        self.assertNotIn(json.dumps(str(Path.home())) + " = ", filesystem)


class CIReceiptTests(unittest.TestCase):
    HEAD = "a" * 40

    def fixture(self):
        return [{"name": name, "head_sha": self.HEAD, "status": "completed", "conclusion": "success"}
                for name in R.REQUIRED_CI]

    def evaluate(self, runs, *, count=None, statuses=None):
        def fake(path):
            if "/check-runs?" in path:
                return {"check_runs": runs, "total_count": len(runs) if count is None else count}
            if path.endswith("/status"):
                return {"statuses": statuses or [], "total_count": len(statuses or [])}
            raise AssertionError(path)
        with patch.object(R, "api", side_effect=fake):
            return R.ci_state(self.HEAD)

    def test_exact_complete_success_receipts_are_accepted(self):
        self.assertEqual(self.evaluate(self.fixture())["status"], "PASS")

    def test_stale_missing_pending_failed_and_incomplete_receipts_hold(self):
        stale = self.fixture()
        stale[0]["head_sha"] = "b" * 40
        pending = self.fixture()
        pending[0].update(status="in_progress", conclusion=None)
        failed = self.fixture()
        failed[0]["conclusion"] = "failure"
        for runs, kwargs in ((stale, {}), (pending, {}), (failed, {}),
                             (self.fixture()[1:], {}), ([], {}),
                             (self.fixture(), {"count": 99}),
                             (self.fixture(), {"statuses": [{"context": "independent", "state": "failure"}]})):
            with self.subTest(runs=runs, kwargs=kwargs):
                self.assertNotEqual(self.evaluate(runs, **kwargs)["status"], "PASS")

    def test_access_failure_is_not_no_change_or_pass(self):
        with patch.object(R, "api", side_effect=OSError("synthetic access failure")):
            result = R.ci_state(self.HEAD)
        self.assertEqual(result["status"], "ACCESS_UNAVAILABLE")


class TabletHandoffTests(SyntheticRepository):
    def prepare(self):
        self.put("execution/tablet_release_install_v976.py", "# synthetic installer\n")
        self.put("execution/tablet_release_preflight_v972.py", "# synthetic preflight\n")
        self.local_git("add", "--", "execution")
        self.local_git("-c", "user.name=PC Support Fixture", "-c", "user.email=fixture@example.invalid",
                       "-c", "core.hooksPath=" + str(self.base / "unused-hooks"), "commit", "-qm", "fixture installer")
        return self.local_git("rev-parse", "HEAD")

    def call_handoff(self, head, tests):
        with patch.object(R, "ci_state", return_value={"status": "PASS", "head": head}), \
             patch.object(R, "api", return_value={"commit": {"sha": head}}):
            return R.tablet_handoff(self.root, self.base / "result", head, tests)

    def test_no_missing_installer_can_be_called_ready(self):
        head = self.local_git("rev-parse", "HEAD")
        result = self.call_handoff(head, {"status": "PASS", "source_digest": R.fingerprint(self.root)})
        self.assertEqual(result["status"], "HOLD_TABLET_HANDOFF")
        self.assertFalse(result["installation_permitted"])
        self.assertFalse(result["physical_device_verified"])

    def test_dirty_candidate_cannot_reuse_old_head_ci_success(self):
        head = self.prepare()
        receipt = {"status": "PASS", "source_digest": R.fingerprint(self.root)}
        self.put("update_promo_events.py", "VALUE = 999\n")
        result = self.call_handoff(head, receipt)
        self.assertEqual(result["status"], "HOLD_TABLET_HANDOFF")
        self.assertFalse(result["installation_permitted"])

    def test_clean_source_with_wrong_test_digest_cannot_be_ready(self):
        head = self.prepare()
        result = self.call_handoff(head, {"status": "PASS", "source_digest": "b" * 64})
        self.assertEqual(result["status"], "HOLD_TABLET_HANDOFF")
        self.assertFalse(result["tested_digest_matches"])

    def test_clean_different_git_head_cannot_borrow_requested_sha_ci(self):
        self.prepare()
        result = self.call_handoff("a" * 40, {"status": "PASS", "source_digest": R.fingerprint(self.root)})
        self.assertEqual(result["status"], "HOLD_TABLET_HANDOFF")


if __name__ == "__main__":
    unittest.main()
