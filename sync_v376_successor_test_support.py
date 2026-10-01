"""Strict test support for historical Tablet GPT sync generations delegating to V376."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json"
EXPECTED_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
EXPECTED_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json"
EXPECTED_TEST = "test_tablet_gpt_tcg_grader_sync_v376.py"
EXPECTED_BASE = "d2813d753a2c5babcc014d3e8a28374fadd887bb"
EXPECTED_CANDIDATE = "372e8fb1f1c546120fb49db3fea52d59129319ca"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v376.py", "tablet_runtime_manifest.py"]


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    return sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


def assert_v376_successor(testcase, relevant):
    """Accept V376 only when the full exact successor generation is self-consistent."""
    testcase.assertTrue(CONTRACT_PATH.is_file(), "missing V376 successor contract")
    contract = _read(CONTRACT_PATH)
    testcase.assertEqual(EXPECTED_PRIOR_CONTRACT, contract["prior_contract"])
    testcase.assertEqual(EXPECTED_PRIOR_DELTA, contract["prior_delta_snapshot"])
    testcase.assertEqual(EXPECTED_TEST, contract["verification_test"])
    candidate = contract["candidate_sync"]
    testcase.assertEqual(EXPECTED_BASE, candidate["base_main_sha"])
    testcase.assertEqual(EXPECTED_CANDIDATE, candidate["candidate_commit"])
    testcase.assertTrue(candidate["requires_exact_watched_path_match"])
    testcase.assertTrue(candidate["post_merge_coverage_allowed"])
    testcase.assertEqual(EXPECTED_WATCHED, sorted(candidate["watched_paths"]))
    testcase.assertEqual(EXPECTED_WATCHED, _watched_paths(contract, EXPECTED_BASE, EXPECTED_CANDIDATE))
    testcase.assertEqual(EXPECTED_WATCHED, sorted(relevant))

    generation = {
        "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json",
        "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v376_delta.json",
        "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v376.json",
        "test_tablet_gpt_tcg_grader_sync_v376.py",
    }
    testcase.assertEqual(generation, set(candidate["generation_files"]))
    testcase.assertTrue(generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
    for key in ("delta_snapshot", "receiver_receipt", "verification_test"):
        testcase.assertTrue((ROOT / contract[key]).is_file(), contract[key])

    delta = _read(ROOT / contract["delta_snapshot"])
    receipt = _read(ROOT / contract["receiver_receipt"])
    raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    testcase.assertEqual(digest, delta["lesson_digest_sha256"])
    testcase.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
    testcase.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
    testcase.assertEqual(EXPECTED_BASE, delta["source_main_sha"])
    testcase.assertEqual(EXPECTED_BASE, receipt["source_main_sha"])
    testcase.assertEqual("SYNCED_VERIFIED", receipt["status"])
    testcase.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
    testcase.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
    testcase.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
    subprocess.run(["git", "merge-base", "--is-ancestor", EXPECTED_BASE, "HEAD"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", EXPECTED_CANDIDATE, "HEAD"], check=True)
    return contract, candidate
