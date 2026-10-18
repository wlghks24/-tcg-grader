import unittest
from tools.catalog_image_identity import checked_image_url,manifest_index,catalog_row_identity

class EditionIdentityTests(unittest.TestCase):
    def test_region_scoped_key(self):
        row={"region":"KR","url":"https://cdn.example.org/k.jpg"}
        idx=manifest_index({"shared":row})
        self.assertIn(("KR","shared"),idx)
        self.assertNotIn(("JP","shared"),idx)
    def test_distinct_country_same_name(self):
        idx=manifest_index({"KR|shared":{"region":"KR","url":"https://cdn.example.org/k.jpg"},"JP|shared":{"region":"JP","url":"https://cdn.example.org/j.jpg"}})
        self.assertEqual(len(idx),2)
    def test_china_scripts_remain_separate(self):
        idx=manifest_index({"CN-S|同名":{"region":"CN-S","url":"https://cdn.example.org/s.jpg"},"CN-T|同名":{"region":"CN-T","url":"https://cdn.example.org/t.jpg"}})
        self.assertEqual(len(idx),2)
    def test_missing_or_conflicting_region_rejected(self):
        for bad in ({"x":{"url":"https://a.example.org/a"}} ,{"KR|x":{"region":"JP","url":"https://a.example.org/a"}}):
            with self.assertRaises(ValueError): manifest_index(bad)
    def test_duplicate_identity_rejected(self):
        with self.assertRaises(ValueError): manifest_index({"KR|x":{"region":"KR","url":"https://a.example.org/a"},"x":{"region":"KR","url":"https://a.example.org/a"}})
    def test_bad_urls_rejected(self):
        urls=["http://x.org/x","https://a:b@x.org/x","https://127.0.0.1/x","https://localhost/x","https://x.org:444/x","https://x.org/x#f",'https://x.org/"x',"https://x.org/\nx"]
        for url in urls:
            with self.subTest(url=url),self.assertRaises(ValueError): checked_image_url(url)
    def test_https_url_accepted(self):
        self.assertEqual(checked_image_url("https://cdn.example.org/x.webp?y=3"),"https://cdn.example.org/x.webp?y=3")
    def test_row_identity(self):
        self.assertEqual(catalog_row_identity(' {country:"US",name:"Box",source:"ref"}'),("US","Box"))
    def test_unsupported_row_rejected(self):
        with self.assertRaises(ValueError): catalog_row_identity(' {country:"ZZ",name:"Box"}')
    def test_alias_supported(self):
        idx=manifest_index({"JP|alias":{"name":"correct","region":"JP","url":"https://a.org/p.jpg"}})
        self.assertIn(("JP","correct"),idx)
