"""Strict successor support for historical Tablet GPT sync generations through V415.

V376-V379 remain immutable history. Later watched changes must be covered by an
exact newer generation; no historical generation is silently relaxed.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
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

V399_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V399.json"
V399_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V398.json"
V399_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v398_delta.json"
V399_TEST = "test_tablet_gpt_tcg_grader_sync_v399.py"
V399_BASE = "866de4ee12382fd7767e0d939b1e154aa0c0cd03"
V399_CANDIDATE = "b054c580f895c08d26c38f799b83babbfbcf9beb"
V399_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
]

V400_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V400.json"
V400_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V399.json"
V400_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v399_delta.json"
V400_TEST = "test_tablet_gpt_tcg_grader_sync_v400.py"
V400_BASE = "aea7ab68f0d75c5373139141db338e9247b04770"
V400_CANDIDATE = "78abaca8851ba0a488626bc94cc568dd454bfb1f"
V400_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
]

V401_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V401.json"
V401_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V400.json"
V401_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v400_delta.json"
V401_TEST = "test_tablet_gpt_tcg_grader_sync_v401.py"
V401_BASE = "ff04ecb767d98df886719573ac6d65bb4f452203"
V401_CANDIDATE = "361812899a42c1b588d015187402234369562d52"
V401_WATCHED = [
    "screen_policy_neural_v401.py",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
]
V401_LEGACY_VISIBLE_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
]
V401_AFTER_V398_VISIBLE_WATCHED = sorted(set(V399_WATCHED) | {"tablet_runtime_manifest.py"})
V401_AFTER_V397_VISIBLE_WATCHED = sorted(set(V398_WATCHED) | {"tablet_runtime_manifest.py"})

V402_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V402.json"
V402_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V401.json"
V402_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v401_delta.json"
V402_TEST = "test_tablet_gpt_tcg_grader_sync_v402.py"
V402_BASE = "221dd2ca754291c878eb894292687146e16a6fb1"
V402_CANDIDATE = "1884da614f74075c421a8c36bf2f0f22a89ef762"
V402_WATCHED = [
    "screen_policy_neural_v401.py",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
]

V403_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V403.json"
V403_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V402.json"
V403_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v402_delta.json"
V403_TEST = "test_tablet_gpt_tcg_grader_sync_v403.py"
V403_BASE = "b3d4c6d4000b5565de80c52294a7efc5b9b5de51"
V403_CANDIDATE = "501e9bcb34910376937bec35cfefa0a1dfb64722"
V403_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
]
V403_AFTER_V401_VISIBLE_WATCHED = sorted(set(V402_WATCHED) | set(V403_WATCHED))
V403_AFTER_V400_VISIBLE_WATCHED = sorted(set(V401_LEGACY_VISIBLE_WATCHED) | {"tablet_autonomy_dashboard_v400.css"})

V404_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V404.json"
V404_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V403.json"
V404_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v403_delta.json"
V404_TEST = "test_tablet_gpt_tcg_grader_sync_v404.py"
V404_BASE = "0f2621f27a2206d487167e9ec4c9ca67d70404d3"
V404_CANDIDATE = "307ddca680441f0263bfcf52a3521fa5da84def1"
V404_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
]

V405_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json"
V405_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V404.json"
V405_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v404_delta.json"
V405_TEST = "test_tablet_gpt_tcg_grader_sync_v405.py"
V405_BASE = "f24d5a127de9ad56431b0b9566c021956b954e65"
V405_CANDIDATE = "7b66ee36088ebd08640d5d42ebdc60c9330cc3ac"
V405_WATCHED = ["TABLET_SCHEDULED_UPDATE.sh"]

V406_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V406.json"
V406_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json"
V406_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v405_delta.json"
V406_TEST = "test_tablet_gpt_tcg_grader_sync_v406.py"
V406_BASE = "13b3925ff2242bfe1f560df1ec3b4fcf8afabfab"
V406_CANDIDATE = "4e349f0f1e1a9d8a6ed4878305d26378bdd71e82"
V406_MERGE_SHA = "7e4665bdc7b4737fa4aff8af8f2b52e09d646b77"
V406_WATCHED = ["TABLET_SCHEDULED_UPDATE.sh"]

V407_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V407.json"
V407_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V406.json"
V407_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v406_delta.json"
V407_TEST = "test_tablet_gpt_tcg_grader_sync_v407.py"
V407_BASE = "7e4665bdc7b4737fa4aff8af8f2b52e09d646b77"
V407_CANDIDATE = "83ed83788bf774c5f755da3490d982115a5c4277"
V407_MERGE_SHA = "83ed83788bf774c5f755da3490d982115a5c4277"
V407_WATCHED = ["feature_category_nav.js", "tablet_autonomy_dashboard_v400.js"]

V408_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V408.json"
V408_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V407.json"
V408_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v407_delta.json"
V408_TEST = "test_tablet_gpt_tcg_grader_sync_v408.py"
V408_BASE = "879d131cdf8877870eb4f5c10528a817bdf3b36c"
V408_CANDIDATE = "7dffbe8311a92fcfb9b77ce5b7bc3e1be2533ccf"
V408_MERGE_SHA = "53a6aef86cb900ef06bdc920a59bd7a9e0e4ff75"
V408_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
]

V409_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V409.json"
V409_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V408.json"
V409_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v408_delta.json"
V409_TEST = "test_tablet_gpt_tcg_grader_sync_v409.py"
V409_BASE = "53a6aef86cb900ef06bdc920a59bd7a9e0e4ff75"
V409_CANDIDATE = "995c92ca384ca65db722068b97524d426a52c1eb"
V409_FUNCTIONAL_CANDIDATE = "b26d82335e9ec4ec260ed4de5656543531e0731a"
V409_MERGE_SHA = "995c92ca384ca65db722068b97524d426a52c1eb"
V409_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
]

V410_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V410.json"
V410_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V409.json"
V410_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v409_delta.json"
V410_TEST = "test_tablet_gpt_tcg_grader_sync_v410.py"
V410_BASE = "3b0cdb01cd3083701dda198b1c1642fa43301d89"
V410_CANDIDATE = "64cfd6393b5c6d7ad51d3a301e1b71ab4a247445"
V410_FUNCTIONAL_CANDIDATE = "69b5a3e6a94d3b523e54b1c7c4415e993951e0a5"
V410_MERGE_SHA = "64cfd6393b5c6d7ad51d3a301e1b71ab4a247445"
V410_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
]

V411_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V411.json"
V411_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V410.json"
V411_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v410_delta.json"
V411_TEST = "test_tablet_gpt_tcg_grader_sync_v411.py"
V411_BASE = "820d874a509affa488bfa0468ba9cefa65d8b226"
V411_CANDIDATE = "c10a3af9326dadab196e60dde53f1a63db871b73"
V411_FUNCTIONAL_CANDIDATE = "fb42766e7c4ee22ce3f8382329f92294867b430a"
V411_MERGE_SHA = "c10a3af9326dadab196e60dde53f1a63db871b73"
V411_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
]

V412_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V412.json"
V412_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V411.json"
V412_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v411_delta.json"
V412_TEST = "test_tablet_gpt_tcg_grader_sync_v412.py"
V412_BASE = "bbb4e6f85f3d5c658ba0f9acd2f56af92985d07d"
V412_CANDIDATE = "2fc7c5a012ac480295b9630a4ebb5d0350ff307e"
V412_WATCHED = [
    "sw.js",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
    "tcg_updater.py",
]

V413_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V413.json"
V413_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V412.json"
V413_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v412_delta.json"
V413_TEST = "test_tablet_gpt_tcg_grader_sync_v413.py"
V413_BASE = "393fe2a43d0ef330a2f47e1b976fa86519beb220"
V413_CANDIDATE = "e68129a3f9305a62fc611237037257d54676cb18"
V413_WATCHED = [
    "auto_update_all.py",
    "feature_contract.py",
    "promoted_tcg_source_monitor_v413.py",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
    "tcg_game_registry.json",
    "tcg_game_registry.py",
    "update_purchase_sources.py",
]
V413_LEGACY_VISIBLE_WATCHED = [
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
]

V414_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V414.json"
V414_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V413.json"
V414_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v413_delta.json"
V414_TEST = "test_tablet_gpt_tcg_grader_sync_v414.py"
V414_BASE = "34bd952f83d5735d5c7f73a3db8af3316cf3d6a4"
V414_CANDIDATE = "40793bef499fd680f2eb30fe1eab601b49565630"
V414_WATCHED = [
    "feature_contract.py",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.js",
    "tcg_game_registry.json",
    "tcg_game_registry.py",
]

V415_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V415.json"
V415_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V414.json"
V415_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v414_delta.json"
V415_TEST = "test_tablet_gpt_tcg_grader_sync_v415.py"
V415_BASE = "404d49f79f3fb597d42f1a36af9215805ea6739f"
V415_CANDIDATE = "66026b140ad80ffc4e5d36fc706a7ae122e7a638"
V415_WATCHED = ["feature_contract.py"]

V416_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V416.json"
V416_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V415.json"
V416_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v415_delta.json"
V416_TEST = "test_tablet_gpt_tcg_grader_sync_v416.py"
V416_BASE = "d2ef5e21194feb54ace894623935c755284d0e27"
V416_CANDIDATE = "eacdd19291f35ff63d3208ec4446a41181dc5107"
V416_WATCHED = ["tcg_game_registry.json"]

V419_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V419.json"
V419_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V416.json"
V419_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v416_delta.json"
V419_TEST = "test_tablet_gpt_tcg_grader_sync_v419.py"
V419_BASE = "0ac9791b7714a4972768311abfc555c08df11602"
V419_CANDIDATE = "726360bda7b79568512358b1c0dd80ce401d1e2f"
V419_WATCHED = ["tcg_game_registry.json", "tcg_game_registry.py"]
V420_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V420.json"
V420_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V419.json"
V420_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v419_delta.json"
V420_TEST = "test_tablet_gpt_tcg_grader_sync_v420.py"
V420_BASE = "6faaea1319623bc378be7209c54ad38cafc66707"
V420_CANDIDATE = "f821c57901e47707c80e5b69dbdcbeda9244871a"
V420_WATCHED = ["feature_contract.py", "tablet_autonomy_dashboard_v400.js", "tcg_updater.py"]
V421_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V421.json"
V421_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V420.json"
V421_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v420_delta.json"
V421_TEST = "test_tablet_gpt_tcg_grader_sync_v421.py"
V421_BASE = "a13f80da8d341020da8e650868816300e0eafcad"
V421_CANDIDATE = "11cff2bd294dbaeb00a04dce4f49d8ddde181fca"
V421_WATCHED = ["feature_contract.py", "tablet_autonomy_dashboard_v400.js", "tcg_game_registry.py"]
V422_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V422.json"
V422_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V421.json"
V422_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v421_delta.json"
V422_TEST = "test_tablet_gpt_tcg_grader_sync_v422.py"
V422_BASE = "b5e43489bc53944f22734b56d1581e636683384f"
V422_CANDIDATE = "587d01bbc273b926c3a417ef8b2674702df36394"
V422_WATCHED = ["feature_contract.py", "tcg_game_registry.json"]
V423_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V423.json"
V423_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V422.json"
V423_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v422_delta.json"
V423_TEST = "test_tablet_gpt_tcg_grader_sync_v423.py"
V423_BASE = "419ab6b068cdcdcb8ab771e47e0aab1fdf6b12f1"
V423_CANDIDATE = "0ba80d955b0e4b704d4cafa387eb13dd62bcbf2c"
V423_WATCHED = ["feature_contract.py", "screen_policy_neural_v401.py", "tcg_game_registry.py"]
V424_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V424.json"
V424_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V423.json"
V424_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v423_delta.json"
V424_TEST = "test_tablet_gpt_tcg_grader_sync_v424.py"
V424_BASE = "58cd34422347584d091c8c22ba9b44e0bd8a8b87"
V424_CANDIDATE = "e9a0bb5868ececa74dc39e747f3097fb3682a6d4"
V424_WATCHED = ["tcg_game_registry.json"]
V425_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V425.json"
V425_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V424.json"
V425_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v424_delta.json"
V425_TEST = "test_tablet_gpt_tcg_grader_sync_v425.py"
V425_BASE = "b0e0a483dee0a77cc054e978b83a83e09323d6b0"
V425_CANDIDATE = "c220fbb0de2320f51d7ad6ba1dd968cdb673c857"
V425_WATCHED = ["tablet_autonomy_dashboard_v400.js", "tcg_game_registry.json"]
V426_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json"
V426_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V425.json"
V426_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v425_delta.json"
V426_TEST = "test_tablet_gpt_tcg_grader_sync_v426.py"
V426_BASE = "7b73dac4be2f66af1441c4992a029e13dea60bea"
V426_CANDIDATE = "1ad0c21facb403483bd39fd59ae63462290f2afa"
V426_WATCHED = [
    ".github/workflows/tcg-autonomy-market-guard-v426.yml",
    "tablet_autonomy_dashboard_v400.js",
    "tcg_game_registry.json",
]
V426_PREDECESSOR_WATCHED = [
    "tablet_autonomy_dashboard_v400.js",
    "tcg_game_registry.json",
]
V427_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V427.json"
V427_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json"
V427_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v426_delta.json"
V427_TEST = "test_tablet_gpt_tcg_grader_sync_v427.py"
V427_BASE = "01040a57889e88ce815d1d978a8bb8707c663e3c"
V427_CANDIDATE = "260c85b5c98ff28730919b932cc554e8d79a2ee9"
V427_WATCHED = ["tcg_game_registry.json"]
V428_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V428.json"
V428_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V427.json"
V428_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v427_delta.json"
V428_TEST = "test_tablet_gpt_tcg_grader_sync_v428.py"
V428_BASE = "b59eb45ab9b5596f0fad76b9b3e85a5e49e5e466"
V428_CANDIDATE = "775303a8e194de67f83a5d1ee51616bf4b505fbc"
V428_WATCHED = ["ui_app_shell_v272.css"]
# V429/V430 are bounded UI successors on the current candidate branch.
# They change only the registry-driven market lens and category focus navigator;
# dedicated regression modules are required before historical sync generations
# may delegate to these paths.
V429_WATCHED = ["tablet_autonomy_dashboard_v400.js"]
V430_WATCHED = ["feature_category_nav.js"]
V429_TEST = "test_tablet_registry_market_lens_v429.py"
V430_TEST = "test_tablet_category_focus_v430.py"
V431_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V431.json"
V431_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V430.json"
V431_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v430_delta.json"
V431_TEST = "test_tablet_gpt_tcg_grader_sync_v431.py"
V431_BASE = "b59eb45ab9b5596f0fad76b9b3e85a5e49e5e466"
V431_CANDIDATE = "783c02fa166802ad5ccb75dc18e05837b74cca21"
V431_WATCHED = [
    "feature_category_nav.js",
    "tablet_autonomy_dashboard_v400.js",
    "tcg_game_registry.py",
    "ui_app_shell_v272.css",
]
V432_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V432.json"
V432_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V431.json"
V432_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v431_delta.json"
V432_TEST = "test_tablet_gpt_tcg_grader_sync_v432.py"
V432_BASE = "783c02fa166802ad5ccb75dc18e05837b74cca21"
V432_CANDIDATE = "a168430ff8e02ea23e4829c03991b81089368fea"
V432_WATCHED = ["auto_update_all.py","tablet_runtime_manifest.py"]
V434_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V434.json"
V434_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V432.json"
V434_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v432_delta.json"
V434_TEST = "test_tablet_gpt_tcg_grader_sync_v434.py"
V434_BASE = "a168430ff8e02ea23e4829c03991b81089368fea"
V434_CANDIDATE = "d4be143444a1f320c9829e62d79807b059902c90"
V434_WATCHED = ["tablet_runtime_manifest.py"]
V435_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V435.json"
V435_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V434.json"
V435_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v434_delta.json"
V435_TEST = "test_tablet_gpt_tcg_grader_sync_v435.py"
V435_BASE = "d4be143444a1f320c9829e62d79807b059902c90"
V435_CANDIDATE = "bdcfb4505772a8e08a2c913bf7d296adc64754b4"
V435_WATCHED = ["tablet_runtime_manifest.py"]
V436_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V436.json"
V436_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V435.json"
V436_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v435_delta.json"
V436_TEST = "test_tablet_gpt_tcg_grader_sync_v436.py"
V436_BASE = "bdcfb4505772a8e08a2c913bf7d296adc64754b4"
V436_CANDIDATE = "22fc676af4bbdadd8e65cfb4dd6a57e24da26188"
V436_WATCHED = ["tablet_runtime_manifest.py"]
V437_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V437.json"
V437_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V436.json"
V437_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v436_delta.json"
V437_TEST = "test_tablet_gpt_tcg_grader_sync_v437.py"
V437_BASE = "22fc676af4bbdadd8e65cfb4dd6a57e24da26188"
V437_CANDIDATE = "62fdd46e1263305bae28e4d102d6b1f37a029ae8"
V437_WATCHED = ["tablet_runtime_manifest.py"]
V439_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V439.json"
V439_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V437.json"
V439_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v437_delta.json"
V439_TEST = "test_tablet_gpt_tcg_grader_sync_v439.py"
V439_BASE = "bfbba33f5c502e96cf7f6cd4de71ba12a716bf38"
V439_CANDIDATE = "c13707e8e24f7ba46d00fb5c5b1dd5ea08a18768"
V439_WATCHED = [".github/workflows/tcg-autonomy-market-guard-v426.yml", "tablet_autonomy_dashboard_v400.js"]
V440_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V440.json"
V440_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V439.json"
V440_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v439_delta.json"
V440_TEST = "test_tablet_gpt_tcg_grader_sync_v440.py"
V440_BASE = "e459bcb89de778f89b013ef520ac0fd26619a568"
V440_CANDIDATE = "cb90b84b5d40a836ead5950237a45c9cc0aadff0"
V440_WATCHED = ["VERIFY_TABLET_FINAL.sh", "main"]
V469_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V469.json"
V469_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V440.json"
V469_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v440_delta.json"
V469_TEST = "test_tablet_gpt_tcg_grader_sync_v469.py"
V469_BASE = "97c0c2f24cef8d723dd025da0f756db89fa5ad23"
V469_CANDIDATE = "909633f2d16f3d5e2319c1646efd6b98cd46abb1"
V469_WATCHED = ["index.html", "sw.js", "tablet_runtime_manifest.py", "tcg_updater.py"]
V470_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V470.json"
V470_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V469.json"
V470_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v469_delta.json"
V470_TEST = "test_tablet_gpt_tcg_grader_sync_v470.py"
V470_BASE = "c2796c4c2d6e22290020c2b1c26be4f50b4f5472"
V470_CANDIDATE = "78a677c5d0bf5480937caeeecb3168b27ebb5002"
V470_WATCHED = ["feature_category_nav.js"]
V471_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V471.json"
V471_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V470.json"
V471_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v470_delta.json"
V471_TEST = "test_tablet_gpt_tcg_grader_sync_v471.py"
V471_BASE = "21d3b37f8d79925302af199cc819f5f1e5a74e1c"
V471_CANDIDATE = "4f37f9a130ce148646d1cd4ff9cf1c45b757127e"
V471_WATCHED = ["feature_category_nav.js"]
V477_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V477.json"
V477_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V471.json"
V477_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v471_delta.json"
V477_TEST = "test_tablet_gpt_tcg_grader_sync_v477.py"
V477_BASE = "e2c79ca8f3be19792d1131a5dcaa38c885d2803a"
V477_CANDIDATE = "43b059830926e21f0ec152cf6f1c4c81de214362"
V477_WATCHED = ["main"]
V478_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V478.json"
V478_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V477.json"
V478_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v477_delta.json"
V478_TEST = "test_tablet_gpt_tcg_grader_sync_v478.py"
V478_BASE = "f4da875dea3dac1da420635e1fdfba7ce74c38aa"
V478_CANDIDATE = "9a0f0215313d1ddf651afe02713fcfffd2437185"
V478_WATCHED = [
    "box_hit_market_discovery.py",
    "box_knowledge_stats.css",
    "box_knowledge_stats.js",
    "index.html",
    "market_catalog_expander.js",
    "update_promo_events.py",
    "update_releases.py",
]
V479_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V479.json"
V479_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V478.json"
V479_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v478_delta.json"
V479_TEST = "test_tablet_gpt_tcg_grader_sync_v479.py"
V479_BASE = "e254fab7071090b2b180b551a70ccfae66466e03"
V479_CANDIDATE = "c059eaa17afc28205b60e6140f43185f4df2531b"
V479_WATCHED = ["box_knowledge_stats.css", "box_knowledge_stats.js"]
V480_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V480.json"
V480_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V479.json"
V480_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v479_delta.json"
V480_TEST = "test_tablet_gpt_tcg_grader_sync_v480.py"
V480_BASE = "381c97818caa4891ebb8903425d9f18612913617"
V480_CANDIDATE = "8f6cc113cda866bf0f25656b2a9dd0ff790703e5"
V480_WATCHED = [
    "multi_market_price_collector.py",
    "multi_market_prices.css",
    "multi_market_prices.js",
    "ui_app_shell_v272.css",
    "ui_app_shell_v272.js",
]
V482_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V482.json"
V482_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V480.json"
V482_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v480_delta.json"
V482_TEST = "test_tablet_gpt_tcg_grader_sync_v482.py"
V482_BASE = "633fb1546a2b2dc6b4b3e9743e0271b23dfb9591"
V482_CANDIDATE = "61ad268f302f2226230d105cf57c1c1c03749d89"
V482_WATCHED = [
    "multi_market_price_collector.py",
    "multi_market_prices.css",
    "multi_market_prices.js",
]
# V485 screenshot-informed local-only market-home evidence generation.
V485_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V485.json"
V485_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V482.json"
V485_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v482_delta.json"
V485_TEST = "test_tablet_gpt_tcg_grader_sync_v485.py"
V485_BASE = "82a3844b60aa13d027e67e8192115bf3767e2730"
V485_CANDIDATE = "913af035b317c45342d64a8470b149c4e16b7b0f"
V485_WATCHED = ["feature_category_nav.css", "index.html"]

# V483 reviewed pricing, seller provenance and local history successor.
V483_CONTRACT_PATH = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V483.json"
V483_PRIOR_CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V482.json"
V483_PRIOR_DELTA = "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v482_delta.json"
V483_TEST = "test_tablet_gpt_tcg_grader_sync_v483.py"
V483_BASE = "82a3844b60aa13d027e67e8192115bf3767e2730"
V483_CANDIDATE = "e47c18e5e9720a5b31f428b22c4a3875ff3f239c"
V483_WATCHED = [
    "apply_multi_market_prices_patch.py",
    "index.html",
    "market_ai_auto_tracker.py",
    "multi_market_price_collector.py",
    "multi_market_prices.css",
    "multi_market_prices.js",
    "tcg_updater.py",
    "ui_app_shell_v272.js",
]

# V488 keeps historical package-workflow snapshots immutable. The later
# reviewed package retry is checked independently against the exact base and
# implementation commit instead of being attributed to an older sync generation.
V488_PACKAGE_BASE = "78c4d2e659f9a55f85504bf3a0d2f1dfe3f82e25"
V488_PACKAGE_CANDIDATE = "729235e3fa3c9051b5ab2d5375819477fd80b862"
V488_PACKAGE_PATH = ".github/workflows/gpt-tcg-drive-package.yml"
V488_PACKAGE_SHA256 = "36f7ce79fd4d1175f4af1dc7830e4dfcd445638e775b1a2bc3cd1859d75f1139"

# V521 validates the exact post-schema last-good recovery separately. Historical
# V432's immutable reviewed scope is retained; the later change is recognized
# only while the candidate commit is an ancestor AND on-disk bytes still match.
V521_RESTORE_BASE = "1561d81103ff209b5d630a721e42255f2773859c"
V521_RESTORE_CANDIDATE = "10f5d23a8fbdd6f5ca469d37220fa81b02f59e8e"
V521_RESTORE_PATH = "auto_update_all.py"
V521_RESTORE_SHA256 = "0c294e1bb1d41c51448f6e0b94fb2f33f6dff1866ae7eea4ed440d165abe8ba7"

# V525: older reviewed generations used these identical grading widget bytes.
# Preserve historical snapshots ONLY for this exact descendant implementation,
# and only if the file was untouched between the historical source and base.
V525_GRADE_BASE = "db7f0639b620e8885201dd20f0b6a51bfc964d05"
V525_GRADE_CANDIDATE = "fb44f5d77a1a3f50d61ce134e333df1f05322390"
V525_GRADE_PATH = "grade_market_flow.js"
V525_GRADE_SHA256 = "4a52caa1da9f4254b9bf50a6f0095864e68fe0f7022ce24be7f6e46e687f2c5f"

# V534: exact BOX release/market-date source correction. Historic generation
# remains immutable; only the reviewed descendant bytes may be excluded.
V534_BOX_BASE = "7713f67ad8243e6881aedebb90d4deeffed2a70d"
V534_BOX_CANDIDATE = "d1bd418ea0decc3f54db4eb00fd16f0d31129df6"
V534_BOX_PATH = "box_knowledge_stats.js"
V534_BOX_SHA256 = "676f76d29d0677ed66e5e8b6ae4f564af90b779540f1e027214a32e4ea8082ce"
# V535: only the exact descendant with age/source-verified trading signals.
V535_BOX_CANDIDATE = "bd3106e98cadcef2fe60e98308b7f4adee86224b"
V535_BOX_SHA256 = "9a5896769073b1dcfe9894dcb97642f0977505eb34268f3c42b972a8f18fc395"
# V537: HOT ranking uses exactly the same verified market observation date as eligibility.
V537_BOX_CANDIDATE = "b0086e7a1edaecd57d4ee6ebf70849b076e6d728"
V537_BOX_SHA256 = "b72abc65e349743503ae40df02cc4f59147d2e6363bd70c9f1e246d42c41c6ad"
# V540: exact ISO market observations prevent partial-date HOT contamination.
V540_BOX_CANDIDATE = "e83146fdb01939730daf5c80997c3b66fd455419"
V540_BOX_SHA256 = "dbb93d29e86ce8e5241bf6ccbaab46760de564d2c80ce39f86eec7f9607e212f"


# V406's immutable freshness watch already covered tablet_* but did not yet
# include feature_category_nav.js. The V407 contract expands that exact scope.
V407_LEGACY_VISIBLE_WATCHED = ["tablet_autonomy_dashboard_v400.js"]
V393_LEGACY_VISIBLE_WATCHED = [path for path in V393_WATCHED if path != "VERIFY_TABLET_FINAL.sh"]
V392_LEGACY_VISIBLE_WATCHED = sorted(
    set(path for path in V392_WATCHED if path != "VERIFY_TABLET_FINAL.sh")
    | set(V393_LEGACY_VISIBLE_WATCHED)
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))



def preserve_reviewed_v525_grade_scope(
    visible: list[str], source: str, head: str = "HEAD", *, prior_head: str | None = None
) -> list[str]:
    """Keep exact reviewed V525/V545 successor changes separate from historic edits."""
    visible = preserve_reviewed_v545_static_scope(visible, source, head, prior_head=prior_head)
    if head != "HEAD" or V525_GRADE_PATH not in visible:
        return visible
    reviewed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V525_GRADE_CANDIDATE, "HEAD"],
        check=False, capture_output=True,
    ).returncode == 0
    target = ROOT / V525_GRADE_PATH
    pinned = target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == V525_GRADE_SHA256
    if not (reviewed and pinned):
        return visible
    earlier = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{V525_GRADE_BASE}", "--", V525_GRADE_PATH],
        text=True,
    ).splitlines()
    return [path for path in visible if path != V525_GRADE_PATH] if not earlier else visible


def preserve_reviewed_v534_box_scope(visible: list[str], source: str, head: str = "HEAD") -> list[str]:
    """Exclude only reviewed V534 BOX bytes from older, unchanged historical scope."""
    if head != "HEAD" or V534_BOX_PATH not in visible:
        return visible
    path = ROOT / V534_BOX_PATH
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    # Accept only immutable reviewed descendants. V535 has an explicit feature
    # commit and pinned content; arbitrary later re-touches fail closed.
    reviewed_pairs = (
        (V534_BOX_CANDIDATE, V534_BOX_SHA256),
        (V535_BOX_CANDIDATE, V535_BOX_SHA256),
        (V537_BOX_CANDIDATE, V537_BOX_SHA256),
        (V540_BOX_CANDIDATE, V540_BOX_SHA256),
    )
    recognized = any(
        digest == expected and subprocess.run(
            ["git", "merge-base", "--is-ancestor", candidate, "HEAD"],
            check=False, capture_output=True,
        ).returncode == 0
        for candidate, expected in reviewed_pairs
    )
    if not recognized:
        return visible
    earlier = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{V534_BOX_BASE}", "--", V534_BOX_PATH],
        text=True,
    ).splitlines()
    # An existing unrelated change before V534 must never disappear from a
    # historical test's watched set.
    return [item for item in visible if item != V534_BOX_PATH] if not earlier else visible


# V545: reviewed, immutable static snapshot is a new data-only successor.
# A scheduled publish was validated but the Actions token could not open a PR.
# Guard this exact rebased snapshot and never ignore unknown future data changes.
V545_STATIC_BASE = "2013f3a999fccfea7118329dc207c7e2ecbbdb6e"
V545_STATIC_CANDIDATE = "6a08b168c8823dfdb53e452517711d17a85d7d8e"
V545_STATIC_BLOBS = {
    "adaptive_collection_stats.json": "85f3963c317b267fba210ee37ba94aa458f3129c",
    "auto_update_issues.json": "13d0f1bc18ab43f57d19717c5e361a5538d80e7e",
    "auto_update_report.json": "81f7943c43a6c2eed7331eb8804f19acbaddd7cc",
    "exchange_rates.json": "0c110acc8f1052a700646e15823d9a930eeb9583",
    "graded_photo_candidates.json": "1c9e0ddf58fc6a65dd995dc02511a20a6544ffe4",
    "grading_company_updates.json": "49140c8e4d704cc716232ec64d6dcc997b1f3bac",
    "market_prices.json": "698a57d9641c308f4292f50f9fca56bac7efef76",
    "market_watch.json": "5ca51efb9df5ef3227e5309c84426dc8ba9105b2",
    "promo_events.json": "032581b72299854bd21683303ef9ef44c51daa9a",
    "purchase_signals.json": "d88f39850ecba864bf86d8b710f19e57b81c0c99",
    "purchase_sources.json": "2beeb1db32a6836cb731c8f29a0bc33ed03866a4",
    "releases.json": "02357816eea15b0d69cd05c03c8572638c093297",
    "social_event_candidates.json": "00ce8c41398bde6588171b1822e89a6c32fb8996",
    "social_stock_signals.json": "af451cc547175a74ba18eb520bb2d34a48ded94f",
    "source_collection_stats.json": "60e2b601487314cf7c6e5f137b1553310f817798",
    "supplementary_candidates.json": "00a6fc96a9dcaa3e2348e49ebdb5c4b9128f3a45",
    "tcg_live_data.json": "cd1afc15ebc3ea98ff00f9f89cc75a88831d1636",
}


@lru_cache(maxsize=1)
def _v545_verified_static_snapshot_paths() -> frozenset[str]:
    """Return the entire exact reviewed set, or nothing if *any* blob differs."""
    candidate_present = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V545_STATIC_CANDIDATE, "HEAD"],
        check=False, capture_output=True,
    ).returncode == 0
    if not candidate_present:
        return frozenset()
    paths = tuple(sorted(V545_STATIC_BLOBS))
    if any(not (ROOT / p).is_file() or (ROOT / p).is_symlink() for p in paths):
        return frozenset()
    result = subprocess.run(
        ["git", "hash-object", "--", *paths],
        cwd=ROOT, check=False, text=True, capture_output=True,
    )
    if result.returncode != 0 or result.stdout.splitlines() != [V545_STATIC_BLOBS[p] for p in paths]:
        return frozenset()
    return frozenset(paths)



def verified_v545_korean_pokemon_movie_source(value: object) -> bool:
    """Retain V356's official original, or the exact pinned official V545 replacement."""
    if value == "https://pokemoncard.co.kr/main":
        return True
    return (value == "https://pokemonkorea.co.kr/news/2"
            and "promo_events.json" in _v545_verified_static_snapshot_paths())


