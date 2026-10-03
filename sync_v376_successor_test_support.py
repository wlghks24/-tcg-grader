"""Strict successor support for historical Tablet GPT sync generations through V395.

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

V385_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V385.json"
V385_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V384.json"
V385_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v384_delta.json"
V385_TEST = "test_tablet_gpt_tcg_grader_sync_v385.py"
V385_BASE = "7406d603e0399dc0f4c353d7295c3fc916e8bbb3"
V385_CANDIDATE = "88754186207dac17f126c832ec0086f3f1991f0c"
V385_WATCHED = ["main", "tablet_autonomous_evolution_v386.py", "tablet_runtime_manifest.py"]

V386_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V386.json"
V386_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V385.json"
V386_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v385_delta.json"
V386_TEST = "test_tablet_gpt_tcg_grader_sync_v386.py"
V386_BASE = "67e656cd5f2e159b156292e3f597f79fbd4e2033"
V386_CANDIDATE = "ea265236e81a19101a08906989f624511ab823ff"
V386_WATCHED = ["main", "tablet_autonomous_evolution_v387.py", "tablet_runtime_manifest.py"]

V387_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V387.json"
V387_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V386.json"
V387_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v386_delta.json"
V387_TEST = "test_tablet_gpt_tcg_grader_sync_v387.py"
V387_BASE = "b5b100f93e8180e81458612b450f9411546463bf"
V387_CANDIDATE = "541e8835a93f2534fe49b0fe69ea762a1d897b63"
V387_WATCHED = ["main", "tablet_autonomous_evolution_v388.py", "tablet_runtime_manifest.py"]

V388_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V388.json"
V388_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V387.json"
V388_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v387_delta.json"
V388_TEST = "test_tablet_gpt_tcg_grader_sync_v388.py"
V388_BASE = "d4e4bd16e7e853a53274119f9f10f7a5521b114c"
V388_CANDIDATE = "3c9a9afa58214f7a67fcfe5373acb7823259684f"
V388_WATCHED = ["main", "tablet_autonomous_evolution_v390.py", "tablet_runtime_manifest.py"]

V389_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V389.json"
V389_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V388.json"
V389_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v388_delta.json"
V389_TEST = "test_tablet_gpt_tcg_grader_sync_v389.py"
V389_BASE = "d450fd918ebb2ed25adb49e2cbb14a4b14f6dadc"
V389_CANDIDATE = "fe3e8e00f3ed5293c6d4a3834e3a6b539891a829"
V389_WATCHED = ["main", "tablet_autonomous_evolution_v391.py", "tablet_runtime_manifest.py"]

V390_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V390.json"
V390_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V389.json"
V390_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v389_delta.json"
V390_TEST = "test_tablet_gpt_tcg_grader_sync_v390.py"
V390_BASE = "8701be1d348cb024e9c9675d4fb0eb3034a75d9d"
V390_CANDIDATE = "fff9ed46696f7b9148c61c60f97f62a820527fa7"
V390_WATCHED = ["main", "tablet_autonomous_evolution_v397.py", "tablet_runtime_manifest.py"]

V391_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V391.json"
V391_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V390.json"
V391_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v390_delta.json"
V391_TEST = "test_tablet_gpt_tcg_grader_sync_v391.py"
V391_BASE = "80c1210c453b779021292d8eb16015bd5f54147d"
V391_CANDIDATE = "47fe605f68e2f8a73b0cf50bb51244db03e12f2b"
V391_WATCHED = ["main", "tablet_autonomous_evolution_v398.py", "tablet_runtime_manifest.py"]

V392_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V392.json"
V392_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V391.json"
V392_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v391_delta.json"
V392_TEST = "test_tablet_gpt_tcg_grader_sync_v392.py"
V392_BASE = "62bc132373bc9dafb88d9057e8b3c54c2c388fea"
V392_CANDIDATE = "e491ff1c64c30f6d72d33ee33999f937cf82e1e6"
V392_WATCHED = [
    "VERIFY_TABLET_FINAL.sh",
    "index.html",
    "main",
    "sw.js",
    "tablet_autonomous_evolution_v399.py",
    "tablet_autonomy_dashboard_v399.css",
    "tablet_autonomy_dashboard_v399.js",
    "tablet_runtime_manifest.py",
    "tcg_updater.py",
]
V393_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V393.json"
V393_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V392.json"
V393_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v392_delta.json"
V393_TEST = "test_tablet_gpt_tcg_grader_sync_v393.py"
V393_BASE = "06ac25a0982dec8d5dc0019fe1d2cd200ce5431d"
V393_CANDIDATE = "860e964398c2986ecf1ed2b6975e4cd02b4b25a1"
V393_WATCHED = [
    "VERIFY_TABLET_FINAL.sh",
    "index.html",
    "main",
    "sw.js",
    "tablet_autonomous_evolution_v398.py",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
    "tcg_updater.py",
]
# V391 and earlier did not watch VERIFY_TABLET_FINAL.sh. Their immutable scope
# sees the V392 and V393 runtime paths, but not that later-added exact path.
V394_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V394.json"
V394_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V393.json"
V394_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v393_delta.json"
V394_TEST = "test_tablet_gpt_tcg_grader_sync_v394.py"
V394_BASE = "62bc132373bc9dafb88d9057e8b3c54c2c388fea"
V394_CANDIDATE = "3b55feb3df6702a0996043429935b9570115d9e1"
V394_WATCHED = ["VERIFY_TABLET_FINAL.sh","index.html","main","sw.js","tablet_autonomous_evolution_v398.py","tablet_autonomous_evolution_v399.py","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v399.css","tablet_autonomy_dashboard_v399.js","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js","tablet_runtime_manifest.py","tcg_updater.py"]
V394_AFTER_V393_WATCHED = ["sw.js", "tablet_autonomous_evolution_v400.py", "tablet_autonomy_dashboard_v400.css", "tablet_autonomy_dashboard_v400.js"]

V395_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V395.json"
V395_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V394.json"
V395_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v394_delta.json"
V395_TEST = "test_tablet_gpt_tcg_grader_sync_v395.py"
V395_BASE = "90fc86cd1fa0d5594d52f57e89b345003859aba5"
V395_CANDIDATE = "5f36e0737976567a5069520961ca56b23028d964"
V395_WATCHED = ["tablet_autonomous_evolution_v400.py"]

V396_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V396.json"
V396_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V395.json"
V396_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v395_delta.json"
V396_TEST = "test_tablet_gpt_tcg_grader_sync_v396.py"
V396_BASE = "dff6e8be13b6bebc793855a728dcd4328a24dadf"
V396_CANDIDATE = "cc50e98cafa560168b6231e3507378790aea5f4b"
V396_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
]

V397_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V397.json"
V397_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V396.json"
V397_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v396_delta.json"
V397_TEST = "test_tablet_gpt_tcg_grader_sync_v397.py"
V397_BASE = "624b5e678f9360de308a5d06a56dc4b69c27c16c"
V397_CANDIDATE = "5866641db9d97d644835b409bc0b10a9f93d4d89"
V397_WATCHED = [
    "VERIFY_TABLET_FINAL.sh",
    "main",
    "tablet_autonomous_evolution_v400.py",
    "tablet_runtime_manifest.py",
]
V397_AFTER_V395_WATCHED = sorted(set(V396_WATCHED) | set(V397_WATCHED))
V397_AFTER_V394_WATCHED = list(V397_AFTER_V395_WATCHED)
V397_AFTER_V393_WATCHED = sorted(set(V394_AFTER_V393_WATCHED) | set(V397_WATCHED))

V398_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V398.json"
V398_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V397.json"
V398_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v397_delta.json"
V398_TEST = "test_tablet_gpt_tcg_grader_sync_v398.py"
V398_BASE = "0777d51075fdba4a8e2d1ac5f3e99668c0380648"
V398_CANDIDATE = "89fc0ed43a36918a62669fdc17e8bea1467e084d"
V398_WATCHED = [
    "index.html",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
]
V398_AFTER_V396_WATCHED = sorted(set(V397_WATCHED) | set(V398_WATCHED))
V398_AFTER_V395_WATCHED = sorted(set(V396_WATCHED) | set(V397_WATCHED) | set(V398_WATCHED))
V398_AFTER_V394_WATCHED = sorted(set(V395_WATCHED) | set(V396_WATCHED) | set(V397_WATCHED) | set(V398_WATCHED))
V398_AFTER_V393_WATCHED = sorted(set(V394_AFTER_V393_WATCHED) | set(V397_WATCHED) | set(V398_WATCHED))

V393_LEGACY_VISIBLE_WATCHED = [path for path in V393_WATCHED if path != "VERIFY_TABLET_FINAL.sh"]
V392_LEGACY_VISIBLE_WATCHED = sorted(
    set(path for path in V392_WATCHED if path != "VERIFY_TABLET_FINAL.sh")
    | set(V393_LEGACY_VISIBLE_WATCHED)
)


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


def assert_v398_successor(testcase):
    """Validate V398 as the exact real-DOM adaptive component successor."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V398_CONTRACT_PATH,
        prior_contract=V398_PRIOR_CONTRACT,
        prior_delta=V398_PRIOR_DELTA,
        verification_test=V398_TEST,
        base=V398_BASE,
        candidate_sha=V398_CANDIDATE,
        watched=V398_WATCHED,
        version="V398",
    )
    testcase.assertEqual(
        [],
        _watched_paths(contract, V398_CANDIDATE),
        "V398 successor has uncovered watched changes",
    )
    return contract, candidate


