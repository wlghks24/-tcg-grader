"""Strict V975 successor for the exact V974 Android pidfd handoff patch.

Historical V651 and V884 immutable proofs remain unchanged. This module is
review/CI-only and never sends a signal or installs a tablet update.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
from functools import lru_cache
import sync_v376_successor_test_support as sync

ROOT = sync.ROOT

# V975 exact descendant review. Historical V651/V884 evidence remains immutable.
V975_BASE = 'cf109bb6e6585a59a9a3f901d2611116091795b1'
V975_CANDIDATE = '3a861f23545626d8aac40d0888be7b9573036892'
V975_CONTRACT = 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V975.json'
V975_DELTA = 'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v975_delta.json'
V975_RECEIPT = 'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v975.json'
V975_TEST = 'execution/tests/test_sync_chain_recovery_v975.py'
V975_GENERATION = (V975_CONTRACT, V975_DELTA, V975_RECEIPT, V975_TEST)
V975_WATCHED = (
    'execution/apply_tablet_candidate_v897.py',
    'execution/tablet_runtime_handoff.py',
    'execution/tests/test_tablet_event_display_v929.py',
)
V975_REVIEWED = {
    'execution/apply_tablet_candidate_v897.py': ('3fdd65a2518ddb6bc8e9c44a5bad43acfdc4299f8b4c1527e194e8ff3f9b2f98', 14828),
    'execution/tablet_runtime_handoff.py': ('84e5173d50ff9d2ca877f61327f0e7d609ed1302b79c2143cc0559fcc929b8d4', 10182),
    'execution/tests/test_tablet_event_display_v929.py': ('c221ccd2389104dd6fc92d8bf6fc7fe109e3786c8ab0b6d5ffe6c1a06f925219', 6408),
}
V975_BASELINE = {
    'execution/apply_tablet_candidate_v897.py': 'b7db984a84716ae62454d93b4f23b932aca383ec38bcb253f828db41990c221a',
    'execution/tablet_runtime_handoff.py': '2233d189195f9553b95f676e7879e4462cab2f67ed4f97073c77314b0e0a619e',
    'execution/tests/test_tablet_event_display_v929.py': '9a00044fd4af9d544e8650e3a7b20d4da8d27566fd0b575c9937d4272573db84',
}
V975_LESSON_DIGEST = '51923fa2220164be44b0ab42dd96da2e6f1c90e75758b2064678c56585f816fb'


@lru_cache(maxsize=4)
def _v975_immutable_git_evidence(head_sha):
    """Cache immutable Git object bytes only, never live proof or file contents."""
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)
    if git('rev-parse', 'HEAD').decode().strip() != head_sha:
        raise AssertionError('V975 head changed during review')
    for older, newer in ((V975_BASE, V975_CANDIDATE), (V975_CANDIDATE, head_sha)):
        if subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer],
                          cwd=ROOT, capture_output=True, timeout=30).returncode:
            raise AssertionError('V975 immutable ancestry mismatch')
    def changed(a, b):
        return tuple(git('diff', '--no-renames', '--name-only', a, b).decode().splitlines())
    pinned = {}
    for path in V975_WATCHED:
        pinned[path] = (
            hashlib.sha256(git('show', V975_BASE + ':' + path)).hexdigest(),
            hashlib.sha256(git('show', V975_CANDIDATE + ':' + path)).hexdigest(),
            len(git('show', V975_CANDIDATE + ':' + path)),
        )
    return changed(V975_BASE, V975_CANDIDATE), changed(V975_CANDIDATE, head_sha), pinned


def assert_v975_successor(testcase):
    """Review the exact V974 patch as a strictly newer V975 sync generation."""
    for path in V975_GENERATION:
        target = ROOT / path
        testcase.assertFalse(target.is_symlink(), path)
        testcase.assertTrue(target.is_file(), path)
    c, d, r = (sync._read(ROOT / p) for p in V975_GENERATION[:3])
    old = sync._read(ROOT / 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V884.json')
    prior = sync._read(ROOT / old['delta_snapshot'])
    testcase.assertEqual('TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V884.json', c['prior_contract'])
    testcase.assertEqual(old['delta_snapshot'], c['prior_delta_snapshot'])
    testcase.assertEqual((V975_DELTA, V975_RECEIPT, V975_TEST),
                         (c['delta_snapshot'], c['receiver_receipt'], c['verification_test']))
    testcase.assertEqual(old['rules'], c['rules'])
    testcase.assertEqual(old['share_policy'], c['share_policy'])
    testcase.assertEqual(old['current_required_merge_prs'], c['current_required_merge_prs'])
    testcase.assertEqual(old['current_required_lesson_count'], c['prior_required_lesson_count'])
    testcase.assertEqual(len(d['lessons']), c['delta_required_lesson_count'])
    testcase.assertEqual(old['current_required_lesson_count'] + len(d['lessons']), c['current_required_lesson_count'])
    testcase.assertEqual(1, len(d['lessons']))
    testcase.assertEqual(sorted(set(old['freshness_watch']['exact_paths']) | set(V975_WATCHED)),
                         c['freshness_watch']['exact_paths'])
    testcase.assertEqual(old['freshness_watch']['path_prefixes'], c['freshness_watch']['path_prefixes'])
    testcase.assertEqual(sorted(set(old['freshness_watch']['exclude_paths']) | set(V975_GENERATION)),
                         c['freshness_watch']['exclude_paths'])
    testcase.assertEqual(prior['lesson_digest_sha256'], d['prior_lesson_digest_sha256'])
    testcase.assertEqual(d['prior_lesson_digest_sha256'], r['prior_lesson_digest_sha256'])
    encoded = json.dumps(d['lessons'], ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    testcase.assertEqual(V975_LESSON_DIGEST, hashlib.sha256(encoded).hexdigest())
    testcase.assertEqual(V975_LESSON_DIGEST, d['lesson_digest_sha256'])
    testcase.assertEqual(V975_LESSON_DIGEST, r['delta_lesson_digest_sha256'])
    testcase.assertEqual([x['lesson_id'] for x in d['lessons']], r['accepted_lesson_ids'])
    testcase.assertEqual('SYNCED_VERIFIED', r['status'])
    testcase.assertEqual('v975', r['verification']['contract_version'])
    testcase.assertEqual(V975_TEST, r['verification']['verification_test'])
    testcase.assertEqual('TABLET_GPT_TCG_GRADER_MATCH', r['verification']['verified_result'])
    testcase.assertEqual(V975_BASE, d['source_main_sha'])
    testcase.assertEqual(V975_BASE, r['source_main_sha'])
    testcase.assertIs(r['verification']['physical_tablet_runtime_verified'], False)
    testcase.assertIs(r['verification']['physical_drive_readback_verified'], False)
    testcase.assertIs(r['verification']['device_reverification_required'], True)
    testcase.assertIs(d['share_policy']['physical_tablet_verified_by_ci'], False)
    testcase.assertIs(c['share_policy']['physical_tablet_runtime_verified'], False)
    cand = c['candidate_sync']
    testcase.assertEqual(V975_BASE, cand['base_main_sha'])
    testcase.assertEqual(V975_CANDIDATE, cand['candidate_commit'])
    testcase.assertEqual(sorted(V975_WATCHED), cand['watched_paths'])
    testcase.assertEqual(set(V975_GENERATION), set(cand['generation_files']))
    testcase.assertIs(cand['requires_exact_watched_path_match'], True)
    testcase.assertIs(cand['post_merge_coverage_allowed'], True)
    testcase.assertEqual({p: h for p, (h, _) in V975_REVIEWED.items()}, cand['reviewed_sha256'])
    testcase.assertEqual({p: n for p, (_, n) in V975_REVIEWED.items()}, cand['reviewed_bytes'])
    testcase.assertEqual(V975_BASELINE, cand['baseline_sha256'])
    head_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                       cwd=ROOT, timeout=30).decode().strip()
    first, later, pinned = _v975_immutable_git_evidence(head_sha)
    watch = c['freshness_watch']
    def watched(changed):
        return sorted(p for p in changed if p not in watch['exclude_paths']
                      and (p in watch['exact_paths'] or p.startswith(tuple(watch['path_prefixes']))))
    testcase.assertEqual(sorted(V975_WATCHED), watched(first))
    testcase.assertEqual([], watched(later), 'unreviewed post-V975 watched edits')
    for name, (digest, size) in V975_REVIEWED.items():
        testcase.assertEqual((V975_BASELINE[name], digest, size), pinned[name], name)
        current = ROOT / name
        testcase.assertFalse(current.is_symlink(), name)
        testcase.assertTrue(current.is_file(), name)
        live = current.read_bytes()  # deliberately uncached, including tamper tests
        testcase.assertEqual(digest, hashlib.sha256(live).hexdigest(), name)
        testcase.assertEqual(size, len(live), name)
    verifier = ROOT / 'execution/tablet_sync_successor_v975.py'
    testcase.assertFalse(verifier.is_symlink())
    testcase.assertEqual(cand['reviewed_verifier_sha256'], hashlib.sha256(verifier.read_bytes()).hexdigest())
    testcase.assertEqual(subprocess.check_output(['git', 'show', 'HEAD:execution/tablet_sync_successor_v975.py'],
                                                 cwd=ROOT, timeout=30), verifier.read_bytes())
    support = ROOT / 'sync_v376_successor_test_support.py'
    testcase.assertFalse(support.is_symlink())
    testcase.assertEqual(cand['reviewed_support_sha256'], hashlib.sha256(support.read_bytes()).hexdigest())
    testcase.assertEqual(subprocess.check_output(['git', 'show', 'HEAD:sync_v376_successor_test_support.py'],
                                                 cwd=ROOT, timeout=30), support.read_bytes())
    return c


def preserve_reviewed_v975_scope(visible, source, head='HEAD'):
    """Hide only the V974 exact reviewed paths, never older/unknown edits."""
    if head != 'HEAD' or not set(visible).intersection(V975_WATCHED):
        return visible
    import unittest
    try:
        assert_v975_successor(unittest.TestCase())
        if subprocess.run(['git', 'merge-base', '--is-ancestor', source, V975_BASE],
                          cwd=ROOT, capture_output=True, timeout=30).returncode:
            return visible
        older = set(subprocess.check_output(
            ['git', 'diff', '--no-renames', '--name-only', source, V975_BASE, '--', *V975_WATCHED],
            cwd=ROOT, text=True, timeout=30).splitlines())
        return [p for p in visible if p not in V975_WATCHED or p in older]
    except (AssertionError, OSError, UnicodeError, ValueError, KeyError,
            subprocess.SubprocessError, ImportError):
        return visible