def preserve_reviewed_v545_static_scope(
    visible: list[str], source: str, head: str = "HEAD", *, prior_head: str | None = None
) -> list[str]:
    """Remove reviewed V545-only diffs, preserving the original historical view."""
    if head != "HEAD" or not visible:
        return visible
    approved = _v545_verified_static_snapshot_paths()
    candidates = sorted(set(visible) & approved)
    if not candidates:
        return visible
    # Some immutable generations stop at a pinned *historical* head, rather
    # than the immediately preceding main. Never remove a path already visible
    # in that original view, even if later data happened to revert the bytes.
    comparison_head = prior_head if prior_head and prior_head != "HEAD" else V545_STATIC_BASE
    prior = set(subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{comparison_head}", "--", *candidates],
        cwd=ROOT, text=True,
    ).splitlines())
    # V376's historical checkpoint temporarily re-touched the grading-company
    # report, whereas the final pre-V545 main has the exact original blob.
    # Attribute ONLY the newer pinned data refresh to V545 in that case.
    graded = "grading_company_updates.json"
    if graded in candidates:
        pre_refresh = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{V545_STATIC_BASE}", "--", graded],
            cwd=ROOT, text=True,
        ).splitlines()
        if not pre_refresh:
            prior.discard(graded)
    return [path for path in visible if path not in approved or path in prior]



