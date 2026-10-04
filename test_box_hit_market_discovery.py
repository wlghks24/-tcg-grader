import unittest
from unittest.mock import patch
import box_hit_market_discovery as m
import tablet_runtime_manifest
import runtime_bundle_guard_v143

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

    def test_registry_promoted_game_is_discoverable_and_watch_is_not_delegated(self):
        rows=[
            {'canonical':'Pokémon','label_ko':'포켓몬','aliases':['Pokemon']},
            {'canonical':'GUNDAM CARD GAME','label_ko':'건담 카드게임','aliases':['Gundam TCG','건담']},
        ]
        with patch.object(m.tcg_game_registry,'enabled_games',return_value=rows) as enabled:
            games=m._market_games()
            enabled.assert_called_once_with('market',root=m.BASE)
            self.assertIn('GUNDAM CARD GAME',games)
            self.assertIn('건담',games['GUNDAM CARD GAME'])
            self.assertEqual(m._game('건담 Booster Box sealed',games),'GUNDAM CARD GAME')
            self.assertEqual(len(m._queries('GUNDAM CARD GAME','BOX')),1)
            self.assertEqual(len(m._queries('GUNDAM CARD GAME','HIT')),1)

    def test_tablet_and_runtime_bundle_include_box_hit_dependency(self):
        self.assertIn('box_hit_market_discovery.py',tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn('box_hit_market_discovery.py',runtime_bundle_guard_v143.REQUIRED_FILES)

if __name__=='__main__':unittest.main()
