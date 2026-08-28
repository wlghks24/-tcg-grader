#!/usr/bin/env python3
import json, unittest
import tcg_updater as server
import grading_accuracy_v99 as accuracy


def row(i, company='BGS', actual=9.5, pred=10, cert=None, card_key=''):
    out={
        'company':company,'actual':actual,'pred':pred,'raw_pred':pred,
        'official_result':True,'certification_id':cert or f'PIPE-{company}-{i:04d}',
        'vision':{'analysisConfidence':90,'frontCenter':48,'backCenter':48,
                  'surfaceRisk':8,'edgeRisk':5,'cornerRisk':4,'surfaceConfidence':88,
                  'multiAngle':True,'engine':'v98-camera-resilience-full-runtime'}
    }
    if card_key: out['card_key']=card_key
    return out


class PipelineTests(unittest.TestCase):
    def test_server_enforces_company_grade_axis(self):
        self.assertEqual(server.valid_learning_rows([row(1,actual=9.3)]),[])
        self.assertEqual(server.valid_learning_rows([row(2,company='TAG',actual=9.5)]),[])
        self.assertEqual(len(server.valid_learning_rows([row(3,actual=9.5)])),1)

    def test_server_preserves_raw_prediction(self):
        x=row(1);x['pred']=9;x['raw_pred']=10
        clean=server.valid_learning_rows([x])
        self.assertEqual(clean[0]['pred'],9);self.assertEqual(clean[0]['raw_pred'],10)

    def test_server_conflicting_cert_is_quarantined(self):
        a=row(1,actual=9,cert='PIPE-CONFLICT');b=row(2,actual=8,cert='PIPE-CONFLICT')
        self.assertEqual(server.valid_learning_rows([a,b]),[])
        self.assertEqual(server.merge_learning_rows([a],[b]),[])

    def test_card_key_groups_same_design(self):
        clean=server.valid_learning_rows([row(i,cert=f'PIPE-GROUP-{i}',card_key='pokemon|set|card|001') for i in range(10)])
        self.assertTrue(all(x['card_id']=='pokemon|set|card|001' for x in clean))
        models=accuracy.train_company_calibration(accuracy.sanitize_rows({'v99_validation':clean}))
        self.assertEqual(models['BGS']['unique_cards'],1);self.assertFalse(models['BGS']['enabled'])

    def test_modern_v99_precedence(self):
        modern=row(1,company='PSA',actual=9,pred=10,cert='PIPE-MODERN')
        legacy=row(2,company='PSA',actual=7,pred=10,cert='PIPE-MODERN')
        clean=accuracy.sanitize_rows({'v99_validation':[modern],'v30_validation':[legacy]})
        self.assertEqual(len(clean),1);self.assertEqual(clean[0]['actual'],9)

    def test_correction_is_downward_only_and_bounded(self):
        self.assertEqual(accuracy.apply_downward_correction('PSA',10,.75),10)
        self.assertEqual(accuracy.apply_downward_correction('PSA',10,-99),9)
        self.assertEqual(accuracy.apply_downward_correction('INVALID',10,-1),1)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PipelineTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'ok':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