def _watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    # Historical generations must be evaluated against the last repository state
    # they already delegated through (V407), not against V408 re-touches of the
    # same runtime files. V407 itself still sees current HEAD so it can delegate
    # the exact V408 watched set, and V408 sees HEAD to prove nothing later is
    # uncovered.
    effective_head = head
    if (
        head == "HEAD"
        and V408_CONTRACT_PATH.is_file()
        and source not in {V407_CANDIDATE, V408_CANDIDATE, V409_CANDIDATE, V410_CANDIDATE, V411_CANDIDATE, V412_CANDIDATE, V413_CANDIDATE, V414_CANDIDATE, V415_CANDIDATE, V416_CANDIDATE, V419_CANDIDATE, V420_CANDIDATE, V421_CANDIDATE, V422_CANDIDATE, V423_CANDIDATE, V424_CANDIDATE, V425_CANDIDATE, V426_CANDIDATE, V427_CANDIDATE, V428_CANDIDATE, V431_CANDIDATE, V432_CANDIDATE, V434_CANDIDATE, V435_CANDIDATE, V436_CANDIDATE, V437_CANDIDATE, V439_CANDIDATE, V440_CANDIDATE, V469_CANDIDATE, V470_CANDIDATE, V471_CANDIDATE, V477_CANDIDATE, V478_CANDIDATE, V479_CANDIDATE, V480_CANDIDATE, V482_CANDIDATE, V483_CANDIDATE, V485_CANDIDATE}
    ):
        effective_head = V407_MERGE_SHA
    # Preserve the last reviewed historical snapshot before V485 re-touched
    # these same UI paths. Only V485 itself evaluates its source-to-current HEAD.
    if head == "HEAD":
        historical_boundary = {
            # V485 serves its catalogue from the same SW/server paths touched
            # after V469. Keep V469's immutable proof at its reviewed V478
            # successor; V485 separately proves its own post-candidate state.
            V469_CANDIDATE: V478_CANDIDATE,
            V470_CANDIDATE: V482_CANDIDATE,
            V471_CANDIDATE: V482_CANDIDATE,
            V478_CANDIDATE: V479_CANDIDATE,
            # Existing V480 watched market files changed again after reviewed V482.
            V480_CANDIDATE: V482_CANDIDATE,
            # Preserve the two independently CI-reviewed branch tips. The
            # integration tests separately check the composite runtime.
            V483_CANDIDATE: "f4a909380c337c0a42218e30f93e76839928eece",
            V485_CANDIDATE: "b1e3c61e496495c826695bb47cb835cd37ca74b5",
        }.get(source)
        if historical_boundary:
            effective_head = historical_boundary
    # V412 touches several paths that were also changed by older immediate
    # successors. Historical generations V407-V410 must keep validating the
    # exact next reviewed generation rather than seeing the later V412 re-touch.
    if head == "HEAD" and V412_CONTRACT_PATH.is_file():
        immediate_successor_head = {
            V407_CANDIDATE: V408_MERGE_SHA,
            V408_CANDIDATE: V409_MERGE_SHA,
            V409_CANDIDATE: V410_MERGE_SHA,
            V410_CANDIDATE: V411_MERGE_SHA,
            V411_CANDIDATE: V412_CANDIDATE,
            V412_CANDIDATE: V413_CANDIDATE,
            V413_CANDIDATE: V414_CANDIDATE,
            V414_CANDIDATE: V415_CANDIDATE,
            V415_CANDIDATE: V416_CANDIDATE,
            V416_CANDIDATE: V419_CANDIDATE,
            V419_CANDIDATE: V420_CANDIDATE,
            V420_CANDIDATE: V421_CANDIDATE,
            V421_CANDIDATE: V422_CANDIDATE,
            V422_CANDIDATE: V423_CANDIDATE,
            V423_CANDIDATE: V424_CANDIDATE,
            V424_CANDIDATE: V425_CANDIDATE,
            V425_CANDIDATE: V426_CANDIDATE,
        }.get(source)
        if immediate_successor_head:
            effective_head = immediate_successor_head
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{effective_head}"], text=True
    ).splitlines()
    visible = sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )
    # V405 is an explicit scheduler-only successor. Historical generations keep
    # validating their original immediate-successor runtime set, while V404
    # remains responsible for delegating the new scheduler change to V405.
    if head == "HEAD" and source not in {V404_CANDIDATE, V405_CANDIDATE} and V405_CONTRACT_PATH.is_file():
        visible = [path for path in visible if path not in V405_WATCHED]
    # The same dashboard path was changed in V404 and then again in V407.
    # For V403-and-earlier sources it must remain visible as the V404 change.
    # For V404/V405 sources, remove only the later V407 re-touch so those
    # immutable generations can validate V405/V406 exactly. V406 itself must
    # see the dashboard and delegate it to V407.
    if (
        head == "HEAD"
        and source in {V404_CANDIDATE, V405_CANDIDATE}
        and V407_CONTRACT_PATH.is_file()
    ):
        visible = [path for path in visible if path not in V407_LEGACY_VISIBLE_WATCHED]
    # V488 only re-touches a V383-era workflow. Keep the earlier generation's
    # immediately reviewed workflow snapshot while validating V488 separately.
    # Any later/unreviewed workflow content or changes already present before
    # V488 still remain visible to historical tests; this is not a broad bypass.
    if head == "HEAD" and V488_PACKAGE_PATH in visible:
        candidate_merged = subprocess.run(
            ["git", "merge-base", "--is-ancestor", V488_PACKAGE_CANDIDATE, "HEAD"],
            check=False, capture_output=True,
        ).returncode == 0
        current_package = ROOT / V488_PACKAGE_PATH
        pinned_bytes = (current_package.is_file()
                        and hashlib.sha256(current_package.read_bytes()).hexdigest() == V488_PACKAGE_SHA256)
        if candidate_merged and pinned_bytes:
            older_changes = subprocess.check_output(
                ["git", "diff", "--name-only", f"{source}..{V488_PACKAGE_BASE}", "--", V488_PACKAGE_PATH],
                text=True,
            ).splitlines()
            if not older_changes:
                visible.remove(V488_PACKAGE_PATH)
    # A later schema-validated recovery legitimately re-touches V432's collector.
    # Do not attribute those bytes to V432; only the pinned, ancestor-reviewed
    # V521 successor can be hidden from historical generations.
    if head == "HEAD" and V521_RESTORE_PATH in visible:
        candidate_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", V521_RESTORE_CANDIDATE, "HEAD"],
            check=False, capture_output=True,
        ).returncode == 0
        current = ROOT / V521_RESTORE_PATH
        pinned = (current.is_file() and
                  hashlib.sha256(current.read_bytes()).hexdigest() == V521_RESTORE_SHA256)
        if candidate_ancestor and pinned:
            pre_review_changes = subprocess.check_output(
                ["git", "diff", "--name-only", f"{source}..{V521_RESTORE_BASE}",
                 "--", V521_RESTORE_PATH], text=True,
            ).splitlines()
            if not pre_review_changes:
                visible.remove(V521_RESTORE_PATH)
    return preserve_reviewed_v534_box_scope(
        preserve_reviewed_v525_grade_scope(visible, source, head, prior_head=effective_head),
        source, head,
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
    post_merge_sha: str | None = None,
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
    candidate_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, "HEAD"],
        check=False,
    ).returncode == 0
    if not candidate_ancestor:
        # A squash merge does not retain the functional candidate as a commit
        # ancestor. Permit that only for generations that explicitly allow
        # post-merge coverage and provide the exact reviewed merge SHA.
        testcase.assertIs(candidate["post_merge_coverage_allowed"], True)
        testcase.assertTrue(post_merge_sha, f"{version} candidate is not an ancestor and has no reviewed merge SHA")
        subprocess.run(["git", "merge-base", "--is-ancestor", post_merge_sha, "HEAD"], check=True)
    return contract, candidate


