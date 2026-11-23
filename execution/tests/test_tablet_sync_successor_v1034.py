"""V1034 exact source synchronization; failed CI evidence is not device approval."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BASE = '9b96d702e128f65afc0b4ef80e288f2ab86a409c'
CANDIDATE = 'ebe077c18aee08b8466f4cd7f2b41216f3b3d813'
PRIOR = 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1021.json'
FILES = ['TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1034.json', 'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1034_delta.json', 'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1034.json', 'execution/tests/test_tablet_sync_successor_v1034.py']
RUNTIME_ADDITIONS = ['execution/event_retention_20261123.py', 'execution/official_cinema_news_20261123.py', 'execution/official_event_watchlist_20261123.py', 'execution/tablet_event_filters_20261122.py', 'execution/tablet_event_refresh_20261123.js', 'execution/tablet_event_summary_v890.py', 'execution/tablet_menu_shell_v903.js', 'execution/tablet_menu_shell_v903.py', 'execution/tablet_workspace_truth_20261123.py', 'multi_market_price_collector.py', 'tablet_autonomy_dashboard_v400.js', 'update_promo_events.py']
PINS = {'execution/event_retention_20261123.py': {'sha256': '889c309d10c69a696a1a1c7f50cc751d6efedc412c4f8bd9759292bc1b43b630', 'bytes': 7790, 'blob': 'e21e2245f40ff738e254694f80e0ff10c5ecc28c'}, 'execution/official_cinema_news_20261123.py': {'sha256': '3c1164d331b9c950ff91f8789345f68e4c185bd16f03ca29edc6ea67ac3fe6e8', 'bytes': 14529, 'blob': '87dc3db03a1e936b7d481756642f550b0181e138'}, 'execution/official_event_watchlist_20261123.py': {'sha256': '5cb49e0dd1e055e7351d8fae9b9d18eee4a5ecb9607eff114228c2ccb8c2825d', 'bytes': 2893, 'blob': 'ca54669b53e6649acd7ab16fe3da800152e27e0a'}, 'execution/tablet_event_filters_20261122.py': {'sha256': '038ce693133651dd31076166ea6abecc4e6858d0ab6b1ab76a035d6c796d7cb2', 'bytes': 6278, 'blob': 'aeaceba7a2d38827fb16265098c830362dd26852'}, 'execution/tablet_event_refresh_20261123.js': {'sha256': 'b83bf4c2470807ec02fb7a94d4787a2cb08f11742d5f502f0c368a5f09201228', 'bytes': 5442, 'blob': 'e92cfa3ddc18632c06dbf733cc857b4dd6410816'}, 'execution/tablet_event_summary_v890.py': {'sha256': '8ae8c5ea6cd53f9ba01bbcc7a284687aa241c4133935912e26591ef23280f6af', 'bytes': 9298, 'blob': '6982e96a172224f396f08c3eb8ed0a6f758437b9'}, 'execution/tablet_menu_shell_v903.js': {'sha256': 'd612179f89f97cd92fe331ec8efd6532cb80883352a4960136adfdd43de899a1', 'bytes': 25070, 'blob': 'b741b7dcd633c8bb94e5fa7dc8e5c6c092c6123f'}, 'execution/tablet_menu_shell_v903.py': {'sha256': '69c7532847cd8c11e4fc733ca38e35f73afd6a955ab0df1bb901c50d067c1742', 'bytes': 31035, 'blob': '1cb0c97ea99c03ded1706858ed0ce7ee672c3242'}, 'execution/tablet_workspace_truth_20261123.py': {'sha256': '22aa112e635010c18db283e177a97cd224fc049ddeeaf4d40bcf3550750b17d6', 'bytes': 2539, 'blob': '5708d7bf64d2c82e174237ec779758a22009e971'}, 'multi_market_price_collector.py': {'sha256': 'dc0c157fc3408310124a486f465aea5cc6c0ab6d3247c147c5b073c2bc95be6c', 'bytes': 61837, 'blob': '6de4171fc595e45c42dfd1e11d261eb1258c98b1'}, 'tablet_autonomy_dashboard_v400.js': {'sha256': 'd330172107e4870880b8d77d8117ce944264a6f84baf869b339c04be501fddab', 'bytes': 83660, 'blob': '068eb20aace21b5324dff0a9bc0117bf0659a0f6'}, 'update_promo_events.py': {'sha256': '50d6ef03e6aab4f27a623a2dc5718b8622cb06ead80cd4fd1f7cc0e60115e2c7', 'bytes': 78247, 'blob': '5cae5ea6b1887da4731cc02d7ca0813a2188f9ba'}}
JSON_PINS = {'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1034.json': 'b64de0c8ac381b6e33510329d6351cacf08639111e25d501b12c89db4fcf3958', 'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1034_delta.json': '01043051761ae125c4e83c0f90b016b5ca9cfadf891279fe1a7edd26c3d6b296', 'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1034.json': 'e550e73739fb1ff6a05dec248af900eb7ae90d4142b815d06ef77d6086760c82'}


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, timeout=90, check=False)
    assert result.returncode == 0, ('Git evidence unavailable', args)
    return result.stdout


def load(relative):
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink(), ('unsafe sync metadata', relative)
    return json.loads(path.read_text(encoding='utf-8'))


def current_bytes(relative):
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink(), ('unsafe live source', relative)
    return path.read_bytes()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def watched(contract, older, newer):
    policy = contract['freshness_watch']
    changed = git('diff', '--no-renames', '--name-only', older, newer).decode().splitlines()
    exact, excluded = set(policy['exact_paths']), set(policy['exclude_paths'])
    prefixes = tuple(policy['path_prefixes'])
    return sorted(name for name in changed if name not in excluded and (name in exact or name.startswith(prefixes)))


def validate_v1034_sync():
    prior = load(PRIOR)
    prior_delta, prior_receipt = load(prior['delta_snapshot']), load(prior['receiver_receipt'])
    for name, obj in ((PRIOR, prior), (prior['delta_snapshot'], prior_delta), (prior['receiver_receipt'], prior_receipt)):
        assert json.loads(git('show', CANDIDATE + ':' + name)) == obj, ('prior generation changed', name)
    contract, delta, receipt = (load(name) for name in FILES[:3])
    for name, obj in zip(FILES, (contract, delta, receipt)):
        assert hashlib.sha256(canonical(obj)).hexdigest() == JSON_PINS[name], ('unreviewed sync metadata', name)
    assert contract['prior_contract'] == PRIOR
    assert contract['prior_delta_snapshot'] == prior['delta_snapshot']
    assert [contract['delta_snapshot'], contract['receiver_receipt'], contract['verification_test']] == FILES[1:]
    for key in ('schema_version', 'rules', 'share_policy', 'current_required_merge_prs'):
        assert contract[key] == prior[key], ('policy changed', key)
    expected_watch = copy.deepcopy(prior['freshness_watch'])
    expected_watch['exact_paths'] = sorted(set(expected_watch['exact_paths']) | set(RUNTIME_ADDITIONS))
    expected_watch['exclude_paths'] = sorted(set(expected_watch['exclude_paths']) | set(FILES))
    assert contract['freshness_watch'] == expected_watch, 'watch scope changed'
    assert contract['prior_required_lesson_count'] == prior['current_required_lesson_count']
    assert contract['delta_required_lesson_count'] == len(delta['lessons']) == 1
    assert contract['current_required_lesson_count'] == prior['current_required_lesson_count'] + 1
    candidate = contract['candidate_sync']
    assert candidate['base_main_sha'] == delta['source_main_sha'] == receipt['source_main_sha'] == BASE
    assert candidate['candidate_commit'] == candidate['functional_candidate_commit'] == CANDIDATE
    assert candidate['generation_files'] == FILES
    assert candidate['requires_exact_watched_path_match'] is True
    assert candidate['post_merge_coverage_allowed'] is True
    assert candidate['watched_paths'] == sorted(PINS) == watched(contract, BASE, CANDIDATE)
    assert watched(contract, CANDIDATE, 'HEAD') == [], 'new watched changes require a successor'
    assert candidate['reviewed_sha256'] == {name: pin['sha256'] for name, pin in PINS.items()}
    assert candidate['reviewed_bytes'] == {name: pin['bytes'] for name, pin in PINS.items()}
    assert candidate['reviewed_blobs'] == {name: pin['blob'] for name, pin in PINS.items()}
    for older, newer in ((BASE, CANDIDATE), (CANDIDATE, 'HEAD')):
        git('merge-base', '--is-ancestor', older, newer)
    for name, pin in PINS.items():
        reviewed = git('show', CANDIDATE + ':' + name)
        assert len(reviewed) == pin['bytes'] and hashlib.sha256(reviewed).hexdigest() == pin['sha256'], name
        mode = ('100644 blob ' + pin['blob'] + '\t' + name + '\0').encode()
        assert git('ls-tree', '-z', CANDIDATE, '--', name) == mode, name
        assert git('ls-tree', '-z', 'HEAD', '--', name) == mode, name
        assert current_bytes(name) == reviewed == git('show', 'HEAD:' + name), name
    assert delta['schema_version'] == receipt['schema_version'] == contract['schema_version']
    assert delta['source_repository'] == receipt['source_repository'] == 'wlghks24/-tcg-grader'
    assert delta['prior_delta'] == prior['delta_snapshot']
    assert delta['prior_lesson_digest_sha256'] == receipt['prior_lesson_digest_sha256'] == prior_delta['lesson_digest_sha256']
    assert delta['share_policy'] == prior_delta['share_policy']
    assert delta['covered_merges'] == [], 'candidate CI failure is not a verified merge'
    digest = hashlib.sha256(canonical(delta['lessons'])).hexdigest()
    assert delta['lesson_digest_sha256'] == receipt['delta_lesson_digest_sha256'] == digest
    assert receipt['accepted_lesson_ids'] == [lesson['lesson_id'] for lesson in delta['lessons']]
    assert receipt['source_snapshots'] == [FILES[1]]
    assert receipt['alignment_policy'] == prior_receipt['alignment_policy']
    assert receipt['status'] == 'SYNCED_VERIFIED'
    verification = receipt['verification']
    assert verification['contract_version'] == 'v1034'
    assert verification['verification_test'] == FILES[3]
    assert verification['verified_result'] == 'TABLET_GPT_TCG_GRADER_MATCH'
    assert verification['verification_mode'] == 'repository_only_exact_runtime_sync_ci_gap_repair'
    assert verification['device_reverification_required'] is True
    for field in ('source_code_and_fixture_review_verified', 'physical_tablet_runtime_verified',
                  'physical_drive_readback_verified', 'model_training_authorized',
                  'raw_grading_calibration_modified', 'main_merge_authorized'):
        assert verification[field] is False, ('false approval claim', field)
    return sorted(PINS)


class TabletSyncV1034Tests(unittest.TestCase):
    def test_exact_source_and_unchanged_previous_policies(self):
        self.assertEqual(sorted(PINS), validate_v1034_sync())

    def test_extra_watched_head_source_is_rejected(self):
        original = watched
        def changed(contract, older, newer):
            names = original(contract, older, newer)
            return names + ['update_promo_events.py'] if older == CANDIDATE and newer == 'HEAD' else names
        with patch(__name__ + '.watched', side_effect=changed), self.assertRaises(AssertionError):
            validate_v1034_sync()

    def test_stale_or_future_candidate_metadata_is_rejected(self):
        original = load
        for substitute in (BASE, 'f' * 40):
            def changed(name):
                obj = original(name)
                if name == FILES[0]: obj['candidate_sync']['candidate_commit'] = substitute
                return obj
            with self.subTest(substitute=substitute), patch(__name__ + '.load', side_effect=changed), self.assertRaises(AssertionError):
                validate_v1034_sync()

    def test_future_sync_timestamp_is_rejected(self):
        original = load
        def changed(name):
            obj = original(name)
            if name == FILES[1]: obj['built_at'] = '2099-01-01T00:00:00+00:00'
            return obj
        with patch(__name__ + '.load', side_effect=changed), self.assertRaises(AssertionError): validate_v1034_sync()

    def test_fake_device_model_or_source_approval_flags_are_rejected(self):
        original = load
        for field in ('physical_tablet_runtime_verified', 'physical_drive_readback_verified',
                      'source_code_and_fixture_review_verified', 'model_training_authorized',
                      'raw_grading_calibration_modified', 'main_merge_authorized'):
            def changed(name):
                obj = original(name)
                if name == FILES[2]: obj['verification'][field] = True
                return obj
            with self.subTest(field=field), patch(__name__ + '.load', side_effect=changed), self.assertRaises(AssertionError):
                validate_v1034_sync()

    def test_uncommitted_changes_to_every_pinned_runtime_are_rejected(self):
        original = current_bytes
        for name in PINS:
            def changed(relative):
                raw = original(relative)
                return raw + b' unreviewed' if relative == name else raw
            with self.subTest(name=name), patch(__name__ + '.current_bytes', side_effect=changed), self.assertRaises(AssertionError):
                validate_v1034_sync()

    def test_live_symlink_is_rejected(self):
        original = Path.is_symlink
        target = ROOT / 'execution/event_retention_20261123.py'
        with patch.object(Path, 'is_symlink', lambda path: path == target or original(path)), self.assertRaises(AssertionError):
            validate_v1034_sync()

    def test_prior_policy_and_receipt_cannot_be_forged(self):
        original = load
        prior = original(PRIOR)
        for relative in (PRIOR, prior['delta_snapshot'], prior['receiver_receipt']):
            def changed(name):
                obj = original(name)
                if name == relative: obj['forged'] = True
                return obj
            with self.subTest(relative=relative), patch(__name__ + '.load', side_effect=changed), self.assertRaises(AssertionError):
                validate_v1034_sync()

    def test_full_source_pin_cannot_be_substituted(self):
        pins = copy.deepcopy(PINS)
        pins['execution/tablet_menu_shell_v903.py']['sha256'] = '0' * 64
        with patch(__name__ + '.PINS', pins), self.assertRaises(AssertionError): validate_v1034_sync()

    def test_committed_head_drift_cannot_hide_behind_clean_live_bytes(self):
        original = git
        def changed(*args):
            raw = original(*args)
            return raw + b'x' if args == ('show', 'HEAD:execution/tablet_menu_shell_v903.py') else raw
        with patch(__name__ + '.git', side_effect=changed), self.assertRaises(AssertionError): validate_v1034_sync()

    def test_unavailable_history_cannot_approve_source(self):
        original = git
        def changed(*args):
            assert args[:2] != ('merge-base', '--is-ancestor'), 'missing history'
            return original(*args)
        with patch(__name__ + '.git', side_effect=changed), self.assertRaises(AssertionError): validate_v1034_sync()


if __name__ == '__main__':
    unittest.main()
