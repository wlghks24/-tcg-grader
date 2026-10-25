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

# V562: the purchase-source collector probes identical exact URLs just once
# within one fresh collection cycle. Historical sync contracts remain immutable.
# Trust this one reviewed production change only while its exact SHA-256 is
# present and the candidate commit remains an ancestor of HEAD.
V562_PURCHASE_BASE = "c346752ff00faaaa70fd40b04cd225f746c6b825"
V562_PURCHASE_CANDIDATE = "a5674816058f23e2d92d8f781adaa4507606a079"
V562_PURCHASE_PATH = "update_purchase_sources.py"
V562_PURCHASE_SHA256 = "1c0d9540f95d7c73315e46a99c1a22a04e7dbbf8574a3887dd9544b353a6c387"

# V563: strictly reviewed one-try CGC transport resilience on the existing
# official source allowlist. This does not widen historical watched scopes:
# later edits, missing ancestry or any byte drift remain visible failures.
V563_CGC_BASE = "c58e21f3a275562432656075bbfbc8aae378a0e2"
V563_CGC_CANDIDATE = "fe36b5bdac06aacb4660d3419688da4ebaab98b0"
V563_CGC_PATH = "grading_company_watch_resilient.py"
V563_CGC_SHA256 = "e683371cdc973fcbf82de82fad8b273e253efb0b7bd38d031e7203bb71008ecf"


# V565: explicitly reviewed successor to the historical 17-file V545
# snapshot. Only this one official grading-report refresh is allowed, after
# proving the original V545 tree is still pinned and the pre-refresh main
# did not change that report. Every other historical byte remains fixed.
V565_GRADING_BASE = "bafee623ceb5e20db5d4e2617eea285aa034bc1b"
V565_GRADING_CANDIDATE = "ec7f551071c77484985e9c1af18b20ae20b36de6"
V565_GRADING_PATH = "grading_company_updates.json"
V565_GRADING_BLOB = "ded51b805ac5a248d4ed89fdb0dfd55f54c30251"
V565_GRADING_SHA256 = "330ba080db4cc2fec44f93fadd3ac2e47228891407bc6eaaa3da7ccaaf7eebae"

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



# V546: GitHub Actions PR-denial status cannot be a green publish result.
# The historic V369 workflow generation is preserved: remove only this exact
# later-reviewed workflow re-touch and never mask unreviewed follow-up changes.
V546_PUBLISH_BASE = "9ccdd7b6b8d86df7f9daaf975fec4d5e783b5d02"
V546_PUBLISH_CANDIDATE = "8259e6fb1462a4fb95e8a59d01e6952df136372f"
V546_PUBLISH_WORKFLOW = ".github/workflows/tcg-static-data-refresh.yml"
V546_PUBLISH_BLOB = "55426f844548c41a8fb4e032ecbec0575bf39791"


def preserve_reviewed_v546_publish_scope(visible: list[str], source: str, head: str = "HEAD") -> list[str]:
    """Acknowledge one reviewed post-V369 workflow patch, not a broad test bypass."""
    if head != "HEAD" or V546_PUBLISH_WORKFLOW not in visible:
        return visible
    approved = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V546_PUBLISH_CANDIDATE, "HEAD"],
        check=False, capture_output=True,
    ).returncode == 0
    current = ROOT / V546_PUBLISH_WORKFLOW
    if not approved or not current.is_file() or current.is_symlink():
        return visible
    blob = subprocess.run(
        ["git", "hash-object", "--", V546_PUBLISH_WORKFLOW],
        cwd=ROOT, text=True, check=False, capture_output=True,
    )
    if blob.returncode != 0 or blob.stdout.strip() != V546_PUBLISH_BLOB:
        return visible
    prior = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{V546_PUBLISH_BASE}",
         "--", V546_PUBLISH_WORKFLOW],
        cwd=ROOT, text=True,
    ).splitlines()
    # Earlier reviewed edits are still visible to their original generations.
    if prior:
        return visible
    return [p for p in visible if p != V546_PUBLISH_WORKFLOW]


# V634: attribute ONLY the exact reviewed post-V546 PR-permission diagnostics.
# Do not waive earlier historical sync changes or accept any later workflow edit.
V634_STATIC_BASE = "3afb759461b4ac0d3662dee645d7229dd10f3ae0"
V634_STATIC_CANDIDATE = "a632054ee89dd4af41cd7bc45fa6bbb0c5e3be66"
V634_STATIC_SHA256 = "1c7fe216c22376b58ab5528b83e8ca7b196f9b15ad810a87830cf78b8c48a1d1"
V634_STATIC_BASE_BLOB = "55426f844548c41a8fb4e032ecbec0575bf39791"


def preserve_reviewed_v634_static_scope(
    visible: list[str], source: str, head: str = "HEAD"
) -> list[str]:
    """Exclude only the pinned V634 descendant; keep all pre-V546 changes visible."""
    path = V546_PUBLISH_WORKFLOW
    if head != "HEAD" or path not in visible:
        return visible
    target = ROOT / path
    if not target.is_file() or target.is_symlink():
        return visible
    if hashlib.sha256(target.read_bytes()).hexdigest() != V634_STATIC_SHA256:
        return visible
    for commit in (V634_STATIC_BASE, V634_STATIC_CANDIDATE):
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=ROOT, check=False, capture_output=True,
        )
        if ancestry.returncode != 0:
            return visible
    base_blob = subprocess.run(
        ["git", "rev-parse", f"{V634_STATIC_BASE}:{path}"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if base_blob.returncode != 0 or base_blob.stdout.strip() != V634_STATIC_BASE_BLOB:
        return visible
    reviewed_change = subprocess.run(
        ["git", "diff", "--name-only",
         f"{V634_STATIC_BASE}..{V634_STATIC_CANDIDATE}", "--", path],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if reviewed_change.returncode != 0 or reviewed_change.stdout.splitlines() != [path]:
        return visible
    older_change = subprocess.run(
        ["git", "diff", "--name-only",
         f"{source}..{V546_PUBLISH_BASE}", "--", path],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if older_change.returncode != 0 or older_change.stdout.splitlines():
        return visible
    return [item for item in visible if item != path]


# V547: distinguish a queued grading-provider update from a delivered update.
V547_GRADING_BASE = "4a0df21f1f776136772937887579f60634d071bd"
V547_GRADING_CANDIDATE = "9244683107f263192df77d9ad01bc5c3ea130754"
V547_GRADING_WORKFLOW = ".github/workflows/grading-company-watch.yml"
V547_GRADING_BLOB = "a2772f9c9ea2c5303eddbf307378e7280b748563"


def preserve_reviewed_v547_grading_scope(visible: list[str], source: str, head: str = "HEAD") -> list[str]:
    """Hide only this immutable reviewed workflow descendant, never prior edits."""
    if head != "HEAD" or V547_GRADING_WORKFLOW not in visible:
        return visible
    approved = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V547_GRADING_CANDIDATE, "HEAD"],
        check=False, capture_output=True,
    ).returncode == 0
    current = ROOT / V547_GRADING_WORKFLOW
    if not approved or not current.is_file() or current.is_symlink():
        return visible
    blob = subprocess.run(
        ["git", "hash-object", "--", V547_GRADING_WORKFLOW],
        cwd=ROOT, text=True, check=False, capture_output=True,
    )
    if blob.returncode != 0 or blob.stdout.strip() != V547_GRADING_BLOB:
        return visible
    prior = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{V547_GRADING_BASE}",
         "--", V547_GRADING_WORKFLOW],
        cwd=ROOT, text=True,
    ).splitlines()
    return visible if prior else [p for p in visible if p != V547_GRADING_WORKFLOW]


def preserve_reviewed_v525_grade_scope(
    visible: list[str], source: str, head: str = "HEAD", *, prior_head: str | None = None
) -> list[str]:
    """Keep exact reviewed V525/V545/V620 successors separate from historic edits."""
    visible=preserve_reviewed_v661_scope(visible,source,head)
    visible=preserve_reviewed_v653_scope(visible,source,head)
    # Legacy V369-V384 local watchers call this public helper directly rather
    # than _watched_paths; keep both entrypoints under the SAME pinned V620 gate.
    visible = preserve_reviewed_v652_scope(visible, source, head)
    visible = preserve_reviewed_v647_ci_scope(visible, source, head, prior_head=prior_head)
    visible = preserve_reviewed_v645_feature_scope(visible, source, head, prior_head=prior_head)
    visible = preserve_reviewed_v644_learning_scope(visible, source, head, prior_head=prior_head)
    visible = preserve_reviewed_v642_ui_scope(visible, source, head, prior_head=prior_head)
    visible = preserve_reviewed_v641_autonomy_scope(visible, source, head)
    visible = preserve_reviewed_v620_ocr_scope(visible, source, head)
    visible = preserve_reviewed_v545_static_scope(visible, source, head, prior_head=prior_head)
    visible = preserve_reviewed_v546_publish_scope(visible, source, head)
    visible = preserve_reviewed_v634_static_scope(visible, source, head)
    visible = preserve_reviewed_v547_grading_scope(visible, source, head)
    # Direct V369-V384 callers bypass _watched_paths. Preserve their exact
    # verified historical scope via the same pinned V563 descendant guard.
    visible = preserve_reviewed_v563_cgc_scope(visible, source, head)
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
    """Verify the immutable V545 tree or one exact, reviewed V565 descendant.

    V545's 17 original blobs remain historical facts at its original commit.
    V565 may only replace grading_company_updates.json with the explicitly
    audited blob, on the exact descendant branch, with no intervening changes.
    Any missing ancestry, changed sibling, symlink or unreviewed later edit
    fails closed. Never accept arbitrary current JSON snapshots.
    """
    v545_present = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V545_STATIC_CANDIDATE, "HEAD"],
        cwd=ROOT, check=False, capture_output=True,
    ).returncode == 0
    if not v545_present:
        return frozenset()
    paths = tuple(sorted(V545_STATIC_BLOBS))
    if any(not (ROOT / p).is_file() or (ROOT / p).is_symlink() for p in paths):
        return frozenset()
    actual = subprocess.run(
        ["git", "hash-object", "--", *paths],
        cwd=ROOT, check=False, text=True, capture_output=True,
    )
    if actual.returncode != 0:
        return frozenset()
    original = [V545_STATIC_BLOBS[p] for p in paths]
    blobs = actual.stdout.splitlines()
    if blobs == original:
        return frozenset(paths)

    # Never reinterpret an arbitrary later data edit as the earlier V545
    # snapshot. A second immutable generation must match in every detail.
    reviewed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V565_GRADING_CANDIDATE, "HEAD"],
        cwd=ROOT, check=False, capture_output=True,
    ).returncode == 0
    expected = [
        V565_GRADING_BLOB if p == V565_GRADING_PATH else V545_STATIC_BLOBS[p]
        for p in paths
    ]
    # V732: accept only the exact CSS-title cleanup commit/blob.
    # Every other V545 source byte and the separately reviewed V565 grade
    # snapshot must remain pinned; arbitrary later edits still fail closed.
    if reviewed and blobs != expected:
        event_path = "social_event_candidates.json"
        event_base = "82f1220dc9137ef5a30f41ad5cbd9fb7e7335eae"
        # PR #732 was squash-merged, so require its exact landed commit.
        event_landing = "0a22abfe02cd8931227e63562d417795932063fd"
        event_blob = "813f6d79a375bdee80fcd1959eed0989a1202920"
        expected_event = [
            event_blob if p == event_path else (
                V565_GRADING_BLOB if p == V565_GRADING_PATH
                else V545_STATIC_BLOBS[p]
            )
            for p in paths
        ]
        if blobs != expected_event:
            return frozenset()
        approved = subprocess.run(
            ["git", "merge-base", "--is-ancestor", event_landing, "HEAD"],
            cwd=ROOT, check=False, capture_output=True,
        )
        baseline = subprocess.run(
            ["git", "diff", "--name-only",
             f"{V545_STATIC_CANDIDATE}..{event_base}", "--", event_path],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        delta = subprocess.run(
            ["git", "diff", "--name-only", f"{event_base}..{event_landing}"],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        if (approved.returncode != 0 or baseline.returncode != 0
                or baseline.stdout.strip() or delta.returncode != 0
                or delta.stdout.splitlines() != [
                    "integrity_manifest.json", event_path,
                    "sync_v376_successor_test_support.py"
                ]):
            return frozenset()
    if not reviewed:
        return frozenset()
    history = subprocess.run(
        ["git", "rev-parse", *(
            f"{V545_STATIC_CANDIDATE}:{p}" for p in paths
        )], cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if history.returncode != 0 or history.stdout.splitlines() != original:
        return frozenset()
    before = subprocess.run(
        ["git", "diff", "--name-only",
         f"{V545_STATIC_CANDIDATE}..{V565_GRADING_BASE}", "--", V565_GRADING_PATH],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if before.returncode != 0 or before.stdout.strip():
        return frozenset()
    candidate = subprocess.run(
        ["git", "diff", "--name-only",
         f"{V565_GRADING_BASE}..{V565_GRADING_CANDIDATE}"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if candidate.returncode != 0 or set(candidate.stdout.splitlines()) != {
        V565_GRADING_PATH, "integrity_manifest.json"
    }:
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



def preserve_reviewed_v562_purchase_scope(
    visible: list[str], source: str, head: str = "HEAD"
) -> list[str]:
    """Attribute only the precisely reviewed V562 collector bytes to V562.

    Older changes remain visible to their historical tests. Later edits, branch
    ancestry mismatches, or any SHA mismatch invalidate this narrow exception.
    """
    if head != "HEAD" or V562_PURCHASE_PATH not in visible:
        return visible
    approved = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V562_PURCHASE_CANDIDATE, "HEAD"],
        check=False, capture_output=True,
    ).returncode == 0
    target = ROOT / V562_PURCHASE_PATH
    pinned = (
        target.is_file() and not target.is_symlink()
        and hashlib.sha256(target.read_bytes()).hexdigest() == V562_PURCHASE_SHA256
    )
    if not (approved and pinned):
        return visible
    old_changes = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{V562_PURCHASE_BASE}",
         "--", V562_PURCHASE_PATH], text=True,
    ).splitlines()
    return visible if old_changes else [path for path in visible if path != V562_PURCHASE_PATH]


def preserve_reviewed_v563_cgc_scope(
    visible: list[str], source: str, head: str = "HEAD"
) -> list[str]:
    """Delegate only the exact reviewed CGC retry bytes; no broad path exemption."""
    if head != "HEAD" or V563_CGC_PATH not in visible:
        return visible
    approved = subprocess.run(
        ["git", "merge-base", "--is-ancestor", V563_CGC_CANDIDATE, "HEAD"],
        check=False, capture_output=True,
    ).returncode == 0
    target = ROOT / V563_CGC_PATH
    pinned = (
        target.is_file() and not target.is_symlink()
        and hashlib.sha256(target.read_bytes()).hexdigest() == V563_CGC_SHA256
    )
    if not (approved and pinned):
        return visible
    # Never suppress a change that predates the reviewed V563 baseline.
    old_changes = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{V563_CGC_BASE}",
         "--", V563_CGC_PATH], text=True,
    ).splitlines()
    return visible if old_changes else [path for path in visible if path != V563_CGC_PATH]



# V599: pin the exact post-V479 official product UI successor, preserving V540.
V599_OFFICIAL_BOX_BASE = "0980937372e3a3af7edacf250f5a34744c976d3c"
V599_OFFICIAL_BOX_CANDIDATE = "250d782bc64134918f8d469a30e7ac81d997f57a"
V599_OFFICIAL_BOX_BLOBS = {
    "box_knowledge_stats.css": "3f4e7af475d7a93068c67a7be25432bd26ac7d14",
    "box_knowledge_stats.js": "bc90743606e48b66ed5d8a4bde94ca8b5d3ed559",
}
V599_OFFICIAL_BOX_BASE_CSS_BLOB = "a2f4c6165146d86014b1bafea14bdd56f6917614"


def preserve_reviewed_v599_official_box_scope(
    visible: list[str], source: str, head: str = "HEAD"
) -> list[str]:
    """Recognize precisely audited V599 after immutable V479/V540, never other edits."""
    if head != "HEAD" or source != V479_CANDIDATE or not (
        set(visible) & set(V599_OFFICIAL_BOX_BLOBS)
    ):
        return visible
    for commit in (V599_OFFICIAL_BOX_BASE, V599_OFFICIAL_BOX_CANDIDATE, V540_BOX_CANDIDATE):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False, capture_output=True, cwd=ROOT,
        ).returncode != 0:
            return visible
    paths = sorted(V599_OFFICIAL_BOX_BLOBS)
    if any(not (ROOT / p).is_file() or (ROOT / p).is_symlink() for p in paths):
        return visible
    blobs = subprocess.run(
        ["git", "hash-object", "--", *paths],
        check=False, capture_output=True, text=True, cwd=ROOT,
    )
    if blobs.returncode != 0:
        return visible
    if blobs.stdout.splitlines() != [V599_OFFICIAL_BOX_BLOBS[p] for p in paths]:
        # Preserve V599's exact baseline, then validate the separate V645 review.
        # This never treats arbitrary later BOX edits as V599's historical bytes.
        import unittest
        try:
            assert_v645_feature_successor(unittest.TestCase())
            base=V645_FEATURE_PROOF['base_commit']
            for name,actual in zip(paths,blobs.stdout.splitlines()):
                baseline=subprocess.check_output(['git','rev-parse',base+':'+name],cwd=ROOT,text=True).strip()
                if baseline!=V599_OFFICIAL_BOX_BLOBS[name]:return visible
                if name not in V645_FEATURE_PROOF['reviewed_sha256'] and actual!=baseline:return visible
        except (AssertionError,OSError,ValueError,KeyError,subprocess.SubprocessError):
            return visible
    prior_js = subprocess.run(
        ["git", "show", f"{V599_OFFICIAL_BOX_BASE}:box_knowledge_stats.js"],
        check=False, capture_output=True, cwd=ROOT,
    )
    if prior_js.returncode != 0 or hashlib.sha256(prior_js.stdout).hexdigest() != V540_BOX_SHA256:
        return visible
    prior_css = subprocess.run(
        ["git", "rev-parse", f"{V599_OFFICIAL_BOX_BASE}:box_knowledge_stats.css"],
        check=False, capture_output=True, text=True, cwd=ROOT,
    )
    if prior_css.returncode != 0 or prior_css.stdout.strip() != V599_OFFICIAL_BOX_BASE_CSS_BLOB:
        return visible
    earlier_css = subprocess.run(
        ["git", "diff", "--quiet", f"{V479_CANDIDATE}..{V599_OFFICIAL_BOX_BASE}",
         "--", "box_knowledge_stats.css"],
        check=False, capture_output=True, cwd=ROOT,
    )
    if earlier_css.returncode != 0:
        return visible
    reviewed = subprocess.run(
        ["git", "diff", "--name-only",
         f"{V599_OFFICIAL_BOX_BASE}..{V599_OFFICIAL_BOX_CANDIDATE}",
         "--", *paths],
        check=False, capture_output=True, text=True, cwd=ROOT,
    )
    if reviewed.returncode != 0 or reviewed.stdout.splitlines() != paths:
        return visible
    return [p for p in visible if p not in V599_OFFICIAL_BOX_BLOBS]