def assert_v432_successor(testcase):
    """Validate promoted-TCG multisource coverage orchestration."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V432_CONTRACT_PATH,
        prior_contract=V432_PRIOR_CONTRACT, prior_delta=V432_PRIOR_DELTA,
        verification_test=V432_TEST, base=V432_BASE,
        candidate_sha=V432_CANDIDATE, watched=V432_WATCHED, version="V432",
    )
    after432 = _watched_paths(contract, V432_CANDIDATE)
    testcase.assertTrue(set(after432).issubset(set(V434_WATCHED + V439_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED)), "V432 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "promoted_tcg_multisource_v432.py").is_file())
    testcase.assertTrue((ROOT / "test_promoted_tcg_multisource_v432.py").is_file())
    if after432:
        return assert_v434_successor(testcase)
    return contract, candidate


def assert_v434_successor(testcase):
    """Validate exact variant pricing/history/scan correction/grading economics runtime packaging."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V434_CONTRACT_PATH,
        prior_contract=V434_PRIOR_CONTRACT, prior_delta=V434_PRIOR_DELTA,
        verification_test=V434_TEST, base=V434_BASE,
        candidate_sha=V434_CANDIDATE, watched=V434_WATCHED, version="V434",
    )
    after434 = _watched_paths(contract, V434_CANDIDATE)
    testcase.assertTrue(set(after434).issubset(set(V435_WATCHED)), "V434 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "market_price_context_v433.py").is_file())
    testcase.assertTrue((ROOT / "test_market_price_context_v433.py").is_file())
    if after434:
        return assert_v435_successor(testcase)
    return contract, candidate


def assert_v435_successor(testcase):
    """Validate bounded multi-channel health/fallback/lineage routing."""
    contract, candidate = _validate_generation(testcase, contract_path=V435_CONTRACT_PATH, prior_contract=V435_PRIOR_CONTRACT, prior_delta=V435_PRIOR_DELTA, verification_test=V435_TEST, base=V435_BASE, candidate_sha=V435_CANDIDATE, watched=V435_WATCHED, version="V435")
    after435 = _watched_paths(contract, V435_CANDIDATE)
    testcase.assertTrue(set(after435).issubset(set(V436_WATCHED)), "V435 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "tcg_channel_reach_v435.py").is_file());testcase.assertTrue((ROOT / "test_tcg_channel_reach_v435.py").is_file())
    if after435:
        return assert_v436_successor(testcase)
    return contract, candidate


def assert_v436_successor(testcase):
    """Validate bounded market-priority and stale-evidence reverification council."""
    contract, candidate = _validate_generation(testcase, contract_path=V436_CONTRACT_PATH, prior_contract=V436_PRIOR_CONTRACT, prior_delta=V436_PRIOR_DELTA, verification_test=V436_TEST, base=V436_BASE, candidate_sha=V436_CANDIDATE, watched=V436_WATCHED, version="V436")
    after436 = _watched_paths(contract, V436_CANDIDATE)
    testcase.assertTrue(set(after436).issubset(set(V437_WATCHED)), "V436 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "tcg_market_council_v436.py").is_file());testcase.assertTrue((ROOT / "test_tcg_market_council_v436.py").is_file())
    if after436:
        return assert_v437_successor(testcase)
    return contract, candidate


def assert_v469_successor(testcase):
    """Validate exact registry-driven expanded-TCG tablet UI/runtime delivery and V478 data-surface successor."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V469_CONTRACT_PATH,
        prior_contract=V469_PRIOR_CONTRACT, prior_delta=V469_PRIOR_DELTA,
        verification_test=V469_TEST, base=V469_BASE,
        candidate_sha=V469_CANDIDATE, watched=V469_WATCHED, version="V469",
    )
    after469 = _watched_paths(contract, V469_CANDIDATE)
    testcase.assertTrue(set(after469).issubset(set(V478_WATCHED)), "V469 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "tcg_registry_ui_v469.js").is_file())
    testcase.assertTrue((ROOT / "tcg_registry_ui_v469.css").is_file())
    testcase.assertTrue((ROOT / "test_tcg_registry_ui_v469.py").is_file())
    if after469 and V478_CONTRACT_PATH.is_file():
        return assert_v478_successor(testcase)
    if V470_CONTRACT_PATH.is_file():
        return assert_v470_successor(testcase)
    testcase.assertEqual([], after469, "V469 successor requires V478 coverage")
    return contract, candidate


def assert_v470_successor(testcase):
    """Validate compact category-first tablet navigation and delegate V471 initial collapse."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V470_CONTRACT_PATH,
        prior_contract=V470_PRIOR_CONTRACT, prior_delta=V470_PRIOR_DELTA,
        verification_test=V470_TEST, base=V470_BASE,
        candidate_sha=V470_CANDIDATE, watched=V470_WATCHED, version="V470",
    )
    after470 = _watched_paths(contract, V470_CANDIDATE)
    testcase.assertTrue(set(after470).issubset(set(V471_WATCHED)), "V470 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "feature_category_nav.js").is_file())
    testcase.assertTrue((ROOT / "feature_category_nav.css").is_file())
    testcase.assertTrue((ROOT / "test_tablet_category_focus_v430.py").is_file())
    if after470 and V471_CONTRACT_PATH.is_file():
        return assert_v471_successor(testcase)
    testcase.assertEqual([], after470, "V470 successor requires V471 coverage")
    return contract, candidate


def assert_v471_successor(testcase):
    """Validate initial category-only app state and delegate later local-only runtime cleanup."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V471_CONTRACT_PATH,
        prior_contract=V471_PRIOR_CONTRACT, prior_delta=V471_PRIOR_DELTA,
        verification_test=V471_TEST, base=V471_BASE,
        candidate_sha=V471_CANDIDATE, watched=V471_WATCHED, version="V471",
    )
    testcase.assertEqual([], _watched_paths(contract, V471_CANDIDATE), "V471 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "feature_category_nav.js").is_file())
    testcase.assertTrue((ROOT / "test_tablet_category_focus_v430.py").is_file())
    if V477_CONTRACT_PATH.is_file():
        return assert_v477_successor(testcase)
    return contract, candidate


def assert_v477_successor(testcase):
    """Validate bounded local-only cleanup of legacy Drive auto-scheduling and delegate V478."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V477_CONTRACT_PATH,
        prior_contract=V477_PRIOR_CONTRACT, prior_delta=V477_PRIOR_DELTA,
        verification_test=V477_TEST, base=V477_BASE,
        candidate_sha=V477_CANDIDATE, watched=V477_WATCHED, version="V477",
    )
    testcase.assertEqual([], _watched_paths(contract, V477_CANDIDATE), "V477 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "test_main_tablet_only_learning_v468.py").is_file())
    if V478_CONTRACT_PATH.is_file():
        return assert_v478_successor(testcase)
    return contract, candidate


def assert_v478_successor(testcase):
    """Validate registry-driven expanded TCG data surfaces and delegate the V479 tablet UI refinement."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V478_CONTRACT_PATH,
        prior_contract=V478_PRIOR_CONTRACT, prior_delta=V478_PRIOR_DELTA,
        verification_test=V478_TEST, base=V478_BASE,
        candidate_sha=V478_CANDIDATE, watched=V478_WATCHED, version="V478",
    )
    after478 = _watched_paths(contract, V478_CANDIDATE)
    testcase.assertTrue(set(after478).issubset(set(V479_WATCHED)), "V478 successor has uncovered watched changes")
    for path in (
        "update_releases.py",
        "update_promo_events.py",
        "box_hit_market_discovery.py",
        "market_catalog_expander.js",
        "box_knowledge_stats.js",
        "index.html",
    ):
        testcase.assertTrue((ROOT / path).is_file(), path)
    if after478 and V479_CONTRACT_PATH.is_file():
        return assert_v479_successor(testcase)
    testcase.assertEqual([], after478, "V478 successor requires V479 coverage")
    return contract, candidate


def assert_v479_successor(testcase):
    """Validate the game-first BOX Knowledge and selected-game BOX/HIT tablet experience."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V479_CONTRACT_PATH,
        prior_contract=V479_PRIOR_CONTRACT, prior_delta=V479_PRIOR_DELTA,
        verification_test=V479_TEST, base=V479_BASE,
        candidate_sha=V479_CANDIDATE, watched=V479_WATCHED, version="V479",
    )
    after479 = _watched_paths(contract, V479_CANDIDATE)
    testcase.assertEqual([], after479, "V479 own watched scope has uncovered changes")
    testcase.assertTrue((ROOT / "box_knowledge_stats.js").is_file())
    testcase.assertTrue((ROOT / "box_knowledge_stats.css").is_file())
    testcase.assertTrue((ROOT / "test_hot_box_hit_runtime_v252.py").is_file())
    if V480_CONTRACT_PATH.is_file():
        return assert_v480_successor(testcase)
    return contract, candidate


def assert_v480_successor(testcase):
    """Validate V480 pricing and delegate reviewed V482 freshness/variant/export changes."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V480_CONTRACT_PATH,
        prior_contract=V480_PRIOR_CONTRACT, prior_delta=V480_PRIOR_DELTA,
        verification_test=V480_TEST, base=V480_BASE,
        candidate_sha=V480_CANDIDATE, watched=V480_WATCHED, version="V480",
    )
    after480 = _watched_paths(contract, V480_CANDIDATE)
    testcase.assertTrue(set(after480).issubset(set(V482_WATCHED)), "V480 successor has uncovered watched changes")
    for path in (
        "multi_market_price_collector.py",
        "multi_market_prices.js",
        "multi_market_prices.css",
        "ui_app_shell_v272.js",
        "ui_app_shell_v272.css",
        "test_multi_market_price_collector.py",
        "test_ui_app_shell_v272.py",
    ):
        testcase.assertTrue((ROOT / path).is_file(), path)
    if after480 and V482_CONTRACT_PATH.is_file():
        return assert_v482_successor(testcase)
    testcase.assertEqual([], after480, "V480 successor requires V482 coverage")
    return contract, candidate


def assert_v482_successor(testcase):
    """Validate price freshness, explicit print-variant resolution, and local evidence export."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V482_CONTRACT_PATH,
        prior_contract=V482_PRIOR_CONTRACT, prior_delta=V482_PRIOR_DELTA,
        verification_test=V482_TEST, base=V482_BASE,
        candidate_sha=V482_CANDIDATE, watched=V482_WATCHED, version="V482",
    )
    after482 = _watched_paths(contract, V482_CANDIDATE)
    testcase.assertTrue(set(after482).issubset(set(V483_WATCHED)), "V482 successor has uncovered watched changes")
    for path in (
        "multi_market_price_collector.py",
        "multi_market_prices.js",
        "multi_market_prices.css",
        "test_multi_market_price_collector.py",
        "test_ui_app_shell_v272.py",
        "TCG_EXTERNAL_APP_REVIEW_V482.md",
    ):
        testcase.assertTrue((ROOT / path).is_file(), path)
    for skill in ("tcg-market-freshness", "tcg-card-variant-resolution", "tcg-local-evidence-export"):
        testcase.assertTrue((ROOT / ".agents/skills" / skill / "SKILL.md").is_file(), skill)
        testcase.assertTrue((ROOT / ".codex/skills" / skill / "SKILL.md").is_file(), skill)
    if after482:
        testcase.assertTrue(V483_CONTRACT_PATH.is_file(), "V482 requires exact V483 market successor")
        assert_v483_successor(testcase)
    if V485_CONTRACT_PATH.is_file():
        return assert_v485_successor(testcase)
    testcase.assertEqual([], after482, "V482 market changes have no reviewed successor")
    return contract, candidate


def assert_v483_successor(testcase):
    """Validate the reviewed V483 source-to-tip seller-pricing correction."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V483_CONTRACT_PATH,
        prior_contract=V483_PRIOR_CONTRACT, prior_delta=V483_PRIOR_DELTA,
        verification_test=V483_TEST, base=V483_BASE,
        candidate_sha=V483_CANDIDATE, watched=V483_WATCHED, version="V483",
    )
    after483 = _watched_paths(contract, V483_CANDIDATE)
    testcase.assertTrue(
        set(after483).issubset({"multi_market_price_collector.py"}),
        "V483 subsequent reviewed correction must not silently widen runtime changes",
    )
    for path in (
        "multi_market_price_collector.py", "multi_market_prices.js",
        "multi_market_prices.css", "tcg_updater.py",
        "market_ai_auto_tracker.py", "apply_multi_market_prices_patch.py",
        "ui_app_shell_v272.js", "index.html",
        "TCG_EXTERNAL_APP_REVIEW_V483.md",
    ):
        testcase.assertTrue((ROOT / path).is_file(), path)
    for skill in ("tcg-condition-language-pricing", "tcg-seller-provenance", "tcg-local-price-history"):
        testcase.assertTrue((ROOT / ".agents/skills" / skill / "SKILL.md").is_file(), skill)
        testcase.assertTrue((ROOT / ".codex/skills" / skill / "SKILL.md").is_file(), skill)
    return contract, candidate


def assert_v485_successor(testcase):
    """Validate immutable V485 market home candidate and absence of later unverified UI changes."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V485_CONTRACT_PATH,
        prior_contract=V485_PRIOR_CONTRACT, prior_delta=V485_PRIOR_DELTA,
        verification_test=V485_TEST, base=V485_BASE,
        candidate_sha=V485_CANDIDATE, watched=V485_WATCHED, version="V485",
    )
    testcase.assertEqual([], _watched_paths(contract, V485_CANDIDATE), "V485 has uncovered watched changes")
    testcase.assertTrue((ROOT / "test_tcg_market_home_v485.py").is_file())
    for filename in ("feature_category_nav.js", "feature_category_nav.css", "index.html"):
        testcase.assertTrue((ROOT / filename).is_file())
    return contract, candidate

