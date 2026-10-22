"""Rebuilt contract tests use fixture bytes/temp storage only; never real downloads."""
import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import tablet_image_library_v1 as library
import tablet_catalog_auto_reflect_v43 as reflect
import tablet_collection_image_bridge_v42 as bridge
from execution import tablet_catalog_bridge as engine

class CatalogBridgeTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.repo=self.root/'repo';self.repo.mkdir();self.store=self.root/'private';self.store.mkdir();(self.store/'images').mkdir()
        self.patch=patch.object(library,'storage_root',return_value=self.store);self.patch.start();self.addCleanup(self.patch.stop)
        self.write('tcg_game_registry.json',{'schema_version':1,'games':[
          {'id':'onepiece','canonical':'ONE PIECE','label_ko':'원피스'},
          {'id':'pokemon','canonical':'Pokémon','label_ko':'포켓몬'}]})
        self.write('market_watch.json',{'items':[]});self.write('market_prices.json',{'entries':{}});self.write('releases.json',{'items':[]})
        b=io.BytesIO();Image.new('RGB',(20,30),'white').save(b,format='PNG');self.png=b.getvalue()
    def write(self,name,data):
        (self.repo/name).write_text(json.dumps(data,ensure_ascii=False))
    def image(self,**change):
        return library.save_image(self.repo,{'game_id':'onepiece','region':'JP','kind':'BOX','name':'Fixture OP-01',
          'image_base64':'data:image/png;base64,'+base64.b64encode(self.png).decode(),**change})
    def source(self,**change):
        return {'game':'ONE PIECE','region':'JP','asset':'BOX','name':'Fixture catalog OP-01',
                'product_code':'OP-01','source':'https://official.example/products/op01','link_status':'정상',**change}
    def seed(self,rows=None):self.write('market_watch.json',{'items':rows if rows is not None else [self.source()]})

    def test_exact_unique_identity_links_and_keeps_source_files_and_photos_unchanged(self):
        self.image();self.seed();before={p.name:p.read_bytes() for p in self.repo.iterdir()};index=(self.store/'index.json').read_bytes()
        r=reflect.read_live(self.repo);self.assertTrue(r['ok']);self.assertEqual(r['version'],46)
        self.assertEqual(r['summary']['auto_linked'],1);self.assertEqual(r['catalog_matches'][0]['match'],'CODE_MATCH')
        self.assertTrue(r['local_catalog'][0]['linked_to_existing_catalog'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.repo.iterdir()});self.assertEqual(index,(self.store/'index.json').read_bytes())
        self.assertFalse(r['prices_inferred']);self.assertFalse(r['model_training_performed'])

    def test_wrong_game_edition_or_kind_never_merges(self):
        self.image()
        for change in ({'game':'Pokémon'},{'region':'KR'},{'region':'CN-T'},{'asset':'PACK'}):
            with self.subTest(change=change):
                self.seed([self.source(**change)]);r=reflect.read_live(self.repo)
                self.assertEqual(r['summary']['auto_linked'],0)

    def test_chinese_simplified_and_traditional_remain_distinct(self):
        self.image(region='CN-S');self.seed([self.source(region='CN-T')]);r=reflect.read_live(self.repo)
        self.assertEqual(r['summary']['auto_linked'],0)
        self.assertEqual({x['region'] for x in r['gap_queue']},{'CN-S','CN-T'})

    def test_names_and_code_prefixes_do_not_create_verified_matches(self):
        self.image(name='Shared display title');self.seed([self.source(name='Shared display title',product_code='OP-01')])
        self.assertEqual(reflect.read_live(self.repo)['summary']['auto_linked'],0)
        self.image(name='OP01-001',kind='CARD');self.seed([self.source(asset='HIT')])
        self.assertEqual(reflect.read_live(self.repo)['summary']['auto_linked'],0)

    def test_multiple_images_or_sources_for_one_code_remain_ambiguous(self):
        self.image();self.image(name='Alternative OP-01');self.seed()
        r=reflect.read_live(self.repo);self.assertEqual(r['summary']['auto_linked'],0);self.assertEqual(r['summary']['ambiguous_images'],2)
        library.delete_image(library.list_images()['items'][0]['id'])
        self.seed([self.source(),self.source(name='Different product OP-01',source='https://official.example/other')])
        self.assertEqual(reflect.read_live(self.repo)['summary']['auto_linked'],0)

    def test_conflicting_identifiers_do_not_match_one_available_source(self):
        self.image(name='Compare OP-01 and OP-02');self.seed()
        self.assertEqual(reflect.read_live(self.repo)['summary']['auto_linked'],0)

    def test_blocked_or_unknown_source_health_cannot_complete_a_metadata_link(self):
        self.image()
        for status in ('HTTP 403','네트워크 지연',''):
            self.seed([self.source(link_status=status)])
            r=reflect.read_live(self.repo)
            self.assertEqual(r['summary']['auto_linked'],0)
            self.assertEqual(r['gap_queue'][0]['reason'],'SOURCE_RECHECK_REQUIRED')

    def test_missing_photos_and_metadata_are_queued_in_both_directions(self):
        self.image(name='Unlinked OP-02');self.seed();r=reflect.read_live(self.repo)
        self.assertEqual({x['direction'] for x in r['gap_queue']},{'IMAGE_NEEDS_METADATA','CATALOG_NEEDS_IMAGE'})
        self.assertEqual(reflect.safe_priority(self.repo),{('onepiece','JP'):1})
        self.assertEqual(bridge.analyze(self.repo)['summary']['catalog_records_analyzed'],1)

    def test_private_gap_queue_updates_without_writing_into_checkout(self):
        self.image();self.seed();before=sorted(p.name for p in self.repo.iterdir())
        r=reflect.safe_cycle(self.repo);self.assertTrue(r['ok']);queue=self.store/'collection_gap_queue_v2.json'
        self.assertTrue(queue.is_file());self.assertEqual(sorted(p.name for p in self.repo.iterdir()),before)
        old=queue.read_bytes();(self.store/'index.json').write_text('broken')
        self.assertFalse(reflect.safe_cycle(self.repo)['ok']);self.assertEqual(queue.read_bytes(),old)

    def test_deleted_file_is_not_returned_as_displayable_image(self):
        self.image();self.seed();next((self.store/'images').iterdir()).unlink()
        r=reflect.read_live(self.repo);self.assertEqual(r['local_catalog'],[]);self.assertEqual(r['summary']['missing_local_files'],1)
        self.assertEqual(r['summary']['catalog_to_image_gaps'],1)

    def test_source_failure_is_reported_and_surviving_sources_are_retained(self):
        self.seed();(self.repo/'releases.json').write_text('broken')
        r=reflect.read_live(self.repo);self.assertTrue(r['ok']);self.assertEqual(len(r['source_catalog']),1)
        self.assertEqual(r['summary']['source_errors'],1)
        self.assertEqual(reflect.safe_priority(self.repo),{})
        self.assertFalse(reflect.safe_cycle(self.repo)['ok'])

    def test_untrusted_urls_unknown_games_and_conflicting_game_ids_are_rejected(self):
        rows=[self.source(source=u) for u in ('http://official.example/x','https://127.0.0.1/x','https://a:b@official.example/x','https://intranet.local/x')]
        rows.extend([self.source(game='Unknown'),self.source(registry_game_id='pokemon')])
        self.seed(rows);r=reflect.read_live(self.repo);self.assertEqual(r['source_catalog'],[])
        self.assertEqual(r['summary']['rejected_source_rows'],6)

    def test_source_alias_and_market_kind_are_interpreted_without_fabricated_prices(self):
        self.image();row=self.source(game='원피스',kind='판매 호가')
        self.write('market_prices.json',{'entries':{'JP|Fixture catalog OP-01|BOX':row}})
        r=reflect.read_live(self.repo);self.assertEqual(r['summary']['auto_linked'],1)
        self.assertNotIn('price',r['local_catalog'][0]);self.assertEqual(r['source_catalog'][0]['kind'],'BOX')

    def test_unsafe_private_index_fails_closed_and_queue_symlink_cannot_write(self):
        self.image();self.seed();outside=self.root/'outside';outside.write_text('keep')
        (self.store/'collection_gap_queue_v2.json').symlink_to(outside)
        with self.assertRaises(ValueError):reflect.safe_cycle(self.repo)
        self.assertEqual(outside.read_text(),'keep')
        p=self.store/'index.json';d=json.loads(p.read_text());d['items'].append(d['items'][0]);p.write_text(json.dumps(d))
        self.assertFalse(reflect.read_live(self.repo)['ok'])

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_product_image_renderer_filters_selected_game_and_chinese_edition(self):
        source=(Path(__file__).resolve().parents[2]/'tablet_image_library_v1.js').read_text()
        fn=source[source.index('  function appendProducts(){'):source.index('  function applyExactBoxPhotos(){')]
        script="""
const assert=require('node:assert/strict');let rendered=[],calls=[];let productLimit=60;
const host={querySelectorAll:()=>[],append:x=>rendered.push(x.game_id)};
const document={getElementById:id=>id==='box12'?host:null,querySelector:()=>({dataset:{kbCountry:'CN'}})};
const productsId='box12',PRODUCT_TYPES=new Set(['BOX']);
const data=[{kind:'BOX',game_id:'onepiece',region:'CN-T'},{kind:'BOX',game_id:'pokemon',region:'CN-T'},{kind:'BOX',game_id:'onepiece',region:'JP'}];
const selected=()=> 'ONE PIECE';const selectedGame=(g,id)=>id==='onepiece';
const selectedCountry=(v,r)=>v==='CN'?['CN-S','CN-T'].includes(r):v===r;
const sourceRows=(k,c,g)=>{calls.push([c,g]);return []};const content=x=>x;
"""+fn+"\nappendProducts();assert.deepEqual(rendered,['onepiece']);assert.deepEqual(calls,[['CN','ONE PIECE']]);"
        p=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

if __name__=='__main__':unittest.main()
