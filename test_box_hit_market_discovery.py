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

if __name__=='__main__':unittest.main()
