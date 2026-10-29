"""Exact descendant successor for V652-protected collection learner (no device claims).

The historical V652 proof remains immutable. This guard accepts only the exact
V882 branch candidate and preserves the failure behavior for any later edit.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = ROOT / 'execution/evidence/p0_feedback_verified_successor_v882.json'
BASE = '6c78831bbb6e188717f86ef90243a836d2e0b67a'
CANDIDATE = '01b892a69429375a08d57553557370a2030a3292'
REVIEWED = {
    'adaptive_collection_learner.py': 'e17aeaa80a186c402cd66f5a7258080dd8bb04c822bf4be52860c9f829402024',
    'ai_performance_runtime.py': '50a0691bc3dfafa36101510c9dff028d3ac8beec3346d7de732c70fc6fbf49d9',
    'execution/tests/test_p0_collection_feedback_bool_gate_v882.py': '00fe50f1c7075db9160a742738c067ff198c3edb7a25717e84f095b9f8c3eb7d',
    'execution/tests/test_p0_verified_runtime_gate_v882.py': '9ca9a00b5e6f15815f54369dc14afa9694cd0a061ae6970af42a02dffbc5007f',
}
BASELINES = {
    'adaptive_collection_learner.py': '38683fbf72ef892f3b401b47ffa044236d6667ed516ea157aec92e1de90a0b37',
    'ai_performance_runtime.py': '2ef3a4bacc89085fe7a42a01161753ab91af2d8152ad3c3c77260ccd28538089',
    'execution/tests/test_p0_collection_feedback_bool_gate_v882.py': None,
    'execution/tests/test_p0_verified_runtime_gate_v882.py': None,
}


def _git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args], cwd=ROOT, stderr=subprocess.PIPE)


def assert_v882_feedback_successor(testcase) -> None:
    testcase.assertFalse(PROOF_PATH.is_symlink())
    testcase.assertTrue(PROOF_PATH.is_file())
    expected = {
        'schema': 'tcg-p0-learning-feedback-successor/v882',
        'base_main_sha': BASE,
        'review_candidate_sha': CANDIDATE,
        'reviewed_sha256': REVIEWED,
        'baseline_sha256': BASELINES,
        'candidate_auxiliary_paths': ['integrity_manifest.json'],
        'physical_tablet_verified': False,
        'auto_merge_allowed': False,
        'status': 'DRAFT_HOLD_PENDING_CURRENT_HEAD_CI',
    }
    testcase.assertEqual(json.loads(PROOF_PATH.read_text(encoding='utf-8')), expected)
    testcase.assertFalse(expected['physical_tablet_verified'])
    testcase.assertFalse(expected['auto_merge_allowed'])
    for ancestor in (BASE, CANDIDATE):
        testcase.assertEqual(subprocess.run(
            ['git','merge-base','--is-ancestor', ancestor, 'HEAD'],cwd=ROOT,
            capture_output=True,check=False).returncode, 0)
    changed = set(_git('diff','--name-only', BASE+'..'+CANDIDATE).decode('utf-8').splitlines())
    testcase.assertEqual(changed, set(REVIEWED) | {'integrity_manifest.json'})
    for path, digest in REVIEWED.items():
        source=ROOT/path
        testcase.assertTrue(source.is_file(),path)
        testcase.assertFalse(source.is_symlink(),path)
        testcase.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest,path)
        testcase.assertEqual(hashlib.sha256(_git('show',CANDIDATE+':'+path)).hexdigest(),digest,path)
        baseline=BASELINES[path]
        if baseline is not None:
            testcase.assertEqual(hashlib.sha256(_git('show',BASE+':'+path)).hexdigest(),baseline,path)
        else:
            testcase.assertNotEqual(subprocess.run(
                ['git','cat-file','-e',BASE+':'+path],cwd=ROOT,
                capture_output=True,check=False).returncode,0)