def assert_v440_successor(testcase):
    """Validate tablet-only verified-learning entrypoints and delegate reviewed later runtime changes."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V440_CONTRACT_PATH,
        prior_contract=V440_PRIOR_CONTRACT, prior_delta=V440_PRIOR_DELTA,
        verification_test=V440_TEST, base=V440_BASE,
        candidate_sha=V440_CANDIDATE, watched=V440_WATCHED, version="V440",
    )
    after440 = _watched_paths(contract, V440_CANDIDATE)
    testcase.assertTrue(set(after440).issubset(set(V477_WATCHED)), "V440 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "test_main_tablet_only_learning_v468.py").is_file())
    if V469_CONTRACT_PATH.is_file():
        return assert_v469_successor(testcase)
    if after440 and V477_CONTRACT_PATH.is_file():
        return assert_v477_successor(testcase)
    testcase.assertEqual([], after440, "V440 successor requires V477 coverage")
    return contract, candidate


def assert_v439_successor(testcase):
    """Validate exact V429 review hardening and delegate later tablet-only learning."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V439_CONTRACT_PATH,
        prior_contract=V439_PRIOR_CONTRACT, prior_delta=V439_PRIOR_DELTA,
        verification_test=V439_TEST, base=V439_BASE,
        candidate_sha=V439_CANDIDATE, watched=V439_WATCHED, version="V439",
    )
    testcase.assertEqual([], _watched_paths(contract, V439_CANDIDATE), "V439 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "test_tablet_registry_market_lens_v429.py").is_file())
    if V440_CONTRACT_PATH.is_file():
        return assert_v440_successor(testcase)
    return contract, candidate


def assert_v437_successor(testcase):
    """Validate bounded new-TCG discovery inbox and delegate later reviewed runtime changes."""
    contract, candidate = _validate_generation(testcase, contract_path=V437_CONTRACT_PATH, prior_contract=V437_PRIOR_CONTRACT, prior_delta=V437_PRIOR_DELTA, verification_test=V437_TEST, base=V437_BASE, candidate_sha=V437_CANDIDATE, watched=V437_WATCHED, version="V437")
    after437 = _watched_paths(contract, V437_CANDIDATE)
    testcase.assertTrue(set(after437).issubset(set(V439_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED)), "V437 successor has uncovered watched changes")
    testcase.assertTrue((ROOT / "tcg_discovery_inbox_v437.py").is_file());testcase.assertTrue((ROOT / "test_tcg_discovery_inbox_v437.py").is_file())
    return assert_v439_successor(testcase)


def assert_v431_successor(testcase):
    """Validate current-mainline UI bundle plus fresh-market evidence gating."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V431_CONTRACT_PATH,
        prior_contract=V431_PRIOR_CONTRACT,
        prior_delta=V431_PRIOR_DELTA,
        verification_test=V431_TEST,
        base=V431_BASE,
        candidate_sha=V431_CANDIDATE,
        watched=V431_WATCHED,
        version="V431",
    )
    after431 = _watched_paths(contract, V431_CANDIDATE)
    testcase.assertTrue(set(after431).issubset(set(V432_WATCHED + V439_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED)))
    if after431:
        return assert_v432_successor(testcase)
    testcase.assertTrue((ROOT / V429_TEST).is_file())
    testcase.assertTrue((ROOT / V430_TEST).is_file())
    return contract, candidate


def assert_v428_successor(testcase):
    """Validate V428 recording-derived tablet readability repair."""
    contract, candidate = _validate_generation(
        testcase, contract_path=V428_CONTRACT_PATH, prior_contract=V428_PRIOR_CONTRACT,
        prior_delta=V428_PRIOR_DELTA, verification_test=V428_TEST, base=V428_BASE,
        candidate_sha=V428_CANDIDATE, watched=V428_WATCHED, version="V428",
    )
    after428 = _watched_paths(contract, V428_CANDIDATE)
    if not after428:
        return contract, candidate
    testcase.assertTrue(set(after428).issubset(set(V431_WATCHED + V432_WATCHED + V439_WATCHED + V440_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED)))
    testcase.assertTrue((ROOT / V429_TEST).is_file())
    testcase.assertTrue((ROOT / V430_TEST).is_file())
    return assert_v431_successor(testcase)

def assert_v427_successor(testcase):
    """Validate V427 evidence-gated WIXOSS WATCH expansion."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V427_CONTRACT_PATH,
        prior_contract=V427_PRIOR_CONTRACT,
        prior_delta=V427_PRIOR_DELTA,
        verification_test=V427_TEST,
        base=V427_BASE,
        candidate_sha=V427_CANDIDATE,
        watched=V427_WATCHED,
        version="V427",
    )
    after427 = _watched_paths(contract, V427_CANDIDATE)
    if not after427:
        return contract, candidate
    testcase.assertEqual(V428_WATCHED, [p for p in after427 if p in V428_WATCHED])
    testcase.assertTrue(set(after427).issubset(set(V431_WATCHED + V432_WATCHED + V439_WATCHED + V440_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED)))
    return assert_v428_successor(testcase)