def assert_v397_successor(testcase):
    """Validate immutable V397 and delegate adaptive component changes to V398."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V397_CONTRACT_PATH,
        prior_contract=V397_PRIOR_CONTRACT,
        prior_delta=V397_PRIOR_DELTA,
        verification_test=V397_TEST,
        base=V397_BASE,
        candidate_sha=V397_CANDIDATE,
        watched=V397_WATCHED,
        version="V397",
    )
    after397 = _watched_paths(contract, V397_CANDIDATE)
    if not after397:
        return contract, candidate
    testcase.assertEqual(V398_WATCHED, after397)
    return assert_v398_successor(testcase)


def assert_v396_successor(testcase):
    """Validate immutable V396 and delegate full control-plane changes to V397."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V396_CONTRACT_PATH,
        prior_contract=V396_PRIOR_CONTRACT,
        prior_delta=V396_PRIOR_DELTA,
        verification_test=V396_TEST,
        base=V396_BASE,
        candidate_sha=V396_CANDIDATE,
        watched=V396_WATCHED,
        version="V396",
    )
    after396 = _watched_paths(contract, V396_CANDIDATE)
    if not after396:
        return contract, candidate
    testcase.assertIn(after396, (V397_WATCHED, V398_AFTER_V396_WATCHED))
    return assert_v397_successor(testcase)


