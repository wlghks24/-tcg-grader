import unittest
import box_hit_market_discovery as m

class BoxHitMarketDiscoveryTests(unittest.TestCase):
    def test_classifies_box(self):
        self.assertEqual(m._asset('Pokemon Scarlet Violet Booster Box Japanese'),'BOX')
    def test_classifies_hit(self):
        self.assertEqual(m._asset('One Piece Manga Rare Parallel SEC card'),'HIT')
    def test_rejects_accessory_box(self):
        self.assertEqual(m._asset('Pokemon deck box storage box sleeve'),'')
    def test_region_and_game(self):
        self.assertEqual(m._region('포켓몬 한국판 카드 박스','kream'),'KR')
        self.assertEqual(m._game('NARUTO CARD GAME booster box'),'NARUTO')
    def test_new_reference_sources_and_game_scope(self):
        names={row[1] for row in m.SOURCES}
        self.assertTrue({'SNKRDUNK','JustTCG','TCGdex','Pavilion TCG'}<=names)
        self.assertTrue(m._source_supports_game('tcgdex','Pokémon'))
        self.assertFalse(m._source_supports_game('tcgdex','ONE PIECE'))
        self.assertFalse(m._source_supports_game('pavilion','NARUTO'))

if __name__=='__main__':unittest.main()
