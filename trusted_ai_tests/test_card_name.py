import unittest

from solution import normalize_card_name


class TestCardNameRegression(unittest.TestCase):
    def test_outer_and_repeated_spaces(self):
        self.assertEqual(normalize_card_name("  피카츄   ex  "), "피카츄 ex")

    def test_non_string_rejected(self):
        with self.assertRaises(TypeError):
            normalize_card_name(None)

    def test_empty_value(self):
        self.assertEqual(normalize_card_name("   "), "")

