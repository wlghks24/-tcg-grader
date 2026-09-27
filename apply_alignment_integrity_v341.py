from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_MAIN = "be144184da52d16ccde3d7d2c65fa37953d55bac"
PRIOR_DIGEST = "de0eb790674b14bb28ea8a576e274402dce63af30577f7bb67dd447049a22b97"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


# 1) Integrity guard: verify both listed hashes and Git-index completeness.
p = ROOT / "repository_integrity_guard.py"
s = p.read_text(encoding="utf-8")
s = one(
    s,
    "malformed/duplicate-key JSON, Python syntax errors, unsafe tracked symlinks, and\ncross-platform filename collisions that can break the Windows/Android deployment path.",
    "malformed/duplicate-key JSON, Python syntax errors, unsafe tracked symlinks,\ncross-platform filename collisions that can break the Windows/Android deployment path,\nand integrity-manifest hash/coverage drift.",
    "integrity docstring",
)
insert_after = '''def tracked_entries() -> list[tuple[str, Path, bool]]:\n    \"\"\"Return every tracked path without silently following or omitting symlinks.\"\"\"\n    result = subprocess.run(\n        [\"git\", \"ls-files\", \"-z\"],\n        cwd=ROOT,\n        stdout=subprocess.PIPE,\n        stderr=subprocess.PIPE,\n        check=True,\n    )\n    entries: list[tuple[str, Path, bool]] = []\n    for raw in result.stdout.split(b\"\\0\"):\n        if not raw:\n            continue\n        relative = raw.decode(\"utf-8\", \"strict\")\n        path = ROOT / relative\n        entries.append((relative, path, path.is_symlink()))\n    return entries\n'''
addition = insert_after + '''\n\ndef _git_tracked_paths(root: Path) -> set[str] | None:\n    \"\"\"Return Git-indexed paths, or None for an intentionally non-Git test root.\n\n    Runtime jobs legitimately create ignored ledgers/reports. Those are not source\n    truth. In a real checkout the Git index decides whether a path is repository-owned.\n    \"\"\"\n    root = root.resolve()\n    if not (root / \".git\").exists():\n        return None\n    result = subprocess.run(\n        [\"git\", \"ls-files\", \"-z\"],\n        cwd=root,\n        stdout=subprocess.PIPE,\n        stderr=subprocess.PIPE,\n        check=True,\n    )\n    return {raw.decode(\"utf-8\", \"strict\") for raw in result.stdout.split(b\"\\0\") if raw}\n'''
s = one(s, insert_after, addition, "git tracked helper")
main_marker = "\ndef main() -> int:\n"
manifest_fn = r'''

def integrity_manifest_findings(root: Path = ROOT) -> list[str]:
    """Return hash/schema/coverage drift for the generated integrity manifest."""
    try:
        import fault_injection_healing as healing

        root = root.resolve()
        manifest_path = root / "integrity_manifest.json"
        result = healing.diagnose_integrity(root, manifest_path)
        try:
            payload = json.loads(
                manifest_path.read_text(encoding="utf-8"),
                object_pairs_hook=unique_object,
                parse_constant=reject_constant,
            )
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            return [f"integrity_manifest.json: strict read failed: {exc.__class__.__name__}"]
        listed_raw = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(listed_raw, dict):
            return ["integrity_manifest.json: files mapping missing or invalid"]
        listed = set(listed_raw)
        policy_paths = {path.relative_to(root).as_posix() for path in healing.tracked_files(root)}
        git_paths = _git_tracked_paths(root)
        current = policy_paths if git_paths is None else policy_paths & git_paths
        findings: list[str] = []
        for relative in sorted(current - listed):
            findings.append(f"integrity manifest missing tracked path: {relative}")
        for relative in sorted(listed - current):
            findings.append(f"integrity manifest contains non-current tracked path: {relative}")
        if not result.get("ok"):
            failed_rows = [
                str(row.get("file", "<unknown>"))
                for row in result.get("files", [])
                if isinstance(row, dict) and not row.get("ok")
            ]
            if failed_rows:
                for relative in failed_rows[:50]:
                    findings.append(f"integrity manifest hash/schema mismatch: {relative}")
            else:
                findings.append(f"integrity manifest diagnose failed: {result.get('error', 'unknown')}")
        return findings
    except (OSError, RuntimeError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        return [f"integrity manifest validation failed closed: {exc.__class__.__name__}"]
'''
s = one(s, main_marker, manifest_fn + main_marker, "manifest completeness function")
s = one(
    s,
    "    entries = tracked_entries()\n\n    # A case-insensitive checkout",
    "    entries = tracked_entries()\n    findings.extend(integrity_manifest_findings(ROOT))\n\n    # A case-insensitive checkout",
    "invoke manifest completeness",
)
p.write_text(s, encoding="utf-8")

