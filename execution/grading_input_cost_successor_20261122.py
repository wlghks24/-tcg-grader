"""Exact reviewed grading-input and KRW-cost source descendants.

Repository source proof only. No installer, event freshness, or model promotion.
The initial source commit and final correction are independently frozen. All Git
objects and live files are re-read, including after a previously successful call.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / '.github/tablet-autonomy/grading_input_cost_successor_20261122.json'
EXPECTED = {'schema': 'tcg-grading-input-cost-successor/20261122',
 'baseline_commit': '3809492f45159d03c41bc18cb7daa0b11b64e6d4',
 'source_commit': 'e083ee51e837d751d1250c71199101fbd6a29721',
 'final_source_commit': '1f59e648a38546ea57d56f0d98c06815a2afc4f8',
 'reviewed_paths': ['grading_self_learning.py', 'grading_total_cost.js'],
 'baseline': {'grading_self_learning.py': {'blob': '437642fe7574dc7f1ba2e890eb7f9dabb72b22f4',
                                           'sha256': '61aea63b4571d520b18a5d73098d2d78c5a98a332302ae4ad35ac0906156cbe8',
                                           'bytes': 16776},
              'grading_total_cost.js': {'blob': '1e36db61c51ee426f16f58586ab506c70c991588',
                                        'sha256': '4586a3f7eecee9b931d1ec0333754e46fb0cab0ff6626b890e93cb6b0411f77b',
                                        'bytes': 7185}},
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
 'final_scope': {'.github/tablet-autonomy/menu_resize_successor_20261122.json': {'blob': '2034f79dd30dd16a2823c300b0b9599c42d82027',
                                                                                 'sha256': '839a0caa393f56fbae96cb85581223503f84159631345ceb318633ae3fa609ca',
                                                                                 'bytes': 2468},
                 'execution/menu_resize_successor_20261122.py': {'blob': '36ff024364d2e5a2058f6be91aef976336b2c5db',
                                                                 'sha256': 'f9b364914fbc3d4600c7217fd1282862ee917752f2a8cbc593fe62ad5469c2f5',
                                                                 'bytes': 6615},
                 'execution/tests/test_grading_total_cost_20261122.js': {'blob': '4c373ac59cc7902b1e08413b8aa6de99ab0a636d',
                                                                         'sha256': '226a5b23acd4328ddfed87bf0a66d577a563084683cf1b41f3ae35923831a00a',
                                                                         'bytes': 13991},
                 'execution/tests/test_menu_resize_successor_20261122.py': {'blob': '088bfa699704e4abe9d0a136a336f7d7784ef009',
                                                                            'sha256': '44da9051ecab3cdbdf55bdf8a058801420537f546c593114870e958d3ade20cb',
                                                                            'bytes': 7996},
                 'execution/tests/test_video_menu_lineage_20261122.py': {'blob': '24a36826bc68d0f3feebeaec6c0d4facdc522423',
                                                                         'sha256': '87932e5a58ad39765c6d803b5d143e1ce4a15a2a967a25a3d618b28a45d69784',
                                                                         'bytes': 291},
                 'execution/tests/test_video_review_repairs_20261122.py': {'blob': '8e207da75d1f5d6c117e7ef380e45167560317b8',
                                                                           'sha256': '8228ddfadca1c6454649da7f7cd6eafe2ede9cffb6e44cda3352493448b148e6',
                                                                           'bytes': 1290},
                 'execution/workspace_review_successor_v1018.py': {'blob': '6908e282c07001d1c8047fe63c48c5e69a18d971',
                                                                   'sha256': '6be7c14991607b40185ee4d8b87be668097e3aba4930a3b9456559e60202f56e',
                                                                   'bytes': 3331},
                 'grading_total_cost.js': {'blob': '1700943cc8ed6d67d481b967cd4a68b51dc75a1b',
                                           'sha256': '790ace81f11e44f2377e016340d2270f80893c547bae02e4c9a1b0912549278c',
                                           'bytes': 11641},
                 'integrity_manifest.json': {'blob': 'e98bb6ea1eb828c95ea04f9bbc9253cdbb44a3f3',
                                             'sha256': '5de3759ecb8b53a18c125cfa1222ed476cf24add66b7b2bdac013c2558864729',
                                             'bytes': 311149},
                 'test_grading_self_learning.py': {'blob': '35dd27f64c14f19bfc4ad6a38d187d419a85f3f8',
                                                   'sha256': 'dcf34a5a09e51e5d46293a0266087e438122d71af0b9ef6b437e36ef58647a63',
                                                   'bytes': 7654},
                 'test_video_review_repairs_20261122.py': None},
 'reviewed': {'grading_self_learning.py': {'blob': 'fe92b2c1702f8114ae51ac0d5f9581102245f019',
                                           'sha256': 'e48561b8f2494d922f922f04795ff4fef68a531c7859531bcfb142329c6fd75a',
                                           'bytes': 17185},
              'grading_total_cost.js': {'blob': '1700943cc8ed6d67d481b967cd4a68b51dc75a1b',
                                        'sha256': '790ace81f11e44f2377e016340d2270f80893c547bae02e4c9a1b0912549278c',
                                        'bytes': 11641}},
 'physical_tablet_verified': False,
 'main_merge_authorized': False,
 'model_training_authorized': False,
 'runtime_data_modified': False}


def _git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)


def _paths(older, newer, *paths):
    args = ['diff', '--no-renames', '--name-only', '-z', older, newer]
    if paths:
        args += ['--', *paths]
    raw = _git(*args)
    if not raw:
        return []
    rows = raw.decode('utf-8', 'strict').split('\0')
    assert rows[-1] == '', 'unterminated grading successor scope'
    return rows[:-1]


def _assert_pin(ref, name, pin):
    if pin is None:
        assert _git('ls-tree', '-z', ref, '--', name) == b'', ('deleted source reappeared', name)
        return None
    assert _git('rev-parse', ref + ':' + name).decode('ascii').strip() == pin['blob'], ('grading Git blob changed', name)
    expected_tree = ('100644 blob ' + pin['blob'] + '\t' + name + '\0').encode('utf-8')
    assert _git('ls-tree', '-z', ref, '--', name) == expected_tree, ('non-regular grading source', name)
    raw = _git('show', ref + ':' + name)
    assert len(raw) == pin['bytes'], ('grading byte count changed', name)
    assert hashlib.sha256(raw).hexdigest() == pin['sha256'], ('grading SHA changed', name)
    return raw


def validate_grading_input_cost_successor_20261122(source):
    """Explain only the two exact runtime paths, from an unchanged older source."""
    base, first, final = (EXPECTED[key] for key in ('baseline_commit', 'source_commit', 'final_source_commit'))
    head = _git('rev-parse', 'HEAD').decode('ascii').strip()
    assert all(isinstance(ref, str) and re.fullmatch('[0-9a-f]{40}', ref)
               for ref in (source, base, first, final, head)), 'invalid grading history ref'
    assert base != first != final, 'distinct grading source commits required'
    assert PROOF.is_file() and not PROOF.is_symlink(), 'grading proof missing or linked'
    proof_bytes = PROOF.read_bytes()
    assert len(proof_bytes) <= 64000, 'oversized grading proof'
    proof = json.loads(proof_bytes.decode('utf-8', 'strict'))
    # JSON serialization equality distinguishes false from integer zero.
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'))
    assert canonical(proof) == canonical(EXPECTED), 'grading proof changed'
    assert EXPECTED['reviewed_paths'] == ['grading_self_learning.py', 'grading_total_cost.js']
    assert set(EXPECTED['baseline']) == set(EXPECTED['reviewed']) == set(EXPECTED['reviewed_paths'])
    assert EXPECTED['final_scope'], 'final correction scope required'
    for older, newer in ((source, base), (base, first), (first, final), (final, head)):
        _git('merge-base', '--is-ancestor', older, newer)
    assert _paths(source, base, *EXPECTED['reviewed_paths']) == [], 'older grading edit would be hidden'
    assert _paths(base, first) == sorted(EXPECTED['source_scope']), 'unreviewed initial grading scope'
    assert _paths(first, final) == sorted(EXPECTED['final_scope']), 'unreviewed final grading scope'
    for name, pin in EXPECTED['source_scope'].items():
        _assert_pin(first, name, pin)
    for name, pin in EXPECTED['final_scope'].items():
        _assert_pin(final, name, pin)
    assert EXPECTED['reviewed']['grading_self_learning.py'] == EXPECTED['source_scope']['grading_self_learning.py'], 'learning source unexpectedly changed again'
    for name in EXPECTED['reviewed_paths']:
        before = _assert_pin(base, name, EXPECTED['baseline'][name])
        original = _assert_pin(first, name, EXPECTED['source_scope'][name])
        reviewed = _assert_pin(final, name, EXPECTED['reviewed'][name])
        committed = _assert_pin(head, name, EXPECTED['reviewed'][name])
        assert before != original, ('no reviewed grading change', name)
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), ('grading live path missing or linked', name)
        live = path.read_bytes()
        assert len(live) == EXPECTED['reviewed'][name]['bytes'], ('grading live size changed', name)
        assert hashlib.sha256(live).hexdigest() == EXPECTED['reviewed'][name]['sha256'], ('grading live SHA changed', name)
        assert live == reviewed == committed, ('unreviewed live grading bytes', name)
    return frozenset(EXPECTED['reviewed_paths'])
