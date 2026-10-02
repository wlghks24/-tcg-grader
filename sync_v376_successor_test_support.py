"""Strict successor support for historical Tablet GPT sync generations through V384.

V376-V379 remain immutable history. Later watched changes must be covered by an
exact newer generation; no historical generation is silently relaxed.
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

V378_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V378.json"
V378_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V377.json"
V378_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v377_delta.json"
V378_TEST = "test_tablet_gpt_tcg_grader_sync_v378.py"
V378_BASE = "e318e7995eb35363256901197413f34aea4facb1"
V378_CANDIDATE = "839c5890752d39343c1345c996dd8568baeecdeb"
V378_WATCHED = ["main", "tablet_autonomous_evolution_v378.py", "tablet_runtime_manifest.py"]

V379_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V379.json"
V379_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V378.json"
V379_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v378_delta.json"
V379_TEST = "test_tablet_gpt_tcg_grader_sync_v379.py"
V379_BASE = "3370896de0324572f7921329ba8f4582a4b56539"
V379_CANDIDATE = "7f68e579e6cb84e65d059ec14b78d7e42e94fb0c"
V379_WATCHED = ["main", "tablet_autonomous_evolution_v379.py", "tablet_runtime_manifest.py"]

V380_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V380.json"
V380_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V379.json"
V380_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v379_delta.json"
V380_TEST = "test_tablet_gpt_tcg_grader_sync_v380.py"
V380_BASE = "6a1006cc699133f0bf8a5b1e4ee40db01ffa605b"
V380_CANDIDATE = "48f8f45d230f252886c6c17d2d2a1b5e432cd263"
V380_WATCHED = ["main", "tablet_autonomous_evolution_v380.py", "tablet_runtime_manifest.py"]

V381_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V381.json"
V381_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V380.json"
V381_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v380_delta.json"
V381_TEST = "test_tablet_gpt_tcg_grader_sync_v381.py"
V381_BASE = "108adece2681783ddb46f6911da345bdb938c0cd"
V381_CANDIDATE = "aced561a5c930b099583fa35f2746104c0420243"
V381_WATCHED = ["main", "tablet_autonomous_evolution_v381.py", "tablet_runtime_manifest.py"]

V382_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V382.json"
V382_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V381.json"
V382_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v381_delta.json"
V382_TEST = "test_tablet_gpt_tcg_grader_sync_v382.py"
V382_BASE = "10265fdcf464fab80d396be1b8afdc2a906118c2"
V382_CANDIDATE = "fdbe8d711dd4eda6e4cc7ed1ec069858d0b3b1d7"
V382_WATCHED = ["main", "tablet_autonomous_evolution_v382.py", "tablet_runtime_manifest.py"]

V383_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V383.json"
V383_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V382.json"
V383_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v382_delta.json"
V383_TEST = "test_tablet_gpt_tcg_grader_sync_v383.py"
V383_BASE = "8e8f8b0f5fa35c93507647d1ecfdc1d84786771d"
V383_CANDIDATE = "f23a48e67a54a90e045bb920bc61a4a76707dc3a"
V383_WATCHED = [".github/workflows/gpt-tcg-drive-package.yml"]

V384_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V384.json"
V384_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V383.json"
V384_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v383_delta.json"
V384_TEST = "test_tablet_gpt_tcg_grader_sync_v384.py"
V384_BASE = "04d0844ccafe09016f070c0691782b88e01b0a6a"
V384_CANDIDATE = "2e23683dbde0f9f9153776bf9f27b57b8c1b32cb"
V384_WATCHED = ["main", "tablet_autonomous_evolution_v385.py", "tablet_runtime_manifest.py"]


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
    testcase.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
    testcase.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
    testcase.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
    subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", candidate_sha, "HEAD"], check=True)
    return contract, candidate


def assert_v384_successor(testcase):
    """Validate V384 as the exact final watched-path successor introducing V385 autonomy."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V384_CONTRACT_PATH,
        prior_contract=V384_PRIOR_CONTRACT,
        prior_delta=V384_PRIOR_DELTA,
        verification_test=V384_TEST,
        base=V384_BASE,
        candidate_sha=V384_CANDIDATE,
        watched=V384_WATCHED,
        version="V384",
    )
    testcase.assertEqual(
        [],
        _watched_paths(contract, V384_CANDIDATE),
        "V384 successor has uncovered watched changes",
    )
    return contract, candidate


def assert_v383_successor(testcase):
    """Validate immutable V383 and delegate later watched changes to exact V384."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V383_CONTRACT_PATH,
        prior_contract=V383_PRIOR_CONTRACT,
        prior_delta=V383_PRIOR_DELTA,
        verification_test=V383_TEST,
        base=V383_BASE,
        candidate_sha=V383_CANDIDATE,
        watched=V383_WATCHED,
        version="V383",
    )
    after383 = _watched_paths(contract, V383_CANDIDATE)
    if not after383:
        return contract, candidate
    testcase.assertEqual(V384_WATCHED, after383)
    return assert_v384_successor(testcase)


def assert_v382_successor(testcase):
    """Validate immutable V382 and delegate its later watched workflow change to V383."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V382_CONTRACT_PATH,
        prior_contract=V382_PRIOR_CONTRACT,
        prior_delta=V382_PRIOR_DELTA,
        verification_test=V382_TEST,
        base=V382_BASE,
        candidate_sha=V382_CANDIDATE,
        watched=V382_WATCHED,
        version="V382",
    )
    after382 = _watched_paths(contract, V382_CANDIDATE)
    if not after382:
        return contract, candidate
    testcase.assertEqual(sorted(set(V383_WATCHED) | set(V384_WATCHED)), after382)
    return assert_v383_successor(testcase)


