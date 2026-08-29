import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import graded_photo_multi_source as g
import graded_photo_evidence as evidence

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

    def test_ocr_label_extracts_company_grade_and_cert(self):
        row=evidence.extract_label_evidence('PSA GEM MT 10 CERT NUMBER 88411675 Pokemon')
        self.assertEqual(row['company'],'PSA')
        self.assertEqual(row['grade'],10.0)
        self.assertEqual(row['certification_id'],'88411675')

    def test_image_probe_rejects_private_or_plain_http_url(self):
        row=evidence.probe_image('http://127.0.0.1/private.jpg')
        self.assertFalse(row['ok'])
        self.assertFalse(row['bytes_persisted'])

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
