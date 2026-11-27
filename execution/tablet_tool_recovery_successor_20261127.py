"""Exact source successor for existing tablet tools and package retry.
Never accepts device delivery, runtime-data writes, or uncommitted source.
"""
import hashlib
import json
from pathlib import Path

from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git, immutable_source_evidence

ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = '.github/tablet-autonomy/tablet_tool_recovery_successor_20261127.json'
EXPECTED = json.loads(r'''{
  "schema": "tcg-tablet-tool-recovery-successor/20261127",
  "baseline_commit": "7f5adbc25f9967207edace9fa314bc0a646e19f2",
  "candidate_commit": "6c7026c70d53075b1938e630d35802d829209d4b",
  "baseline": {
    ".github/workflows/gpt-tcg-drive-package.yml": {
      "blob": "6404b694c47a883e3bc4ef6ef444350a331bc505",
      "sha256": "36f7ce79fd4d1175f4af1dc7830e4dfcd445638e775b1a2bc3cd1859d75f1139",
      "bytes": 11961
    },
    "execution/tablet_menu_shell_v903.js": {
      "blob": "b741b7dcd633c8bb94e5fa7dc8e5c6c092c6123f",
      "sha256": "d612179f89f97cd92fe331ec8efd6532cb80883352a4960136adfdd43de899a1",
      "bytes": 25070
    },
    "execution/tablet_menu_shell_v903.py": {
      "blob": "1cb0c97ea99c03ded1706858ed0ce7ee672c3242",
      "sha256": "69c7532847cd8c11e4fc733ca38e35f73afd6a955ab0df1bb901c50d067c1742",
      "bytes": 31035
    }
  },
  "files": {
    ".github/workflows/gpt-tcg-drive-package.yml": {
      "blob": "e9b5c4271f2dfa987e6eb3e69e2fa1d2bd54320c",
      "sha256": "1e0f7daefb58ca8bb11c145b92613361da55dcf40d3bf010bc879bc3e3a32510",
      "bytes": 12547
    },
    "execution/tablet_menu_shell_v903.js": {
      "blob": "8fd9cc86b730aae7ebf31987c661d7441a8f4ee7",
      "sha256": "88984e8b3fb44ed48d3cc3f17bc23a03d5262ba0d4856dd7423196684d47ec99",
      "bytes": 25291
    },
    "execution/tablet_menu_shell_v903.py": {
      "blob": "ee2e4168aeb468ceaa6c4d33d7b4b428bf90f03f",
      "sha256": "2cdd02b0acf1dfc0c0381acf3de7fcb811f71b435b9a0c34adb1f5625bbc2424",
      "bytes": 31154
    },
    "execution/tests/test_package_event_recovery_20261127.py": {
      "blob": "afe245d30767fcd6ef8e11a30f84e3f8b8a74d04",
      "sha256": "21221828c6063c78a60bf3bdd37f696d08d2f9c77987868ed1d5870ab0e5acff",
      "bytes": 3968
    },
    "execution/tests/test_successor_git_reads_20261122.py": {
      "blob": "d694443451d1abd9e9dbbb71550c5ae9153bc877",
      "sha256": "823e2ad4d7b0c50f70b17db1aaffab60923c97067fa29a48fb63cb5061c2f071",
      "bytes": 60218
    },
    "execution/tests/test_tablet_menu_shell_v903.js": {
      "blob": "5158648118ca40e3eb88f8b9c9eb17b680f41f15",
      "sha256": "2541fc0e4ba7d5267822687ca7d0a2bd455b182f3cb56de0a42a92a6a116d0d7",
      "bytes": 51354
    },
    "execution/tests/test_tablet_menu_shell_v903.py": {
      "blob": "c32614f71159ebfdbe3d50bbcaf2268d99da2f1a",
      "sha256": "fb2e21ad734835c85ac7a3dccf7216e3e6c894cf116cf89239c86b3172a5ba43",
      "bytes": 16088
    },
    "integrity_manifest.json": {
      "blob": "ddab4e767ae379f3abf7c9122243cb98fb05a0f2",
      "sha256": "bafb70184706a96565d73c40e0cda9471bbf6be458fb5e2844e1fa52d7a62663",
      "bytes": 322853
    }
  },
  "live_paths": [
    ".github/workflows/gpt-tcg-drive-package.yml",
    "execution/tablet_menu_shell_v903.js",
    "execution/tablet_menu_shell_v903.py",
    "execution/tests/test_package_event_recovery_20261127.py",
    "execution/tests/test_successor_git_reads_20261122.py",
    "execution/tests/test_tablet_menu_shell_v903.js",
    "execution/tests/test_tablet_menu_shell_v903.py"
  ],
  "physical_tablet_verified": false,
  "runtime_data_modified": false,
  "main_merge_authorized": false,
  "device_restart_authorized": false
}''')


def git(*args):
    return read_git(ROOT, *args)


def pinned(ref, name, pin):
    assert git('ls-tree', '-z', ref, '--', name) == (
        '100644 blob ' + pin['blob'] + '\t' + name + '\0').encode(), name
    raw = git('show', ref + ':' + name)
    assert len(raw) == pin['bytes'], name
    assert hashlib.sha256(raw).hexdigest() == pin['sha256'], name
    return raw


def live_bytes(name):
    target = ROOT / name
    assert target.is_file() and not target.is_symlink(), name
    return target.read_bytes()


@head_validation_request(share_objects=True)
def validate_tablet_tool_recovery(name, prior_digest):
    e = EXPECTED
    assert name in e['baseline'], 'unreviewed tablet tool recovery path'
    assert prior_digest == e['baseline'][name]['sha256'], 'wrong prior digest'
    proof = live_bytes(PROOF_PATH)
    assert json.loads(proof) == e, 'tablet tool recovery proof changed'
    assert git('show', 'HEAD:' + PROOF_PATH) == proof, 'uncommitted proof'
    reviewed = immutable_source_evidence(ROOT, e, git, pinned)
    git('merge-base', '--is-ancestor', e['candidate_commit'], 'HEAD')
    # Historical acceptance and mutable/live acceptance are deliberately separate.
    # The common Git reader can reuse immutable objects; each call rereads files.
    for path in e['live_paths']:
        assert live_bytes(path) == reviewed[path], 'unreviewed live bytes: ' + path
        assert pinned('HEAD', path, e['files'][path]) == reviewed[path], path
    manifest_raw = live_bytes('integrity_manifest.json')
    assert git('show', 'HEAD:integrity_manifest.json') == manifest_raw, 'uncommitted manifest'
    manifest = json.loads(manifest_raw)['files']
    for path in e['live_paths']:
        row = e['files'][path]
        assert manifest[path] == {'sha256': row['sha256'], 'bytes': row['bytes']}, path
    # The descendant adds proof files to the source checkpoint manifest. Bind
    # those live bytes to both the committed tree and its current integrity row.
    for path in (PROOF_PATH, 'execution/tablet_tool_recovery_successor_20261127.py'):
        raw = live_bytes(path)
        assert git('show', 'HEAD:' + path) == raw, 'uncommitted proof source: ' + path
        assert manifest[path] == {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}, path
    for key in ('physical_tablet_verified', 'runtime_data_modified',
                'main_merge_authorized', 'device_restart_authorized'):
        assert e[key] is False, key
    return True
