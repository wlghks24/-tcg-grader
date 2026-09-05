import pathlib
import unittest

import gpt_data_engine as gde


class GPTDataEngineSafetyTests(unittest.TestCase):
    def test_protected_tcg_columns(self):
        for name in ('price_krw','source_url','release_date','card_number','grade','region','lineage_key'):
            self.assertTrue(gde.is_protected_column(name), name)

    def test_generic_feature_not_protected(self):
        self.assertFalse(gde.is_protected_column('temperature'))
        self.assertFalse(gde.is_protected_column('sensor_score'))

    def test_safe_defaults_do_not_mutate(self):
        p = gde.CorrectionPolicy()
        self.assertFalse(p.allow_numeric_imputation)
        self.assertFalse(p.allow_categorical_imputation)
        self.assertFalse(p.allow_outlier_clipping)

    def test_original_split_typo_not_present(self):
        text = pathlib.Path(gde.__file__).read_text(encoding='utf-8')
        self.assertNotIn('test_state=', text)
        self.assertIn('random_state=42', text)

    @unittest.skipIf(gde.pd is None, 'optional pandas/sklearn dependencies not installed')
    def test_price_outlier_is_diagnosed_not_clipped_by_default(self):
        df = gde.pd.DataFrame({'price_krw':[1000,1100,1200,1300,999999], 'sensor_score':[1,2,3,4,100]})
        engine = gde.GPTDataOptimizationEngine()
        raw = engine.collect_data(df)
        report = engine.diagnose_errors(raw)
        clean = engine.auto_correct(raw)
        self.assertTrue(report['outliers']['price_krw']['protected'])
        self.assertEqual(clean['price_krw'].tolist(), df['price_krw'].tolist())
        self.assertEqual(engine.correction_log, [])


if __name__ == '__main__':
    unittest.main()
