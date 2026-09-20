from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import main_branch_protection_audit


class MainBranchProtectionAuditV265Tests(unittest.TestCase):
    def test_policy_is_machine_readable(self):
        policy = main_branch_protection_audit.load_policy('.github/main-branch-policy.json')
        self.assertEqual(policy['branch'], 'main')
        self.assertTrue(policy['require_protected_branch'])
        self.assertTrue(policy['require_pull_request_before_merge'])
        self.assertGreaterEqual(len(policy['recommended_required_checks']), 4)

    def test_unprotected_main_fails_evaluation(self):
        policy = {
            'schema_version': 1,
            'branch': 'main',
            'require_protected_branch': True,
            'recommended_required_checks': ['Guard A'],
        }
        result = main_branch_protection_audit.evaluate(policy, {
            'name': 'main',
            'protected': False,
            'protection': {'required_status_checks': {'contexts': [], 'checks': []}},
        })
        self.assertFalse(result['ok'])
        self.assertEqual(result['failures'], ['main branch is not protected'])

    def test_protected_main_passes_and_surfaces_checks(self):
        policy = {
            'schema_version': 1,
            'branch': 'main',
            'require_protected_branch': True,
            'recommended_required_checks': ['Guard A'],
        }
        result = main_branch_protection_audit.evaluate(policy, {
            'name': 'main',
            'protected': True,
            'protection': {
                'required_status_checks': {
                    'contexts': ['Guard A / verify'],
                    'checks': [{'context': 'Guard A / verify'}],
                },
            },
        })
        self.assertTrue(result['ok'])
        self.assertEqual(result['required_status_check_contexts'], ['Guard A / verify'])

    def test_bad_policy_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            path.write_text(json.dumps({'schema_version': 2}), encoding='utf-8')
            with self.assertRaises(ValueError):
                main_branch_protection_audit.load_policy(path)


if __name__ == '__main__':
    unittest.main()
