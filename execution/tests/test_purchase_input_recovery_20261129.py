"""Regression checks for malformed purchase keys without network calls."""
import copy
import unittest

import update_purchase_sources as purchase


class PurchaseInputRecoveryTests(unittest.TestCase):
    @staticmethod
    def row():
        return {"name": "fixture", "region": "KR", "type": "map", "games": ["Pokemon"],
                "channel": "online", "url_template": "https://www.google.com/maps/search/{query}"}

    def test_malformed_keys_never_stop_any_restore_generator(self):
        for field in ("name", "region", "channel"):
            for value in ([], {}, None, False, 42):
                row = self.row()
                row[field] = value
                for restore in (purchase.ensure_gyeonggi_lotte_stores,
                                purchase.ensure_diverse_retail_channels,
                                purchase.ensure_registry_tcg_sources):
                    with self.subTest(field=field, value=value, restore=restore.__name__):
                        before = copy.deepcopy(row)
                        result = restore([row])
                        self.assertEqual(before, row)
                        self.assertEqual(before, result[0])
                        self.assertGreater(len(result), 1)

    def test_malformed_fields_are_value_errors_not_type_errors(self):
        for field in ("region", "type", "channel", "retailer_category"):
            for value in ([], {}, False, 42):
                row = self.row()
                row[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    purchase.normalize_source(row)

    def test_default_channel_and_nonobject_rows(self):
        self.assertEqual({("a", "KR", "online")},
                         purchase._known_source_keys([None, [], {"name": "a", "region": "KR"}],
                                                     ("name", "region", "channel")))

    def test_valid_row_and_idempotent_restore(self):
        row = self.row()
        self.assertEqual("KR", purchase.normalize_source(row)["region"])
        for restore in (purchase.ensure_gyeonggi_lotte_stores,
                        purchase.ensure_diverse_retail_channels,
                        purchase.ensure_registry_tcg_sources):
            result = restore([row])
            self.assertEqual(result, restore(result))


if __name__ == "__main__":
    unittest.main()
