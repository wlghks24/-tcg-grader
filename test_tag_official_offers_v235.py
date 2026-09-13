import copy
import json
import unittest
from unittest.mock import patch

import grading_company_watch as w


def page(name, prices=(30, 35), states=('OutOfStock', 'InStock')):
    url = w.TAG_PRODUCT_SOURCES[name]
    product = {'@type': 'Product', 'name': 'GRADING | ' + name.upper(), 'url': url,
               'offers': [{'@type': 'Offer', 'url': url, 'priceCurrency': 'USD',
                           'price': price, 'availability': 'https://schema.org/' + state}
                          for price, state in zip(prices, states)]}
    return product


def html(product):
    return '<p>Insurance $500. Shipping kit $49.95. Review price $1.</p><script type="application/ld+json">' + json.dumps(product) + '</script>'


class TagOfficialOffersTests(unittest.TestCase):
    def test_price_comes_from_available_offer_not_insurance_or_review(self):
        row = w.parse_tag_product_offers(html(page('Standard')), 'Standard', w.TAG_PRODUCT_SOURCES['Standard'])
        self.assertEqual(row['fee'], 35)
        self.assertEqual(row['availability'], 'open')

    def test_paused_tier_keeps_listed_price_without_claiming_available(self):
        row = w.parse_tag_product_offers(html(page('Basic', states=('OutOfStock', 'OutOfStock'))), 'Basic', w.TAG_PRODUCT_SOURCES['Basic'])
        self.assertEqual(row['fee'], 30)
        self.assertEqual(row['availability'], 'paused')

    def test_invalid_identity_currency_price_and_foreign_urls_fail(self):
        for field, value in [('priceCurrency', 'JPY'), ('price', float('nan')),
                             ('price', True), ('url', 'https://example.com/fake'),
                             ('url', 'https://www.psacard.com/products/grading-standard'),
                             ('availability', 'https://example.com/InStock')]:
            with self.subTest(field=field, value=value):
                product = page('Standard')
                product['offers'][0][field] = value
                with self.assertRaises(ValueError):
                    w.parse_tag_product_offers(html(product), 'Standard', w.TAG_PRODUCT_SOURCES['Standard'])
        product = page('Basic')
        with self.assertRaises(ValueError):
            w.parse_tag_product_offers(html(product), 'Standard', w.TAG_PRODUCT_SOURCES['Standard'])

    def test_soldout_template_converts_minor_units_and_preserves_pause(self):
        data = {'shop': {'money_with_currency_format': '${{amount}} USD'},
                'product': {'title': 'GRADING | EXPRESS', 'handle': 'grading-express',
                            'variants': [{'price': 7900, 'available': False}]}}
        raw = '<script id="tpo-store-data" type="application/json">' + json.dumps(data) + '</script>'
        row = w.parse_tag_product_offers(raw, 'Express', w.TAG_PRODUCT_SOURCES['Express'])
        self.assertEqual(row['fee'], 79)
        self.assertEqual(row['availability'], 'paused')

    def test_complete_fallback_and_failure_preserve_last_good(self):
        spec = w.WATCH_SOURCES['TAG'][0]
        overview = '<h1>Grading services</h1>' + '<p>See our service table image.</p>' * 8
        pages = {url: html(page(name)) for name, url in w.TAG_PRODUCT_SOURCES.items()}
        pages[spec['url']] = overview
        with patch.object(w, 'WATCH_SOURCES', {'TAG': (spec,)}):
            good = w.collect(fetcher=pages.__getitem__)
            self.assertEqual(good['summary']['healthy_sources'], 1)
            self.assertEqual(len(good['sources'][spec['id']]['services']), 5)
            before = copy.deepcopy(good['sources'][spec['id']]['services'])
            pages[w.TAG_PRODUCT_SOURCES['Express']] = '<html>Temporary maintenance</html>'
            failed = w.collect(good, fetcher=pages.__getitem__)
        self.assertEqual(failed['sources'][spec['id']]['status'], 'degraded')
        self.assertEqual(failed['sources'][spec['id']]['services'], before)
        self.assertTrue(failed['companies']['TAG']['markets']['US']['retained_last_good'])


if __name__ == '__main__':
    unittest.main()
