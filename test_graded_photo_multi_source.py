import unittest
import graded_photo_multi_source as g

class GradedPhotoMultiSourceTests(unittest.TestCase):
    def test_company_grade_parse(self):
        self.assertEqual(g._company('Pokemon PSA 10 graded card'),'PSA')
        self.assertEqual(g._grade('Pokemon PSA 10 graded card','PSA'),10.0)

    def test_unverified_never_becomes_training(self):
        self.assertFalse(g._verified_status('PSA','12345678',10.0,{}))

    def test_registry_exact_match_required(self):
        reg={('PSA','12345678'):10.0}
        self.assertTrue(g._verified_status('PSA','12345678',10.0,reg))
        self.assertFalse(g._verified_status('PSA','12345678',9.0,reg))

    def test_source_domains_are_public_marketplaces(self):
        ids={x['id'] for x in g.SOURCES}
        self.assertTrue({'amazon_us','amazon_jp','kream','daangn'}.issubset(ids))

if __name__=='__main__':unittest.main()