def assert_v426_successor(testcase):
    """Validate V426 and delegate later verified registry expansion to V427."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V426_CONTRACT_PATH,
        prior_contract=V426_PRIOR_CONTRACT,
        prior_delta=V426_PRIOR_DELTA,
        verification_test=V426_TEST,
        base=V426_BASE,
        candidate_sha=V426_CANDIDATE,
        watched=V426_WATCHED,
        version="V426",
    )
    after426 = _watched_paths(contract, V426_CANDIDATE)
    if not after426:
        return contract, candidate
    testcase.assertEqual(V427_WATCHED, [p for p in after426 if p in V427_WATCHED])
    testcase.assertTrue(set(after426).issubset(set(V427_WATCHED + V431_WATCHED + V432_WATCHED + V439_WATCHED + V440_WATCHED + V440_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED)))
    return assert_v427_successor(testcase)


def assert_v425_successor(testcase):
    """Validate V425 and delegate V426 registry/market hardening when present."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V425_CONTRACT_PATH,
        prior_contract=V425_PRIOR_CONTRACT,
        prior_delta=V425_PRIOR_DELTA,
        verification_test=V425_TEST,
        base=V425_BASE,
        candidate_sha=V425_CANDIDATE,
        watched=V425_WATCHED,
        version="V425",
        post_merge_sha=V426_BASE,
    )
    after425 = _watched_paths(contract, V425_CANDIDATE)
    if not after425:
        return contract, candidate
    testcase.assertEqual(V426_PREDECESSOR_WATCHED, after425)
    return assert_v426_successor(testcase)