# V620 OCR successor: historical tablet sync generations must continue to
# validate every change up to their recorded source. A new, independently
# reviewed OCR candidate may be attributed only after its exact commit/blob
# and immutable pre-candidate main OCR snapshot have been demonstrated.
V620_OCR_PATH = "card_identity_recognition.py"
V620_OCR_BASE = "0eb066b8b1cd9604320efea949404f5237cb0174"
V620_OCR_CANDIDATE = "d47f297031d746177f6aef8992a880ded1a70489"
V620_OCR_SHA256 = "da72a75a21e96ef71a21f5d61c8f731803dff293f4df68ec251641f76fe674c1"
V620_OCR_BASE_SHA256 = "c69fb139151c11fcdc366f845f24bc0cf2188511b0f7c558af40342f997ee8ac"


def preserve_reviewed_v620_ocr_scope(
    visible: list[str], source: str, head: str = "HEAD"
) -> list[str]:
    """Attribute only an exact reviewed OCR successor; keep all prior edits visible."""
    if head != "HEAD" or V620_OCR_PATH not in visible:
        return visible
    target = ROOT / V620_OCR_PATH
    if not target.is_file() or target.is_symlink():
        return visible
    if hashlib.sha256(target.read_bytes()).hexdigest() != V620_OCR_SHA256:
        return visible
    for commit in (V620_OCR_BASE, V620_OCR_CANDIDATE):
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=ROOT, check=False, capture_output=True,
        )
        if ancestry.returncode != 0:
            return visible
    # The baseline was already fully validated against historical sync contracts.
    # Pin the exact baseline blob instead of treating its older approved OCR
    # edits as new uncovered V620 changes for each earlier generation.
    baseline = subprocess.run(
        ["git", "show", f"{V620_OCR_BASE}:{V620_OCR_PATH}"],
        cwd=ROOT, check=False, capture_output=True,
    )
    if (baseline.returncode != 0
            or hashlib.sha256(baseline.stdout).hexdigest() != V620_OCR_BASE_SHA256):
        return visible
    reviewed = subprocess.run(
        ["git", "diff", "--name-only",
         f"{V620_OCR_BASE}..{V620_OCR_CANDIDATE}", "--", V620_OCR_PATH],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if reviewed.returncode != 0 or reviewed.stdout.splitlines() != [V620_OCR_PATH]:
        return visible
    return [p for p in visible if p != V620_OCR_PATH]


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
    # CGC scope is already pinned by preserve_reviewed_v525_grade_scope.
    return preserve_reviewed_v599_official_box_scope(
        preserve_reviewed_v562_purchase_scope(
            preserve_reviewed_v534_box_scope(
                preserve_reviewed_v525_grade_scope(visible, source, head, prior_head=effective_head),
                source, head,
            ),
            source, head,
        ),
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
    _assert_successor_paths_reviewed(testcase, after432, V434_WATCHED + V439_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED, generation="V432")
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
        testcase.assertTrue(_reviewed_document_path(testcase, path).is_file(), path)
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
        testcase.assertTrue(_reviewed_document_path(testcase, path).is_file(), path)
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
    _assert_successor_paths_reviewed(testcase, after431, V432_WATCHED + V439_WATCHED + V440_WATCHED + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED, generation="V431")
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
    _assert_successor_paths_reviewed(
        testcase, after428,
        V431_WATCHED + V432_WATCHED + V439_WATCHED + V440_WATCHED
        + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED,
        generation="V428",
    )
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
    _assert_successor_paths_reviewed(
        testcase, after427,
        V431_WATCHED + V432_WATCHED + V439_WATCHED + V440_WATCHED
        + V469_WATCHED + V470_WATCHED + V471_WATCHED + V480_WATCHED,
        generation="V427",
    )
    return assert_v428_successor(testcase)


# Independent byte pins: editing the JSON alongside runtime code is insufficient.
V641_BASE = '4c8e210069867f68818661ee93127dce960f5b9c'
V641_CANDIDATE = 'dcf287caf103d0aa19c5aec0231e5643096eee67'
V641_PINS = {'.github/workflows/tablet-autonomy-patch-checks.yml': '831e5a2b030c15fb43c7c450de7ba815f5f59827f1fa9e07670af6959dd40ac6', 'TABLET_SCHEDULED_UPDATE.sh': '7ee7addb10e41cfad2b700e142adffa08548e5db71cea8c5e980d7278f97d912', 'tablet_autonomous_evolution_v372.py': '0cab6ba76f339f33800d2210fd9e3cd7b332f54dd5f505eb692e949e505e6170', 'tablet_autonomous_evolution_v387.py': '006f62226eeb26abd9f0a13661d066c497381c37d0ce699b0b5f167e345ad4ae'}
V641_BASE_PINS = {'.github/workflows/tablet-autonomy-patch-checks.yml': None, 'TABLET_SCHEDULED_UPDATE.sh': '2ff46aea34c81af80ab86562f09ff24b1a6e025ddd4baff255e52d5653b78a29', 'tablet_autonomous_evolution_v372.py': '00db718f88afe8b8bed62b0a961c767124f6ee74a9bfad60270141dfcbef8237', 'tablet_autonomous_evolution_v387.py': '299412c48ab84758cbd003187b743ba7d53956f9619ef6058c3a3681b7739535'}
V641_GAPS = frozenset(['.github/workflows/tablet-autonomy-patch-checks.yml', 'tablet_autonomous_evolution_v372.py', 'tablet_autonomous_evolution_v387.py'])


def assert_v641_autonomy_successor(testcase):
    """Review exact PR768 bytes without changing any immutable generation."""
    path = ROOT / ".github/tablet-autonomy/sync_successor_v641.json"
    testcase.assertFalse(path.is_symlink())
    proof = _read(path)
    testcase.assertEqual(proof["schema"], "tablet-autonomy-sync-successor/v641")
    testcase.assertEqual(proof["base_main_sha"], V641_BASE)
    testcase.assertEqual(proof["candidate_commit"], V641_CANDIDATE)
    testcase.assertEqual(proof["reviewed_sha256"], V641_PINS)
    testcase.assertEqual(proof["baseline_sha256"], V641_BASE_PINS)
    testcase.assertEqual(set(proof["historical_gap_paths"]), V641_GAPS)
    testcase.assertEqual(proof["historical_generations"], ["V426", "V427", "V428", "V431", "V432"])
    testcase.assertIs(proof["physical_tablet_runtime_verified"], False)
    testcase.assertIs(proof["deployment_allowed"], False)
    for ancestor, descendant in ((V641_BASE, V641_CANDIDATE), (V641_CANDIDATE, "HEAD")):
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                            cwd=ROOT, capture_output=True, check=False).returncode
        testcase.assertEqual(rc, 0, "missing or divergent V641 review history")
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{V641_BASE}..{V641_CANDIDATE}"],
        cwd=ROOT, text=True).splitlines()
    testcase.assertTrue(set(V641_PINS).issubset(changed))
    for relative, digest in V641_PINS.items():
        target = ROOT / relative
        testcase.assertFalse(target.is_symlink())
        if relative == "TABLET_SCHEDULED_UPDATE.sh" and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            assert_v643_schedule_successor(testcase)
        else:
            testcase.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest,
                                 f"unreviewed current bytes: {relative}")
        reviewed = subprocess.check_output(
            ["git", "show", f"{V641_CANDIDATE}:{relative}"], cwd=ROOT)
        testcase.assertEqual(hashlib.sha256(reviewed).hexdigest(), digest)
        before = subprocess.run(["git", "show", f"{V641_BASE}:{relative}"],
                                cwd=ROOT, capture_output=True, check=False)
        if V641_BASE_PINS[relative] is None:
            testcase.assertNotEqual(before.returncode, 0)
        else:
            testcase.assertEqual(before.returncode, 0)
            testcase.assertEqual(hashlib.sha256(before.stdout).hexdigest(),
                                 V641_BASE_PINS[relative])


V642_UI_PROOF = {'schema': 'tablet-ui-dom-successor/v642', 'base_commit': '64d1a3b4d6a2084b1b8f586f9d046b8b3f5f3252', 'candidate_commit': '81efce9ab4abc7798b9f2fea0af860085fae4276', 'path': 'tablet_autonomous_evolution_v400.py', 'baseline_sha256': '8eb9b452e78bdd99484d960cfdf531153e4545f128caa3918b8c9fc18e3ff454', 'reviewed_sha256': '6fa2411c057f437f38863b793ae2c3ba4edd06ed16927888be2f50ddfa2cc1b0', 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


def preserve_reviewed_v642_ui_scope(visible, source, head="HEAD", *, prior_head=None):
    """Delegate exact dynamic-DOM checker bytes, retaining every older change."""
    relative = V642_UI_PROOF["path"]
    if head != "HEAD" or relative not in visible:
        return visible
    proof_path = ROOT / ".github/tablet-autonomy/ui_dom_successor_v642.json"
    target = ROOT / relative
    try:
        if proof_path.is_symlink() or target.is_symlink() or _read(proof_path) != V642_UI_PROOF:
            return visible
        if hashlib.sha256(target.read_bytes()).hexdigest() != V642_UI_PROOF["reviewed_sha256"]:
            return visible
        base, candidate = V642_UI_PROOF["base_commit"], V642_UI_PROOF["candidate_commit"]
        for ancestor, descendant in ((base, candidate), (candidate, "HEAD")):
            rc = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                                cwd=ROOT, capture_output=True, check=False).returncode
            if rc != 0:
                return visible
        for commit, key in ((base, "baseline_sha256"), (candidate, "reviewed_sha256")):
            data = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)
            if hashlib.sha256(data).hexdigest() != V642_UI_PROOF[key]:
                return visible
        boundary = prior_head if prior_head and prior_head != "HEAD" else base
        earlier = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{boundary}", "--", relative],
            cwd=ROOT, text=True).splitlines()
        return visible if earlier else [path for path in visible if path != relative]
    except (OSError, UnicodeError, ValueError, KeyError, subprocess.SubprocessError):
        return visible  # Absent or invalid review evidence never hides a change.


def preserve_reviewed_v641_autonomy_scope(visible, source, head="HEAD"):
    """Attribute only newly introduced PR768 diffs in legacy direct watchers."""
    legacy_sources = {'48f8f45d230f252886c6c17d2d2a1b5e432cd263', 'af47dc6e95735be99800669f57610069865efca6', 'd7c8577b514abdbbc15ba9323c4c0deb1945efed', '372e8fb1f1c546120fb49db3fea52d59129319ca', 'd77ec75aeb00e0c2394d0e8d3cf3259b9622c56b', '7f68e579e6cb84e65d059ec14b78d7e42e94fb0c', 'fdbe8d711dd4eda6e4cc7ed1ec069858d0b3b1d7', 'c144c08bc38fa36deb49c3b2dc3d1de28e5e5dee', 'f23a48e67a54a90e045bb920bc61a4a76707dc3a', '0631210ccff73c41f983a40d3629f5d2f2a503a2', 'b1000eb9f155ce343fc3bc59bcc0c35c5efb19c3', 'ae1262997cf6a60e9aba5d6be25559605787ed85', '5364126c153b3f13704fbe07f0a56ad1c323f413', '839c5890752d39343c1345c996dd8568baeecdeb', '2e23683dbde0f9f9153776bf9f27b57b8c1b32cb', 'aced561a5c930b099583fa35f2746104c0420243'}
    candidates = sorted(set(visible) & V641_GAPS)
    if head != "HEAD" or source not in legacy_sources or not candidates:
        return visible
    import unittest
    try:
        assert_v641_autonomy_successor(unittest.TestCase())
        prior = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{V641_BASE}", "--", *candidates],
            cwd=ROOT, text=True).splitlines()
    except (AssertionError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        return visible  # Missing proof never hides a watched-path change.
    # Retain every change already visible before PR768, including older edits
    # to the same path. Only exact newly introduced candidate bytes delegate.
    removable = set(candidates) - set(prior)
    return [path for path in visible if path not in removable]


def _assert_successor_paths_reviewed(testcase, actual, approved, *, generation: str) -> None:
    """Delegate only exact byte-reviewed V641 gaps; unrelated paths still block."""
    unexpected = sorted(set(actual) - set(approved))
    if unexpected and generation in {"V426", "V427", "V428", "V431", "V432"}:
        testcase.assertTrue(set(unexpected).issubset(V641_GAPS),
                            f"{generation} unreviewed watched paths: {unexpected}; "
                            "a separately reviewed sync successor is required")
        assert_v641_autonomy_successor(testcase)
        return
    testcase.assertFalse(
        unexpected,
        f"{generation} unreviewed watched paths: {unexpected}; "
        "a separately reviewed sync successor is required",
    )


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
    _assert_successor_paths_reviewed(
        testcase, after426,
        V427_WATCHED + V431_WATCHED + V432_WATCHED + V439_WATCHED
        + V440_WATCHED + V469_WATCHED + V470_WATCHED
        + V471_WATCHED + V480_WATCHED,
        generation="V426",
    )
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


V643_SCHEDULE_PROOF = {'schema': 'tablet-schedule-hold-successor/v643', 'base_commit': 'd0ae1e2c9a18f704e6770487fbf8c5a6f72c85b4', 'candidate_commit': '806c8b248ec299c90c4b1ba27126d50b0349f7ae', 'reviewed_sha256': {'TABLET_SCHEDULED_UPDATE.sh': '425d0cde76b3ebbde07ef294f0f86e887093f76c098ca0c2db6b225df470e9b4', 'execution/tablet_autonomy_result.py': '4a7b35dafa977d152f40d3fa5e206980b295222ec4c3b606f6e1b40e00efe6ca', 'execution/tests/test_tablet_autonomy_result.py': '0352219cf50092be924cf09f3c857d31ce223f3ccd7997bc84243b161bb9e34c'}, 'baseline_sha256': {'TABLET_SCHEDULED_UPDATE.sh': '7ee7addb10e41cfad2b700e142adffa08548e5db71cea8c5e980d7278f97d912', 'execution/tablet_autonomy_result.py': None, 'execution/tests/test_tablet_autonomy_result.py': None}, 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


def assert_v643_schedule_successor(testcase):
    """Verify a bounded scheduler-only descendant, retaining older byte pins."""
    proof_path = ROOT / ".github/tablet-autonomy/schedule_hold_successor_v643.json"
    testcase.assertFalse(proof_path.is_symlink())
    testcase.assertEqual(_read(proof_path), V643_SCHEDULE_PROOF)
    proof = V643_SCHEDULE_PROOF
    base, candidate = proof["base_commit"], proof["candidate_commit"]
    for ancestor, descendant in ((base, candidate), (candidate, "HEAD")):
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                            cwd=ROOT, capture_output=True, check=False).returncode
        testcase.assertEqual(rc, 0, "missing or divergent V643 schedule review")
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}..{candidate}"], cwd=ROOT, text=True).splitlines()
    testcase.assertEqual(set(changed), set(proof["reviewed_sha256"]))
    for relative, digest in proof["reviewed_sha256"].items():
        target = ROOT / relative
        testcase.assertFalse(target.is_symlink())
        if relative == "TABLET_SCHEDULED_UPDATE.sh" and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            assert_v644_learning_successor(testcase)
        else:
            testcase.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest,
                                 f"unreviewed V643 current bytes: {relative}")
        reviewed = subprocess.check_output(["git", "show", f"{candidate}:{relative}"], cwd=ROOT)
        testcase.assertEqual(hashlib.sha256(reviewed).hexdigest(), digest)
        before = subprocess.run(["git", "show", f"{base}:{relative}"], cwd=ROOT, capture_output=True, check=False)
        expected = proof["baseline_sha256"][relative]
        if expected is None:
            testcase.assertNotEqual(before.returncode, 0)
        else:
            testcase.assertEqual(before.returncode, 0)
            testcase.assertEqual(hashlib.sha256(before.stdout).hexdigest(), expected)