def assert_v395_successor(testcase):
    """Validate immutable V395 and delegate later adaptive-UI changes to V396."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V395_CONTRACT_PATH,
        prior_contract=V395_PRIOR_CONTRACT,
        prior_delta=V395_PRIOR_DELTA,
        verification_test=V395_TEST,
        base=V395_BASE,
        candidate_sha=V395_CANDIDATE,
        watched=V395_WATCHED,
        version="V395",
    )
    after395 = _watched_paths(contract, V395_CANDIDATE)
    if not after395:
        return contract, candidate
    testcase.assertIn(after395, (V396_WATCHED, V397_AFTER_V395_WATCHED, V398_AFTER_V395_WATCHED))
    return assert_v396_successor(testcase)


def assert_v394_successor(testcase):
    """Validate immutable V394 and delegate later card-verification change to V395."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V394_CONTRACT_PATH,
        prior_contract=V394_PRIOR_CONTRACT,
        prior_delta=V394_PRIOR_DELTA,
        verification_test=V394_TEST,
        base=V394_BASE,
        candidate_sha=V394_CANDIDATE,
        watched=V394_WATCHED,
        version="V394",
    )
    after394 = _watched_paths(contract, V394_CANDIDATE)
    if not after394:
        return contract, candidate
    testcase.assertIn(after394, (V395_WATCHED, V396_WATCHED, V397_AFTER_V394_WATCHED, V398_AFTER_V394_WATCHED))
    return assert_v395_successor(testcase)


