"""Strict successor support for historical Tablet GPT sync generations through V377.

V376 remains immutable history. When later watched changes exist, V377 must be a
fully bound exact successor; no historical generation is silently relaxed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent

V376_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json"
V376_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
V376_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v375_delta.json"
V376_TEST = "test_tablet_gpt_tcg_grader_sync_v376.py"
V376_BASE = "d2813d753a2c5babcc014d3e8a28374fadd887bb"
V376_CANDIDATE = "372e8fb1f1c546120fb49db3fea52d59129319ca"
V376_WATCHED = ["main", "tablet_autonomous_evolution_v376.py", "tablet_runtime_manifest.py"]

V377_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V377.json"
V377_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json"
V377_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v376_delta.json"
V377_TEST = "test_tablet_gpt_tcg_grader_sync_v377.py"
V377_BASE = "24cad558d756d57e06a8309c8d5fbc73626f1d45"
V377_CANDIDATE = "b1000eb9f155ce343fc3bc59bcc0c35c5efb19c3"
V377_WATCHED = ["main", "tablet_autonomous_evolution_v377.py", "tablet_runtime_manifest.py"]


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


def _validate_generation(
    testcase,
    *,
    contract_path: Path,
    prior_contract: str,
    prior_delta: str,
    verification_test: str,
    base: str,
    candidate_sha: str,
    watched: list[str],
    version: str,
):
    testcase.assertTrue(contract_path.is_file(), f"missing {version} successor contract")
    contract = _read(contract_path)
    testcase.assertEqual(prior_contract, contract["prior_contract"])
    testcase.assertEqual(prior_delta, contract["prior_delta_snapshot"])
    testcase.assertEqual(verification_test, contract["verification_test"])

    candidate = contract["candidate_sync"]
    testcase.assertEqual(base, candidate["base_main_sha"])
    testcase.assertEqual(candidate_sha, candidate["candidate_commit"])
    testcase.assertIs(candidate["requires_exact_watched_path_match"], True)
    testcase.assertIs(candidate["post_merge_coverage_allowed"], True)
    testcase.assertEqual(watched, sorted(candidate["watched_paths"]))
    testcase.assertEqual(watched, _watched_paths(contract, base, candidate_sha))

    generation = {
        contract_path.relative_to(ROOT).as_posix(),
        contract["delta_snapshot"],
        contract["receiver_receipt"],
        verification_test,
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
    testcase.assertEqual(base, delta["source_main_sha"])
    testcase.assertEqual(base, receipt["source_main_sha"])
    testcase.assertEqual("SYNCED_VERIFIED", receipt["status"])
    testcase.assertEqual(
        "TABLET_GPT_TCG_GRADER_MATCH",
        receipt["verification"]["verified_result"],
    )
    testcase.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
    testcase.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
    subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", candidate_sha, "HEAD"], check=True)
    return contract, candidate


def assert_v377_successor(testcase):
    """Validate V377 as the exact final watched-path successor of V376."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V377_CONTRACT_PATH,
        prior_contract=V377_PRIOR_CONTRACT,
        prior_delta=V377_PRIOR_DELTA,
        verification_test=V377_TEST,
        base=V377_BASE,
        candidate_sha=V377_CANDIDATE,
        watched=V377_WATCHED,
        version="V377",
    )
    testcase.assertEqual(
        [],
        _watched_paths(contract, V377_CANDIDATE),
        "V377 successor has uncovered watched changes",
    )
    return contract, candidate


def assert_v376_successor(testcase, relevant):
    """Validate immutable V376 history and, when needed, its exact V377 successor."""
    contract376, candidate376 = _validate_generation(
        testcase,
        contract_path=V376_CONTRACT_PATH,
        prior_contract=V376_PRIOR_CONTRACT,
        prior_delta=V376_PRIOR_DELTA,
        verification_test=V376_TEST,
        base=V376_BASE,
        candidate_sha=V376_CANDIDATE,
        watched=V376_WATCHED,
        version="V376",
    )

    after376 = _watched_paths(contract376, V376_CANDIDATE)
    if not after376:
        testcase.assertEqual(V376_WATCHED, sorted(relevant))
        return contract376, candidate376

    contract377, candidate377 = assert_v377_successor(testcase)
    testcase.assertEqual(V377_WATCHED, after376)
    testcase.assertEqual(
        sorted(set(V376_WATCHED) | set(V377_WATCHED)),
        sorted(relevant),
    )
    return contract377, candidate377


def assert_current_autonomy_route_v377(testcase, main_text=None, manifest_text=None):
    """Require the current supported autonomy route to use verified V377 while preserving V376."""
    assert_v377_successor(testcase)
    if main_text is None:
        main_text = (ROOT / "main").read_text(encoding="utf-8")
    if manifest_text is None:
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
    testcase.assertIn(
        "tablet_autonomous_evolution_v377.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
        main_text,
    )
    testcase.assertIn('"tablet_autonomous_evolution_v377.py"', manifest_text)
    testcase.assertIn('"tablet_autonomous_evolution_v376.py"', manifest_text)
