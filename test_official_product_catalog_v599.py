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
  self.assertEqual(len(self.items),47)
  self.assertEqual(len(set(p['id'] for p in self.items)),47)
  self.assertEqual({p['game'] for p in self.items},{'Pokémon','ONE PIECE','GUNDAM CARD GAME','Digimon Card Game','Star Wars: Unlimited','DRAGON BALL SUPER: FUSION WORLD','Yu-Gi-Oh!','Disney Lorcana','Godzilla Card Game','Palworld OFFICIAL CARD GAME'})
 def test_official_sources_and_dates(self):
  hosts={'Pokémon':'pokemoncard.co.kr','ONE PIECE':'onepiece-cardgame.kr','GUNDAM CARD GAME':'gundam-gcg.com','Digimon Card Game':'digimoncard.com','Star Wars: Unlimited':'starwarsunlimited.com','DRAGON BALL SUPER: FUSION WORLD':'dbs-cardgame.com','Yu-Gi-Oh!':'yugioh-card.com','Disney Lorcana':'disneylorcana.com','Godzilla Card Game':'godzilla-cardgame.com','Palworld OFFICIAL CARD GAME':'palworld-official-cardgame.com'}
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
  t=[x for x in self.items if x['game']=='ONE PIECE'];self.assertEqual(len(t),9)
  for x in t:self.assertEqual((x['country'],x['packs_per_box'],x['cards_per_pack'],x['msrp']['amount']),('KR',24,'6',48000))
 def test_five_official_korean_pokemon_boxes_include_pack_math_and_msrp(self):
  pokemon=[p for p in self.items if p['game']=='Pokémon' and p['country']=='KR']
  self.assertEqual(5,len(pokemon))
  self.assertEqual({'2026-09-16','2026-08-21','2026-06-26','2026-05-01','2026-01-23'},
                   {p['release_date'] for p in pokemon})
  expected={('LOCAL-30TH-2026',20,6,70000),('LOCAL-STORM-2026',30,5,45000),
            ('LOCAL-ABYSS-2026',30,5,45000),('LOCAL-NINJA-2026',30,5,30000),
            ('LOCAL-MEGADREAMEX-2026',10,10,50000)}
  observed={(p['set_code'],p['packs_per_box'],int(p['cards_per_pack']),p['msrp']['amount']) for p in pokemon}
  self.assertEqual(expected,observed)
  for p in pokemon:
   self.assertEqual('KR',p['country'])
   self.assertEqual('BOX',p['product_type'])
   self.assertFalse(p['set_code_verified']);self.assertTrue(p['set_code'].startswith('LOCAL-'))
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
 def test_new_official_games_use_native_region_and_pack_type(self):
  expected={'DRAGON BALL SUPER: FUSION WORLD':5,'Yu-Gi-Oh!':4,'Disney Lorcana':1}
  for game,count in expected.items():
   subset=[p for p in self.items if p['game']==game]
   self.assertEqual(count,len(subset),game)
   self.assertTrue(all(p['country']=='US' for p in subset))
  db=[p for p in self.items if p['game']=='DRAGON BALL SUPER: FUSION WORLD']
  self.assertTrue(all(p['product_type']=='BOOSTER_PACK' and 'packs_per_box' not in p for p in db))
  self.assertEqual('2026-10-16',next(p for p in db if p['set_code']=='FB11')['release_date'])
  fb09=next(p for p in db if p['set_code']=='FB09')
  self.assertEqual('12',fb09['cards_per_pack'])
  self.assertNotIn('pull_rate',fb09)
  lorcana=next(p for p in self.items if p['game']=='Disney Lorcana')
  self.assertEqual(('PRERELEASE_BOX',6), (lorcana['product_type'],lorcana['packs_per_box']))
  self.assertNotIn('msrp',lorcana)

 def test_all_japanese_pokemon_products_are_packs_with_only_official_pricing(self):
  items=[p for p in self.items if p['game']=='Pokémon' and p['country']=='JP']
  self.assertEqual(5,len(items))
  self.assertEqual({'2026-09-16','2026-07-31','2026-05-22','2026-03-13','2026-01-23'},
                   {p['release_date'] for p in items})
  self.assertTrue(all(p['product_type']=='BOOSTER_PACK' for p in items))
  self.assertTrue(all(p.get('set_code_verified') is False for p in items))
  self.assertTrue(all(p['msrp']['currency']=='JPY' and p['msrp']['unit']=='PACK'
                      and 'packs_per_box' not in p for p in items))

 def test_official_godzilla_palworld_are_independent_games(self):
  g=[p for p in self.items if p['game']=='Godzilla Card Game']
  self.assertEqual(3,len(g))
  self.assertEqual({'EBP01','EBP03','EBP04'},{p['set_code'] for p in g})
  self.assertTrue(all(p['product_type']=='BOOSTER_PACK' and p['country']=='US' for p in g))
  pal=[p for p in self.items if p['game']=='Palworld OFFICIAL CARD GAME']
  self.assertEqual(2,len(pal))
  box=next(p for p in pal if p['set_code']=='BP01')
  self.assertEqual(('BOX',12,'7'),(box['product_type'],box['packs_per_box'],box['cards_per_pack']))
  self.assertEqual('2026-10-30',next(p for p in pal if p['set_code']=='BP02')['release_date'])
  self.assertTrue(all('verified_sales' not in p and 'pull_rate' not in p for p in pal))

 def test_hyperia_prerelease_event_is_not_box_shelf_date(self):
  row=next(p for p in self.items if p['id']=='lc-HYPERIA-PRE-US')
  self.assertEqual(('', '2026-10-16','2026-10-23'),
                   (row['release_date'],row['event_start_date'],row['set_release_date']))
  self.assertEqual(('PRERELEASE_BOX',6),(row['product_type'],row['packs_per_box']))
  self.assertNotIn('msrp',row)
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