def assert_v424_successor(testcase):
    """Validate V424 and delegate market-opportunity/UI expansion to V425."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V424_CONTRACT_PATH,
        prior_contract=V424_PRIOR_CONTRACT,
        prior_delta=V424_PRIOR_DELTA,
        verification_test=V424_TEST,
        base=V424_BASE,
        candidate_sha=V424_CANDIDATE,
        watched=V424_WATCHED,
        version="V424",
        post_merge_sha=V425_BASE,
    )
    after424 = _watched_paths(contract, V424_CANDIDATE)
    if not after424:
        return contract, candidate
    testcase.assertEqual(V425_WATCHED, after424)
    return assert_v425_successor(testcase)


def assert_v423_successor(testcase):
    """Validate V423 and delegate later verified market-watch expansion to V424."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V423_CONTRACT_PATH,
        prior_contract=V423_PRIOR_CONTRACT,
        prior_delta=V423_PRIOR_DELTA,
        verification_test=V423_TEST,
        base=V423_BASE,
        candidate_sha=V423_CANDIDATE,
        watched=V423_WATCHED,
        version="V423",
        post_merge_sha=V424_BASE,
    )
    after423 = _watched_paths(contract, V423_CANDIDATE)
    if not after423:
        return contract, candidate
    testcase.assertEqual(V424_WATCHED, after423)
    return assert_v424_successor(testcase)


def assert_v422_successor(testcase):
    """Validate V422 and delegate verified activation/neural holdout hardening to V423."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V422_CONTRACT_PATH,
        prior_contract=V422_PRIOR_CONTRACT,
        prior_delta=V422_PRIOR_DELTA,
        verification_test=V422_TEST,
        base=V422_BASE,
        candidate_sha=V422_CANDIDATE,
        watched=V422_WATCHED,
        version="V422",
        post_merge_sha=V423_BASE,
    )
    after422 = _watched_paths(contract, V422_CANDIDATE)
    if not after422:
        return contract, candidate
    testcase.assertEqual(V423_WATCHED, after422)
    return assert_v423_successor(testcase)


def assert_v421_successor(testcase):
    """Validate V421 and delegate Rush of Ikorr WATCH coverage to V422."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V421_CONTRACT_PATH,
        prior_contract=V421_PRIOR_CONTRACT,
        prior_delta=V421_PRIOR_DELTA,
        verification_test=V421_TEST,
        base=V421_BASE,
        candidate_sha=V421_CANDIDATE,
        watched=V421_WATCHED,
        version="V421",
    )
    after421 = _watched_paths(contract, V421_CANDIDATE)
    if not after421:
        return contract, candidate
    testcase.assertEqual(V422_WATCHED, after421)
    return assert_v422_successor(testcase)


def assert_v420_successor(testcase):
    """Validate V420 and delegate verified activation observability to V421."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V420_CONTRACT_PATH,
        prior_contract=V420_PRIOR_CONTRACT,
        prior_delta=V420_PRIOR_DELTA,
        verification_test=V420_TEST,
        base=V420_BASE,
        candidate_sha=V420_CANDIDATE,
        watched=V420_WATCHED,
        version="V420",
    )
    after420 = _watched_paths(contract, V420_CANDIDATE)
    if not after420:
        return contract, candidate
    testcase.assertEqual(V421_WATCHED, after420)
    return assert_v421_successor(testcase)


def assert_v419_successor(testcase):
    """Validate V419 and delegate promoted market/purchase routing to V420."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V419_CONTRACT_PATH,
        prior_contract=V419_PRIOR_CONTRACT,
        prior_delta=V419_PRIOR_DELTA,
        verification_test=V419_TEST,
        base=V419_BASE,
        candidate_sha=V419_CANDIDATE,
        watched=V419_WATCHED,
        version="V419",
    )
    after419 = _watched_paths(contract, V419_CANDIDATE)
    if not after419:
        return contract, candidate
    testcase.assertEqual(V420_WATCHED, after419)
    return assert_v420_successor(testcase)


def assert_v416_successor(testcase):
    """Validate V416 and delegate later registry lifecycle changes to V419."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V416_CONTRACT_PATH,
        prior_contract=V416_PRIOR_CONTRACT,
        prior_delta=V416_PRIOR_DELTA,
        verification_test=V416_TEST,
        base=V416_BASE,
        candidate_sha=V416_CANDIDATE,
        watched=V416_WATCHED,
        version="V416",
    )
    after416 = _watched_paths(contract, V416_CANDIDATE)
    if not after416:
        return contract, candidate
    testcase.assertEqual(V419_WATCHED, after416)
    return assert_v419_successor(testcase)


def assert_v415_successor(testcase):
    """Validate V415 registry-driven purchase-surface successor."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V415_CONTRACT_PATH,
        prior_contract=V415_PRIOR_CONTRACT,
        prior_delta=V415_PRIOR_DELTA,
        verification_test=V415_TEST,
        base=V415_BASE,
        candidate_sha=V415_CANDIDATE,
        watched=V415_WATCHED,
        version="V415",
    )
    after415 = _watched_paths(contract, V415_CANDIDATE)
    if not after415:
        return contract, candidate
    testcase.assertEqual(V416_WATCHED, after415)
    return assert_v416_successor(testcase)


def assert_v414_successor(testcase):
    """Validate V414 and delegate registry purchase-surface hardening to V415."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V414_CONTRACT_PATH,
        prior_contract=V414_PRIOR_CONTRACT,
        prior_delta=V414_PRIOR_DELTA,
        verification_test=V414_TEST,
        base=V414_BASE,
        candidate_sha=V414_CANDIDATE,
        watched=V414_WATCHED,
        version="V414",
    )
    after414 = _watched_paths(contract, V414_CANDIDATE)
    if not after414:
        return contract, candidate
    testcase.assertEqual(V415_WATCHED, after414)
    return assert_v415_successor(testcase)


def assert_v413_successor(testcase):
    """Validate V413 and delegate autonomous unknown-TCG WATCH seeding to V414."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V413_CONTRACT_PATH,
        prior_contract=V413_PRIOR_CONTRACT,
        prior_delta=V413_PRIOR_DELTA,
        verification_test=V413_TEST,
        base=V413_BASE,
        candidate_sha=V413_CANDIDATE,
        watched=V413_WATCHED,
        version="V413",
    )
    after413 = _watched_paths(contract, V413_CANDIDATE)
    if not after413:
        return contract, candidate
    testcase.assertEqual(V414_WATCHED, after413)
    return assert_v414_successor(testcase)


