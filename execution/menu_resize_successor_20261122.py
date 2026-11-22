"""Exact menu-only descendant of the immutable V1018 workspace proof.

This validates repository source history, never device delivery or installation.
Immutable Git reads may be reused; live bytes/proofs are re-read on every call.
"""
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git

import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / '.github/tablet-autonomy/menu_resize_successor_20261122.json'
# The complete source candidate is frozen, but delegation authorizes only menu JS.
EXPECTED = {'schema': 'tcg-menu-resize-successor/20261122',
 'baseline_commit': '3809492f45159d03c41bc18cb7daa0b11b64e6d4',
 'candidate_commit': 'e083ee51e837d751d1250c71199101fbd6a29721',
 'reviewed_path': 'execution/tablet_menu_shell_v903.js',
 'baseline': {'blob': 'f0fce37cd0ccc262ca604599f8d0e3f2539794ac',
              'sha256': '5960c623288904cb9794a988d47e6ecec99ff9a31d5be28704bfc2dba3d5e49e',
              'bytes': 24315},
 'reviewed': {'blob': '3ac2ef897c301ceeff60cce56e3ae2cc8852ccf3',
              'sha256': '02014c642ac51a80be1f15bb6bcbd76ba9148932d6e0ff1a8a033f995ce7cacd',
              'bytes': 24475},
 'source_scope': {'execution/tablet_menu_shell_v903.js': {'blob': '3ac2ef897c301ceeff60cce56e3ae2cc8852ccf3',
                                                          'sha256': '02014c642ac51a80be1f15bb6bcbd76ba9148932d6e0ff1a8a033f995ce7cacd',
                                                          'bytes': 24475},
                  'execution/tests/test_grading_total_cost_20261122.js': {'blob': 'c6f8a9c14af302a79a780164df126432a851e67f',
                                                                          'sha256': '473e170352423e30838767b6d7eadea0620e609a4cb51e676997fd2610064054',
                                                                          'bytes': 8834},
                  'execution/tests/test_tablet_menu_shell_v903.js': {'blob': '0b4256732c0a23f1b30cf4ad3b3af78c7eee49c6',
                                                                     'sha256': '3fd019f9f7b9cdd5bdd1fff391a75520b3befeb146542120d4f8ad8d01a13fae',
                                                                     'bytes': 43709},
                  'grading_self_learning.py': {'blob': 'fe92b2c1702f8114ae51ac0d5f9581102245f019',
                                               'sha256': 'e48561b8f2494d922f922f04795ff4fef68a531c7859531bcfb142329c6fd75a',
                                               'bytes': 17185},
                  'grading_total_cost.js': {'blob': '74efd91087459c3a4fee56471dbfb2fd5be26d8b',
                                            'sha256': '241faf5e92be24f2b1e99ab571a6f430215cea56ab914d9d2ab970151cad67b0',
                                            'bytes': 9634},
                  'integrity_manifest.json': {'blob': '00f9fdc5203f4944e53ded43a0978c632cecd601',
                                              'sha256': '2ca4df52f813891d40e88de24581f48ca577740e25c0356b4e20d9f96e6d7273',
                                              'bytes': 310621},
                  'test_grading_self_learning.py': {'blob': '58a8488f17201e0365277f79fa45eb1d675488a3',
                                                    'sha256': 'e4098581355d828c580d3d8a9c1c0ac34fb0e21be72a6ec1e0631932d9dc3deb',
                                                    'bytes': 7258},
                  'test_video_review_repairs_20261122.py': {'blob': 'c425834bec1bb397a7eccf355ef4fe0caae939a0',
                                                            'sha256': '7fd97aba73fb04f03a3bc237f5c7b6a62d182d6fd45a4319ade6c9e43bafebe5',
                                                            'bytes': 1285}},
 'physical_tablet_verified': False,
 'main_merge_authorized': False,
 'model_training_authorized': False,
 'runtime_data_modified': False}


def _git(*args):
    return read_git(ROOT,*args)


def _assert_pin(ref, name, pin):
    blob = _git('rev-parse', ref + ':' + name).decode('ascii').strip()
    assert blob == pin['blob'], ('menu successor Git blob changed', name)
    raw = _git('show', ref + ':' + name)
    assert len(raw) == pin['bytes'], ('menu successor byte count changed', name)
    assert hashlib.sha256(raw).hexdigest() == pin['sha256'], ('menu successor SHA changed', name)
    return raw


@head_validation_request()
def validate_menu_resize_successor_20261122(name, prior_digest=None):
    assert name == EXPECTED['reviewed_path'], 'unreviewed menu successor path'
    assert prior_digest in (None, EXPECTED['baseline']['sha256']), 'wrong menu prior digest'
    assert PROOF.is_file() and not PROOF.is_symlink(), 'menu proof missing or linked'
    assert json.loads(PROOF.read_bytes().decode('utf-8', 'strict')) == EXPECTED, 'menu proof changed'

    base, candidate = EXPECTED['baseline_commit'], EXPECTED['candidate_commit']
    head = _git('rev-parse', 'HEAD').decode('ascii').strip()
    assert all(re.fullmatch('[0-9a-f]{40}', ref) for ref in (base, candidate, head)), 'invalid menu history ref'
    _git('merge-base', '--is-ancestor', base, candidate)
    _git('merge-base', '--is-ancestor', candidate, head)
    scope = _git('diff', '--no-renames', '--name-only', '-z', base, candidate).decode('utf-8', 'strict').split('\0')
    assert scope[-1] == '' and scope[:-1] == sorted(EXPECTED['source_scope']), 'unreviewed menu source scope'
    for path, pin in EXPECTED['source_scope'].items():
        _assert_pin(candidate, path, pin)

    before = _assert_pin(base, name, EXPECTED['baseline'])
    reviewed = _assert_pin(candidate, name, EXPECTED['reviewed'])
    assert before != reviewed, 'menu successor has no source change'
    assert EXPECTED['source_scope'][name] == EXPECTED['reviewed'], 'menu source pin disagrees'
    committed = _assert_pin(head, name, EXPECTED['reviewed'])
    for ref in (base, candidate, head):
        expected_tree = ('100644 blob ' + (EXPECTED['baseline'] if ref == base else EXPECTED['reviewed'])['blob']
                         + '\t' + name + '\0').encode('utf-8')
        assert _git('ls-tree', '-z', ref, '--', name) == expected_tree, 'linked or non-regular committed menu'
    path = ROOT / name
    assert path.is_file() and not path.is_symlink(), 'menu live path missing or linked'
    # Never cache this read: a second call after mutation must still fail closed.
    live = path.read_bytes()
    assert len(live) == EXPECTED['reviewed']['bytes'], 'menu live byte count changed'
    assert hashlib.sha256(live).hexdigest() == EXPECTED['reviewed']['sha256'], 'menu live SHA changed'
    assert live == reviewed == committed, 'unreviewed live menu bytes'
    return True