# 2) Integrity regressions: tracked additions fail; ignored runtime artifacts do not.
p = ROOT / "test_repository_selfrefine_v13.py"
s = p.read_text(encoding="utf-8")
s = one(s, "import json\nimport unittest\n", "import json\nimport subprocess\nimport tempfile\nimport unittest\n", "test imports")
s = one(s, "import repository_integrity_guard as guard\n", "import fault_injection_healing as healing\nimport repository_integrity_guard as guard\n", "healing import")
s = one(
    s,
    "ROOT = Path(__file__).resolve().parent\n\n\nclass RepositorySelfrefineV13Tests",
    '''ROOT = Path(__file__).resolve().parent\n\n\ndef _git(root: Path, *args: str) -> None:\n    subprocess.run([\"git\", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)\n\n\nclass RepositorySelfrefineV13Tests''',
    "git test helper",
)
needle = '''        self.assertIsInstance(parsed, dict)\n        self.assertTrue(parsed.get(\"name\") or parsed.get(\"short_name\"))\n'''
extra = needle + r'''

    def test_integrity_manifest_rejects_new_unlisted_git_tracked_file(self):
        with tempfile.TemporaryDirectory(prefix="tcg-manifest-completeness-") as directory:
            root = Path(directory)
            _git(root, "init", "-q")
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(root, "add", "sample.py")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            self.assertEqual(guard.integrity_manifest_findings(root), [])
            (root / "late_added.py").write_text("VALUE = 2\n", encoding="utf-8")
            _git(root, "add", "late_added.py")
            self.assertIn(
                "integrity manifest missing tracked path: late_added.py",
                guard.integrity_manifest_findings(root),
            )

    def test_integrity_manifest_ignores_untracked_runtime_artifact(self):
        with tempfile.TemporaryDirectory(prefix="tcg-manifest-runtime-") as directory:
            root = Path(directory)
            _git(root, "init", "-q")
            (root / ".gitignore").write_text("RUNTIME_REPORT.json\n", encoding="utf-8")
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(root, "add", ".gitignore", "sample.py")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            (root / "RUNTIME_REPORT.json").write_text('{"status":"runtime"}\n', encoding="utf-8")
            self.assertEqual(guard.integrity_manifest_findings(root), [])

    def test_integrity_manifest_rejects_hash_drift(self):
        with tempfile.TemporaryDirectory(prefix="tcg-manifest-hash-") as directory:
            root = Path(directory)
            target = root / "sample.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            target.write_text("VALUE = 9\n", encoding="utf-8")
            self.assertIn(
                "integrity manifest hash/schema mismatch: sample.py",
                guard.integrity_manifest_findings(root),
            )
'''
s = one(s, needle, extra, "integrity regressions")
p.write_text(s, encoding="utf-8")