def assert_v393_successor(testcase):
    """Validate immutable V393 and delegate the cache-ABI repair to V394."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V393_CONTRACT_PATH,
        prior_contract=V393_PRIOR_CONTRACT,
        prior_delta=V393_PRIOR_DELTA,
        verification_test=V393_TEST,
        base=V393_BASE,
        candidate_sha=V393_CANDIDATE,
        watched=V393_WATCHED,
        version="V393",
    )
    after393 = _watched_paths(contract, V393_CANDIDATE)
    if not after393:
        return contract, candidate
    testcase.assertIn(after393, (V394_AFTER_V393_WATCHED, V397_AFTER_V393_WATCHED, V398_AFTER_V393_WATCHED))
    return assert_v394_successor(testcase)


def assert_v392_successor(testcase):
    """Validate immutable V392 and delegate later watched changes to V393."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V392_CONTRACT_PATH,
        prior_contract=V392_PRIOR_CONTRACT,
        prior_delta=V392_PRIOR_DELTA,
        verification_test=V392_TEST,
        base=V392_BASE,
        candidate_sha=V392_CANDIDATE,
        watched=V392_WATCHED,
        version="V392",
    )
    after392 = _watched_paths(contract, V392_CANDIDATE)
    if not after392:
        return contract, candidate
    testcase.assertEqual(V393_WATCHED, after392)
    return assert_v393_successor(testcase)


