"""Provider detail enrichment is bounded, local and identity-specific; no live calls."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library
from execution import tablet_catalog_bridge as bridge


class ImageMetadataTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.base=Path(temp.name);self.repo=self.base/'repo';self.repo.mkdir()
        self.store=self.base/'private';self.store.mkdir();(self.store/'images').mkdir()
        self.addCleanup(patch.stopall);patch.object(library,'storage_root',return_value=self.store).start()
        self.write('tcg_game_registry.json',{'schema_version':1,'games':[{'id':'pokemon','canonical':'Pokémon'}]})
        self.write('market_watch.json',{'items':[]});self.write('releases.json',{'items':[]});self.write('market_prices.json',{'entries':{}})
        buf=io.BytesIO();Image.new('RGB',(20,30),'white').save(buf,format='PNG');self.png=buf.getvalue()
        self.row={'key':'pokemon/ja/sv1s-001','provider':'TCGdex','game_id':'pokemon','region':'JP','kind':'CARD',
                  'name':'Fixture sv1s-001','url':'https://assets.tcgdex.net/ja/sv/sv1s/001/high.webp',
                  'source':'https://api.tcgdex.net/v2/ja/cards',
                  'card_metadata':{'card_code':'sv1s-001','language':'ja'}}
    def write(self,name,payload):(self.repo/name).write_text(json.dumps(payload))
    def save(self,metadata=None):
        return library.save_image(self.repo,{'game_id':'pokemon','region':'JP','kind':'CARD','name':'Fixture',
            'provider':'TCGdex','source_id':self.row['key'],'source_url':self.row['source'],
            'card_metadata':metadata if metadata is not None else self.row['card_metadata'],
            'image_base64':'data:image/png;base64,'+base64.b64encode(self.png).decode()},trusted_auto=True)
    def test_detail_request_uses_exact_locale_and_card_id(self):
        with patch.object(auto,'fetch_json',return_value={'id':'sv1s-001','localId':'001',
                'set':{'id':'sv1s','name':'Fixture Set'},'rarity':'Rare','category':'Pokemon'}) as fetch:
            row=auto._complete_candidate_metadata(self.row)
        fetch.assert_called_once_with('https://api.tcgdex.net/v2/ja/cards/sv1s-001')
        self.assertEqual(row['card_metadata']['set_code'],'sv1s')
        self.assertEqual(row['card_metadata']['card_number'],'001')
        self.assertEqual(row['source'],'https://api.tcgdex.net/v2/ja/cards/sv1s-001')
        self.assertNotIn('set_code',self.row['card_metadata'])
    def test_wrong_card_detail_is_not_attached(self):
        for detail in ({'id':'sv1s-002'},[],None):
            with self.subTest(detail=detail),patch.object(auto,'fetch_json',return_value=detail):
                with self.assertRaises(auto.ProviderError):auto._complete_candidate_metadata(self.row)
    def test_existing_complete_metadata_does_not_trigger_detail(self):
        row={**self.row,'card_metadata':{'card_code':'sv1s-001','set_code':'sv1s'}}
        with patch.object(auto,'fetch_json') as fetch:self.assertEqual(auto._complete_candidate_metadata(row),row)
        fetch.assert_not_called()
    def test_metadata_persists_with_image_and_missing_fields_are_queued(self):
        saved=self.save();record=library.list_images()['items'][0]
        self.assertEqual(record['card_metadata'],self.row['card_metadata'])
        report=bridge.build_report(self.repo)
        self.assertEqual(report['summary']['card_metadata_gaps'],1)
        task=next(x for x in report['gap_queue'] if x.get('image_id')==saved['id'])
        self.assertEqual(task['missing_fields'],['set_reference'])
        bridge.write_gap_queue(self.repo)
        self.assertTrue((self.store/'collection_gap_queue_v2.json').is_file())
    def test_enrichment_updates_only_missing_metadata_and_keeps_image_bytes(self):
        saved=self.save();before={x.name:x.read_bytes() for x in (self.store/'images').iterdir()}
        self.assertTrue(library.enrich_auto_metadata(saved['id'],'TCGdex',self.row['key'],{'set_code':'sv1s'}))
        self.assertEqual(before,{x.name:x.read_bytes() for x in (self.store/'images').iterdir()})
        self.assertFalse(library.enrich_auto_metadata(saved['id'],'TCGdex',self.row['key'],{'set_code':'other'}))
        self.assertFalse(library.enrich_auto_metadata(saved['id'],'Scryfall',self.row['key'],{'rarity':'Rare'}))
        self.assertFalse(library.enrich_auto_metadata(saved['id'],'TCGdex','wrong',{'rarity':'Rare'}))
        self.assertEqual(bridge.build_report(self.repo)['summary']['card_metadata_gaps'],0)
    def test_deleted_image_is_not_recreated_by_metadata_enrichment(self):
        saved=self.save();library.delete_image(saved['id'])
        self.assertFalse(library.enrich_auto_metadata(saved['id'],'TCGdex',self.row['key'],{'set_code':'sv1s'}))
        self.assertEqual(library.list_images()['count'],0)
        self.assertEqual(list((self.store/'images').iterdir()),[])
    def test_untrusted_or_unbounded_metadata_is_rejected_before_storage(self):
        for metadata in ({'unsupported':'x'},{'set_code':'x'*41},{'card_code':True},{'card_code':'a\nb'}):
            with self.subTest(metadata=metadata),self.assertRaises(ValueError):self.save(metadata)
        self.assertEqual(list((self.store/'images').iterdir()),[])
    def test_old_completed_image_is_enriched_without_image_download(self):
        saved=self.save();state=auto._state(self.store)
        state['completed'][hashlib.sha256(self.row['key'].encode()).hexdigest()]={'id':saved['id']}
        auto._save(self.store,state)
        complete={**self.row,'card_metadata':{**self.row['card_metadata'],'set_code':'sv1s'}}
        with patch.object(auto,'_candidate_batches',return_value=[(0,'pokemon|JP',1,'pokemon','JP')]), \
             patch.object(auto,'candidates_pokemon',return_value=[self.row]), \
             patch.object(auto,'_complete_candidate_metadata',return_value=complete), \
             patch.object(auto,'fetch_binary') as download:
            result=auto.collect_once(self.repo,sleeper=lambda _:None)
        download.assert_not_called();self.assertEqual(result['metadata_enriched'],1)
        self.assertEqual(result['saved'],0);self.assertEqual(result['skipped'],1)
        self.assertEqual(library.list_images()['items'][0]['card_metadata']['set_code'],'sv1s')
    def test_completed_deleted_card_does_not_request_metadata(self):
        saved=self.save();library.delete_image(saved['id']);state=auto._state(self.store)
        state['completed'][hashlib.sha256(self.row['key'].encode()).hexdigest()]={'id':saved['id']}
        auto._save(self.store,state)
        with patch.object(auto,'_candidate_batches',return_value=[(0,'pokemon|JP',1,'pokemon','JP')]), \
             patch.object(auto,'candidates_pokemon',return_value=[self.row]), \
             patch.object(auto,'_complete_candidate_metadata') as detail:
            result=auto.collect_once(self.repo,sleeper=lambda _:None)
        detail.assert_not_called();self.assertEqual(result['skipped'],1)
    def test_set_metadata_alone_never_joins_a_card(self):
        self.assertEqual(bridge.codes('pokemon',{'card_metadata':{'set_code':'SV1S'}}),[])
        self.assertEqual(bridge.codes('pokemon',{'card_metadata':{'card_code':'SV1S-001'}}),['SV1S001'])

if __name__=='__main__':unittest.main()