V644_LEARNING_PROOF = {'schema': 'tablet-learning-readiness-successor/v644', 'base_commit': '65eb272c5d0561326fad3e350b87b3e832224260', 'candidate_commit': 'fcfb2d53de6fc1c29f1440a15b01921f1ff798db', 'reviewed_sha256': {'main': 'ff63c4f1604025da5b5d7560e5081fe50a5292fa216f77c0c6397a3d8a22f921', 'TABLET_SCHEDULED_UPDATE.sh': 'bd5bbc6fddf61b0dd705e1ab4ee373e5a0278387b4051516f746ba361bf5de48', 'execution/tests/test_tablet_learning_entrypoint.py': 'a8f6e22ca071c4d6454bab6287cdfe19bc32cf140b06aad0ca83a066dc1f0f62'}, 'baseline_sha256': {'main': '91c2292cbfbbea1cbbdc92dac46b08d32c4546f673b8e9c03047bdebf3a57ab5', 'TABLET_SCHEDULED_UPDATE.sh': '425d0cde76b3ebbde07ef294f0f86e887093f76c098ca0c2db6b225df470e9b4', 'execution/tests/test_tablet_learning_entrypoint.py': None}, 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


def assert_v644_learning_successor(testcase):
    """Keep all original pins and verify only the exact readiness descendant."""
    proof_path = ROOT / ".github/tablet-autonomy/learning_readiness_successor_v644.json"
    testcase.assertFalse(proof_path.is_symlink())
    testcase.assertEqual(_read(proof_path), V644_LEARNING_PROOF)
    proof = V644_LEARNING_PROOF
    base, candidate = proof["base_commit"], proof["candidate_commit"]
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0,'missing or divergent V644 immutable learning review')
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256']))
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    for relative, digest in proof["reviewed_sha256"].items():
        target = ROOT / relative
        testcase.assertFalse(target.is_symlink())
        if relative in ['execution/tests/test_tablet_learning_entrypoint.py']:
            testcase.assertEqual(V656_PROOF['baseline_sha256'][relative],digest,relative)
        elif relative in V651_UPDATE_PROOF['reviewed_sha256']:
            assert_v651_update_successor(testcase)
            testcase.assertEqual(V651_UPDATE_PROOF['baseline_sha256'][relative], digest)
        elif relative in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][relative], digest)
        else:
            testcase.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest,
                                 f"unreviewed V644 current bytes: {relative}")
        # Commit objects are immutable; current proof bytes, current source bytes,
        # symlinks and candidate-to-HEAD ancestry above remain uncached.
        testcase.assertEqual(rows[relative],(proof['baseline_sha256'][relative],digest),relative)


def preserve_reviewed_v644_learning_scope(visible, source, head="HEAD", *, prior_head=None):
    """Retain every older main diff; delegate only exact new status behavior."""
    if head != "HEAD" or "main" not in visible:
        return visible
    import unittest
    try:
        assert_v644_learning_successor(unittest.TestCase())
        boundary = prior_head if prior_head and prior_head != "HEAD" else V644_LEARNING_PROOF["base_commit"]
        earlier = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{boundary}", "--", "main"],
            cwd=ROOT, text=True).splitlines()
        return visible if earlier else [path for path in visible if path != "main"]
    except (AssertionError, OSError, UnicodeError, ValueError, KeyError, subprocess.SubprocessError):
        return visible


V645_FEATURE_PROOF = {'schema': 'tablet-private-catalog-successor/v645', 'base_commit': '6ce814e70ecbeca7ee2c659e6bb7c479f2d8bccc', 'candidate_commit': '76f42981bda20f76cf5b935b1ebab8f511399761', 'reviewed_sha256': {'box_knowledge_stats.js': 'd1e9a9665dc3277cc6732406694647ed870860bb90a72653f7fed73cae8b268f', 'execution/tablet_catalog_bridge.py': '502a129c74ec4a7f7e806f9cf5b959705634c5b4aa681fe3ac3da24fb3ad5667', 'execution/tablet_feature_source_bundle.py': '2a9fc38ff9b0fff0f29f1ff3f410b5b600c60daa95555680cd442b7d51ef2847', 'execution/tablet_image_collection_policy.py': 'faa6afe84c3e7654cee141b7be3d6985411b3572e6e0da7673e952d53373815c', 'execution/tablet_preserved_update.py': 'e4be638d802f3ec573b3d7bf485748a42843b233eb0d33d7bae3a65052b208e0', 'execution/tests/test_box_country_navigation.py': '4f9fb8e63b2bc709a3bd269243e79ac2041b4aadc996446ff6066e693dd8fbf2', 'execution/tests/test_feature_source_bundle.py': 'cdf6b9da59738354763b711dbe7db848c9e018ea6281478adb0be26f27d6a230', 'execution/tests/test_image_collection_policy.py': '4e9f1045bfc6a491c5820c9a6a758f1c928a988821750f31137015eb54bf6fea', 'execution/tests/test_restored_private_images.py': '1688e4af1327e87173b1e46891c740323a3a334f6ebf899bc28d33aa0de5ea11', 'execution/tests/test_tablet_catalog_bridge.py': '942f695856dbd68d06667429e0ef7769a156e8430233521d9bc8049d565507bb', 'execution/tests/test_tablet_navigation_actions.py': 'c91f05ba81c7088a8ad47563b4ae9f308f6acc397dc8330efa9f4f4a70871c23', 'execution/tests/test_tablet_preserved_update.py': '156f59bc777f5311e03b88cbef19e4509d246a05e343f6d49ef952f80c165937', 'execution/tests/test_ui_navigation_audit.py': 'e56aec4abd1c025cbc5b578bd72461b1653eb1c2243e3f27ffdde03254112566', 'execution/ui_navigation_audit.py': '2302b846754bcb3d676be567e04ec2c4e07be61191ad3f5d12bcbca300dbb7d8', 'feature_category_nav.css': 'af465d6c3647e5b2d8f54533a72c17020e1ce7683a17e71c43e440b39f9bf153', 'feature_category_nav.js': 'd37e5776f6d41aa77f851ba2687546b499694e688bc5719092431f1c009bd7ed', 'index.html': '78e56cc3e3a75e9285caa257dd717bc0ea43a1f9d55fa468ff096e13e8aaaf52', 'sw.js': '0578a2ca84f9f352fcb579be18a3c44c166b24789b34290c3f31eb5be04e4697', 'tablet_catalog_auto_reflect_v43.py': 'e39b350927665817b224a9797e47c4e2dbc8acc267b873d4e2116dbc5d823ec2', 'tablet_collection_image_bridge_v42.py': 'a9ca0dfd6931e0ee74ae236c1a7cfb6e4a918c0624ed853823de67e70eec71e2', 'tablet_image_auto_v2.js': '390adacb811f97c2990a7b1d23c5608de0a7bfa675d1c752bc3a70f2136ca751', 'tablet_image_auto_v2.py': '421cf7e1ecfd0cefc26aa401ff562e5e980742379bc173619f83593b651605a0', 'tablet_image_library_v1.js': '426d3bb237b702edde3e02671573d9ff03adb1eada95e9fc2a5a64a72cb17155', 'tablet_image_library_v1.py': '02972b63243a93974938ea5f649e04f4593364b1623d81dd247bf8b9647f08be', 'tablet_runtime_manifest.py': 'eba10373da839f6c2ab41487732ae4b6e7457c7854f579977b560e6be64a47c7', 'tcg_local_collection_v505.js': '5cffa8abcadb2915029097b310f7316d93e14e181cac234b3d6c281463148a6c', 'tcg_market_expanded_v487.js': 'cff3d31bc71f00a6ac3f4ddd893583edf091b60ce8aff427df687a37ece880d3', 'tcg_profit_radar_v47.py': 'c02212273e0cbfdd97a279ecf6c77c974cabf992c1eb4d18a39583d09af1a13a', 'tcg_reliability/china_official_catalog_v571.py': '34457a1d6baeabb9d33dc6b5084f5d96786e427da331f82b15ce441985aef192', 'tcg_reliability/test_china_official_catalog_v571.py': '869709910ad016be5618ab4373a1ba3102a9e3750deaab7feaa4e00ca3366abb', 'tcg_updater.py': 'feefdeb8fc0ce20a0dd042aa82f8848dd548ee1961b37205ec30328b0b8bedad', 'tcg_updater_v135.py': '8c789483fb4e8a331a513dc6b6642bdb8d38ba5025f40e75a719a49a49bf269c', 'test_collection_scope_compat_v214.py': 'bbf6f34e561eb884ffddb7fc2b05e6dc2b6052ad352697e526a60e6be534c22b', 'test_tablet_private_catalog_v645.py': '7a0480470b49b6b1899552bcdf3cb7d46fb6cbf98ae2e8af61441379384a1533', 'test_tcg_local_collection_v505.py': '1723fbd10a6a6d7389cba0a1ce82a56ff42764c62488e9e0e563f1ebc6a6bd89', 'ui_app_shell_v272.js': '3d89d0fd23c7192ef7181e0e42d7cff09bac7cee46db3c279326574f473d00cd', 'update_market_watch.py': 'f53b3ef93c7522d837e1725156a6de8d04b519f63899ae3b58106af94cea6f34'}, 'baseline_sha256': {'box_knowledge_stats.js': '82a96e9b07a2f714db89e9d665003046d3d4ed0852fca07f0eb61cc6db718076', 'execution/tablet_catalog_bridge.py': None, 'execution/tablet_feature_source_bundle.py': None, 'execution/tablet_image_collection_policy.py': None, 'execution/tablet_preserved_update.py': '2107cea05e2255a5efcdba796bcd75245dcaa3a98e4ab0f8466f7a0696d39afb', 'execution/tests/test_box_country_navigation.py': None, 'execution/tests/test_feature_source_bundle.py': None, 'execution/tests/test_image_collection_policy.py': None, 'execution/tests/test_restored_private_images.py': None, 'execution/tests/test_tablet_catalog_bridge.py': None, 'execution/tests/test_tablet_navigation_actions.py': None, 'execution/tests/test_tablet_preserved_update.py': 'a2b8aadd62314e8a3e982f6b50361a3e32a9833aea3c06662325d2ec966630d0', 'execution/tests/test_ui_navigation_audit.py': None, 'execution/ui_navigation_audit.py': None, 'feature_category_nav.css': '09f895ddc780de75e424650dfc7b0bdb180a57cceebb7a9392f4c9e1b40f5239', 'feature_category_nav.js': '965a12d1ff798d684a7a17bd3cf002b458551655d946d282b9a13270d929290c', 'index.html': 'f8b35f3b5c86874bb6a88c3a98710de386be12aac37545ed91613d210b47b5e0', 'sw.js': 'bf0485580a3d650d96976a015f573f6fec0280b56aa1de38081fbc89f9375ac0', 'tablet_catalog_auto_reflect_v43.py': None, 'tablet_collection_image_bridge_v42.py': None, 'tablet_image_auto_v2.js': None, 'tablet_image_auto_v2.py': None, 'tablet_image_library_v1.js': None, 'tablet_image_library_v1.py': None, 'tablet_runtime_manifest.py': '62f070e105147150807f965fb6bf195f9cf12ae2e4eeed26babcf09e0f692006', 'tcg_local_collection_v505.js': '5c1425cf2bfc82f24b06a4913b541428ff2bfe59dd6b3809b73efea38255bc5b', 'tcg_market_expanded_v487.js': '1d6d6040e6c47c264e090a3dbc4ca0f004a7cf167d1d94700b3c9c7eff17b38b', 'tcg_profit_radar_v47.py': None, 'tcg_reliability/china_official_catalog_v571.py': None, 'tcg_reliability/test_china_official_catalog_v571.py': None, 'tcg_updater.py': '55b1e3fee24fb45daf4925a7d5135870fc3d23c1e8004938c3d810c4fb64b908', 'tcg_updater_v135.py': '053cd2bed902e5b6b2ee24e04edc471a0f4d04c7d007611046905876092b7923', 'test_collection_scope_compat_v214.py': '5d335edbdf735abd7c930da3eb08be2308124c440dc86b8831f822cffa44c37f', 'test_tablet_private_catalog_v645.py': None, 'test_tcg_local_collection_v505.py': 'aae9dd410f51a51e75c48226f82bd2713098328fea1fdd357a39d516cd16b300', 'ui_app_shell_v272.js': '4e86af00e440db20b192822f33cfa9c60807ee8187d13f10d16cc1b2b252b6b2', 'update_market_watch.py': 'e443a103f7c34f9bc3f0025238100dd392e384ab0eac7f1e9eb859154e21fbc0'}, 'candidate_auxiliary_paths': ['integrity_manifest.json', '.github/tablet-autonomy/FEATURE_RESTORE.md'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


@lru_cache(maxsize=32)
def _v645_immutable_commit_evidence(base,candidate,paths):
    # Commit objects are immutable. Keep current worktree hashes uncached below.
    ancestor=subprocess.run(['git','merge-base','--is-ancestor',base,candidate],cwd=ROOT,capture_output=True).returncode
    changed=set(subprocess.check_output(['git','diff','--name-only',base,candidate],cwd=ROOT,text=True).splitlines())
    rows={}
    for name in paths:
        reviewed=subprocess.check_output(['git','show',candidate+':'+name],cwd=ROOT)
        previous=subprocess.run(['git','show',base+':'+name],cwd=ROOT,capture_output=True)
        rows[name]=(hashlib.sha256(reviewed).hexdigest(),previous.returncode,hashlib.sha256(previous.stdout).hexdigest())
    return ancestor,changed,rows


def assert_v645_feature_successor(testcase):
    proof=V645_FEATURE_PROOF
    path=ROOT/'.github/tablet-autonomy/feature_catalog_successor_v645.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v645_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    # Validate each descendant once per call; live worktree checks remain uncached.
    if set(proof['reviewed_sha256']) & set(V646_FEATURE_PROOF['reviewed_sha256']):
        assert_v646_feature_successor(testcase)
    if set(proof['reviewed_sha256']) - set(V646_FEATURE_PROOF['reviewed_sha256']) & set(V648_UPDATE_PROOF['reviewed_sha256']):
        assert_v648_update_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V653_PROOF['reviewed_sha256']):
        assert_v653_successor(testcase)
    assert_v666_successor(testcase)
    assert_v667_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name
        testcase.assertFalse(current.is_symlink())
        if name in V667_PROOF['reviewed_sha256'] and V667_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V667_PROOF['baseline_sha256'][name],digest,name)
        elif name in V666_PROOF['reviewed_sha256'] and V666_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V666_PROOF['baseline_sha256'][name],digest,name)
        elif name in V646_FEATURE_PROOF['reviewed_sha256']:
            testcase.assertEqual(V646_FEATURE_PROOF['baseline_sha256'][name],digest)
        elif name in V648_UPDATE_PROOF['reviewed_sha256']:
            testcase.assertEqual(V648_UPDATE_PROOF['baseline_sha256'][name],digest)
        elif name in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][name],digest)
        elif name in V653_PROOF['reviewed_sha256']:
            testcase.assertEqual(V653_PROOF['baseline_sha256'][name],digest)
        elif name == 'tcg_reliability/china_official_catalog_v571.py':
            _assert_v665_exact_pr814_source_successor(testcase,name,digest)
        else:
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V645 current source: '+name)
        reviewed_digest,previous_rc,previous_digest=rows[name]
        testcase.assertEqual(reviewed_digest,digest)
        expected=proof['baseline_sha256'][name]
        if expected is None:testcase.assertNotEqual(previous_rc,0)
        else:
            testcase.assertEqual(previous_rc,0)
            testcase.assertEqual(previous_digest,expected)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v645_feature_scope(visible,source,head='HEAD',*,prior_head=None):
    scope=set(V645_FEATURE_PROOF['reviewed_sha256'])|set(V646_FEATURE_PROOF['reviewed_sha256'])|set(V648_UPDATE_PROOF['reviewed_sha256'])|set(V649_UPDATE_PROOF['reviewed_sha256'])|set(V650_UPDATE_PROOF['reviewed_sha256'])|set(V651_UPDATE_PROOF['reviewed_sha256'])
    if head!='HEAD' or not set(visible)&scope:return visible
    import unittest
    try:
        assert_v645_feature_successor(unittest.TestCase())
        boundary=prior_head if prior_head and prior_head!='HEAD' else V645_FEATURE_PROOF['base_commit']
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+boundary,'--',*sorted(scope)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in scope or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):
        return visible


