import json
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
R=Path(__file__).resolve().parent
class OfficialBoxCatalogV599Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.data=json.loads((R/'tcg_official_product_catalog_v599.json').read_text(encoding='utf8'));cls.items=cls.data['products']
 def test_coverage(self):
  self.assertEqual(len(self.items),21)
  self.assertEqual(len(set(p['id'] for p in self.items)),21)
  self.assertEqual({p['game'] for p in self.items},{'Pokémon','ONE PIECE','GUNDAM CARD GAME','Digimon Card Game','Star Wars: Unlimited'})
 def test_official_sources_and_dates(self):
  hosts={'Pokémon':'pokemoncard.co.kr','ONE PIECE':'onepiece-cardgame.kr','GUNDAM CARD GAME':'gundam-gcg.com','Digimon Card Game':'digimoncard.com','Star Wars: Unlimited':'starwarsunlimited.com'}
  for p in self.items:
   u=urlparse(p['source']);h=hosts[p['game']]
   self.assertEqual(u.scheme,'https');self.assertTrue(u.hostname==h or u.hostname.endswith('.'+h))
   for key in ('release_date','set_release_date'):
    if p.get(key):self.assertEqual(date.fromisoformat(p[key]).isoformat(),p[key])
 def test_packages_and_prices_are_not_sold_prices(self):
  for p in self.items:
   if p['product_type']=='BOOSTER_PACK':self.assertNotIn('packs_per_box',p)
   if 'packs_per_box' in p:self.assertIn(p['product_type'],('BOX','PRERELEASE_BOX'))
   self.assertNotIn('verified_sales',p);self.assertNotIn('market_price',p);self.assertNotIn('psa_grade',p)
  self.assertTrue(self.data['policy']['msrp_is_not_market_price'])
 def test_onepiece_korean_boxes(self):
  t=[x for x in self.items if x['game']=='ONE PIECE'];self.assertEqual(len(t),4)
  for x in t:self.assertEqual((x['country'],x['packs_per_box'],x['cards_per_pack'],x['msrp']['amount']),('KR',24,'6',48000))
 def test_five_official_korean_pokemon_boxes_include_pack_math_and_msrp(self):
  pokemon=[p for p in self.items if p['game']=='Pokémon']
  self.assertEqual(5,len(pokemon))
  self.assertEqual({'2026-09-16','2026-08-21','2026-06-26','2026-05-01','2026-01-23'},
                   {p['release_date'] for p in pokemon})
  expected={('30TH-2026',20,6,70000),('STORM-2026',30,5,45000),
            ('ABYSS-2026',30,5,45000),('NINJA-2026',30,5,30000),
            ('MEGADREAMEX-2026',10,10,50000)}
  observed={(p['set_code'],p['packs_per_box'],int(p['cards_per_pack']),p['msrp']['amount']) for p in pokemon}
  self.assertEqual(expected,observed)
  for p in pokemon:
   self.assertEqual('KR',p['country'])
   self.assertEqual('BOX',p['product_type'])
   self.assertEqual('KRW',p['msrp']['currency'])
   self.assertTrue(p['source'].startswith('https://pokemoncard.co.kr/card/'))

 def test_official_gundam_and_digimon_products_are_pack_not_box(self):
  additions=[p for p in self.items if p['id'] in ('gd-GD04','gd-EB01','dg-EX-13')]
  self.assertEqual(3,len(additions))
  self.assertEqual({('gd-GD04','2026-04-24','12+1'),
                    ('gd-EB01','2026-06-26','12'),
                    ('dg-EX-13','2026-10-03','6')},
                   {(p['id'],p['release_date'],p['cards_per_pack']) for p in additions})
  self.assertTrue(all(p['product_type']=='BOOSTER_PACK' for p in additions))
  self.assertTrue(all('packs_per_box' not in p for p in additions))
  self.assertTrue(all('pull_rate' not in p and 'verified_sales' not in p for p in additions))
 def test_reviewed_v599_successor_is_exact_pinned(self):
  support=(R/'sync_v376_successor_test_support.py').read_text(encoding='utf8')
  for marker in ('V599_OFFICIAL_BOX_BASE','V599_OFFICIAL_BOX_CANDIDATE',
                 'V599_OFFICIAL_BOX_BLOBS','V540_BOX_SHA256',
                 'V599_OFFICIAL_BOX_BASE_CSS_BLOB',
                 'preserve_reviewed_v599_official_box_scope'):
   self.assertIn(marker,support)
 def test_compact_user_ui(self):
  js=(R/'box_knowledge_stats.js').read_text(encoding='utf8')
  for term in ('boxOfficialCatalog','<summary>','boxKbGame','box-kb-country','제조사 원문','tcg_official_product_catalog_v599.json'):self.assertIn(term,js)
  self.assertNotIn('tcg_official_product_catalog_v599.json',(R/'box_hit_market_discovery.py').read_text(encoding='utf8'))
if __name__=="__main__":unittest.main()
