"""V1037 exact source transition; no CI, merge, training or device approval."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

from execution.git_validation_cache import head_validation_request
from execution.tests.test_tablet_sync_successor_v1035 import ROOT, git, live, load, require, watched
from execution.tests.test_tablet_sync_successor_v1036 import (
    CANDIDATE as PREVIOUS, PINS as PREVIOUS_PINS, validate_v1036)
from execution.tablet_tool_recovery_successor_20261127 import validate_tablet_tool_recovery

BASE = '7f5adbc25f9967207edace9fa314bc0a646e19f2'
CANDIDATE = '82baff2f553e9ebeb8f7c45f4727bac9700bdaf2'
FILES = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1037.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1037_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1037.json","execution/tests/test_tablet_sync_successor_v1037.py"]
PRIOR = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1036.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1036_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1036.json"]
PINS = json.loads(r'''{".github/workflows/gpt-tcg-drive-package.yml":{"blob":"e9b5c4271f2dfa987e6eb3e69e2fa1d2bd54320c","sha256":"1e0f7daefb58ca8bb11c145b92613361da55dcf40d3bf010bc879bc3e3a32510","bytes":12547},"execution/tablet_menu_shell_v903.js":{"blob":"8fd9cc86b730aae7ebf31987c661d7441a8f4ee7","sha256":"88984e8b3fb44ed48d3cc3f17bc23a03d5262ba0d4856dd7423196684d47ec99","bytes":25291},"execution/tablet_menu_shell_v903.py":{"blob":"ee2e4168aeb468ceaa6c4d33d7b4b428bf90f03f","sha256":"2cdd02b0acf1dfc0c0381acf3de7fcb811f71b435b9a0c34adb1f5625bbc2424","bytes":31154}}''')
META = json.loads(r'''{"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1037.json":"e4124ae3429d78a864d6a72e49e886e2a133d19238802ef8bcf126b947b502e7","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1037_delta.json":"c41e2aab8c68eacb77a25ebfe6e39843b20cda293106ec697764ea4c843add64","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1037.json":"e1a1b69a854bdf44f508ec0f5039d4b338fb31c01440dba771f3cb2a82a16909"}''')
PRIOR_META = json.loads(r'''{"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1036.json":"aa6204511a70e8066c3469625aafd6a326df3569dd6c0ae6719f6d222e3eb91d","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1036_delta.json":"bf6cbe87ba337a73354c12f8d376663dafa71e8f3b5fa383ab8cf2753dd2c175","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1036.json":"c0d798795a90e8b0cc0c6add26c49df1618715dfe31585f5f0f82ffeb3913115"}''')


@head_validation_request(share_objects=True)
def validate_v1037():
    prior, previous_delta, previous_receipt = (load(name, PRIOR_META[name]) for name in PRIOR)
    for name in PRIOR:
        require(git('show', BASE + ':' + name) == live(name), 'previous metadata changed')
    c, d, r = (load(name, META[name]) for name in FILES[:3])
    for name in FILES[:3]:
        require(git('show', 'HEAD:' + name) == live(name), 'uncommitted generation metadata')
    require(c['prior_contract'] == PRIOR[0] and c['prior_delta_snapshot'] == PRIOR[1], 'prior lineage')
    require([c['delta_snapshot'], c['receiver_receipt'], c['verification_test']] == FILES[1:], 'generation paths')
    for key in ('schema_version', 'rules', 'share_policy', 'current_required_merge_prs'):
        require(c[key] == prior[key], 'policy drift: ' + key)
    watch = copy.deepcopy(prior['freshness_watch'])
    watch['exact_paths'] = sorted(set(watch['exact_paths']) | set(PINS))
    watch['exclude_paths'] = sorted(set(watch['exclude_paths']) | set(FILES))
    require(c['freshness_watch'] == watch, 'watch policy drift')
    require(c['prior_required_lesson_count'] == prior['current_required_lesson_count']
            and c['delta_required_lesson_count'] == len(d['lessons']) == 1
            and c['current_required_lesson_count'] == prior['current_required_lesson_count'] + 1, 'lesson counts')
    q = c['candidate_sync']
    require(q['base_main_sha'] == d['source_main_sha'] == r['source_main_sha'] == BASE, 'source main')
    require(q['candidate_commit'] == q['functional_candidate_commit'] == CANDIDATE, 'candidate')
    require(q['generation_files'] == FILES and q['watched_paths'] == sorted(PINS), 'candidate scope')
    require(q['requires_exact_watched_path_match'] is True and q['post_merge_coverage_allowed'] is True, 'scope flags')
    for key, field in (('reviewed_blobs', 'blob'), ('reviewed_sha256', 'sha256'), ('reviewed_bytes', 'bytes')):
        require(q[key] == {name: row[field] for name, row in PINS.items()}, 'source pins: ' + key)
    digest = hashlib.sha256(json.dumps(d['lessons'], ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    require(d['prior_delta'] == PRIOR[1] and d['prior_lesson_digest_sha256']
            == r['prior_lesson_digest_sha256'] == previous_delta['lesson_digest_sha256'], 'prior digest')
    require(digest == d['lesson_digest_sha256'] == r['delta_lesson_digest_sha256'], 'lesson digest')
    require(r['accepted_lesson_ids'] == [row['lesson_id'] for row in d['lessons']]
            and r['source_snapshots'] == [FILES[1]], 'receipt lessons')
    require(d['covered_merges'] == [] and d['share_policy'] == previous_delta['share_policy']
            and r['alignment_policy'] == previous_receipt['alignment_policy'], 'merge or policy drift')
    v = r['verification']
    require(r['status'] == 'SYNCED_VERIFIED' and v['verified_result'] == 'TABLET_GPT_TCG_GRADER_MATCH'
            and v['contract_version'] == 'v1037' and v['verification_test'] == FILES[3]
            and v['verification_mode'] == 'repository_only_exact_tablet_tool_package_successor', 'receipt metadata')
    require(v['device_reverification_required'] is True, 'device recheck required')
    for key in ('source_code_and_fixture_review_verified', 'physical_tablet_runtime_verified',
                'physical_drive_readback_verified', 'model_training_authorized',
                'raw_grading_calibration_modified', 'main_merge_authorized'):
        require(v[key] is False, 'false approval: ' + key)
    for value in (d['built_at'], r['received_at']):
        observed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(observed.tzinfo is not None
                and observed.timestamp() <= datetime.now(timezone.utc).timestamp() + 180, 'future sync timestamp')
    require(validate_v1036() == sorted(PREVIOUS_PINS), 'previous exact generation')
    for older, newer in ((BASE, CANDIDATE), (PREVIOUS, CANDIDATE), (CANDIDATE, 'HEAD')):
        git('merge-base', '--is-ancestor', older, newer)
    require(watched(c, BASE, CANDIDATE) == sorted(PINS), 'candidate watched scope')
    require(watched(c, PREVIOUS, CANDIDATE) == sorted(PINS), 'unexpected source transition')
    require(watched(c, CANDIDATE, 'HEAD') == [], 'unreviewed watched change')
    for name, pin in PINS.items():
        raw = git('show', CANDIDATE + ':' + name)
        entry = ('100644 blob ' + pin['blob'] + '\t' + name + '\0').encode()
        require(git('ls-tree', '-z', CANDIDATE, '--', name) == entry
                == git('ls-tree', '-z', 'HEAD', '--', name), 'source tree: ' + name)
        require(hashlib.sha256(raw).hexdigest() == pin['sha256'] and len(raw) == pin['bytes'], 'source digest: ' + name)
        require(live(name) == raw == git('show', 'HEAD:' + name), 'live source: ' + name)
        # This also proves the complete eight-file source checkpoint and its
        # baseline pin, not only this generation's three watched paths.
        prior_digest = ('36f7ce79fd4d1175f4af1dc7830e4dfcd445638e775b1a2bc3cd1859d75f1139'
                        if name.startswith('.github/') else PREVIOUS_PINS[name]['sha256'])
        require(validate_tablet_tool_recovery(name, prior_digest, repo=ROOT), 'exact source checkpoint')
    return sorted(PINS)


class TabletSyncV1037Tests(unittest.TestCase):
    def test_exact_generation_preserves_previous_source_and_policy(self):
        self.assertEqual(sorted(PINS), validate_v1037())

    def test_extra_watched_head_change_rejected(self):
        original = watched
        with patch(__name__ + '.watched', side_effect=lambda c,a,b: original(c,a,b)
                   + (['unknown_runtime.py'] if a == CANDIDATE and b == 'HEAD' else [])):
            with self.assertRaises(AssertionError):
                validate_v1037()

    def test_current_live_source_mutation_rejected(self):
        original = live
        name = 'execution/tablet_menu_shell_v903.py'
        with patch(__name__ + '.live', side_effect=lambda n: original(n) + (b'x' if n == name else b'')):
            with self.assertRaises(AssertionError):
                validate_v1037()

    def test_committed_head_and_generation_metadata_mutation_rejected(self):
        original = git
        name = 'execution/tablet_menu_shell_v903.js'
        with patch(__name__ + '.git', side_effect=lambda *args: original(*args)
                   + (b'x' if args == ('show', 'HEAD:' + name) else b'')):
            with self.assertRaises(AssertionError):
                validate_v1037()
        changed = dict(META, **{FILES[0]: '0'*64})
        with patch(__name__ + '.META', changed), self.assertRaises(AssertionError):
            validate_v1037()

    def test_approval_flags_and_future_evidence_rejected(self):
        original = load
        for field in ('main_merge_authorized', 'physical_tablet_runtime_verified', 'model_training_authorized'):
            def changed(name, digest):
                obj = original(name, digest)
                if name == FILES[2]:
                    obj['verification'][field] = True
                return obj
            with self.subTest(field=field), patch(__name__ + '.load', changed):
                with self.assertRaises(AssertionError):
                    validate_v1037()
        def future(name, digest):
            obj = original(name, digest)
            if name == FILES[1]:
                obj['built_at'] = '2099-01-01T00:00:00+00:00'
            return obj
        with patch(__name__ + '.load', future), self.assertRaises(AssertionError):
            validate_v1037()


if __name__ == '__main__':
    unittest.main()