V646_FEATURE_PROOF = {'schema': 'tablet-private-catalog-ci-successor/v646', 'base_commit': '8d13d2ccab6a8dc359fa51acfec5356e9b706864', 'candidate_commit': '5368cbfe8f4d4a2390c4168705c3e1c4e43e96ca', 'reviewed_sha256': {'.github/workflows/repository-integrity-guard.yml': 'a48de0532132d8c381b79dceb23e133e84045d496e5118906973463843d7921e', '.github/workflows/selfrefine-full-repo.yml': '0e2ec493e4b9e2c50aa9a38b9f1edc45a794efb0613c4047a92985ec064a309b', 'AGENT_SKILL_SOURCES.md': None, 'ANDROID_TABLET_SETUP.md': None, 'GPT_DATA_ENGINE_GUIDE.md': None, 'GRAPHIFY_CHATGPT_GUIDE.md': None, 'SETUP_GRAPHIFY_TERMUX.sh': '55f18ef79e5ced716a45a56695cf62c852f1579d3e31c52a053f7a4725fc2a4f', 'TABLET_COLLECTION_PUBLISH.md': None, 'TABLET_GDRIVE_SYNC.md': None, 'TCG_INTEGRATED_MANAGEMENT.md': None, 'WORKFLOW_PUBLISH_SAFETY_V363.md': None, 'docs/archive/INDEX.md': '506ed77889d371172112fd02fdf1335e0065b056e321dc6fc5e736853f4eb9f9', 'docs/tablet/AGENT_SKILL_SOURCES.md': 'f0e3582f316099c550fb75810d83815e69fa98bda730d157186516f98c6a1044', 'docs/tablet/ANDROID_TABLET_SETUP.md': 'ac4b9a9afd850e46ae720f844390e33ee43deb0a6a6160e7463afce6efd4e5ab', 'docs/tablet/GPT_DATA_ENGINE_GUIDE.md': 'cd049d86102992ae8696153e45cc1b5b7fabd170a118e85c1e6734adfe9f6abb', 'docs/tablet/GRAPHIFY_CHATGPT_GUIDE.md': '574cefd1ecb57c2361a28c467aa09fe3e21e2da68d22107292bd9358fcae5eb5', 'docs/tablet/TABLET_COLLECTION_PUBLISH.md': '16b7465a9a056bdec2b671c605fded4fb89bfc2641e432831b5fd13a43f72c8b', 'docs/tablet/TABLET_GDRIVE_SYNC.md': '0e29bb25d3f6d065e5ce30eb37ebf3003af485d228395ad15ce2fd1666f79bc1', 'docs/tablet/TCG_INTEGRATED_MANAGEMENT.md': 'd58a541467d361ec16737207bfd35d455ce3a97e6a4acc80fb0e1abcb5112c4f', 'docs/tablet/WORKFLOW_PUBLISH_SAFETY_V363.md': '572f06439d18273d55ceaac0c110085482bd91d1f3eed703423542f8a9e11624', 'execution/tablet_preserved_update.py': '044d96fc3748493ae72ff504761712ff69afd46d8b9a531764181ae6678295d2', 'execution/tablet_runtime_handoff.py': '6cc28afc71122734abf2acad10632afd3680ee6361b7f3feded8bcc0c08bf0d1', 'execution/tests/private_catalog_test_registration_v645.py': '7a0480470b49b6b1899552bcdf3cb7d46fb6cbf98ae2e8af61441379384a1533', 'execution/tests/test_tablet_document_locations.py': '431dc78354a2618c54cc7cdb9290269ef5330adc5c38c656af4d7df9aa99016a', 'execution/tests/test_tablet_runtime_handoff.py': 'f82c17ce0b6e7c9111e04e67b1926cf95895b926ec26cb16bbc3f1751309668e', 'index.html': '6bda6e370e1f9a6945821e7c9407e8ccf1bdcd8b2a592421ab5ea45e702c8473', 'tablet_runtime_manifest.py': '0c99b823ecb6f067788c91d55f548d0c965b8a6510091d8489dca4727cc02845', 'tcg_market_expanded_v487.js': '1b301e36f872f6ab8c730d2e88c9eecccc5301d4fa09fabc4cbf47c561ed3367', 'test_tablet_private_catalog_v645.py': None, 'ui_app_shell_v272.js': '581c80afc7be358c4902a62aae6ba5d57c03a45d19d4c2cf02c548d4ae77d1da', 'verify_code_map_internal.py': '1951eeedd578490f6ff965d2ff2096ee09e4c17b204f5ea79da2e6c220c0d37b', 'verify_tablet_ui_repair.js': 'e1dac4b62fc8863a4f93da2d24264d9b887cc11b762ab59c8ec2cbc19bcfa48d'}, 'baseline_sha256': {'.github/workflows/repository-integrity-guard.yml': '47519437fb2c23e36592b8fe3a5c84f67fdc6581edafc68738662d5e1564f5e3', '.github/workflows/selfrefine-full-repo.yml': 'e8ce274bca582879443b03e2c874f26294d64a651331efdd9430599a3c13b470', 'AGENT_SKILL_SOURCES.md': 'f0e3582f316099c550fb75810d83815e69fa98bda730d157186516f98c6a1044', 'ANDROID_TABLET_SETUP.md': 'ac4b9a9afd850e46ae720f844390e33ee43deb0a6a6160e7463afce6efd4e5ab', 'GPT_DATA_ENGINE_GUIDE.md': 'cd049d86102992ae8696153e45cc1b5b7fabd170a118e85c1e6734adfe9f6abb', 'GRAPHIFY_CHATGPT_GUIDE.md': '574cefd1ecb57c2361a28c467aa09fe3e21e2da68d22107292bd9358fcae5eb5', 'SETUP_GRAPHIFY_TERMUX.sh': 'fd340489f9fd2d4ab865ae85904769eb1df10c2f9688a36570a246aa45e7ab2d', 'TABLET_COLLECTION_PUBLISH.md': '16b7465a9a056bdec2b671c605fded4fb89bfc2641e432831b5fd13a43f72c8b', 'TABLET_GDRIVE_SYNC.md': '0e29bb25d3f6d065e5ce30eb37ebf3003af485d228395ad15ce2fd1666f79bc1', 'TCG_INTEGRATED_MANAGEMENT.md': 'd58a541467d361ec16737207bfd35d455ce3a97e6a4acc80fb0e1abcb5112c4f', 'WORKFLOW_PUBLISH_SAFETY_V363.md': '572f06439d18273d55ceaac0c110085482bd91d1f3eed703423542f8a9e11624', 'docs/archive/INDEX.md': '71914d366f8dd116b166290a8bfccc9d04d06138a34385b27788bf7bd7b1061c', 'docs/tablet/AGENT_SKILL_SOURCES.md': None, 'docs/tablet/ANDROID_TABLET_SETUP.md': None, 'docs/tablet/GPT_DATA_ENGINE_GUIDE.md': None, 'docs/tablet/GRAPHIFY_CHATGPT_GUIDE.md': None, 'docs/tablet/TABLET_COLLECTION_PUBLISH.md': None, 'docs/tablet/TABLET_GDRIVE_SYNC.md': None, 'docs/tablet/TCG_INTEGRATED_MANAGEMENT.md': None, 'docs/tablet/WORKFLOW_PUBLISH_SAFETY_V363.md': None, 'execution/tablet_preserved_update.py': 'e4be638d802f3ec573b3d7bf485748a42843b233eb0d33d7bae3a65052b208e0', 'execution/tablet_runtime_handoff.py': None, 'execution/tests/private_catalog_test_registration_v645.py': None, 'execution/tests/test_tablet_document_locations.py': None, 'execution/tests/test_tablet_runtime_handoff.py': None, 'index.html': '78e56cc3e3a75e9285caa257dd717bc0ea43a1f9d55fa468ff096e13e8aaaf52', 'tablet_runtime_manifest.py': 'eba10373da839f6c2ab41487732ae4b6e7457c7854f579977b560e6be64a47c7', 'tcg_market_expanded_v487.js': 'cff3d31bc71f00a6ac3f4ddd893583edf091b60ce8aff427df687a37ece880d3', 'test_tablet_private_catalog_v645.py': '7a0480470b49b6b1899552bcdf3cb7d46fb6cbf98ae2e8af61441379384a1533', 'ui_app_shell_v272.js': '3d89d0fd23c7192ef7181e0e42d7cff09bac7cee46db3c279326574f473d00cd', 'verify_code_map_internal.py': '96e56f02f178c3a3a6ac4613a21e505d2201c52f8b3564b5ba58d80eb8160bbc', 'verify_tablet_ui_repair.js': '614cc58396dffd9d6cfc912cbe7247bb936041461e1c16559a164576a4b0eab3'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

# Cache only immutable commit-object evidence. Live bytes, proof JSON and HEAD
# ancestry are still checked on every call. The reviewed chain now exceeds eight
# entries; an eight-entry LRU evicted active ancestors and repeated git show.
@lru_cache(maxsize=32)
def _v646_immutable_commit_evidence(base,candidate,paths):
    ancestor=subprocess.run(['git','merge-base','--is-ancestor',base,candidate],cwd=ROOT,capture_output=True).returncode
    changed=set(subprocess.check_output(['git','diff','--no-renames','--name-only',base,candidate],cwd=ROOT,text=True).splitlines())
    def digest(ref,name):
        row=subprocess.run(['git','show',ref+':'+name],cwd=ROOT,capture_output=True)
        return hashlib.sha256(row.stdout).hexdigest() if row.returncode==0 else None
    return ancestor,changed,{p:(digest(base,p),digest(candidate,p)) for p in paths}


def assert_v646_feature_successor(testcase):
    proof=V646_FEATURE_PROOF
    path=ROOT/'.github/tablet-autonomy/feature_catalog_successor_v646.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V653_PROOF['reviewed_sha256']):
        assert_v653_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V654_PROOF['reviewed_sha256']):
        assert_v654_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V648_UPDATE_PROOF['reviewed_sha256']:
            assert_v648_update_successor(testcase)
            testcase.assertEqual(V648_UPDATE_PROOF['baseline_sha256'][name],digest)
        elif name in V651_UPDATE_PROOF['reviewed_sha256']:
            assert_v651_update_successor(testcase)
            testcase.assertEqual(V651_UPDATE_PROOF['baseline_sha256'][name],digest)
        elif name in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][name],digest)
        elif name in V653_PROOF['reviewed_sha256']:
            testcase.assertEqual(V653_PROOF['baseline_sha256'][name],digest)
        elif name in V654_PROOF['reviewed_sha256']:
            testcase.assertEqual(V654_PROOF['baseline_sha256'][name],digest)
        elif digest is None:
            testcase.assertFalse(current.exists(),'unreviewed restored V646 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V646 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


V647_CI_PROOF = {'schema': 'tablet-alignment-dependency-successor/v647', 'base_commit': 'e07fadd0ab30fbb0936ab454bbd757b890dde613', 'candidate_commit': '453540970de48cb8fe443e6a8b98418fc25356c5', 'reviewed_sha256': {'.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml': '83d6bf6009269550311fd2b242ed5e95145b5c4a67554c16f3127e6ca5f3acbb'}, 'baseline_sha256': {'.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml': '6227ecd1a0bb3e6644cf2c9ba4b583a6a4e2740429cbde22b0ee357056b5408c'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v647_ci_successor(testcase):
    proof=V647_CI_PROOF
    path=ROOT/'.github/tablet-autonomy/alignment_dependency_successor_v647.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name
        testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest))
        if hashlib.sha256(current.read_bytes()).hexdigest() != digest:
            assert_v659_ci_successor(testcase)
            testcase.assertEqual(V659_CI_PROOF['baseline_sha256'][name],digest)
        else:
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v647_ci_scope(visible,source,head='HEAD',*,prior_head=None):
    paths=set(V647_CI_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v647_ci_successor(unittest.TestCase())
        boundary=prior_head if prior_head and prior_head!='HEAD' else V647_CI_PROOF['base_commit']
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+boundary,'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V648_UPDATE_PROOF = {'schema': 'tablet-preserved-update-successor/v648', 'base_commit': '2dbc1c72698dc4842e50ad8645528802d9153f00', 'candidate_commit': '5681a936c8bbcfd5b14756d7b2cd389d3ba58fb7', 'reviewed_sha256': {'directives/TCG_RELIABILITY_SOP.md': 'db8dc0fd2d1f4e9526fd5505a925de0ae6444087184f5ff8cb9de1d2842140c3', 'execution/tablet_preserved_update.py': 'fc27284be3965019178fcb1bab6fbb785e3671c6c0d656e0c1cf635f352cf970', 'execution/tests/test_graphify_preserved_update_v648.py': '489eeb78bb9996c5d63eae4647fec889be7606bfc648433d9845d954b7f0fd60', 'execution/tests/test_tablet_successor_v646.py': '65b617142efec764f303c433663d7f489a81fc42f88115bd590fa9cf9ecb394b', 'execution/tests/test_tcg_local_collection_v505.py': '3eb4df6ff44518abef910d8644da2c0e91a56d8068c4d5a30eef44f205a35f1f', 'test_tcg_local_collection_v505.py': None}, 'baseline_sha256': {'directives/TCG_RELIABILITY_SOP.md': 'b9b21e03e8c021e7386d94bf06893741aefd31ad56cc1dbb25c9e4808b91f3ee', 'execution/tablet_preserved_update.py': '044d96fc3748493ae72ff504761712ff69afd46d8b9a531764181ae6678295d2', 'execution/tests/test_graphify_preserved_update_v648.py': None, 'execution/tests/test_tablet_successor_v646.py': '82e8c2dc33c7fb4c26c1889f3c89ea8a752424a45a7285fa78ff38329826950c', 'execution/tests/test_tcg_local_collection_v505.py': None, 'test_tcg_local_collection_v505.py': '1723fbd10a6a6d7389cba0a1ce82a56ff42764c62488e9e0e563f1ebc6a6bd89'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


def assert_v648_update_successor(testcase):
    proof=V648_UPDATE_PROOF
    path=ROOT/'.github/tablet-autonomy/preserved_update_successor_v648.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V649_UPDATE_PROOF['reviewed_sha256']):
        assert_v649_update_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V649_UPDATE_PROOF['reviewed_sha256']:
            testcase.assertEqual(V649_UPDATE_PROOF['baseline_sha256'][name],digest)
        elif name in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][name],digest)
        elif digest is None:
            testcase.assertFalse(current.exists(),'unreviewed restored V648 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V648 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v648_update_scope(visible,source,head='HEAD',*,prior_head=None):
    visible=_preserve_v665_exact_later_source(visible,source,head)
    visible=preserve_reviewed_v652_scope(visible,source,head)
    visible=preserve_reviewed_v651_update_scope(visible,source,head,prior_head=prior_head)
    paths=set(V648_UPDATE_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v648_update_successor(unittest.TestCase())
        boundary=prior_head if prior_head and prior_head!='HEAD' else V648_UPDATE_PROOF['base_commit']
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+boundary,'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


def assert_v649_update_successor(testcase):
    proof=V649_UPDATE_PROOF
    path=ROOT/'.github/tablet-autonomy/preserved_update_successor_v649.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V650_UPDATE_PROOF['reviewed_sha256']):
        assert_v650_update_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V650_UPDATE_PROOF['reviewed_sha256']:
            testcase.assertEqual(V650_UPDATE_PROOF['baseline_sha256'][name],digest)
        elif name in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][name],digest)
        elif digest is None:
            testcase.assertFalse(current.exists(),'unreviewed restored V649 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V649 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v649_update_scope(visible,source,head='HEAD',*,prior_head=None):
    paths=set(V649_UPDATE_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v649_update_successor(unittest.TestCase())
        boundary=prior_head if prior_head and prior_head!='HEAD' else V649_UPDATE_PROOF['base_commit']
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+boundary,'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


def assert_v650_update_successor(testcase):
    proof=V650_UPDATE_PROOF
    path=ROOT/'.github/tablet-autonomy/preserved_update_successor_v650.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V651_UPDATE_PROOF['reviewed_sha256']):
        assert_v651_update_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V651_UPDATE_PROOF['reviewed_sha256']:
            testcase.assertEqual(V651_UPDATE_PROOF['baseline_sha256'][name],digest)
        elif name in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][name],digest)
        elif digest is None:
            testcase.assertFalse(current.exists(),'unreviewed restored V650 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V650 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v650_update_scope(visible,source,head='HEAD',*,prior_head=None):
    paths=set(V650_UPDATE_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v650_update_successor(unittest.TestCase())
        boundary=prior_head if prior_head and prior_head!='HEAD' else V650_UPDATE_PROOF['base_commit']
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+boundary,'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


def assert_v651_update_successor(testcase):
    proof=V651_UPDATE_PROOF
    path=ROOT/'.github/tablet-autonomy/preserved_update_successor_v651.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V652_PROOF['reviewed_sha256']):
        assert_v652_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in ['TABLET_SCHEDULED_UPDATE.sh']:
            testcase.assertEqual(V656_PROOF['baseline_sha256'][name],digest,name)
        elif name in V652_PROOF['reviewed_sha256']:
            testcase.assertEqual(V652_PROOF['baseline_sha256'][name],digest)
        elif digest is None:
            testcase.assertFalse(current.exists(),'unreviewed restored V651 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V651 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v651_update_scope(visible,source,head='HEAD',*,prior_head=None):
    visible=preserve_reviewed_v652_scope(visible,source,head)
    paths=set(V651_UPDATE_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v651_update_successor(unittest.TestCase())
        boundary=prior_head if prior_head and prior_head!='HEAD' else V651_UPDATE_PROOF['base_commit']
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+boundary,'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V649_UPDATE_PROOF = {'schema': 'tablet-preserved-update-successor/v649', 'base_commit': 'c729145a2df04490bd3d9fcedfdd2c8ba1c6f5f1', 'candidate_commit': '0a397a99376d12fe7936c6d96cd62b3cf3e0ef48', 'reviewed_sha256': {'directives/TCG_RELIABILITY_SOP.md': 'f152fbbd7a3593201451b57377c63e27d80c772391765d1d94b3c75c5390c934', 'execution/tablet_preserved_update.py': 'e6d96fdda9e5c629f853e2ca4f57ffd49c1881d8a839f4c674dd977412eef810', 'execution/tests/test_graphify_successor_v648.py': 'fdc0d501c8f7aca891e6972454304f8f88f426b6a12a398da4bb4974da4c53e4', 'execution/tests/test_observed_source_recovery_v649.py': '76fe2b73e3c27c0842ba4e36fc500a49ac3fb7d9c9f3ec7f187a823c6d819584', 'execution/tests/test_update_market_price_identity_v523.py': 'eac4170a5b168c2618361ea0f8ed8e957503e723ad70e1d8d8ee4797b0b54dc7', 'test_update_market_price_identity_v523.py': None}, 'baseline_sha256': {'directives/TCG_RELIABILITY_SOP.md': 'db8dc0fd2d1f4e9526fd5505a925de0ae6444087184f5ff8cb9de1d2842140c3', 'execution/tablet_preserved_update.py': 'fc27284be3965019178fcb1bab6fbb785e3671c6c0d656e0c1cf635f352cf970', 'execution/tests/test_graphify_successor_v648.py': 'b9a08ff024d78371139ed680e146075432f024edd2483357522293993d7d69ef', 'execution/tests/test_observed_source_recovery_v649.py': None, 'execution/tests/test_update_market_price_identity_v523.py': None, 'test_update_market_price_identity_v523.py': 'a54555c47186cd21082aa6a43ba2f812b2ccd7e5371bbb70e3a87bd40b6ce38d'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


V650_UPDATE_PROOF = {'schema': 'tablet-preserved-update-successor/v650', 'base_commit': '5058224de13ba14e87c551b09d6f23c46198a677', 'candidate_commit': '140a8ae4d0d3845bc875b18ff54c631144da323c', 'reviewed_sha256': {'directives/TCG_RELIABILITY_SOP.md': '44e7f8dcb286410f0a9bb58d139b9cae5a9e1cb811e53fc7ae831e822096f63e', 'execution/tablet_preserved_update.py': '9c380408d53f314a8723ff537c8fdab587fc9e3a2d9fba84dd13edf12589f4cc', 'execution/tests/test_china_preserved_update_v650.py': 'cab6a2c1323231d29a75d551b48d69862b8b1724dbcbb91739d5cf9a8132477a', 'execution/tests/test_observed_source_successor_v649.py': 'c1db0a6e13f35f931b2d2ea04cf5c43207144146b0c3fc40ddc6daa6e793a48b', 'execution/tests/test_update_market_prices_packmagik_v353.py': 'b622fb4d7bbcf1f189a7c93648ecd59da090e80f31736a5b457d7cce341fc2ed', 'test_update_market_prices_packmagik_v353.py': None}, 'baseline_sha256': {'directives/TCG_RELIABILITY_SOP.md': 'f152fbbd7a3593201451b57377c63e27d80c772391765d1d94b3c75c5390c934', 'execution/tablet_preserved_update.py': 'e6d96fdda9e5c629f853e2ca4f57ffd49c1881d8a839f4c674dd977412eef810', 'execution/tests/test_china_preserved_update_v650.py': None, 'execution/tests/test_observed_source_successor_v649.py': '41b81513c3de1d31eeba4efaa47d3af7746e227d29dfa2e32d84ce3477813804', 'execution/tests/test_update_market_prices_packmagik_v353.py': None, 'test_update_market_prices_packmagik_v353.py': 'b622fb4d7bbcf1f189a7c93648ecd59da090e80f31736a5b457d7cce341fc2ed'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


V651_UPDATE_PROOF = {'schema': 'tablet-preserved-update-successor/v651', 'base_commit': '1883fef756c12fcc17fdb358538437105befaac5', 'candidate_commit': '60e31efad1dfd573456349b91f2375d2720ce58b', 'reviewed_sha256': {'TABLET_SCHEDULED_UPDATE.sh': '7540f5954e2d8112e155b0e79c2e1fdda6d3161d84b34e8d4ccc82d4e58ee9c8', 'directives/TCG_RELIABILITY_SOP.md': '76c4456e8648a8fec028c1909cafa6d3ef5ea255baebb1d23f819089a617394c', 'execution/tablet_runtime_handoff.py': '2233d189195f9553b95f676e7879e4462cab2f67ed4f97073c77314b0e0a619e', 'execution/tests/test_android_handoff_v651.py': '5c67abd69cdc0fe4612d41e8a01a426641147766ddd6864ef11c2a3b8af388e2', 'execution/tests/test_china_successor_v650.py': 'bd9086c2f0c4fc8e63386cd798c38a348dca2ae5657555808df7f5c989d5587c', 'execution/tests/test_update_guidance_consistency_v218.py': 'a4c331c54f64b4249dad029697bee11e8df5997b3c8100574424a5d971fead99', 'test_update_guidance_consistency_v218.py': None}, 'baseline_sha256': {'TABLET_SCHEDULED_UPDATE.sh': 'bd5bbc6fddf61b0dd705e1ab4ee373e5a0278387b4051516f746ba361bf5de48', 'directives/TCG_RELIABILITY_SOP.md': '44e7f8dcb286410f0a9bb58d139b9cae5a9e1cb811e53fc7ae831e822096f63e', 'execution/tablet_runtime_handoff.py': '6cc28afc71122734abf2acad10632afd3680ee6361b7f3feded8bcc0c08bf0d1', 'execution/tests/test_android_handoff_v651.py': None, 'execution/tests/test_china_successor_v650.py': '168bf8c174bf1886f11fb7c8af8dd2b8135e770ae2601d1d552b5a80747aa952', 'execution/tests/test_update_guidance_consistency_v218.py': None, 'test_update_guidance_consistency_v218.py': 'b4c4601d2647510f1c75abad865cc598d3ad6cf2a3aa234158c7b4f96e1a35c2'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}


V652_PROOF = {'schema': 'tablet-continuous-learning-image-ui-successor/v652', 'base_commit': '328782f6b92835c4aab39224bb0c6c5c6b3e0067', 'candidate_commit': '901e211693d6fad84ef33be46a909444bd2d57dd', 'reviewed_sha256': {'adaptive_collection_learner.py': '38683fbf72ef892f3d401b47ffa044236d6667ed516ea157aec92e1de90a0b37', 'collection_learning_hardening_v142.py': '324f1d7ee14d0329acd8b75ee962771599be72cc06757c0c77644c8d2d117d03', 'docs/tablet/V652_REPAIR_REVIEW.md': 'd82037df5243f9bfd3b5a8191b991b089b31e2e5d1ce3222a55f6fa79262d457', 'execution/tablet_catalog_bridge.py': '8f5ba228a3c6bb2900acd26d5e5008e55e2049c4f6d70a62f27b00e2f1af9329', 'execution/tablet_image_collection_policy.py': 'f4ee3e7a75f9e657d50fd9ae6834cee9a94f71c52b39ccb25050e0448540671f', 'execution/tests/test_android_successor_v651.py': 'a6a82021476db8ec87eb24cfca40bd50dacad04f0f25131b1cab7f4817e61e51', 'execution/tests/test_country_reset_v652.py': '567f2e2e7988583c73b5fd41dde8a470251a1bf2cd0c36b39b200af46f33cd29', 'execution/tests/test_image_collection_policy.py': '729390ce69d10ee6c0a4102426362c7407b73ead38fb6ec1e811b2df10f5267a', 'execution/tests/test_image_metadata_enrichment.py': 'dc0f691abdd49c569cfdb4a46281494e7b9c89c60bad74309cb9616756f4bb4c', 'execution/tests/test_learning_status_eligibility_v652.py': '6709dfef2b7eecb3dfa7498372f83618db933a3c7bf6a9c687fe078930ad8bdc', 'execution/tests/test_release_date_evidence_v652.py': 'd146a952b07298e9b3e1ba1330a6640ce814afa5db1a78106fa5d72d5f37f753', 'execution/tests/test_ui_recording_repairs.py': '188c13d84d5d69b106e5ec638135a587c2a09e109d37178da40fc6ba189a5f7d', 'feature_category_nav.css': '9fdd7d9ec4373012f0568021fa66a8e052f0721944ec8cfd86533ebf217d8a7b', 'feature_category_nav.js': '4f40c72633663229365d2710494fd265ac11624f767245fdff4758b736d7d64e', 'image_quality_guard.js': 'bbf1b52da006ed4b3c6fb794cfcdf9654d8e63dfbde713bf8dcee26dc07abe46', 'index.html': '3115f1925677d4d305a39de156cf8b5fdab44610f287c348483cc8a4a53b05db', 'main': '773b4120cba2d1050f8606275b5655441c50be62ee615fb2957510c5ab45bd02', 'tablet_image_auto_v2.py': '356cbf5ce2d80b9499e9309ee70e01fa5108cfe756dea876a6f9c9ab98c8a164', 'tablet_image_library_v1.js': 'a74f7eb6f08e24c7e60fb10748702328580e417cf723170c3320fb623e376d65', 'tablet_image_library_v1.py': 'd8c0d3809d4571a740d40b0e064729c7928ca5ae14fd5500f5a797c2d124092f', 'tcg_updater.py': 'a7d930aca8afbc37497256ae0c0b60ff77a1aa75dc4704f6d9d12e349ae0bfa5', 'test_tablet_learning_progress.py': 'cad089f6034dff188b330039f27c68132b2fcbf388966d11b659cc8c1b46adf2', 'test_verified_collection_neural_v211.py': '5063ee2d59a1bfe3d3cf69a931048e341cdbf0cc2f36ae1cfb61517dc9ad37c1', 'update_releases.py': 'e2f030194b2ea44bee162e0368b45168b586a4ecf6281866e58e1afcef2fbb1e', 'verified_collection_job_neural.py': 'dc13eefddaae9c5b5f21a0ffd71be6b1c17af0f1849de52fe37cdf75d355939a', 'verified_collection_neural.py': '09651a9cffdf490eed79512077a6c1efa292b1a56799887abac469f0b2731a32'}, 'baseline_sha256': {'adaptive_collection_learner.py': '87c03074db9f8599e9b4ae197869d127c8ae955d3be71b10f441800239b7cd4a', 'collection_learning_hardening_v142.py': 'a9cb2b9d2a6ab1f5ab063791a512fadaf11cb7e067c335abe8419645e4934dfe', 'docs/tablet/V652_REPAIR_REVIEW.md': None, 'execution/tablet_catalog_bridge.py': '502a129c74ec4a7f7e806f9cf5b959705634c5b4aa681fe3ac3da24fb3ad5667', 'execution/tablet_image_collection_policy.py': 'faa6afe84c3e7654cee141b7be3d6985411b3572e6e0da7673e952d53373815c', 'execution/tests/test_android_successor_v651.py': '9fa8e751eb57cc96193d89522eca58f8df1ee14f82b7318a59c4ee9ef5f7a484', 'execution/tests/test_country_reset_v652.py': None, 'execution/tests/test_image_collection_policy.py': '4e9f1045bfc6a491c5820c9a6a758f1c928a988821750f31137015eb54bf6fea', 'execution/tests/test_image_metadata_enrichment.py': None, 'execution/tests/test_learning_status_eligibility_v652.py': None, 'execution/tests/test_release_date_evidence_v652.py': None, 'execution/tests/test_ui_recording_repairs.py': None, 'feature_category_nav.css': 'af465d6c3647e5b2d8f54533a72c17020e1ce7683a17e71c43e440b39f9bf153', 'feature_category_nav.js': 'd37e5776f6d41aa77f851ba2687546b499694e688bc5719092431f1c009bd7ed', 'image_quality_guard.js': '7ceefb3e1a2be2067271a3448ade8baff127b668db8f4a4359b99340ef305e94', 'index.html': '6bda6e370e1f9a6945821e7c9407e8ccf1bdcd8b2a592421ab5ea45e702c8473', 'main': 'ff63c4f1604025da5b5d7560e5081fe50a5292fa216f77c0c6397a3d8a22f921', 'tablet_image_auto_v2.py': '421cf7e1ecfd0cefc26aa401ff562e5e980742379bc173619f83593b651605a0', 'tablet_image_library_v1.js': '426d3bb237b702edde3e02671573d9ff03adb1eada95e9fc2a5a64a72cb17155', 'tablet_image_library_v1.py': '02972b63243a93974938ea5f649e04f4593364b1623d81dd247bf8b9647f08be', 'tcg_updater.py': 'feefdeb8fc0ce20a0dd042aa82f8848dd548ee1961b37205ec30328b0b8bedad', 'test_tablet_learning_progress.py': None, 'test_verified_collection_neural_v211.py': '1d08c6406a6f58f3be50779ff938b5b6f0560c2ed25b9305076ab8e74015fa25', 'update_releases.py': '387c880ea458c43208ec6b2464aa6c864d54d68038ea3068e207a891cd88c15a', 'verified_collection_job_neural.py': 'b4e11dfd384c4e0d69ab462133683b1c98f4c509e30ef5fc2de1aa2079686533', 'verified_collection_neural.py': '6f31453f543c5f6926dcbf76d1b6e685490280539f59b176a7e44c4ec9847895'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v652_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V652_PROOF
    path=ROOT/'.github/tablet-autonomy/continuous_learning_image_ui_successor_v652.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V654_PROOF['reviewed_sha256']):
        assert_v654_successor(testcase)
    if set(proof['reviewed_sha256']) & set(V653_PROOF['reviewed_sha256']):
        assert_v653_successor(testcase)
    assert_v666_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V666_PROOF['reviewed_sha256'] and V666_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V666_PROOF['baseline_sha256'][name],digest,name)
        elif name in ['main']:
            testcase.assertEqual(V656_PROOF['baseline_sha256'][name],digest,name)
        elif name in V654_PROOF['reviewed_sha256']:
            testcase.assertEqual(V654_PROOF['baseline_sha256'][name],digest)
        elif name in V653_PROOF['reviewed_sha256']:
            testcase.assertEqual(V653_PROOF['baseline_sha256'][name],digest)
        elif digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V652 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V652 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v652_scope(visible,source,head='HEAD'):
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    visible=preserve_reviewed_v653_scope(visible,source,head)
    paths=set(V652_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v652_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V652_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V652_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V652_ARCHIVED_REVIEWS = {
    'TCG_EXTERNAL_APP_REVIEW_V482.md': '56c95bad31e9b374b4c261d1f399c09250253022d145a3bd03d2afe7dac8b1d2',
    'TCG_EXTERNAL_APP_REVIEW_V483.md': 'a20bc30abb32ee664474ca8a10882d4af44540f1312f6b27fc1f83f3879f8941',
}

@lru_cache(maxsize=2)
def _immutable_review_document_digest(name):
    data=subprocess.check_output(['git','show','328782f6b92835c4aab39224bb0c6c5c6b3e0067:'+name],cwd=ROOT)
    return hashlib.sha256(data).hexdigest()

def _reviewed_document_path(testcase, name):
    """Retain historical review text byte-for-byte after a docs-only relocation."""
    if name not in V652_ARCHIVED_REVIEWS:return ROOT/name
    original=ROOT/name;target=ROOT/'docs/archive'/name
    testcase.assertFalse(original.exists(), 'archived review must not regrow the GitHub root')
    testcase.assertFalse(original.is_symlink())
    testcase.assertFalse(target.is_symlink())
    testcase.assertTrue(target.is_file(),name)
    expected=V652_ARCHIVED_REVIEWS[name]
    testcase.assertEqual(_immutable_review_document_digest(name),expected,name)
    testcase.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),expected,name)
    return target


V653_PROOF = {'schema': 'tablet-workspace-evidence-successor/v653', 'base_commit': '88ce4476bf0e2b2515ab375323aed1b87ed0d52c', 'candidate_commit': '25541824d810f5c99563faa8edc53a10b25bb32a', 'reviewed_sha256': {'docs/tablet/V653_WORKSPACE_REVIEW.md': 'cc18e73a4ddeb61fddd08316e4587fda2b030be99c00d856f1c83f44a76cd7a4', 'execution/tablet_catalog_bridge.py': 'e2789fca6f90c69db42b72e7671b0491664312995aba4cce951271a13e710cf9', 'execution/tests/test_continuous_successor_v652.py': '51a566fdc3e8425f8d86c0c5eb0ff62a916c2376fcaa95d75da62af5ee0b0763', 'execution/tests/test_tablet_learning_progress.py': 'cad089f6034dff188b330039f27c68132b2fcbf388966d11b659cc8c1b46adf2', 'execution/tests/test_workspace_features_v653.py': '2fee1b03a2584f0c8ce88a5c9745fb5977f91e3a3d89d72e80a3908937e4f54e', 'feature_category_nav.css': 'b0183d459ca17cc8e632453a4ecfcd1e7df4aa9a2ed9bf3e0e2347bdeeb2db83', 'index.html': '0716baf9d953e804446a49f956fb8ec578a1b3218f515d1e158735a88a6e1be6', 'social_event_discovery.py': 'bf6e44e66bdfaa605e3f55768255c5e70142c93d712f0be9bce26fbd383653e6', 'tablet_image_library_v1.js': '647ff9d439c1735e245387313d74e1ff7c61e748c8e527eec2fada76639ff205', 'tablet_image_library_v1.py': 'accaa34a559981aff051dce79f384a1026de2b0a0e8143d2ec93981743da9ab8', 'tcg_card_detail_v566.css': '0b4213aee2a4125da0f2263ab438a74c795c56601072aa9a2c9b167f2381bec5', 'tcg_card_detail_v566.js': '60c7621b6f0071fda09f348d4e8e4d69da2e5b3ab62be4285e9b1991b01e8093', 'test_tablet_gpt_tcg_grader_sync_v652.py': 'ee2af805a57241af4cd6fe2ac9fc9418c621ad9d1033745c4a00d43cafe09a7a', 'test_tablet_learning_progress.py': None, 'update_promo_events.py': '02959b8c5868ea6c6f188b8a8ac13614d17633d4f6e858bc46d0e5629558a024'}, 'baseline_sha256': {'docs/tablet/V653_WORKSPACE_REVIEW.md': None, 'execution/tablet_catalog_bridge.py': '8f5ba228a3c6bb2900acd26d5e5008e55e2049c4f6d70a62f27b00e2f1af9329', 'execution/tests/test_continuous_successor_v652.py': '7598f0a08610600bd68350077dea8f3fd071f45877811a86509ea191b66c8f61', 'execution/tests/test_tablet_learning_progress.py': None, 'execution/tests/test_workspace_features_v653.py': None, 'feature_category_nav.css': '9fdd7d9ec4373012f0568021fa66a8e052f0721944ec8cfd86533ebf217d8a7b', 'index.html': '3115f1925677d4d305a39de156cf8b5fdab44610f287c348483cc8a4a53b05db', 'social_event_discovery.py': 'e1067750e11e3c3a4af9005fbf4f42bcbaf008415a857d2c313a5be6393ff824', 'tablet_image_library_v1.js': 'a74f7eb6f08e24c7e60fb10748702328580e417cf723170c3320fb623e376d65', 'tablet_image_library_v1.py': 'd8c0d3809d4571a740d40b0e064729c7928ca5ae14fd5500f5a797c2d124092f', 'tcg_card_detail_v566.css': '28cf226ff692ab57c98ad95533257ef2195d330c41cfb2e1ce36ab7a7aa0e9b9', 'tcg_card_detail_v566.js': '87186e18ef098ea3bba56869a1de0f61db846103ee093cfaf1022601733dfe88', 'test_tablet_gpt_tcg_grader_sync_v652.py': 'd0e7faa8c57e3eecad1bfa9191682face4d3aad1189f2a8003891612a1a12251', 'test_tablet_learning_progress.py': 'cad089f6034dff188b330039f27c68132b2fcbf388966d11b659cc8c1b46adf2', 'update_promo_events.py': '3df84a23f7dd04b932a8ba8b81d74d8ffb0336f7c1d5917c923d8121f5ee3877'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v653_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V653_PROOF
    path=ROOT/'.github/tablet-autonomy/workspace_evidence_successor_v653.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V655_PROOF['reviewed_sha256']):
        assert_v655_successor(testcase)
    assert_v666_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V666_PROOF['reviewed_sha256'] and V666_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V666_PROOF['baseline_sha256'][name],digest,name)
        elif name in V655_PROOF['reviewed_sha256']:
            testcase.assertEqual(V655_PROOF['baseline_sha256'][name],digest,name)
        elif name == 'update_promo_events.py':
            _assert_v665_exact_pr814_source_successor(testcase,name,digest)
        elif digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V653 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V653 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v653_scope(visible,source,head='HEAD'):
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    visible=preserve_reviewed_v654_scope(visible,source,head)
    paths=set(V653_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v653_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V653_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V653_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible

V654_PROOF = {'schema': 'tablet-metadata-repair-successor/v654', 'base_commit': '6412c6cdf956f159805b058f4c08c06a86b9be41', 'candidate_commit': 'e5e898f8dd6e93fea5c4042e9ca2c763ab5d0421', 'reviewed_sha256': {'_audit_progress.py': None, 'docs/tablet/V654_METADATA_REPAIR.md': '3be190f595d17d9f83a60de684ad68fc721b9efe3838dc64ff640f63a7cce2cd', 'execution/tablet_image_metadata_repair.py': 'ea499f1daa587475bc18b8da993da6584c44bb7a03f60872ac0d32dd042d0a94', 'execution/tests/test_metadata_repair_v654.py': '30cd2ff07d26db3da119be2939517d22d3a44815c758e5da32f30032d2d9395e', 'execution/tests/test_workspace_successor_v653.py': '852e2fff8e6c2e4f358fce4a2c4c0354276d95a89fa1d9e70ffe716598989fcb', 'tablet_image_auto_v2.py': 'b6f5318e15c0ff68f1b8b4fd01beca9711478ea15842ebaff931578b6d61e48b', 'tablet_runtime_manifest.py': '9eaf980db06a4d6e9948a10fd130b0429c695293c1e9b16cd660aa0d1fa424a3'}, 'baseline_sha256': {'_audit_progress.py': 'e4561a89779fc9c8f4b4d474bc2ce4285b65174eb29a6bf20f47a5e30456d674', 'docs/tablet/V654_METADATA_REPAIR.md': None, 'execution/tablet_image_metadata_repair.py': None, 'execution/tests/test_metadata_repair_v654.py': None, 'execution/tests/test_workspace_successor_v653.py': '228a85eb1c56565804da953929677df8642e4ef86ad1ffd56c0a51e1beffb3b5', 'tablet_image_auto_v2.py': '356cbf5ce2d80b9499e9309ee70e01fa5108cfe756dea876a6f9c9ab98c8a164', 'tablet_runtime_manifest.py': '0c99b823ecb6f067788c91d55f548d0c965b8a6510091d8489dca4727cc02845'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v654_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V654_PROOF
    path=ROOT/'.github/tablet-autonomy/metadata_repair_successor_v654.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V655_PROOF['reviewed_sha256']):
        assert_v655_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V655_PROOF['reviewed_sha256']:
            testcase.assertEqual(V655_PROOF['baseline_sha256'][name],digest,name)
        elif name in V668_PROOF['reviewed_sha256']:
            testcase.assertEqual(V668_PROOF['baseline_sha256'][name],digest,name)
            assert_v668_successor(testcase)
        elif digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V654 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V654 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v654_scope(visible,source,head='HEAD'):
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    visible=preserve_reviewed_v655_scope(visible,source,head)
    paths=set(V654_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v654_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V654_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V654_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible

V655_PROOF = {'schema': 'tablet-official-source-successor/v655', 'base_commit': '19953a2e25a4369d07ae99f095c7f8008ba5d5bc', 'candidate_commit': '627e4727eae2b69ee4a96e3671928282eaffe849', 'reviewed_sha256': {'docs/tablet/V655_SOURCE_COLLECTION.md': '08535ce5ad1a72d62340a4d1d7acba0e37875c688541d1d9778abdf3176f1517', 'execution/official_social_discovery.py': 'b3901bdc27f79facca008d73dc4f812d34d8fd5696114fa57d8c604f45dd6020', 'execution/tests/test_current_runtime_verifier_v295.py': 'cdbe7dcd7018c4672dd94ae3f89017732d52fed44ca4c9df9fb334f19bcd437d', 'execution/tests/test_info_filters_v655.py': '55f92b753901990574c58def815ce3f9e26108aadb086c668b9bbccf73659757', 'execution/tests/test_metadata_successor_v654.py': '0ab5d306b45fcee052bfc7f0057f4ea3c5906a25e52cb6fa1e3a58ab3fff20c0', 'execution/tests/test_source_collection_v655.py': '80a161498175586b4b34d53ca71e14a2155de5e09b4d801725538ed2c484e5f2', 'execution/tests/verify_info_filters_v655.js': '2aae00b1307649898d160ccd7a64cc6b3dcc58fd23903293eb026aa73cc4cb59', 'feature_category_nav.css': '48e499427c7e1cff471a0c1cb13091b69ab7a4fd9ddabb7afd1e5c023c900a5d', 'index.html': '34550c2bc3c97f948a1b1908c689aea68d21d2ab629ba33e081b62890f732732', 'multi_route_event_discovery.py': '619729ec51e4c6b17c5b1f2a5cf7ffa856be5d5daae4970f46a36be5b010a00c', 'social_event_discovery.py': 'a1abcfaa0836bf0298638ea696b84f465e02af34c8b0a66ca9dc21fef4288521', 'tablet_runtime_manifest.py': 'c21c380700b9a441cfe5303b29319ae83f1cfd99d3c861485f7e71218eea67b2', 'test_current_runtime_verifier_v295.py': None, 'verify_browser_runtime.js': 'b844c5440313ba10a229dce18355e5055ba1571d69516f6b8349af3017777beb'}, 'baseline_sha256': {'docs/tablet/V655_SOURCE_COLLECTION.md': None, 'execution/official_social_discovery.py': None, 'execution/tests/test_current_runtime_verifier_v295.py': None, 'execution/tests/test_info_filters_v655.py': None, 'execution/tests/test_metadata_successor_v654.py': '54d0ca548c03f27e48dd076aef35abd7dd00c9be73f2436665bf3811bb63533c', 'execution/tests/test_source_collection_v655.py': None, 'execution/tests/verify_info_filters_v655.js': None, 'feature_category_nav.css': 'b0183d459ca17cc8e632453a4ecfcd1e7df4aa9a2ed9bf3e0e2347bdeeb2db83', 'index.html': '0716baf9d953e804446a49f956fb8ec578a1b3218f515d1e158735a88a6e1be6', 'multi_route_event_discovery.py': '2062ed6fd7f2ae996e8b10974acc3bb8b750ceb29e7670f7b6f5a4613f6424d4', 'social_event_discovery.py': 'bf6e44e66bdfaa605e3f55768255c5e70142c93d712f0be9bce26fbd383653e6', 'tablet_runtime_manifest.py': '9eaf980db06a4d6e9948a10fd130b0429c695293c1e9b16cd660aa0d1fa424a3', 'test_current_runtime_verifier_v295.py': 'cdbe7dcd7018c4672dd94ae3f89017732d52fed44ca4c9df9fb334f19bcd437d', 'verify_browser_runtime.js': '8e126fea09b4cf7fd2a2fe5f9453cef71ce563b64a317b4c89146d4aaba54df8'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v655_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V655_PROOF
    path=ROOT/'.github/tablet-autonomy/official_source_successor_v655.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    if set(proof['reviewed_sha256']) & set(V656_PROOF['reviewed_sha256']):
        assert_v656_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V657_PROOF['reviewed_sha256'] and V657_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V657_PROOF['baseline_sha256'][name],digest,name)
        elif name in V656_PROOF['reviewed_sha256']:
            testcase.assertEqual(V656_PROOF['baseline_sha256'][name],digest,name)
        elif digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V655 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V655 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v655_scope(visible,source,head='HEAD'):
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    visible=preserve_reviewed_v656_scope(visible,source,head)
    paths=set(V655_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v655_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V655_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V655_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible

V656_PROOF = {'schema': 'tablet-source-recovery-successor/v656', 'base_commit': '0aefc13834a202c4d5213476e6ba1281816369d2', 'candidate_commit': '3345fb845217d2d331b4feb80180c6a1ac9dfc12', 'reviewed_sha256': {'TABLET_SCHEDULED_UPDATE.sh': 'b6bd75a65089cf8e34a168eadcd4d05da1591d24301171da2204ea4f987e26c6', 'docs/tablet/V656_SOURCE_RECOVERY.md': 'c6a9c1f04ed3a98fb2d9cfd88fc3f73d53d5717a067b4ae411e8c342170a38b8', 'docs/tablet/V656_TERMUX_AUTOMATION.md': '6259dd78774e3318fb24d8851ed0cfdb082d0953e57f1a8f52ec5ab76e2c200d', 'execution/official_social_discovery.py': '1e9059055bb2f155d129d9986fae43314222060d0de1c7c701303dfb7c1f43f5', 'execution/tablet_local_automation.py': 'c600fe6c3fff9c4e69c256fad4dd22ceded7fbc28f395ac76a20700fcc0dd2ed', 'execution/tablet_local_learning.py': '6b95f175c694a07e571a40466f97f3bd5dc43ae4aa076f8249a7d0741ee3309c', 'execution/tests/test_grading_proxy_costs.py': 'ebd90d953fa58d1f3205284b74c3281a37fff81456ba5ce120b8ccadf7e4aa8a', 'execution/tests/test_source_recovery_v656.py': 'd23e49777b05d72a44d4c30500f9956e4231953516971177cf25f42563166fac', 'execution/tests/test_source_successor_v655.py': '04f3e2cd6cfb145eb0fb0e3bd03a18d34b2df9953efbf67d48ae933dbc12eca9', 'execution/tests/test_tablet_learning_entrypoint.py': 'ac9ae48b242f62e15415af8f0e4e02473ac46fb1d70303e3f3215fea9c4aba06', 'execution/tests/test_tablet_local_automation_v656.py': '9378c1d4d62b0b0bb2194b3c103dccf38041728b0fe8ca8ff2c91c5bd0e91fec', 'main': '20409d12bf5bf5b0caadf83a530f7d26b3520b8c330cce4ce6e1c26ef089c90e', 'social_event_discovery.py': '4672954b71d3df216f3abf231c4d594d4e8e70a191fe705911b11eb40fea270d', 'tablet_runtime_manifest.py': '81fe1354027dac2701571534e35acbd47cda46d038513e30f2a7f2d3664febff', 'test_grading_proxy_costs.py': None}, 'baseline_sha256': {'TABLET_SCHEDULED_UPDATE.sh': '7540f5954e2d8112e155b0e79c2e1fdda6d3161d84b34e8d4ccc82d4e58ee9c8', 'docs/tablet/V656_SOURCE_RECOVERY.md': None, 'docs/tablet/V656_TERMUX_AUTOMATION.md': None, 'execution/official_social_discovery.py': 'b3901bdc27f79facca008d73dc4f812d34d8fd5696114fa57d8c604f45dd6020', 'execution/tablet_local_automation.py': None, 'execution/tablet_local_learning.py': None, 'execution/tests/test_grading_proxy_costs.py': None, 'execution/tests/test_source_recovery_v656.py': None, 'execution/tests/test_source_successor_v655.py': '5afa09b9bf4e1a2b2156b75affa81316266e90988f4a0066c0bcbf514d73a354', 'execution/tests/test_tablet_learning_entrypoint.py': 'a8f6e22ca071c4d6454bab6287cdfe19bc32cf140b06aad0ca83a066dc1f0f62', 'execution/tests/test_tablet_local_automation_v656.py': None, 'main': '773b4120cba2d1050f8606275b5655441c50be62ee615fb2957510c5ab45bd02', 'social_event_discovery.py': 'a1abcfaa0836bf0298638ea696b84f465e02af34c8b0a66ca9dc21fef4288521', 'tablet_runtime_manifest.py': 'c21c380700b9a441cfe5303b29319ae83f1cfd99d3c861485f7e71218eea67b2', 'test_grading_proxy_costs.py': 'ebd90d953fa58d1f3205284b74c3281a37fff81456ba5ce120b8ccadf7e4aa8a'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v656_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V656_PROOF
    path=ROOT/'.github/tablet-autonomy/source_recovery_successor_v656.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v657_successor(testcase)
    assert_v661_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V661_PROOF['reviewed_sha256'] and V661_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V661_PROOF['baseline_sha256'][name],digest,name)
        elif name in V657_PROOF['reviewed_sha256'] and V657_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V657_PROOF['baseline_sha256'][name],digest,name)
        elif digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V656 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V656 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v656_scope(visible,source,head='HEAD'):
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    visible=preserve_reviewed_v657_scope(visible,source,head)
    paths=set(V656_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v656_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V656_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V656_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V657_PROOF = {'schema': 'tablet-learning-scan-provider-wait-successor/v657', 'base_commit': 'bec299218c6ae78c909c5461fe497dff16f3da56', 'candidate_commit': '4a1baf4fc3b52b1a81829b02070a58452854b33e', 'reviewed_sha256': {'docs/tablet/V657_COLLECTION_LEARNING_REVIEW.md': 'bd34ac0c7d523f6259a3dcd82fa8301fd800a8e8a60c75d300d6151c3a9fbd2d', 'execution/official_social_discovery.py': '1f1596821349b54a6eef6f9688e264231fea880b5c74db01b254a6a694655ae5', 'execution/tablet_local_automation.py': 'df1ed867a9acbeaf58d5979163106214502e0a67bfc2d9f64d5c237d26afbff7', 'execution/tablet_local_ui_review.py': 'abf6ade31a467b72e59cf5bae2a4c48a8e21bd41b6c50329a638d555bbae0445', 'execution/tests/test_info_filters_v655.py': '1a780c8f09548b18761d277bf635ca95fe93c14bc2077dc68b60bb31daca6f2f', 'execution/tests/test_learning_scan_budget_v657.py': '807702ffe522c0301b37288c146bdeac27ca3eb8db7fd48ca3818e0e6d0bea52', 'execution/tests/test_provider_wait_v657.py': '4962980f38cf0263f2e0a329f0ac1c536e4567a8036ede0598f8bcb29314baff', 'execution/tests/test_source_collection_v655.py': '1c14d815a429b4c1df2d0800dc0bec1d99c060112f52e0e865dbb12790fb1f1c', 'execution/tests/test_source_recovery_successor_v656.py': 'ecddb62c7b7a58acd83e173eb3c8947d87f4d2656e4442a7d444f527bec20ac3', 'execution/tests/test_tablet_local_automation_v656.py': '97e6ba37140892b10f07986c0f915c9a508f775cb8886d466d8f3e270acb558e'}, 'baseline_sha256': {'docs/tablet/V657_COLLECTION_LEARNING_REVIEW.md': None, 'execution/official_social_discovery.py': '1e9059055bb2f155d129d9986fae43314222060d0de1c7c701303dfb7c1f43f5', 'execution/tablet_local_automation.py': 'c600fe6c3fff9c4e69c256fad4dd22ceded7fbc28f395ac76a20700fcc0dd2ed', 'execution/tablet_local_ui_review.py': '4fa3dc6a3312e9babd244d2194b244b5bd744c621b8789a535bcc682903091e2', 'execution/tests/test_info_filters_v655.py': '55f92b753901990574c58def815ce3f9e26108aadb086c668b9bbccf73659757', 'execution/tests/test_learning_scan_budget_v657.py': None, 'execution/tests/test_provider_wait_v657.py': None, 'execution/tests/test_source_collection_v655.py': '80a161498175586b4b34d53ca71e14a2155de5e09b4d801725538ed2c484e5f2', 'execution/tests/test_source_recovery_successor_v656.py': 'b03ba0266fefc6519c8713ce0b6f827a6e5af2e92f4ef195e5800501b692f268', 'execution/tests/test_tablet_local_automation_v656.py': '9378c1d4d62b0b0bb2194b3c103dccf38041728b0fe8ca8ff2c91c5bd0e91fec'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v657_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V657_PROOF
    path=ROOT/'.github/tablet-autonomy/learning_scan_successor_v657.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v658_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if name in V658_PROOF['reviewed_sha256'] and V658_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V658_PROOF['baseline_sha256'][name],digest,name)
        elif digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V657 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V657 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v657_scope(visible,source,head='HEAD'):
    visible=_preserve_v668_exact_later_fixture(visible,source,head)
    visible=_preserve_v665_exact_later_source(visible,source,head)
    visible=preserve_reviewed_v661_scope(visible,source,head)
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    visible=preserve_reviewed_v658_scope(visible,source,head)
    paths=set(V657_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v657_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V657_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V657_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V658_PROOF = {'schema': 'tablet-verification-repair-successor/v658', 'base_commit': '7e73d62637a97681830689133ee97df8bae339fe', 'candidate_commit': '8990c3ecb0e7c42f38a2ce1fcbfa94fd9ae6dc63', 'reviewed_sha256': {'README_v31.md': 'ff1dba5b0472104f84e8d8193f5705c0465aaf4700a7bbef3dd38438b5ac0de8', 'execution/tests/test_card_catalog_region_isolation_v317.py': 'f98502a8bbe4cef9366e25b55a13c8997ba28c47b746fcfe35a1153114e28cbe', 'execution/tests/test_collection_coverage_completion_v143.py': 'e1db13ff7997f318b498ebc7e22a732379243cc482f710ad22b035eea9e77551', 'execution/tests/test_info_filters_v655.py': '33c67491441aac4fda0260ef2f20cda11fe9259c34ad4950f0e3205f63d8fdaa', 'execution/tests/test_learning_successor_v657.py': 'e386d5ce2b505d0aa2f7ba94fc14d85b3db0ecd54a6f96711548673ea9df2e21', 'test_tablet_gpt_tcg_grader_sync_v657.py': 'e2b66f699de28ff688af3ddba7d426252e758643ad65c2da395881d6f316df60', 'docs/archive/README_v31.md': None, 'test_card_catalog_region_isolation_v317.py': None, 'test_collection_coverage_completion_v143.py': None}, 'baseline_sha256': {'README_v31.md': None, 'execution/tests/test_card_catalog_region_isolation_v317.py': None, 'execution/tests/test_collection_coverage_completion_v143.py': None, 'execution/tests/test_info_filters_v655.py': '1a780c8f09548b18761d277bf635ca95fe93c14bc2077dc68b60bb31daca6f2f', 'execution/tests/test_learning_successor_v657.py': '98f09db0e8888b4c52d6813d7c36f8d9dfc05bb8f72bb79b5fc08188fb3affe1', 'test_tablet_gpt_tcg_grader_sync_v657.py': '257018e9732f11e15971cd480e9d9cdce7ce598ec5550d4645dd3708f719c143', 'docs/archive/README_v31.md': 'ff1dba5b0472104f84e8d8193f5705c0465aaf4700a7bbef3dd38438b5ac0de8', 'test_card_catalog_region_isolation_v317.py': 'f98502a8bbe4cef9366e25b55a13c8997ba28c47b746fcfe35a1153114e28cbe', 'test_collection_coverage_completion_v143.py': 'e1db13ff7997f318b498ebc7e22a732379243cc482f710ad22b035eea9e77551'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v658_successor(testcase):
    """Immutable ancestry/source pins plus uncached live bytes, no device claim."""
    proof=V658_PROOF
    path=ROOT/'.github/tablet-autonomy/verification_repair_successor_v658.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    for name,digest in proof['reviewed_sha256'].items():
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        current=ROOT/name
        testcase.assertFalse(current.is_symlink(),name)
        if digest is None:testcase.assertFalse(current.exists(),'unreviewed restored V658 path: '+name)
        else:
            testcase.assertTrue(current.is_file(),name)
            testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,'unreviewed V658 current source: '+name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)

def preserve_reviewed_v658_scope(visible,source,head='HEAD'):
    visible=_preserve_v665_exact_later_source(visible,source,head)
    visible=preserve_reviewed_v661_scope(visible,source,head)
    """Hide only exact new reviewed bytes, never an earlier or divergent edit."""
    paths=set(V658_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v658_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V658_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only',source+'..'+V658_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V659_CI_PROOF = {'schema': 'tablet-alignment-partition-successor/v659', 'base_commit': 'd98f17324506cb6e673c621a3e414f5248e2dd01', 'candidate_commit': '474ad5afe8207cae2ef8341f40aabbac4a5b99ef', 'reviewed_sha256': {'.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml': 'f1141310f15215d1375c2c36ffa6a760532c5d20d278a43d0021f155c4652a68'}, 'baseline_sha256': {'.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml': '83d6bf6009269550311fd2b242ed5e95145b5c4a67554c16f3127e6ca5f3acbb'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v659_ci_successor(testcase):
    proof=V659_CI_PROOF
    path=ROOT/'.github/tablet-autonomy/alignment_partition_successor_v659.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name
        testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest))
        testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


V661_PROOF = {'schema': 'tablet-image-autonomy-successor/v661', 'base_commit': '7fe4c91054eb734541fb1d8c04c8cd8f7b9932df', 'candidate_commit': 'a5c6b08a980587fab67ace7dfbf0e163499c5c12', 'reviewed_sha256': {'docs/tablet/V660_IMAGE_TRAINING_CHALLENGER.md': '46a37136cf3335de24e53b5703c6cb795a55d514deef6e7c6aadfabe3e81c068', 'docs/tablet/V661_IMAGE_AUTOMATION.md': '79ce5fa3183e0f5743fd573ebc5ab52df80fca5a59b80358dce663e09e6797ef', 'execution/tablet_image_autonomy.py': 'f2eb68829ceb277000282908e0ad64141b9716201bc6b7fdc58535cda8269886', 'execution/tablet_image_model_gate.py': '7a6541b9374107bf5acda9e6aaf18f29ac63a04f55b524960f2f14119aa93a1b', 'execution/tablet_image_training.py': '620b8cf75c13f3a32c38bea011d1725d2893314bab134192b351960cfc7052ab', 'execution/tablet_local_learning.py': 'c1a43515e60ba791575ff61ba5c478b131f6c13c251ab0eba8f2d06d40ad519e', 'execution/tablet_vision_readiness.py': 'e1de7e18ed839bc7272433d80d50e660847d972092f7fc05ba95a7d71704fadb', 'execution/tests/test_free_only_ai_code_improver_v619.py': 'a88e01c7b4d7b79502cefb993ed7ddd1ce9383bb9c6690aff1f622a3d29ba9e6', 'execution/tests/test_image_autonomy_v661.py': '44487c7ccf14313e383de10c71d1ca49f0298dddb07abb2b3946405ef5d42021', 'execution/tests/test_tablet_image_training.py': '2bc84da71589159d39d936850835beaff8ab64db422642a1b5803282b67ffe8b', 'tablet_runtime_manifest.py': '3956c07d4328a829f8c72f1098fe7a8c6a3c2b00b3c105ada628029fb34ff987', 'test_free_only_ai_code_improver_v619.py': None}, 'baseline_sha256': {'docs/tablet/V660_IMAGE_TRAINING_CHALLENGER.md': '6cd190e45ccc0443e67143cf5b6514ff609bbf4d6413068995da29ef93fe2ef9', 'docs/tablet/V661_IMAGE_AUTOMATION.md': None, 'execution/tablet_image_autonomy.py': None, 'execution/tablet_image_model_gate.py': None, 'execution/tablet_image_training.py': 'a49eebcf8b69b5829f7953e35b49ef48b3574a2db1eda5bc9422c4f32aa559f8', 'execution/tablet_local_learning.py': '6b95f175c694a07e571a40466f97f3bd5dc43ae4aa076f8249a7d0741ee3309c', 'execution/tablet_vision_readiness.py': '4862d8ac76a91e343ec3ac39fb244640ee419e8d186d3b8b87b174b1880862e4', 'execution/tests/test_free_only_ai_code_improver_v619.py': None, 'execution/tests/test_image_autonomy_v661.py': None, 'execution/tests/test_tablet_image_training.py': '69e79e0f903e69adab554142ad5edfc4b9bf05025bce5103645d838355b6c285', 'tablet_runtime_manifest.py': '81fe1354027dac2701571534e35acbd47cda46d038513e30f2a7f2d3664febff', 'test_free_only_ai_code_improver_v619.py': 'a88e01c7b4d7b79502cefb993ed7ddd1ce9383bb9c6690aff1f622a3d29ba9e6'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v661_successor(testcase):
    proof=V661_PROOF
    path=ROOT/'.github/tablet-autonomy/image_autonomy_successor_v661.json'
    testcase.assertFalse(path.is_symlink());testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v662_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name;testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        if digest is None:testcase.assertFalse(current.exists(),name)
        elif name in V664_PROOF['reviewed_sha256'] and V664_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V664_PROOF['baseline_sha256'][name],digest,name)
        elif name in V662_PROOF['reviewed_sha256'] and V662_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V662_PROOF['baseline_sha256'][name],digest,name)
        else:testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)


def preserve_reviewed_v661_scope(visible,source,head='HEAD'):
    visible=preserve_reviewed_v662_scope(visible,source,head)
    paths=set(V661_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v661_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V661_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only','--no-renames',source+'..'+V661_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V662_PROOF = {'schema': 'tablet-image-retention-successor/v662', 'base_commit': '8e03c422628c8368555a5631995b74e3f64ea0a6', 'candidate_commit': 'ecdb7b7ba381fbb6c141ff1838fe7a217d46bc86', 'reviewed_sha256': {'docs/tablet/V661_IMAGE_AUTOMATION.md': '18f95dd2de4bbc8cde50381ee1e4c52e71ef508e88acaf2f800dbbe59fa86359', 'execution/tablet_image_training.py': '6509aa2a393072410d861727eb9296618a34cf8f958204e63c1f1971c35e4f5d', 'execution/tests/test_image_autonomy_v661.py': '8159ecc3a981e35f4e538c56c8058fc947debf1d2d700cae816d89aba6821bd1', 'execution/tests/test_v426_successor_path_diagnostics_v635.py': '818ed0bc1a1256087db062cdb9fced84a04e3f878ea5ca1c60160ea3e6519eeb', 'test_v426_successor_path_diagnostics_v635.py': None}, 'baseline_sha256': {'docs/tablet/V661_IMAGE_AUTOMATION.md': '79ce5fa3183e0f5743fd573ebc5ab52df80fca5a59b80358dce663e09e6797ef', 'execution/tablet_image_training.py': '620b8cf75c13f3a32c38bea011d1725d2893314bab134192b351960cfc7052ab', 'execution/tests/test_image_autonomy_v661.py': '44487c7ccf14313e383de10c71d1ca49f0298dddb07abb2b3946405ef5d42021', 'execution/tests/test_v426_successor_path_diagnostics_v635.py': None, 'test_v426_successor_path_diagnostics_v635.py': '818ed0bc1a1256087db062cdb9fced84a04e3f878ea5ca1c60160ea3e6519eeb'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v662_successor(testcase):
    proof=V662_PROOF
    path=ROOT/'.github/tablet-autonomy/image_retention_successor_v662.json'
    testcase.assertFalse(path.is_symlink());testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v663_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name;testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        if digest is None:testcase.assertFalse(current.exists(),name)
        elif name in V663_PROOF['reviewed_sha256'] and V663_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V663_PROOF['baseline_sha256'][name],digest,name)
        else:testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)



def preserve_reviewed_v662_scope(visible,source,head='HEAD'):
    visible=preserve_reviewed_v663_scope(visible,source,head)
    paths=set(V662_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v662_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V662_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only','--no-renames',source+'..'+V662_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V663_PROOF = {'schema': 'tablet-image-cache-budget-successor/v663', 'base_commit': '038e32aa7d0db8307e2945aee93af9e4e86f91e1', 'candidate_commit': '50d353db55a9075c5be2d17429ec1e1621fc054f', 'reviewed_sha256': {'docs/tablet/V663_IMAGE_CACHE_BUDGET.md': '97f78a7c3f9473fda1ffa32af0a42e05fd91c34baccc70eb7da30153689588cf', 'execution/tablet_image_training.py': '4c19fc8cbd5dcbe95c015ffcf615e5e404c1a892037441213dc91f5f24c26132', 'execution/tests/test_image_cache_budget_v663.py': '8184de9625294da5731443ee8672bb94558a191319a0d24bcbb5630d0c4c418b', 'execution/tests/test_pokemon_retired_link_migration_v356.py': '0f9c27be9f380405ce5e140ccd8363465bcfa22b29e7ea26047fb38ec4513b09', 'test_pokemon_retired_link_migration_v356.py': None}, 'baseline_sha256': {'docs/tablet/V663_IMAGE_CACHE_BUDGET.md': None, 'execution/tablet_image_training.py': '6509aa2a393072410d861727eb9296618a34cf8f958204e63c1f1971c35e4f5d', 'execution/tests/test_image_cache_budget_v663.py': None, 'execution/tests/test_pokemon_retired_link_migration_v356.py': None, 'test_pokemon_retired_link_migration_v356.py': '0f9c27be9f380405ce5e140ccd8363465bcfa22b29e7ea26047fb38ec4513b09'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v663_successor(testcase):
    proof=V663_PROOF
    path=ROOT/'.github/tablet-autonomy/image_cache_budget_successor_v663.json'
    testcase.assertFalse(path.is_symlink());testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v664_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name;testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        if digest is None:testcase.assertFalse(current.exists(),name)
        elif name in V664_PROOF['reviewed_sha256'] and V664_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V664_PROOF['baseline_sha256'][name],digest,name)
        else:testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)




def preserve_reviewed_v663_scope(visible,source,head='HEAD'):
    visible=preserve_reviewed_v664_scope(visible,source,head)
    paths=set(V663_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v663_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V663_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only','--no-renames',source+'..'+V663_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V664_PROOF = {'schema': 'tablet-image-worker-isolation-successor/v664', 'base_commit': 'c1fa775c630b18ca98abece0578df218391be11b', 'candidate_commit': 'f60d909a4bc9eee3e2430183754b104f8939aece', 'reviewed_sha256': {'docs/tablet/V664_IMAGE_WORKER_ISOLATION.md': '6d0e1767e69b19e5a40fc27c3386cf88b352e711b38d7d4539124aaa052ffe05', 'execution/tablet_image_autonomy.py': 'a899004500b58a0a2c0ffc12a8662828f0480159d640163dcf32d3bd60e08fba', 'execution/tablet_image_training.py': '4436c894186bda40292cc14cf8a65057170273d07dbde8c7f54988ff4653e579', 'execution/tests/test_image_worker_isolation_v664.py': '046e1b501b3d8f2eb2921faabd1391018bfe38e6ad698078f4a6a60141d85a55', 'execution/tests/test_promo_discovery_worker_isolation_v513.py': 'fda68e41936984552e55a7699a0ab62fb421c83cb36bbfde7f7d4f726224b80e', 'test_promo_discovery_worker_isolation_v513.py': None}, 'baseline_sha256': {'docs/tablet/V664_IMAGE_WORKER_ISOLATION.md': None, 'execution/tablet_image_autonomy.py': 'f2eb68829ceb277000282908e0ad64141b9716201bc6b7fdc58535cda8269886', 'execution/tablet_image_training.py': '4c19fc8cbd5dcbe95c015ffcf615e5e404c1a892037441213dc91f5f24c26132', 'execution/tests/test_image_worker_isolation_v664.py': None, 'execution/tests/test_promo_discovery_worker_isolation_v513.py': None, 'test_promo_discovery_worker_isolation_v513.py': 'fda68e41936984552e55a7699a0ab62fb421c83cb36bbfde7f7d4f726224b80e'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v664_successor(testcase):
    proof=V664_PROOF
    path=ROOT/'.github/tablet-autonomy/image_worker_isolation_successor_v664.json'
    testcase.assertFalse(path.is_symlink());testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v666_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name;testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        if digest is None:testcase.assertFalse(current.exists(),name)
        elif name in V666_PROOF['reviewed_sha256'] and V666_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V666_PROOF['baseline_sha256'][name],digest,name)
        else:testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)





def preserve_reviewed_v664_scope(visible,source,head='HEAD'):
    visible=preserve_reviewed_v666_scope(visible,source,head)
    paths=set(V664_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v664_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V664_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only','--no-renames',source+'..'+V664_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


def _assert_v665_exact_pr814_source_successor(testcase,name,prior_digest):
    """Delegate ONLY the two immutable V665 source descendants; any tamper fails closed.

    Historical V645/V653 pins stay unchanged. New evidence must be present,
    ancestry and BOTH source hashes exact, and the append-only digest chained.
    """
    from execution.pr814_source_preflight_v665 import (
        EXPECTED as source_proof, Hold as SourceHold,
        load as load_source_proof, verify as verify_source_proof,
    )
    testcase.assertIn(name, source_proof['reviewed_sha256'])
    testcase.assertEqual(source_proof['reviewed_sha256'][name]['before'],prior_digest)
    try:
        outcome=verify_source_proof(ROOT,load_source_proof(ROOT))
    except (SourceHold, OSError, ValueError) as error:
        testcase.fail('PR814 V665 source proof missing/invalid: '+str(error))
    testcase.assertEqual(outcome['decision'],'SOURCE_PREFLIGHT_ONLY')
    contract_path=ROOT/'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V665.json'
    testcase.assertFalse(contract_path.is_symlink())
    c=_read(contract_path)
    d=_read(ROOT/c['delta_snapshot'])
    r=_read(ROOT/c['receiver_receipt'])
    prior=_read(ROOT/c['prior_contract'])
    prior_delta=_read(ROOT/c['prior_delta_snapshot'])
    testcase.assertEqual(c['prior_contract'],'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V664.json')
    testcase.assertEqual(c['rules'],prior['rules'])
    testcase.assertEqual(c['candidate_sync']['base_main_sha'],source_proof['base_commit'])
    testcase.assertEqual(c['candidate_sync']['candidate_commit'],source_proof['candidate_commit'])
    testcase.assertEqual(set(c['candidate_sync']['watched_paths']),set(source_proof['reviewed_sha256']))
    testcase.assertEqual(c['current_required_lesson_count'],prior['current_required_lesson_count']+len(d['lessons']))
    serialized=json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
    current_digest=hashlib.sha256(serialized.encode()).hexdigest()
    testcase.assertEqual(d['lesson_digest_sha256'],current_digest)
    testcase.assertEqual(r['delta_lesson_digest_sha256'],current_digest)
    testcase.assertEqual(prior_delta['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
    testcase.assertEqual(prior_delta['lesson_digest_sha256'],r['prior_lesson_digest_sha256'])
    testcase.assertEqual([x['lesson_id'] for x in d['lessons']],r['accepted_lesson_ids'])
    testcase.assertIs(r['verification']['physical_tablet_runtime_verified'],False)
    testcase.assertIs(r['verification']['physical_drive_readback_verified'],False)
    testcase.assertIs(source_proof['deployment_allowed'],False)
    testcase.assertIs(source_proof['legacy_successor_ci_repaired'],False)


def _preserve_v665_exact_later_source(visible,source,head='HEAD'):
    """Only mask an EXACT new V665 source descendant with immutable ancestry.

    Any watched path edited before the V665 base or modified again after
    the pinned candidate remains visible.  Invalid proof also remains visible.
    """
    from execution.pr814_source_preflight_v665 import EXPECTED as proof
    if head != 'HEAD':
        return visible
    affected=set(visible).intersection(proof['reviewed_sha256'])
    if not affected:
        return visible
    try:
        ancestor=subprocess.run(
            ['git','merge-base','--is-ancestor',source,proof['base_commit']],
            cwd=ROOT,capture_output=True,timeout=20)
        if ancestor.returncode:
            return visible
        historical=set(subprocess.check_output(
            ['git','diff','--name-only','--no-renames',source+'..'+proof['base_commit'],
             '--',*sorted(affected)],cwd=ROOT,text=True,timeout=20
        ).splitlines())
        import unittest
        covered=affected-historical
        for path in sorted(covered):
            _assert_v665_exact_pr814_source_successor(
                unittest.TestCase(),path,proof['reviewed_sha256'][path]['before'])
        return [path for path in visible if path not in covered]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,
            subprocess.SubprocessError):
        return visible


V666_PROOF = {'schema': 'tablet-evidence-boundary-successor/v666', 'base_commit': 'a8d4cf1757dd46b353c2ef09609ba573e2ca53da', 'candidate_commit': '8febc24f73605a9ad90c5d7460e54787eb15b233', 'reviewed_sha256': {'docs/tablet/V666_EVIDENCE_BOUNDARIES.md': 'fa2e3fca3b91bee7c09072a2cc915fde68fdcc657dbd60f3e6cd8911876e38aa', 'execution/pr814_source_preflight_v665.py': '2214fa83d458e8a29cf5dd9f75bb519486f71d9dd29f8f4f65a4da0cb40e53e4', 'execution/tablet_image_training.py': '069d078185d637b9dd19f89cf3e137aa6718dc74598732a9a16cef2c439dd21d', 'execution/tests/test_dashboard_verified_boundary_v246.py': '274913d5b631bb2f4ba817b07dd28f5f02bd154cbbaf80209a616618465e3cbd', 'execution/tests/test_image_receipt_integrity_v666.py': 'da6f7cc2a12b202058128d494fd1b2b8f7dc4e9c1a9adb346d02536dcdba0f58', 'execution/tests/test_tablet_learning_progress.py': 'd6c7b9db51b4e7cf16fd019378b068944e9ebdc455fdca0a8a84aab6284ed13c', 'tcg_reliability/china_official_catalog_v571.py': 'c632c95388cfa695380eabae83c9e37b6caa02cd3c5ec600c55e327730418116', 'tcg_reliability/test_china_catalog_retry_20261025.py': '4c8f3ed03c3f36c0bad134dee6abc606ddcbb8e3d59fbc6f52e6080dbcc61a2d', 'tcg_reliability/test_china_official_catalog_v571.py': 'd4734ac4958b0feb901732555851d1216057df437bc16164012dbe4f64d0e7df', 'tcg_reliability/test_event_title_date_safety_20261025.py': 'cc7b79ba2763c4e49fc16cdfa725bc52a185122d0b42c829d7a6529b78f0eb38', 'tcg_reliability/test_job_neural_postflight_20261025.py': '6446ba534f4340bf383e1c7d3340bcf14f44b4d686a4b1b2bc44f201ce9d91f8', 'tcg_reliability/test_neural_label_safety_20261025.py': 'f71cf639e780cb1c47128c19291475d821dcc6581aa35ddc0150efa3c2043d07', 'test_dashboard_verified_boundary_v246.py': None, 'test_verified_collection_neural_v211.py': 'fa30efe62cc68af1e79238f1c2fce6bdd0a13411a13df6bdfc20399b8ad7ca66', 'update_promo_events.py': 'b4d76df619e67ad222ac488de09202d9f1c2b993dc9ba3dfed1ba1f8f630cef3', 'verified_collection_job_neural.py': '231a13ceaa58fe27b8d70bfd24f557f41480d848cdfb98c332909d3c86b0fcaf', 'verified_collection_neural.py': '45e1ca15ecaba0780722e6880561ce051074c5f1fb53f1577d052b975661cefd', 'verify_all_legacy_v99.py': '4f5ab6752a96708e51f53226545ea687ce233effbc7a6af35863821844946c9b'}, 'baseline_sha256': {'docs/tablet/V666_EVIDENCE_BOUNDARIES.md': None, 'execution/pr814_source_preflight_v665.py': '332e2e71cc5f696aa988a2d969d20d2158949f07f3ec82fb4ed19a7ff0c3824d', 'execution/tablet_image_training.py': '4436c894186bda40292cc14cf8a65057170273d07dbde8c7f54988ff4653e579', 'execution/tests/test_dashboard_verified_boundary_v246.py': None, 'execution/tests/test_image_receipt_integrity_v666.py': None, 'execution/tests/test_tablet_learning_progress.py': 'cad089f6034dff188b330039f27c68132b2fcbf388966d11b659cc8c1b46adf2', 'tcg_reliability/china_official_catalog_v571.py': '5321afb65d990ccdab8ba300fa3ea3181a2e32742a2b78f9dc66e8ef8a5f3cd2', 'tcg_reliability/test_china_catalog_retry_20261025.py': '46f76dc58a9b87d8986ba9f02e5512cad2e0ef38494b872561f57ff7bcb2639b', 'tcg_reliability/test_china_official_catalog_v571.py': '869709910ad016be5618ab4373a1ba3102a9e3750deaab7feaa4e00ca3366abb', 'tcg_reliability/test_event_title_date_safety_20261025.py': '2149bc3caebaaacf69237f8686551e8960d6ee421883a0dfec988ad1128b720c', 'tcg_reliability/test_job_neural_postflight_20261025.py': 'da8eaf22f8e823d70e9db04fe9135accd526e03ff9920eff212ef47ddc975efe', 'tcg_reliability/test_neural_label_safety_20261025.py': '3e37b5136f797d938e5939969e01c1e59ae22336f2f575d71362d0fcf1f6b71c', 'test_dashboard_verified_boundary_v246.py': '274913d5b631bb2f4ba817b07dd28f5f02bd154cbbaf80209a616618465e3cbd', 'test_verified_collection_neural_v211.py': '5063ee2d59a1bfe3d3cf69a931048e341cdbf0cc2f36ae1cfb61517dc9ad37c1', 'update_promo_events.py': '86c6fca020d22d92b176d26199fd4543bdc1294a6e851805caf199d95fc6e843', 'verified_collection_job_neural.py': 'dc13eefddaae9c5b5f21a0ffd71be6b1c17af0f1849de52fe37cdf75d355939a', 'verified_collection_neural.py': '09651a9cffdf490eed79512077a6c1efa292b1a56799887abac469f0b2731a32', 'verify_all_legacy_v99.py': 'd61729ada28344cc32dea53fbcbab5c61debfc032a92e21f3dbac7653f985098'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v666_successor(testcase):
    proof=V666_PROOF
    path=ROOT/'.github/tablet-autonomy/evidence_boundaries_successor_v666.json'
    testcase.assertFalse(path.is_symlink());testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    assert_v667_successor(testcase)
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name;testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        if digest is None:testcase.assertFalse(current.exists(),name)
        elif name in V667_PROOF['reviewed_sha256'] and V667_PROOF['baseline_sha256'][name]==digest:
            testcase.assertEqual(V667_PROOF['baseline_sha256'][name],digest,name)
        else:testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)






def preserve_reviewed_v666_scope(visible,source,head='HEAD'):
    visible=preserve_reviewed_v667_scope(visible,source,head)
    paths=set(V666_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v666_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V666_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only','--no-renames',source+'..'+V666_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V667_PROOF = {'schema': 'tablet-evidence-boundary-successor/v667', 'base_commit': '951fd31ddda68362f07db46cc7a441e01ad9e6db', 'candidate_commit': '5a3c43f3e5b59966f2658c19adbb82886fb1dd78', 'reviewed_sha256': {'docs/tablet/V667_FULL_SWEEP_RECOVERY.md': '9a6fb3381e767490c96d97db179be972cfd5d0c8b3abe9fc28c1d7cc922ea23a', 'execution/pr814_source_preflight_v665.py': '7b28428d3b4a6738ca3099965a41917404c06accb0551136e296a3c09820c33a', 'execution/tests/test_manual_registration_delete_v151.py': 'be4bdf6602b9f099ea3f5b7b84115ed5bc4a57e5c35352d770c5709d500b7747', 'execution/tests/test_source_object_cache_v667.py': '7da23912e6ad020aa9b0f03402ea678fac33cd9005fc8df5b12ace37ab021000', 'tcg_reliability/test_neural_label_safety_20261025.py': '6832fa2de69ddf1ad7426a71064211f601befe0d0cd6941c13b7c1d7ffb2d7ee', 'test_collection_scope_compat_v214.py': 'ac63e01d92d5bf28412ef3d3c513618df1fdb14b91cf571eb1440ffa8df37336', 'test_manual_registration_delete_v151.py': None, 'verified_collection_neural.py': '884975e33992e727ed14410c5957eeb167dcb1dc9e38bc7fdf4ee682058a1932'}, 'baseline_sha256': {'docs/tablet/V667_FULL_SWEEP_RECOVERY.md': None, 'execution/pr814_source_preflight_v665.py': '2214fa83d458e8a29cf5dd9f75bb519486f71d9dd29f8f4f65a4da0cb40e53e4', 'execution/tests/test_manual_registration_delete_v151.py': None, 'execution/tests/test_source_object_cache_v667.py': None, 'tcg_reliability/test_neural_label_safety_20261025.py': 'f71cf639e780cb1c47128c19291475d821dcc6581aa35ddc0150efa3c2043d07', 'test_collection_scope_compat_v214.py': 'bbf6f34e561eb884ffddb7fc2b05e6dc2b6052ad352697e526a60e6be534c22b', 'test_manual_registration_delete_v151.py': 'be4bdf6602b9f099ea3f5b7b84115ed5bc4a57e5c35352d770c5709d500b7747', 'verified_collection_neural.py': '45e1ca15ecaba0780722e6880561ce051074c5f1fb53f1577d052b975661cefd'}, 'candidate_auxiliary_paths': ['integrity_manifest.json'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False}

def assert_v667_successor(testcase):
    proof=V667_PROOF
    path=ROOT/'.github/tablet-autonomy/evidence_boundaries_successor_v667.json'
    testcase.assertFalse(path.is_symlink());testcase.assertEqual(_read(path),proof)
    base,candidate=proof['base_commit'],proof['candidate_commit']
    ancestor,changed,rows=_v646_immutable_commit_evidence(base,candidate,tuple(proof['reviewed_sha256']))
    testcase.assertEqual(ancestor,0)
    testcase.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',candidate,'HEAD'],cwd=ROOT,capture_output=True).returncode,0)
    testcase.assertEqual(changed,set(proof['reviewed_sha256'])|set(proof['candidate_auxiliary_paths']))
    for name,digest in proof['reviewed_sha256'].items():
        current=ROOT/name;testcase.assertFalse(current.is_symlink())
        testcase.assertEqual(rows[name],(proof['baseline_sha256'][name],digest),name)
        if digest is None:testcase.assertFalse(current.exists(),name)
        else:testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),digest,name)
    testcase.assertIs(proof['physical_tablet_runtime_verified'],False)
    testcase.assertIs(proof['deployment_allowed'],False)







def preserve_reviewed_v667_scope(visible,source,head='HEAD'):
    paths=set(V667_PROOF['reviewed_sha256'])
    if head!='HEAD' or not paths.intersection(visible):return visible
    import unittest
    try:
        assert_v667_successor(unittest.TestCase())
        if subprocess.run(['git','merge-base','--is-ancestor',source,V667_PROOF['base_commit']],cwd=ROOT,capture_output=True).returncode!=0:return visible
        older=set(subprocess.check_output(['git','diff','--name-only','--no-renames',source+'..'+V667_PROOF['base_commit'],'--',*sorted(paths)],cwd=ROOT,text=True).splitlines())
        return [p for p in visible if p not in paths or p in older]
    except (AssertionError,OSError,UnicodeError,ValueError,KeyError,subprocess.SubprocessError):return visible


V668_PROOF = {
    'schema': 'tablet-workspace-fixture-successor/v668',
    'base_commit': 'dd975b8f6e278bffbd7cdb4e85e49cfc57fa5fbe',
    'candidate_commit': '34930e9b3f55416b290368ee44a7c024395cf797',
    'reviewed_sha256': {
        'execution/tests/test_workspace_successor_v653.py':
        'e24ffbc4893593fe16cb5e9beafc922a2bbb3ad7f92fe785f6bba675218fd2e1',
    },
    'baseline_sha256': {
        'execution/tests/test_workspace_successor_v653.py':
        '852e2fff8e6c2e4f358fce4a2c4c0354276d95a89fa1d9e70ffe716598989fcb',
    },
    'candidate_auxiliary_paths': ['integrity_manifest.json'],
    'physical_tablet_runtime_verified': False,
    'deployment_allowed': False,
}


def assert_v668_successor(testcase):
    """Preserve V654 test hash, plus exact V668 replacement and V666 learning bytes."""
    proof = V668_PROOF
    path = ROOT / '.github/tablet-autonomy/workspace_fixture_successor_v668.json'
    testcase.assertFalse(path.is_symlink())
    testcase.assertEqual(_read(path), proof)
    base, candidate = proof['base_commit'], proof['candidate_commit']
    name = 'execution/tests/test_workspace_successor_v653.py'
    ancestor, changed, rows = _v646_immutable_commit_evidence(base, candidate, (name,))
    testcase.assertEqual(ancestor, 0)
    testcase.assertEqual(subprocess.run(
        ['git', 'merge-base', '--is-ancestor', candidate, 'HEAD'],
        cwd=ROOT, capture_output=True).returncode, 0)
    testcase.assertEqual(changed, set(proof['reviewed_sha256']) | set(proof['candidate_auxiliary_paths']))
    testcase.assertEqual(proof['baseline_sha256'][name], V654_PROOF['reviewed_sha256'][name])
    testcase.assertEqual(rows[name], (proof['baseline_sha256'][name], proof['reviewed_sha256'][name]))
    current = ROOT / name
    testcase.assertFalse(current.is_symlink())
    testcase.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(), proof['reviewed_sha256'][name])
    original = _v668_historical_bytes(V653_PROOF['base_commit'], 'test_tablet_learning_progress.py')
    moved = _v668_historical_bytes(
        V653_PROOF['candidate_commit'], 'execution/tests/test_tablet_learning_progress.py')
    testcase.assertEqual(original, moved)
    before_v666 = _v668_historical_bytes(
        V666_PROOF['base_commit'], 'execution/tests/test_tablet_learning_progress.py')
    testcase.assertEqual(moved, before_v666)
    after_v666 = _v668_historical_bytes(
        V666_PROOF['candidate_commit'], 'execution/tests/test_tablet_learning_progress.py')
    lesson = 'execution/tests/test_tablet_learning_progress.py'
    testcase.assertEqual(hashlib.sha256(before_v666).hexdigest(), V666_PROOF['baseline_sha256'][lesson])
    testcase.assertEqual(hashlib.sha256(after_v666).hexdigest(), V666_PROOF['reviewed_sha256'][lesson])
    target = ROOT / lesson
    testcase.assertFalse(target.is_symlink())
    testcase.assertEqual(target.read_bytes(), after_v666)
    testcase.assertFalse((ROOT / 'test_tablet_learning_progress.py').exists())
    testcase.assertIs(proof['physical_tablet_runtime_verified'], False)
    testcase.assertIs(proof['deployment_allowed'], False)


@lru_cache(maxsize=12)
def _v668_historical_bytes(commit, path):
    """Cache ONLY immutable Git objects; never cache working tree evidence."""
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def _preserve_v668_exact_later_fixture(visible, source, head='HEAD'):
    """Exclude only exact source changes after prior history, never an unknown edit."""
    affected = set(visible) & set(V668_PROOF['reviewed_sha256'])
    if head != 'HEAD' or not affected:
        return visible
    try:
        if subprocess.run(['git', 'merge-base', '--is-ancestor',
                           source, V668_PROOF['base_commit']],
                          cwd=ROOT, capture_output=True).returncode:
            return visible
        older = set(subprocess.check_output(
            ['git', 'diff', '--name-only', '--no-renames',
             source + '..' + V668_PROOF['base_commit'],
             '--', *sorted(affected)], cwd=ROOT, text=True).splitlines())
        covered = affected - older
        if covered:
            import unittest
            assert_v668_successor(unittest.TestCase())
        return [x for x in visible if x not in covered]
    except (AssertionError, OSError, UnicodeError, ValueError, KeyError,
            subprocess.SubprocessError):
        return visible