def assert_v412_successor(testcase):
    """Validate V412 and delegate registry-first market expansion to V413."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V412_CONTRACT_PATH,
        prior_contract=V412_PRIOR_CONTRACT,
        prior_delta=V412_PRIOR_DELTA,
        verification_test=V412_TEST,
        base=V412_BASE,
        candidate_sha=V412_CANDIDATE,
        watched=V412_WATCHED,
        version="V412",
    )
    after412 = _watched_paths(contract, V412_CANDIDATE)
    if not after412:
        return contract, candidate
    testcase.assertEqual(V413_LEGACY_VISIBLE_WATCHED, after412)
    return assert_v413_successor(testcase)


def assert_v411_successor(testcase):
    """Validate V411 and delegate autonomous verified TCG discovery to V412."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V411_CONTRACT_PATH,
        prior_contract=V411_PRIOR_CONTRACT,
        prior_delta=V411_PRIOR_DELTA,
        verification_test=V411_TEST,
        base=V411_BASE,
        candidate_sha=V411_CANDIDATE,
        watched=V411_WATCHED,
        version="V411",
        post_merge_sha=V411_MERGE_SHA,
    )
    after411 = _watched_paths(contract, V411_CANDIDATE)
    if not after411:
        return contract, candidate
    testcase.assertEqual(V412_WATCHED, after411)
    return assert_v412_successor(testcase)


def assert_v410_successor(testcase):
    """Validate V410 and delegate stable market-context hysteresis to V411."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V410_CONTRACT_PATH,
        prior_contract=V410_PRIOR_CONTRACT,
        prior_delta=V410_PRIOR_DELTA,
        verification_test=V410_TEST,
        base=V410_BASE,
        candidate_sha=V410_CANDIDATE,
        watched=V410_WATCHED,
        version="V410",
        post_merge_sha=V410_MERGE_SHA,
    )
    after410 = _watched_paths(contract, V410_CANDIDATE)
    if not after410:
        return contract, candidate
    testcase.assertEqual(V411_WATCHED, after410)
    return assert_v411_successor(testcase)


def assert_v409_successor(testcase):
    """Validate V409 and delegate verified market-context UI policy to V410."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V409_CONTRACT_PATH,
        prior_contract=V409_PRIOR_CONTRACT,
        prior_delta=V409_PRIOR_DELTA,
        verification_test=V409_TEST,
        base=V409_BASE,
        candidate_sha=V409_CANDIDATE,
        watched=V409_WATCHED,
        version="V409",
        post_merge_sha=V409_MERGE_SHA,
    )
    after409 = _watched_paths(contract, V409_CANDIDATE)
    if not after409:
        return contract, candidate
    testcase.assertEqual(V410_WATCHED, after409)
    return assert_v410_successor(testcase)


def assert_v408_successor(testcase):
    """Validate V408 and delegate claim-window/top-k hardening to V409."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V408_CONTRACT_PATH,
        prior_contract=V408_PRIOR_CONTRACT,
        prior_delta=V408_PRIOR_DELTA,
        verification_test=V408_TEST,
        base=V408_BASE,
        candidate_sha=V408_CANDIDATE,
        watched=V408_WATCHED,
        version="V408",
        post_merge_sha=V408_MERGE_SHA,
    )
    after408 = _watched_paths(contract, V408_CANDIDATE)
    if not after408:
        return contract, candidate
    testcase.assertEqual(V409_WATCHED, after408)
    return assert_v409_successor(testcase)


def assert_v407_successor(testcase):
    """Validate V407 and delegate freshness-aware market-lens changes to V408."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V407_CONTRACT_PATH,
        prior_contract=V407_PRIOR_CONTRACT,
        prior_delta=V407_PRIOR_DELTA,
        verification_test=V407_TEST,
        base=V407_BASE,
        candidate_sha=V407_CANDIDATE,
        watched=V407_WATCHED,
        version="V407",
        post_merge_sha=V407_MERGE_SHA,
    )
    after407 = _watched_paths(contract, V407_CANDIDATE)
    if not after407:
        return contract, candidate
    testcase.assertEqual(V408_WATCHED, after407)
    return assert_v408_successor(testcase)


def assert_v406_successor(testcase):
    """Validate immutable V406 and delegate video-neural dock changes to V407."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V406_CONTRACT_PATH,
        prior_contract=V406_PRIOR_CONTRACT,
        prior_delta=V406_PRIOR_DELTA,
        verification_test=V406_TEST,
        base=V406_BASE,
        candidate_sha=V406_CANDIDATE,
        watched=V406_WATCHED,
        version="V406",
        post_merge_sha=V406_MERGE_SHA,
    )
    after406 = _watched_paths(contract, V406_CANDIDATE)
    if not after406:
        return contract, candidate
    testcase.assertEqual(V407_LEGACY_VISIBLE_WATCHED, after406)
    return assert_v407_successor(testcase)


def assert_v405_successor(testcase):
    """Validate immutable V405 and delegate atomic status correction to V406."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V405_CONTRACT_PATH,
        prior_contract=V405_PRIOR_CONTRACT,
        prior_delta=V405_PRIOR_DELTA,
        verification_test=V405_TEST,
        base=V405_BASE,
        candidate_sha=V405_CANDIDATE,
        watched=V405_WATCHED,
        version="V405",
    )
    after405 = _watched_paths(contract, V405_CANDIDATE)
    if not after405:
        return contract, candidate
    testcase.assertEqual(V406_WATCHED, after405)
    return assert_v406_successor(testcase)


def assert_v404_successor(testcase):
    """Validate immutable V404 and delegate scheduled autonomy to V405."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V404_CONTRACT_PATH,
        prior_contract=V404_PRIOR_CONTRACT,
        prior_delta=V404_PRIOR_DELTA,
        verification_test=V404_TEST,
        base=V404_BASE,
        candidate_sha=V404_CANDIDATE,
        watched=V404_WATCHED,
        version="V404",
    )
    after404 = _watched_paths(contract, V404_CANDIDATE)
    if not after404:
        return contract, candidate
    testcase.assertEqual(V405_WATCHED, after404)
    return assert_v405_successor(testcase)


def assert_v403_successor(testcase):
    """Validate immutable V403 and delegate second-pass video UX to V404."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V403_CONTRACT_PATH,
        prior_contract=V403_PRIOR_CONTRACT,
        prior_delta=V403_PRIOR_DELTA,
        verification_test=V403_TEST,
        base=V403_BASE,
        candidate_sha=V403_CANDIDATE,
        watched=V403_WATCHED,
        version="V403",
    )
    after403 = _watched_paths(contract, V403_CANDIDATE)
    if not after403:
        return contract, candidate
    testcase.assertEqual(V404_WATCHED, after403)
    return assert_v404_successor(testcase)


def assert_v402_successor(testcase):
    """Validate immutable V402 and delegate video-reference UI changes to V403."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V402_CONTRACT_PATH,
        prior_contract=V402_PRIOR_CONTRACT,
        prior_delta=V402_PRIOR_DELTA,
        verification_test=V402_TEST,
        base=V402_BASE,
        candidate_sha=V402_CANDIDATE,
        watched=V402_WATCHED,
        version="V402",
    )
    after402 = _watched_paths(contract, V402_CANDIDATE)
    if not after402:
        return contract, candidate
    testcase.assertEqual(V403_WATCHED, after402)
    return assert_v403_successor(testcase)


def assert_v401_successor(testcase):
    """Validate immutable V401 and delegate neural model governance to V402."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V401_CONTRACT_PATH,
        prior_contract=V401_PRIOR_CONTRACT,
        prior_delta=V401_PRIOR_DELTA,
        verification_test=V401_TEST,
        base=V401_BASE,
        candidate_sha=V401_CANDIDATE,
        watched=V401_WATCHED,
        version="V401",
    )
    after401 = _watched_paths(contract, V401_CANDIDATE)
    if not after401:
        return contract, candidate
    testcase.assertIn(after401, (V402_WATCHED, V403_AFTER_V401_VISIBLE_WATCHED))
    return assert_v402_successor(testcase)


def assert_v400_successor(testcase):
    """Validate immutable V400 and delegate the dedicated screen neural to V401."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V400_CONTRACT_PATH,
        prior_contract=V400_PRIOR_CONTRACT,
        prior_delta=V400_PRIOR_DELTA,
        verification_test=V400_TEST,
        base=V400_BASE,
        candidate_sha=V400_CANDIDATE,
        watched=V400_WATCHED,
        version="V400",
    )
    after400 = _watched_paths(contract, V400_CANDIDATE)
    if not after400:
        return contract, candidate
    testcase.assertIn(after400, (V401_LEGACY_VISIBLE_WATCHED, V403_AFTER_V400_VISIBLE_WATCHED))
    return assert_v401_successor(testcase)


def assert_v399_successor(testcase):
    """Validate immutable V399 and delegate neural policy-loop changes to V400."""
    contract, candidate = _validate_generation(
        testcase,
        contract_path=V399_CONTRACT_PATH,
        prior_contract=V399_PRIOR_CONTRACT,
        prior_delta=V399_PRIOR_DELTA,
        verification_test=V399_TEST,
        base=V399_BASE,
        candidate_sha=V399_CANDIDATE,
        watched=V399_WATCHED,
        version="V399",
    )
    after399 = _watched_paths(contract, V399_CANDIDATE)
    if not after399:
        return contract, candidate
    testcase.assertIn(after399, (V400_WATCHED, V401_LEGACY_VISIBLE_WATCHED, V403_AFTER_V400_VISIBLE_WATCHED))
    return assert_v400_successor(testcase)


def assert_v398_successor(testcase):
    """Validate immutable V398 and delegate full-screen changes to V399."""
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
    after398 = _watched_paths(contract, V398_CANDIDATE)
    if not after398:
        return contract, candidate
    testcase.assertIn(after398, (V399_WATCHED, V401_AFTER_V398_VISIBLE_WATCHED))
    return assert_v399_successor(testcase)


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
    testcase.assertIn(after397, (V398_WATCHED, V401_AFTER_V397_VISIBLE_WATCHED))
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
