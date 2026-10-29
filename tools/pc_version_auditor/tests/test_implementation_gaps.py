"""Review leads remain unverified; repeated evidence cannot inflate task counts."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc_auditor'))
import audit
import repair


class ImplementationGapTests(unittest.TestCase):
    def scan(self, source):
        with mock.patch.object(audit, 'git', return_value=source.encode()):
            return audit.code_map(Path('.'), ['feature.py'])

    def test_explicit_stubs_are_review_leads_without_running_source(self):
        data = self.scan('raise RuntimeError("must not execute")\ndef pending():\n    "doc"\n    pass\nasync def other():\n    ...\ndef missing():\n    raise NotImplementedError("pending")\n')
        hints = data['risk_hints']
        self.assertEqual(['PLACEHOLDER_FUNCTION_REVIEW', 'PLACEHOLDER_FUNCTION_REVIEW', 'UNIMPLEMENTED_RAISE_REVIEW'], [x['rule'] for x in hints])
        self.assertTrue(all(x['status'] == 'REVIEW_REQUIRED' for x in hints))

    def test_executable_functions_and_string_mentions_are_not_stubs(self):
        data = self.scan('def real():\n    "pass NotImplementedError"\n    return None\ndef handler():\n    try:\n        return 1\n    except ValueError:\n        pass\n')
        self.assertEqual([], data['risk_hints'])

    def test_bare_unimplemented_raise_is_detected(self):
        data = self.scan('def f():\n    raise NotImplementedError\n')
        self.assertEqual('UNIMPLEMENTED_RAISE_REVIEW', data['risk_hints'][0]['rule'])

    def test_exact_duplicate_rows_merge_but_locations_remain(self):
        hint = {'rule': 'PLACEHOLDER_FUNCTION_REVIEW', 'path': 'x.py', 'line': 2}
        code = {'risk_hints': [hint, dict(hint), dict(hint, line=3)]}
        items = repair.improvement_items(code, [])
        self.assertEqual([2, 3], [x['line'] for x in items])
        self.assertTrue(all(x['state'] == 'REVIEW_REQUIRED' for x in items))

    def test_distinct_inherited_finding_ids_remain_open(self):
        rows = [{'id': 'W001-F001', 'summary': 'same', 'state': 'OPEN_LINEAGE_GUARD'},
                {'id': 'W001-F002', 'summary': 'same', 'state': 'OPEN_LINEAGE_GUARD'}]
        items = repair.improvement_items({}, rows + [dict(rows[0])])
        self.assertEqual(2, len(items))
        self.assertTrue(all(x['state'] == 'OPEN_NOT_AUTOCLOSED' for x in items))


if __name__ == '__main__':
    unittest.main()
