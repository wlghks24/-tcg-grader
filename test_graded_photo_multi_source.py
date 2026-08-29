import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import graded_photo_multi_source as g
import graded_photo_evidence as evidence
import ebay_grader_learning as ebay

class GradedPhotoMultiSourceTests(unittest.TestCase):
    def test_company_grade_parse(self):
        self.assertEqual(g._company('Pokemon PSA 10 graded card'),'PSA')
        self.assertEqual(g._grade('Pokemon PSA 10 graded card','PSA'),10.0)

    def test_unverified_never_becomes_training(self):
        self.assertFalse(g._verified_status('PSA','12345678',10.0,{}))

    def test_registry_exact_match_required(self):
        reg={('PSA','12345678'):10.0}
        self.assertTrue(g._verified_status('PSA','12345678',10.0,reg))
        self.assertFalse(g._verified_status('PSA','12345678',9.0,reg))

    def test_source_domains_are_public_marketplaces(self):
        ids={x['id'] for x in g.SOURCES}
        self.assertTrue({'amazon_us','amazon_jp','kream','daangn'}.issubset(ids))

    def test_ebay_public_alias_builds_real_queries(self):
        source=next(x for x in g.SOURCES if x['id']=='ebay_public')
        queries=g._queries(source,'pokemon')
        self.assertEqual(len(queries),3)
        self.assertTrue(all('site:ebay.com' in query for _,query in queries))
        self.assertEqual({company for company,_ in queries},{'ALL','PSA','CGC'})

    def test_targeted_graders_rotate_after_each_source_game_cycle(self):
        source=next(x for x in g.SOURCES if x['id']=='ebay_public')
        with mock.patch.object(g,'route_run_count',return_value=1):
            queries=g._queries(source,'pokemon')
        self.assertEqual({company for company,_ in queries},{'ALL','BGS','TAG'})
        self.assertTrue(any('BGS' in query for company,query in queries if company=='BGS'))

    def test_all_games_build_localized_marketplace_queries(self):
        source=next(x for x in g.SOURCES if x['id']=='ebay_public')
        expected={'pokemon':('Pokemon','포켓몬','ポケモン'),
                  'onepiece':('One Piece','원피스','ワンピース'),
                  'naruto':('Naruto','나루토','ナルト')}
        for game,names in expected.items():
            queries=g._queries(source,game)
            text=' '.join(query for _,query in queries)
            self.assertEqual(len(queries),3)
            self.assertTrue(all('site:ebay.com' in query for _,query in queries))
            self.assertTrue(any(name in text for name in names))

    def test_source_cap_is_balanced_across_three_games(self):
        source=next(x for x in g.SOURCES if x['id']=='ebay_public')
        def fake_discover(_source,game):
            rows=[{'url':f'https://www.ebay.com/itm/{game}-{i}','game':game} for i in range(20)]
            diag={'raw_results':20,'domain_matches':20,'company_matches':20,'resolved_redirects':0,'image_results':0,'google_image_results':0}
            return rows,[],3,diag
        with mock.patch.object(g,'_discover_source_game',side_effect=fake_discover):
            _,rows,errors,queries,diag=g._collect_public_source(source)
        self.assertEqual(errors,[])
        self.assertEqual(queries,9)
        self.assertEqual(len(rows),g.MAX_PER_SOURCE)
        self.assertEqual(diag['game_candidates'],{'pokemon':8,'onepiece':8,'naruto':8})

    def test_source_cap_is_balanced_across_games_and_graders(self):
        source=next(x for x in g.SOURCES if x['id']=='ebay_public')
        def fake_discover(_source,game):
            companies=['PSA']*20+['BGS','CGC','TAG','BRG']
            rows=[{'url':f'https://www.ebay.com/itm/{game}-{company}-{i}','game':game,'company':company} for i,company in enumerate(companies)]
            diag={'raw_results':24,'domain_matches':24,'company_matches':24,'resolved_redirects':0,'image_results':0,'google_image_results':0}
            return rows,[],3,diag
        with mock.patch.object(g,'_discover_source_game',side_effect=fake_discover):
            _,rows,_,_,diag=g._collect_public_source(source)
        self.assertEqual(len(rows),g.MAX_PER_SOURCE)
        self.assertEqual(diag['game_candidates'],{'pokemon':8,'onepiece':8,'naruto':8})
        self.assertEqual(diag['company_candidates'],{'PSA':12,'BGS':3,'CGC':3,'TAG':3,'BRG':3})

    def test_image_search_never_defaults_unknown_grader_to_psa(self):
        source=next(x for x in g.SOURCES if x['id']=='ebay_public')
        image_row={'title':'graded card slab','url':'https://www.ebay.com/itm/tag-1','image_url':'https://i.ebayimg.com/tag.jpg'}
        plan=(('ALL','broad'),('TAG','tag query'),('BGS','bgs query'))
        with mock.patch.object(g,'_queries',return_value=plan), \
             mock.patch.object(g,'_query_rows',return_value=([],[])), \
             mock.patch.object(g,'_bing_image_rows',return_value=[image_row]), \
             mock.patch.object(g,'_google_cse_images',return_value=[]), \
             mock.patch.object(g,'_ebay_public_rows',return_value=[]), \
             mock.patch.object(g,'record_collection_cycle'):
            rows,_,_,_=g._discover_source_game(source,'pokemon')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['company'],'TAG')
        self.assertNotEqual(rows[0]['company'],'PSA')

    def test_source_selection_keeps_coverage_and_uses_learned_slot(self):
        state={'source_cursor':0}
        def priority(source_id):return 0.99 if source_id=='cardmarket' else 0.1
        with mock.patch.object(g,'source_priority',side_effect=priority):
            active=g._select_active_sources(state,False,False)
        self.assertEqual(len(active),g.RUN_SOURCE_LIMIT)
        self.assertEqual([row['id'] for row in active[:g.RUN_SOURCE_LIMIT-1]],
                         [row['id'] for row in g.SOURCES[:g.RUN_SOURCE_LIMIT-1]])
        self.assertEqual(active[-1]['id'],'cardmarket')
        self.assertEqual(state['source_cursor'],g.RUN_SOURCE_LIMIT-1)
        self.assertEqual(state['source_selection_policy'],'coverage_plus_recency_weighted_exploitation')

    def test_ebay_api_rotates_games_before_next_grader(self):
        queries=[]
        def fake_api(url,_token):
            if '/item_summary/search?' in url:
                queries.append(url)
                return {'itemSummaries':[]}
            return {}
        with mock.patch.object(ebay,'_api_get',side_effect=fake_api):
            ebay.discover('x'*24,per_query=1,max_items=1,pause=0)
        first=[urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['q'][0] for url in queries[:3]]
        self.assertEqual(first,['Pokemon PSA graded card','One Piece PSA graded card','Naruto PSA graded card'])

    def test_ocr_label_extracts_company_grade_and_cert(self):
        row=evidence.extract_label_evidence('PSA GEM MT 10 CERT NUMBER 88411675 Pokemon')
        self.assertEqual(row['company'],'PSA')
        self.assertEqual(row['grade'],10.0)
        self.assertEqual(row['certification_id'],'88411675')

    def test_image_probe_rejects_private_or_plain_http_url(self):
        row=evidence.probe_image('http://127.0.0.1/private.jpg')
        self.assertFalse(row['ok'])
        self.assertFalse(row['bytes_persisted'])

    def test_ocr_probe_budget_is_balanced_across_graders(self):
        rows=[]
        for index in range(8):rows.append({'company':'PSA','game':'pokemon','image_url':f'https://images.example/psa-{index}.jpg'})
        for company in ('BGS','CGC','TAG','BRG'):rows.append({'company':company,'game':'pokemon','image_url':f'https://images.example/{company}.jpg'})
        priorities=list(enumerate(rows))
        selected=evidence._balanced_probe_selection(priorities,5)
        self.assertEqual({row['company'] for _,row in selected},set(g.COMPANIES))

    def test_measurement_photo_quality_requires_official_high_resolution_ocr_identity(self):
        strong={'company':'PSA','company_evidence':'image_ocr','grade':10,'certification_id':'12345678','official_result':True,
                'image_validated':True,'image_width':1200,'image_height':1600,'ocr_label_text':'PSA 10 CERT 12345678'}
        weak={**strong,'image_width':240,'image_height':320}
        scored=g._apply_measurement_photo_quality([strong,weak])
        self.assertTrue(scored[0]['measurement_photo_ready'])
        self.assertEqual(scored[0]['measurement_photo_quality'],1.0)
        self.assertFalse(scored[1]['measurement_photo_ready'])

    def test_reference_learning_keeps_distinct_verified_photo_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'references.json'
            saved={'company':'BGS','certification_id':'12345678','official_grade':10,'official_result':True,
                   'game':'pokemon','image_sha256':'a'*64,'measurement_image_url':'https://images.example/a.jpg',
                   'measurement_photo_quality':.9,'measurement_photo_ready':True,
                   'learning_scope':'slab_label_and_source_reference_only'}
            path.write_text(json.dumps({'references':[saved]}),encoding='utf-8')
            current={**saved,'image_sha256':'b'*64,'image_url':'https://images.example/b.jpg',
                     'measurement_photo_quality':1.0,'official_reference_url':'https://www.beckett.com/grading/card-lookup'}
            with mock.patch.object(g,'REFERENCE_LEARNING',path):payload=g._save_reference_learning([current])
        self.assertEqual(payload['summary']['reference_learning_count'],2)
        self.assertEqual(payload['summary']['certifications'],1)
        self.assertEqual(payload['summary']['measurement_photo_ready'],2)

    def test_search_fallback_company_is_not_treated_as_ocr_identity(self):
        row={'company':'TAG','grade':10,'certification_id':'A1234567'}
        probe={'ok':True,'width':1200,'height':1600,'sha256':'a'*64,'perceptual_hash':'b'*16,
               'ocr_text':'10 A1234567','ocr_company':'TAG','ocr_company_explicit':'',
               'ocr_grade':10,'ocr_certification_id':'A1234567'}
        merged=evidence._merge_probe(row,probe)
        self.assertNotIn('company_evidence',merged)
        merged.update({'official_result':True})
        self.assertFalse(g._apply_measurement_photo_quality([merged])[0]['measurement_photo_ready'])

    def test_google_cse_empty_response_is_empty_not_exception(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self,_): return b'{"items":[]}'
        with mock.patch.dict(g.os.environ,{'GOOGLE_CSE_KEY':'key','GOOGLE_CSE_CX':'cx'},clear=False), \
             mock.patch.object(g,'safe_urlopen',return_value=Response()):
            self.assertEqual(g._google_cse('test'),[])

    def test_google_cse_keeps_every_result(self):
        payload={'items':[
            {'title':'one','link':'https://www.ebay.com/itm/1','snippet':'a'},
            {'title':'two','link':'https://www.ebay.com/itm/2','snippet':'b'},
        ]}
        class Response:
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self,_): return json.dumps(payload).encode('utf-8')
        with mock.patch.dict(g.os.environ,{'GOOGLE_CSE_KEY':'key','GOOGLE_CSE_CX':'cx'},clear=False), \
             mock.patch.object(g,'safe_urlopen',return_value=Response()):
            rows=g._google_cse('test')
        self.assertEqual([row['title'] for row in rows],['one','two'])

    def test_provider_failure_does_not_suppress_other_search_results(self):
        class Searcher:
            def _search_bing_rss(self,*_): return ([{'title':'bing','url':'https://www.ebay.com/itm/1','search_provider':'bing_rss'}],None,1,True)
            def _search_ddg(self,*_): raise TimeoutError('blocked')
        google=[{'title':'google','url':'https://www.ebay.com/itm/2','search_provider':'google_cse'}]
        with mock.patch.object(g,'_google_cse',return_value=google),mock.patch.object(g,'_searcher',return_value=Searcher()):
            rows,errors=g._query_rows('test',10)
        self.assertEqual({row['title'] for row in rows},{'bing','google'})
        self.assertTrue(any(error.startswith('duckduckgo:') for error in errors))

    def test_conflicting_cert_grade_keeps_official_and_quarantines_claim(self):
        rows=[
            {'company':'PSA','certification_id':'12345678','grade':10,'official_grade':10,'official_result':True},
            {'company':'PSA','certification_id':'12345678','grade':9,'official_result':False},
        ]
        resolved=g._resolve_cert_conflicts(rows)
        self.assertTrue(resolved[0]['official_result'])
        self.assertFalse(resolved[1]['official_result'])
        self.assertIn('cross_source_grade_conflict',resolved[1]['evidence_conflicts'])

    def test_same_image_with_conflicting_label_is_quarantined(self):
        digest='a'*64
        rows=[
            {'company':'PSA','certification_id':'12345678','grade':10,'official_result':True,'image_sha256':digest},
            {'company':'BGS','certification_id':'87654321','grade':9.5,'official_result':False,'image_sha256':digest},
        ]
        resolved,stats=g._resolve_image_conflicts(rows)
        self.assertTrue(resolved[0]['official_result'])
        self.assertFalse(resolved[1]['official_result'])
        self.assertIn('duplicate_image_label_conflict',resolved[1]['evidence_conflicts'])
        self.assertEqual(stats['image_label_conflicts'],1)

    def test_registry_seed_is_visible_without_marketplace_hit(self):
        seeds=g._registry_seed_rows()
        psa=[x for x in seeds if x.get('company')=='PSA' and x.get('certification_id')=='88411675']
        self.assertEqual(len(psa),1)
        self.assertEqual(psa[0]['status'],'verified_reference')
        self.assertEqual(psa[0]['learning_eligibility'],'reference_learning_only')

    def test_collect_keeps_verified_reference_separate_from_raw_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            paths={
                'OUT':root/'candidates.json','LEARNING':root/'source-learning.json',
                'VERIFIED':root/'verified.json','OFFICIAL_CACHE':root/'official-cache.json',
                'REFERENCE_LEARNING':root/'reference-learning.json','LIBRARY_OFFICIAL':root/'official-library.json',
            }
            paths['VERIFIED'].write_text(json.dumps({'certifications':[{
                'company':'PSA','certification_id':'12345678','grade':10,'verified':True,
                'card_name':'Verified test card'
            }]}),encoding='utf-8')
            paths['LIBRARY_OFFICIAL'].write_text('{"certifications":[]}',encoding='utf-8')
            def fake_source(source):
                found=[]
                if source['id']=='ebay_public':
                    found=[
                        {'source_id':'ebay_public','source':'eBay 공개검색','search_provider':'test','url':'https://www.ebay.com/itm/1','title':'PSA 10 cert 12345678','snippet':'','image_url':'','company':'PSA','grade':10.0,'certification_id':'12345678','game':'pokemon','mode':'slab','source_weight':.9},
                        {'source_id':'ebay_public','source':'eBay 공개검색','search_provider':'test','url':'https://www.ebay.com/itm/2','title':'BGS card','snippet':'','image_url':'','company':'BGS','grade':None,'certification_id':'','game':'pokemon','mode':'slab','source_weight':.9},
                    ]
                diag={'raw_results':len(found),'domain_matches':len(found),'company_matches':len(found),'resolved_redirects':0,'image_results':0,'google_image_results':0}
                return source['id'],found,[],3,diag
            image_stats={'attempted':0,'validated':0,'ocr_readable':0,'certs_extracted':0,'failed':0}
            with mock.patch.multiple(g,**paths), \
                 mock.patch.object(g,'_ebay_candidates',return_value=[]), \
                 mock.patch.object(g,'_collect_public_source',side_effect=fake_source), \
                 mock.patch.object(g,'enrich_rows',side_effect=lambda rows,**_:([dict(x) for x in rows],image_stats)):
                payload=g.collect()
            self.assertEqual(payload['summary']['verified_references'],1)
            self.assertEqual(payload['summary']['raw_grade_calibration_eligible'],0)
            self.assertGreaterEqual(payload['summary']['quarantined'],1)
            learned=json.loads(paths['REFERENCE_LEARNING'].read_text(encoding='utf-8'))
            self.assertEqual(learned['summary']['reference_learning_count'],1)
            self.assertEqual(learned['summary']['raw_grade_calibration_rows_written'],0)
            self.assertTrue(learned['policy']['raw_and_slab_isolated'])

if __name__=='__main__':unittest.main()