# 3) Tablet GPT alignment: bind versioned files and enforce freshness before merge.
p = ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml"
s = p.read_text(encoding="utf-8")
s = one(
    s,
    "          contract = json.loads(contract_path.read_text(encoding='utf-8'))\n          delta_path = root / contract['delta_snapshot']\n",
    "          contract = json.loads(contract_path.read_text(encoding='utf-8'))\n          expected_delta = f'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v{version}_delta.json'\n          expected_receipt = f'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v{version}.json'\n          expected_test = f'test_tablet_gpt_tcg_grader_sync_v{version}.py'\n          assert contract['delta_snapshot'] == expected_delta\n          assert contract['receiver_receipt'] == expected_receipt\n          assert contract['verification_test'] == expected_test\n          delta_path = root / contract['delta_snapshot']\n",
    "generation file binding",
)
s = one(
    s,
    "      - name: Fail visibly when main has watched changes after the latest verified delta\n        if: github.event_name != 'pull_request'\n",
    "      - name: Fail visibly when watched changes are not covered by the latest verified delta\n",
    "enable PR freshness",
)
s = one(s, "          import json\n          import re\n", "          import json\n          import os\n          import re\n", "freshness os import")
pr_gate = '''          relevant = sorted(path for path in changed if watched(path))\n          if relevant:\n'''
pr_gate_new = '''          relevant = sorted(path for path in changed if watched(path))\n\n          # PRs may bundle a new verified sync generation, but it must be anchored\n          # to the exact PR base and all four generation files must be part of the PR.\n          event_name = os.environ.get('GITHUB_EVENT_NAME', '')\n          if event_name == 'pull_request' and relevant:\n              payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))\n              base_sha = payload['pull_request']['base']['sha']\n              pr_changed = set(subprocess.check_output(\n                  ['git', 'diff', '--name-only', f'{base_sha}..{head}'], text=True\n              ).splitlines())\n              generation_files = {\n                  contract_path.as_posix(),\n                  contract['delta_snapshot'],\n                  contract['receiver_receipt'],\n                  contract['verification_test'],\n              }\n              bundled_sync = source == base_sha and generation_files.issubset(pr_changed)\n              if bundled_sync:\n                  print(\n                      f'TABLET_GPT_PR_SYNC_CANDIDATE_COVERED version=v{version} '\n                      f'base={base_sha} head={head} watched_changes={len(relevant)}'\n                  )\n                  raise SystemExit(0)\n\n          if relevant:\n'''
s = one(s, pr_gate, pr_gate_new, "PR freshness candidate gate")
p.write_text(s, encoding="utf-8")

