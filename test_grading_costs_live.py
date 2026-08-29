import unittest
import grading_costs_live as g

class GradingCostTests(unittest.TestCase):
    def test_all_five_companies_present(self):
        self.assertEqual(set(g.COMPANIES),{'PSA','BGS','CGC','TAG','BRG'})
    def test_official_sources_and_positive_fees(self):
        for name,c in g.COMPANIES.items():
            self.assertTrue(c['source'].startswith('https://'))
            self.assertTrue(c['services'])
            for s in c['services']:
                self.assertGreater(float(s['fee']),0)
    def test_variable_shipping_is_not_fabricated(self):
        for c in g.COMPANIES.values():
            self.assertIsInstance(c.get('shipping'),str)
            self.assertNotIn('fixed_fake',c.get('shipping',''))
    def test_known_current_fees(self):
        by={k:{x['name']:x['fee'] for x in v['services']} for k,v in g.COMPANIES.items()}
        self.assertEqual(by['PSA']['Regular'],79.99)
        self.assertEqual(by['CGC']['Economy'],20.0)
        self.assertEqual(by['TAG']['Standard'],39.0)
        self.assertEqual(by['BRG']['Regular'],19800)

if __name__=='__main__': unittest.main()
