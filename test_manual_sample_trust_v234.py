import json
import subprocess
import unittest
from pathlib import Path

import manual_collection_mode as mode


class ManualSampleTrustTests(unittest.TestCase):
    def test_stale_trust_is_removed_at_runtime_boundary(self):
        for company, cert, grade, registry in [
            ('PSA', '12345678', 10, {}),
            ('PSA', '12345678', 10, {('PSA', '12345678'): 9}),
            ('UNKNOWN', '12345678', 10, {}),
            ('PSA', '', 10, {}),
            ('PSA', '12345678', float('nan'), {}),
        ]:
            with self.subTest(company=company, cert=cert, grade=grade):
                row = dict(company=company, certification_id=cert, grade=grade,
                           official_result=True, official_grade=10,
                           verification_method='live_official_lookup',
                           manual_official_verification_required=False)
                out, _ = mode._registry_only_official_verify_rows([row], registry)
                self.assertFalse(out[0]['official_result'])
                self.assertTrue(out[0]['manual_official_verification_required'])
                self.assertNotEqual(out[0]['verification_method'], 'live_official_lookup')
                self.assertTrue(row['official_result'])  # no input mutation

    def test_dashboard_does_not_treat_pending_text_as_verified(self):
        source = Path('graded_photo_dashboard.js').read_text()
        functions = '\n'.join(line for line in source.splitlines()
                              if line.startswith(('function statusOf(', 'function isVerified(')))
        rows = [
            {'status': '공식검증 대기'}, {'verified': True},
            {'status': 'verified_reference', 'official_result': False},
            {'official_result': True, 'manual_official_verification_required': True},
            {'official_result': True, 'evidence_conflicts': ['grade_conflict']},
            {'official_result': True},
        ]
        output = subprocess.check_output(['node', '-e', functions +
            '\nconsole.log(JSON.stringify(' + json.dumps(rows) + '.map(isVerified)));'], text=True)
        self.assertEqual(json.loads(output), [False, False, False, False, False, True])

    def test_summary_keeps_reference_and_official_counts_separate(self):
        source = Path('manual_official_verify_bridge.js').read_text()
        functions = source[source.index('function countFromCard('):source.index('function installSummaryObserver(')]
        script = functions + '''
const card=(label,count)=>({label:{textContent:label},value:{textContent:count},
 removed:false,querySelector(s){return s==='span'?this.label:this.value},
 remove(){this.removed=true}});
const official=card('공식검증','1'),reference=card('참고학습 반영','5');
const summary={children:[official,reference]},footer={textContent:''};
global.document={querySelector(s){return s.includes('.gpd-summary')?summary:footer}};
mergeVerifiedLearningSummary();mergeVerifiedLearningSummary();
console.log(JSON.stringify([official.value.textContent,reference.value.textContent,
 reference.removed,official.label.textContent]));
'''
        output = subprocess.check_output(['node', '-e', script], text=True)
        self.assertEqual(json.loads(output), ['1', '5', False, '공식검증'])


if __name__ == '__main__':
    unittest.main()
