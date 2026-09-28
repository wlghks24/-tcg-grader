import unittest

import update_market_prices as market


class PackMagikMarketParserTests(unittest.TestCase):
    def test_market_label_is_card_local(self):
        text = "Other Card OP14-001 Market $999.99 Trafalgar Law [Alt Art] The Azure Sea's Seven OP14-009 Market $17.15 PSA 10 $66.50"
        self.assertEqual(market.packmagik_card_market_price(text, "OP14-009", "Trafalgar Law"), "17.15")

    def test_market_value_label_is_supported(self):
        text = "Trafalgar Law [Alternate Art] Azure Sea's Seven [Japanese] OP14-009 Market Value $11.49 PSA 10 $63.20"
        self.assertEqual(market.packmagik_card_market_price(text, "OP14-009", "Trafalgar Law"), "11.49")

    def test_wrong_card_is_not_reused(self):
        text = "Nami OP14-031 Market $74.53 Trafalgar Law OP14-001 Market $19.99"
        self.assertIsNone(market.packmagik_card_market_price(text, "OP14-009", "Trafalgar Law"))


if __name__ == "__main__":
    unittest.main()
