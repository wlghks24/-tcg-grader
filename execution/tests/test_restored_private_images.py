"""Private storage tests use only fixture bytes/temp files; no live fetch or training."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import tablet_image_library_v1 as library
import tablet_image_auto_v2 as auto

def fixture_png():
    import io
    from PIL import Image
    out=io.BytesIO();Image.new('RGB',(12,18),'white').save(out,format='PNG');return out.getvalue()

PNG=fixture_png()


class PrivateImageRestorationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=self.root/'repo';self.repo.mkdir()
        self.store=self.root/'private-pictures';self.store.mkdir();(self.store/'images').mkdir()
        (self.repo/'tcg_game_registry.json').write_text(json.dumps({'schema_version':1,'games':[{'id':'pokemon'}]}))
        self.addCleanup(patch.stopall)
        patch.object(library,'storage_root',return_value=self.store).start()
        self.payload={'game_id':'pokemon','region':'JP','kind':'CARD','name':'Fixture SV1S-001',
                      'image_base64':'data:image/png;base64,'+base64.b64encode(PNG).decode()}

    def test_private_roundtrip_keeps_bytes_outside_checkout(self):
        saved=library.save_image(self.repo,self.payload)
        mime,data=library.get_image(saved['id'])
        self.assertEqual((mime,data),('image/png',PNG))
        row=library.list_images()['items'][0]
        self.assertEqual(row['region'],'JP');self.assertEqual(row['origin'],'manual')
        self.assertNotIn('sha256',row)
        self.assertEqual([p.name for p in self.repo.iterdir()],['tcg_game_registry.json'])

    def test_duplicate_blob_survives_until_last_reference_deleted(self):
        a=library.save_image(self.repo,self.payload);b=library.save_image(self.repo,{**self.payload,'region':'CN-T'})
        self.assertEqual(len(list((self.store/'images').iterdir())),1)
        library.delete_image(a['id']);self.assertEqual(library.get_image(b['id'])[1],PNG)
        library.delete_image(b['id']);self.assertEqual(list((self.store/'images').iterdir()),[])

    def test_edition_and_provenance_not_inferred_or_forged(self):
        for change in ({'region':'CN'},{'region':'EN'},{'provider':'TCGdex','source_id':'x','source_url':'https://api.tcgdex.net/v2/ja/cards/x'}):
            with self.assertRaises(ValueError):library.save_image(self.repo,{**self.payload,**change})
        self.assertEqual(list((self.store/'images').iterdir()),[])

    def test_tampered_blob_is_not_served(self):
        x=library.save_image(self.repo,self.payload)
        p=next((self.store/'images').iterdir());p.write_bytes(PNG+b'extra')
        with self.assertRaises(ValueError):library.get_image(x['id'])

    def test_index_size_failure_restores_previous_index_and_removes_new_blob(self):
        before=b'{"version":1,"items":[]}'
        (self.store/'index.json').write_bytes(before)
        with patch.object(library,'MAX_INDEX_BYTES',len(before)+1):
            with self.assertRaises(ValueError):library.save_image(self.repo,self.payload)
        self.assertEqual((self.store/'index.json').read_bytes(),before)
        self.assertEqual(list((self.store/'images').iterdir()),[])

    def test_symlink_index_cannot_overwrite_external_file(self):
        elsewhere=self.root/'unchanged';elsewhere.write_text('keep')
        (self.store/'index.json').symlink_to(elsewhere)
        with self.assertRaises(ValueError):library.save_image(self.repo,self.payload)
        self.assertEqual(elsewhere.read_text(),'keep')

    def test_corrupt_index_is_preserved(self):
        p=self.store/'index.json';p.write_text('broken JSON')
        with self.assertRaises(ValueError):library.save_image(self.repo,self.payload)
        self.assertEqual(p.read_text(),'broken JSON')

    def test_auto_persisted_opt_in_is_not_implicitly_enabled(self):
        self.assertIs(auto.status(self.repo)['auto_enabled'],False)
        auto.set_enabled(True);self.assertIs(auto.status(self.repo)['auto_enabled'],True)
        auto.set_enabled(False);self.assertIs(auto.status(self.repo)['auto_enabled'],False)

    def test_completed_source_does_not_redownload_even_after_manual_delete(self):
        row={'key':'pokemon/ja/fixture','provider':'TCGdex','game_id':'pokemon','region':'JP','kind':'CARD',
             'name':'Fixture SV1S-001','url':'https://assets.tcgdex.net/ja/fixture/low.webp','source':'https://api.tcgdex.net/v2/ja/cards'}
        with patch.object(auto,'_candidate_batches',return_value=[(0,'pokemon|JP',1,'pokemon','JP')]), \
             patch.object(auto,'candidates_pokemon',return_value=[row]), \
             patch.object(auto,'fetch_binary',return_value=PNG) as fetch:
            a=auto.collect_once(self.repo,sleeper=lambda _:None)
            self.assertEqual(a['saved'],1,a)
            library.delete_image(library.list_images()['items'][0]['id'])
            b=auto.collect_once(self.repo,sleeper=lambda _:None)
            self.assertEqual(b['saved'],0);self.assertEqual(b['skipped'],1)
            fetch.assert_called_once()
        self.assertIs(auto.status(self.repo)['auto_enabled'],False)

    def test_scheduler_registration_is_idempotent_without_starting_live_thread(self):
        with patch.object(auto,'_SCHEDULER',None),patch.object(auto.threading,'Thread') as thread:
            auto.start_scheduler(self.repo);auto.start_scheduler(self.repo)
            thread.assert_called_once();thread.return_value.start.assert_called_once()

    def test_nonlocal_clients_cannot_read_or_mutate_private_library(self):
        h=Mock();h.client_address=('192.168.1.2',1234)
        library.handle_get(h,'/api/local-card-images')
        self.assertEqual(h.json.call_args.args[1],403)
        library.handle_post(h,'/api/local-card-images/save')
        self.assertEqual(h.json.call_args.args[1],403)
        h._read_json_body.assert_not_called()

    def test_redirect_and_internal_image_urls_are_rejected(self):
        for url in ['http://assets.tcgdex.net/x','https://127.0.0.1/x','https://assets.tcgdex.net.evil.test/x',
                    'https://user@assets.tcgdex.net/x','https://assets.tcgdex.net:444/x']:
            self.assertFalse(auto._url_allowed(url),url)
        with self.assertRaises(auto.ProviderError):auto._NoRedirect().redirect_request(None,None,302,'',{},'https://assets.tcgdex.net/x')

    def test_actual_ui_reflects_scheduled_progress_without_duplicate_events(self):
        import shutil, subprocess
        if not shutil.which('node'):self.skipTest('Node.js required for actual UI behavior')
        source=Path(__file__).resolve().parents[2]/'tablet_image_auto_v2.js'
        script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class El {constructor(){this.style={};this.disabled=false;}append(){}prepend(){}setAttribute(){}querySelector(){return null;}addEventListener(){}}
const wrap=new El(),timers=[],events=[];let saved=0,requests=0;
const document={hidden:false,getElementById:id=>id==='tcgImageLibraryV1'?wrap:null,
 createElement:()=>new El(),createTextNode:()=>({}),dispatchEvent:e=>events.push(e.type)};
const fetch=async()=>{requests++;return {ok:true,json:async()=>({ok:true,auto_enabled:true,
 job:{running:true,started_at:'fixture',saved},last_result:{},coverage:{supported_sources:[]}})}};
const sandbox={document,fetch,Event:class {constructor(type){this.type=type}},setInterval:(fn,ms)=>{timers.push({fn,ms});return timers.length},clearInterval(){}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{await tick();assert.equal(events.length,1);
const watch=timers.find(x=>x.ms===5000);assert.ok(watch);
watch.fn();await tick();assert.equal(events.length,1);
saved=1;watch.fn();watch.fn();await tick();assert.equal(events.length,2);
assert.deepEqual(events,['tcg-local-images-updated','tcg-local-images-updated']);
document.hidden=true;const before=requests;watch.fn();await tick();assert.equal(requests,before);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script,str(source)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_partial_page_is_resumed_instead_of_losing_uncollected_cards(self):
        row={'key':'pokemon/ja/a','provider':'TCGdex','game_id':'pokemon','region':'JP','kind':'CARD',
             'name':'Fixture SV1S-001','url':'https://assets.tcgdex.net/ja/a/low.webp','source':'https://api.tcgdex.net/v2/ja/cards'}
        rows=[row,{**row,'key':'pokemon/ja/b','name':'Fixture SV1S-002'}]
        with patch.object(auto,'_candidate_batches',return_value=[(0,'pokemon|JP',1,'pokemon','JP')]), \
             patch.object(auto,'candidates_pokemon',return_value=rows),patch.object(auto,'fetch_binary',return_value=PNG):
            with patch.object(auto,'RUN_IMAGE_LIMIT',1):
                first=auto.collect_once(self.repo,sleeper=lambda _:None)
            self.assertEqual(first['saved'],1)
            self.assertEqual(auto._state(self.store)['pages'].get('pokemon|JP',1),1)
            second=auto.collect_once(self.repo,sleeper=lambda _:None)
            self.assertEqual(second['saved'],1)
            self.assertEqual(auto._state(self.store)['pages']['pokemon|JP'],2)

    def test_network_429_respects_provider_cooldown_without_repeat_request(self):
        import io, urllib.error
        from execution import tablet_image_collection_policy as policy
        clock=lambda:2_000_000_000.0
        budget=policy.Budget({},lambda:None,clock=clock,timer=clock);budget.provider='TCGdex'
        auto._BUDGET_CONTEXT.current=budget
        self.addCleanup(lambda:delattr(auto._BUDGET_CONTEXT,'current'))
        error=urllib.error.HTTPError('https://api.tcgdex.net/x',429,'limit',{'Retry-After':'7200'},io.BytesIO())
        with patch.object(auto.urllib.request,'build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(auto.ProviderError):auto.fetch_binary('https://api.tcgdex.net/x')
            with self.assertRaises(policy.Deferred):auto.fetch_binary('https://api.tcgdex.net/x')
            opener.return_value.open.assert_called_once()
        self.assertEqual(budget.snapshot()['requests_last_24h'],1)

    def test_full_card_assets_are_selected_without_thumbnail_substitution(self):
        with patch.object(auto,'fetch_json',return_value=[{'id':'swsh3-136','name':'Fixture',
             'image':'https://assets.tcgdex.net/ja/swsh/swsh3/136'}]):
            self.assertTrue(auto.candidates_pokemon('JP',1)[0]['url'].endswith('/high.webp'))
        with patch.object(auto,'fetch_json',return_value={'data':[{'id':123,'name':'Fixture',
             'card_images':[{'image_url':'https://images.ygoprodeck.com/images/cards/123.jpg'}]}]}):
            self.assertEqual(auto.candidates_yugioh(1)[0]['url'],'https://images.ygoprodeck.com/images/cards/123.jpg')

    def test_every_registry_game_resolves_from_its_actual_category_label(self):
        import shutil,subprocess
        if not shutil.which('node'):self.skipTest('Node.js required')
        root=Path(__file__).resolve().parents[2]
        src=(root/'tablet_image_library_v1.js').read_text()
        definitions=src[src.index('  const gameNames='):src.index('  let data=[], matches=')]
        resolver='function selectedGame'+src.split('function selectedGame',1)[1].split('  function selectedCountry',1)[0]
        registration='function updateGameRegistry'+src.split('function updateGameRegistry',1)[1].split("    document.addEventListener('tcg-image-registry-loaded'",1)[0]
        registry=json.loads((root/'tcg_game_registry.json').read_text())['games']
        script='const assert=require("node:assert/strict");const window={TCGLocalImageRegistry:'+json.dumps(registry)+'};function render(){}\n'+definitions+resolver+registration+'''
updateGameRegistry();
for(const row of window.TCGLocalImageRegistry){
 assert.equal(selectedGame(row.canonical,row.id),true,row.canonical);
 assert.equal(selectedGame(row.label_ko,row.id),true,row.label_ko);
 assert.equal(selectedGame(row.id,row.id),true,row.id);
}
assert.equal(selectedGame('Pokémon','onepiece'),false);
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