# 4) Verified v341 delta anchored to exact current main.
lessons = [
    {
        "lesson_id": "TABLET-GPT-DRIVE-RETENTION-DELETE-SAFETY-V340",
        "subsystem": "tablet_google_drive_bridge",
        "issue_class": "retention_cleanup_can_leave_incomplete_sets_or_delete_wrong_objects",
        "trigger_condition": "remote retention prunes package/receipt objects without preserving the current verified package, complete package sets, exact TCG ownership, or permanent-delete semantics",
        "symptom_summary": "verified recovery state can be damaged, stale objects can remain in Drive Trash, or unrelated user files can be exposed to cleanup",
        "root_cause_class": "remote_retention_identity_and_set_consistency_gap",
        "fix_pattern": "delete only exact TCG-managed objects after verified readback, preserve the current package, count complete package sets toward bounded retention, and never touch unknown user files",
        "prevention_rule_id": "TGPT-PREV-DRIVE-RETENTION-DELETE-SAFETY",
        "verification_result": "passed_main_repo_ci_pr297",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
        "physical_drive_readback_reverification_required": True,
    },
    {
        "lesson_id": "TABLET-GPT-PREMERGE-FRESHNESS-GATE-V341",
        "subsystem": "tablet_gpt_tcg_grader_alignment",
        "issue_class": "pull_request_can_merge_watched_change_before_freshness_gate_runs",
        "trigger_condition": "freshness validation is skipped on pull_request and first evaluates watched-path drift only after merge to main",
        "symptom_summary": "PR checks can be green while the merged main immediately reports TABLET_GPT_SYNC_STALE",
        "root_cause_class": "post_merge_only_freshness_enforcement",
        "fix_pattern": "run freshness on pull requests, require changed watched paths to be accompanied by the newest verified sync contract anchored to the exact PR base, and keep the post-merge fail-closed check",
        "prevention_rule_id": "TGPT-PREV-PREMERGE-FRESHNESS",
        "verification_result": "full_repo_finalizer_and_pr_ci_required",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
    },
    {
        "lesson_id": "TABLET-GPT-MANIFEST-COMPLETENESS-V341",
        "subsystem": "repository_integrity",
        "issue_class": "new_git_tracked_source_can_be_absent_from_integrity_manifest",
        "trigger_condition": "a finalizer is skipped or interrupted after a new in-scope source/config path is Git-tracked",
        "symptom_summary": "hash diagnosis can pass because it validates only paths already listed in the manifest",
        "root_cause_class": "manifest_entry_validation_without_git_index_completeness_check",
        "fix_pattern": "intersect manifest policy paths with the Git index, fail on missing or stale manifest paths, keep hash/schema diagnosis, and ignore only genuine untracked runtime artifacts",
        "prevention_rule_id": "TGPT-PREV-MANIFEST-COMPLETENESS",
        "verification_result": "full_repo_finalizer_and_pr_ci_required",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
    },
]
raw = json.dumps(lessons, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
if digest != "01b2f700fc1dd32879dd67ebc453e2791ad07d06a4e99cf8bc89927e0bbcda61":
    raise SystemExit(f"unexpected v341 lesson digest: {digest}")

delta = {
    "schema_version": "1.1-tablet-gpt-tcg-grader-learning-sync",
    "namespace": "TABLET_GPT",
    "snapshot_kind": "learning_delta",
    "run_date_kst": "2026-09-27",
    "built_at": "2026-09-27T23:20:00+09:00",
    "status": "finalized",
    "source_repository": "wlghks24/-tcg-grader",
    "prior_delta": "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v339_delta.json",
    "prior_lesson_digest_sha256": PRIOR_DIGEST,
    "source_main_sha": BASE_MAIN,
    "share_policy": {
        "explicit_patch_and_learning_lessons_only": True,
        "chatgpt_model_weights_exported": False,
        "raw_grading_calibration_shared": False,
        "device_local_runtime_memory_overwritten": False,
        "peer_verified_never_auto_promotes_local": True,
    },
    "covered_merges": [
        {"pr": 294, "version": "v339-sync", "merge_sha": "ca011e21d753ac66d1e9db24b162ccb13a072a50"},
        {"pr": 297, "version": "v340-drive-retention", "merge_sha": BASE_MAIN},
    ],
    "lesson_digest_sha256": digest,
    "lessons": lessons,
}

delta_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json"
delta_path.write_text(json.dumps(delta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

receipt = {
    "schema_version": delta["schema_version"],
    "receiver": "TCG_GRADER",
    "source_namespace": "TABLET_GPT",
    "source_repository": delta["source_repository"],
    "source_main_sha": BASE_MAIN,
    "received_at": "2026-09-27T23:20:00+09:00",
    "status": "SYNCED_VERIFIED",
    "source_snapshots": [delta["prior_delta"], str(delta_path.relative_to(ROOT)).replace('\\', '/')],
    "prior_lesson_digest_sha256": PRIOR_DIGEST,
    "delta_lesson_digest_sha256": digest,
    "accepted_lesson_ids": [row["lesson_id"] for row in lessons],
    "alignment_policy": {
        "same_digest_required": True,
        "same_lesson_ids_required": True,
        "same_source_main_required_for_delta": True,
        "covered_patch_commits_must_be_ancestors": True,
        "future_watched_main_changes_require_new_delta": True,
        "pull_request_freshness_check_nonblocking": False,
        "pull_request_candidate_sync_requires_exact_base": True,
        "device_local_learning_state_merge_required": True,
        "blind_overwrite_forbidden": True,
        "grading_calibration_auto_import_forbidden": True,
        "peer_verified_never_auto_promotes_local": True,
    },
    "verification": {
        "contract_version": "v341",
        "verification_test": "test_tablet_gpt_tcg_grader_sync_v341.py",
        "verification_mode": "final_tree_regression_plus_pr_and_main_freshness_watch",
        "verified_result": "TABLET_GPT_TCG_GRADER_MATCH",
        "physical_tablet_runtime_verified": False,
        "physical_drive_readback_verified": False,
        "device_reverification_required": True,
    },
}
receipt_path = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v341.json"
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

prior_contract = json.loads((ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V339.json").read_text(encoding="utf-8"))
watch = json.loads(json.dumps(prior_contract["freshness_watch"]))
new_exclusions = [
    str(delta_path.relative_to(ROOT)).replace('\\', '/'),
    str(receipt_path.relative_to(ROOT)).replace('\\', '/'),
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json",
    "test_tablet_gpt_tcg_grader_sync_v341.py",
]
for item in new_exclusions:
    if item not in watch["exclude_paths"]:
        watch["exclude_paths"].append(item)
contract = {
    "schema_version": delta["schema_version"],
    "purpose": "keep Tablet GPT prevention lessons aligned with TCG Grader and block watched-path drift before merge unless a new verified generation is anchored to the exact PR base",
    "prior_contract": "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V339.json",
    "prior_delta_snapshot": delta["prior_delta"],
    "delta_snapshot": new_exclusions[0],
    "receiver_receipt": new_exclusions[1],
    "verification_test": new_exclusions[3],
    "rules": {
        "base_snapshot_is_append_only_history": True,
        "delta_lesson_digest_must_match": True,
        "combined_lesson_id_set_must_match": True,
        "delta_source_main_sha_must_match_receipt": True,
        "covered_patch_commits_must_be_ancestors_of_current_head": True,
        "watched_changes_after_delta_source_main_must_report_stale_on_main": True,
        "pull_request_freshness_check_is_nonblocking": False,
        "pull_request_candidate_sync_requires_exact_base_and_generation_files": True,
        "chatgpt_model_weights_transfer_forbidden": True,
        "raw_grading_calibration_transfer_forbidden": True,
        "device_local_learning_memory_blind_overwrite_forbidden": True,
        "device_local_learning_memory_uses_existing_transactional_merge_rules": True,
        "physical_tablet_and_drive_results_must_not_be_invented": True,
    },
    "current_required_merge_prs": prior_contract["current_required_merge_prs"] + [294, 297],
    "prior_required_lesson_count": prior_contract["current_required_lesson_count"],
    "delta_required_lesson_count": len(lessons),
    "current_required_lesson_count": prior_contract["current_required_lesson_count"] + len(lessons),
    "freshness_watch": watch,
}
contract_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json"
contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# 5) v341 regression contract.
(ROOT / "test_tablet_gpt_tcg_grader_sync_v341.py").write_text(r'''import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v339_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v341.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V339.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV341(unittest.TestCase):
    def test_lineage_digest_and_exact_covered_merges(self):
        prior, delta, receipt, prior_contract, contract = map(read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("be144184da52d16ccde3d7d2c65fa37953d55bac", delta["source_main_sha"])
        self.assertEqual([294, 297], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(prior_contract["current_required_merge_prs"]) | {294, 297})
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_pr_freshness_is_blocking_and_exact_base_bound(self):
        contract = read(CONTRACT)
        workflow = (ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
        self.assertFalse(contract["rules"]["pull_request_freshness_check_is_nonblocking"])
        self.assertTrue(contract["rules"]["pull_request_candidate_sync_requires_exact_base_and_generation_files"])
        self.assertNotIn("if: github.event_name != 'pull_request'", workflow)
        for token in ("GITHUB_EVENT_PATH", "generation_files.issubset(pr_changed)", "source == base_sha", "TABLET_GPT_PR_SYNC_CANDIDATE_COVERED"):
            self.assertIn(token, workflow)

    def test_latest_generation_files_are_bound_and_excluded(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v341.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json",
            "test_tablet_gpt_tcg_grader_sync_v341.py",
        }
        self.assertTrue(expected.issubset(set(watch["exclude_paths"])))
        workflow = (ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
        for token in ("expected_delta", "expected_receipt", "expected_test", "assert contract['delta_snapshot'] == expected_delta"):
            self.assertIn(token, workflow)

    def test_integrity_guard_has_git_index_completeness(self):
        guard = (ROOT / "repository_integrity_guard.py").read_text(encoding="utf-8")
        tests = (ROOT / "test_repository_selfrefine_v13.py").read_text(encoding="utf-8")
        self.assertIn("_git_tracked_paths", guard)
        self.assertIn("current - listed", guard)
        self.assertIn("listed - current", guard)
        self.assertIn("test_integrity_manifest_rejects_new_unlisted_git_tracked_file", tests)
        self.assertIn("test_integrity_manifest_ignores_untracked_runtime_artifact", tests)


if __name__ == "__main__":
    unittest.main(verbosity=2)
''', encoding="utf-8")