def assert_v391_successor(testcase):
    """Validate immutable V391 and delegate later visible changes to exact V392."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V391_CONTRACT_PATH,
        prior_contract=V391_PRIOR_CONTRACT,
        prior_delta=V391_PRIOR_DELTA,
        verification_test=V391_TEST,
        base=V391_BASE,
        candidate_sha=V391_CANDIDATE,
        watched=V391_WATCHED,
        version="V391",
    )
    after391 = _watched_paths(contract, V391_CANDIDATE)
    if not after391:
        return contract, candidate
    testcase.assertEqual(V392_LEGACY_VISIBLE_WATCHED, after391)
    return assert_v392_successor(testcase)


def assert_v390_successor(testcase):
    """Validate immutable V390 and delegate later watched changes to exact V391."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V390_CONTRACT_PATH,
        prior_contract=V390_PRIOR_CONTRACT,
        prior_delta=V390_PRIOR_DELTA,
        verification_test=V390_TEST,
        base=V390_BASE,
        candidate_sha=V390_CANDIDATE,
        watched=V390_WATCHED,
        version="V390",
    )
    after390 = _watched_paths(contract, V390_CANDIDATE)
    if not after390:
        return contract, candidate
    testcase.assertEqual(sorted(set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after390)
    return assert_v391_successor(testcase)


def assert_v389_successor(testcase):
    """Validate immutable V389 and delegate later watched changes to exact V390."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V389_CONTRACT_PATH,
        prior_contract=V389_PRIOR_CONTRACT,
        prior_delta=V389_PRIOR_DELTA,
        verification_test=V389_TEST,
        base=V389_BASE,
        candidate_sha=V389_CANDIDATE,
        watched=V389_WATCHED,
        version="V389",
    )
    after389 = _watched_paths(contract, V389_CANDIDATE)
    if not after389:
        return contract, candidate
    testcase.assertEqual(sorted(set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after389)
    return assert_v390_successor(testcase)


def assert_v388_successor(testcase):
    """Validate immutable V388 and delegate later watched changes to exact V389."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V388_CONTRACT_PATH,
        prior_contract=V388_PRIOR_CONTRACT,
        prior_delta=V388_PRIOR_DELTA,
        verification_test=V388_TEST,
        base=V388_BASE,
        candidate_sha=V388_CANDIDATE,
        watched=V388_WATCHED,
        version="V388",
    )
    after388 = _watched_paths(contract, V388_CANDIDATE)
    if not after388:
        return contract, candidate
    testcase.assertEqual(sorted(set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after388)
    return assert_v389_successor(testcase)


def assert_v387_successor(testcase):
    """Validate immutable V387 and delegate later watched changes to exact V388."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V387_CONTRACT_PATH,
        prior_contract=V387_PRIOR_CONTRACT,
        prior_delta=V387_PRIOR_DELTA,
        verification_test=V387_TEST,
        base=V387_BASE,
        candidate_sha=V387_CANDIDATE,
        watched=V387_WATCHED,
        version="V387",
    )
    after387 = _watched_paths(contract, V387_CANDIDATE)
    if not after387:
        return contract, candidate
    testcase.assertEqual(sorted(set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after387)
    return assert_v388_successor(testcase)


def assert_v386_successor(testcase):
    """Validate immutable V386 and delegate later watched changes to exact V387."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V386_CONTRACT_PATH,
        prior_contract=V386_PRIOR_CONTRACT,
        prior_delta=V386_PRIOR_DELTA,
        verification_test=V386_TEST,
        base=V386_BASE,
        candidate_sha=V386_CANDIDATE,
        watched=V386_WATCHED,
        version="V386",
    )
    after386 = _watched_paths(contract, V386_CANDIDATE)
    if not after386:
        return contract, candidate
    testcase.assertEqual(sorted(set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after386)
    return assert_v387_successor(testcase)


def assert_v385_successor(testcase):
    """Validate immutable V385 and delegate later watched changes to exact V386."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V385_CONTRACT_PATH,
        prior_contract=V385_PRIOR_CONTRACT,
        prior_delta=V385_PRIOR_DELTA,
        verification_test=V385_TEST,
        base=V385_BASE,
        candidate_sha=V385_CANDIDATE,
        watched=V385_WATCHED,
        version="V385",
    )
    after385 = _watched_paths(contract, V385_CANDIDATE)
    if not after385:
        return contract, candidate
    testcase.assertEqual(sorted(set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after385)
    return assert_v386_successor(testcase)


def assert_v384_successor(testcase):
    """Validate immutable V384 and delegate later watched changes to exact V385."""
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
    after384 = _watched_paths(contract, V384_CANDIDATE)
    if not after384:
        return contract, candidate
    testcase.assertEqual(sorted(set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after384)
    return assert_v385_successor(testcase)


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
    testcase.assertEqual(sorted(set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after383)
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
    testcase.assertEqual(sorted(set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after382)
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
    testcase.assertEqual(sorted(set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after381)
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
    testcase.assertEqual(sorted(set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after380)
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

    testcase.assertEqual(sorted(set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), after379)
    contract380, candidate380 = assert_v380_successor(testcase)
    if relevant is not None:
        testcase.assertEqual(
            sorted(set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)),
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

    expected = sorted(set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED))
    testcase.assertEqual(expected, after378)
    contract380, candidate380 = assert_v379_successor(testcase, after378)
    if relevant is not None:
        testcase.assertEqual(
            sorted(set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)),
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

    expected = sorted(set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED))
    testcase.assertEqual(expected, after377)
    contract380, candidate380 = assert_v378_successor(testcase, after377)
    if relevant is not None:
        testcase.assertEqual(
            sorted(set(V377_WATCHED) | set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)),
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

    expected = sorted(set(V377_WATCHED) | set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED))
    testcase.assertEqual(expected, after376)
    contract380, candidate380 = assert_v377_successor(testcase, after376)
    testcase.assertEqual(
        sorted(set(V376_WATCHED) | set(V377_WATCHED) | set(V378_WATCHED) | set(V379_WATCHED) | set(V380_WATCHED) | set(V381_WATCHED) | set(V382_WATCHED) | set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)),
        sorted(relevant),
    )
    return contract380, candidate380


def assert_current_autonomy_route_v393(testcase, main_text=None, manifest_text=None):
    """Require exact V393 sync evidence and current V400 domain-aware runtime."""
    assert_v393_successor(testcase)
    if main_text is None:
        main_text = (ROOT / "main").read_text(encoding="utf-8")
    if manifest_text is None:
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
    testcase.assertIn(
        "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
        main_text,
    )
    for version in ("v400", "v399", "v398", "v397", "v391", "v390", "v388", "v387", "v386", "v385", "v382", "v381", "v380", "v379", "v378", "v377", "v376"):
        testcase.assertIn(f'"tablet_autonomous_evolution_{version}.py"', manifest_text)


def assert_current_autonomy_route_v392(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v391(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v390(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v389(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v388(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v387(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v386(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v385(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v384(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v383(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v382(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v381(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v380(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v379(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v378(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)


def assert_current_autonomy_route_v377(testcase, main_text=None, manifest_text=None):
    return assert_current_autonomy_route_v393(testcase, main_text, manifest_text)