def assert_v381_successor(testcase):
    """Validate immutable V381 and delegate later watched changes to exact V382."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V381_CONTRACT_PATH,
        prior_contract=V381_PRIOR_CONTRACT,
        prior_delta=V381_PRIOR_DELTA,
        verification_test=V381_TEST,
        base=V381_BASE,
        candidate_sha=V381_CANDIDATE,
        watched=V381_WATCHED,
        version="V381",
    )
    after381 = _watched_paths(contract, V381_CANDIDATE)
    if not after381:
        return contract, candidate
    testcase.assertEqual(sorted(set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)), after381)
    return assert_v382_successor(testcase)


def assert_v380_successor(testcase):
    """Validate immutable V380 and delegate later watched changes to exact V381."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V380_CONTRACT_PATH,
        prior_contract=V380_PRIOR_CONTRACT,
        prior_delta=V380_PRIOR_DELTA,
        verification_test=V380_TEST,
        base=V380_BASE,
        candidate_sha=V380_CANDIDATE,
        watched=V380_WATCHED,
        version="V380",
    )
    after380 = _watched_paths(contract, V380_CANDIDATE)
    if not after380:
        return contract, candidate
    testcase.assertEqual(sorted(set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)), after380)
    return assert_v381_successor(testcase)


def assert_v379_successor(testcase, relevant=None):
    """Validate immutable V379 and delegate later watched changes to exact V380."""
    contract379, candidate379 = _validate_generation(
        testcase,
        contract_path=V379_CONTRACT_PATH,
        prior_contract=V379_PRIOR_CONTRACT,
        prior_delta=V379_PRIOR_DELTA,
        verification_test=V379_TEST,
        base=V379_BASE,
        candidate_sha=V379_CANDIDATE,
        watched=V379_WATCHED,
        version="V379",
    )
    after379 = _watched_paths(contract379, V379_CANDIDATE)
    if not after379:
        if relevant is not None:
            testcase.assertEqual(V379_WATCHED, sorted(relevant))
        return contract379, candidate379

    testcase.assertEqual(sorted(set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)), after379)
    contract380, candidate380 = assert_v380_successor(testcase)
    if relevant is not None:
        testcase.assertEqual(
            sorted(set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)),
            sorted(relevant),
        )
    return contract380, candidate380


def assert_v378_successor(testcase, relevant=None):
    """Validate immutable V378 through exact V379/V380 successors."""
    contract378, candidate378 = _validate_generation(
        testcase,
        contract_path=V378_CONTRACT_PATH,
        prior_contract=V378_PRIOR_CONTRACT,
        prior_delta=V378_PRIOR_DELTA,
        verification_test=V378_TEST,
        base=V378_BASE,
        candidate_sha=V378_CANDIDATE,
        watched=V378_WATCHED,
        version="V378",
    )
    after378 = _watched_paths(contract378, V378_CANDIDATE)
    if not after378:
        if relevant is not None:
            testcase.assertEqual(V378_WATCHED, sorted(relevant))
        return contract378, candidate378

    expected = sorted(set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED))
    testcase.assertEqual(expected, after378)
    contract380, candidate380 = assert_v379_successor(testcase, after378)
    if relevant is not None:
        testcase.assertEqual(
            sorted(set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)),
            sorted(relevant),
        )
    return contract380, candidate380


def assert_v377_successor(testcase, relevant=None):
    """Validate immutable V377 through exact V378/V379/V380 successors."""
    contract377, candidate377 = _validate_generation(
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
    after377 = _watched_paths(contract377, V377_CANDIDATE)
    if not after377:
        if relevant is not None:
            testcase.assertEqual(V377_WATCHED, sorted(relevant))
        return contract377, candidate377

    expected = sorted(set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED))
    testcase.assertEqual(expected, after377)
    contract380, candidate380 = assert_v378_successor(testcase, after377)
    if relevant is not None:
        testcase.assertEqual(
            sorted(set(V377_WATCHED) | set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)),
            sorted(relevant),
        )
    return contract380, candidate380


def assert_v376_successor(testcase, relevant):
    """Validate immutable V376 history through exact V377-V380 successors."""
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

    expected = sorted(set(V377_WATCHED) | set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED))
    testcase.assertEqual(expected, after376)
    contract380, candidate380 = assert_v377_successor(testcase, after376)
    testcase.assertEqual(
        sorted(set(V376_WATCHED) | set(V377_WATCHED) | set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED)),
        sorted(relevant),
    )
    return contract380, candidate380


def assert_current_autonomy_route_v384(testcase, main_text=None, manifest_text=None):
    """Require exact V384 sync evidence and current V385 autonomy runtime."""
    assert_v384_successor(testcase)
    if main_text is None:
        main_text = (ROOT / "main").read_text(encoding="utf-8")
    if manifest_text is None:
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
    testcase.assertIn(
        "tablet_autonomous_evolution_v385.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
        main_text,
    )
    for version in ("v385", "v382", "v381", "v380", "v379", "v378", "v377", "v376"):
        testcase.assertIn(f'"tablet_autonomous_evolution_{version}.py"', manifest_text)


def assert_current_autonomy_route_v383(testcase, main_text=None, manifest_text=None):
    """Backward-compatible helper: current route is exact verified V384/V385 successor."""
    return assert_current_autonomy_route_v384(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v382(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v383(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v381(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v382(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v380(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v381(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v379(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v381(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v378(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v381(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v377(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v381(testcase, main_text, manifest_text)
