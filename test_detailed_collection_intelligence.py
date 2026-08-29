#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import detailed_collection_intelligence as learning
from safe_runtime import exclusive_file_lock


class DetailedCollectionIntelligenceTests(unittest.TestCase):
    def paths(self, root: Path):
        return mock.patch.multiple(
            learning,
            LEARNING=root / 'detailed_collection_learning.json',
            LEARNING_BACKUP=root / 'detailed_collection_learning.json.bak',
        )

    def test_productive_verified_query_ranks_above_failed_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.paths(root):
                candidates=[query for source,query in learning.build_queries('onepiece','graded_photo','PSA') if source=='ebay']
                favorite=candidates[-1]
                query_stats={query:{'runs':8,'raw':20,'accepted':0,'images':0,'errors':8,'elapsed_total':80,'verified':0} for query in candidates}
                query_stats[favorite]={'runs':8,'raw':20,'accepted':18,'images':16,'errors':0,'elapsed_total':8,'verified':6}
                learning.LEARNING.write_text(json.dumps({'schema_version':2,'source_query_stats':{
                    'ebay':{'runs':len(candidates)*8,'score':0.5,'queries':query_stats}
                }}),encoding='utf-8')
                ranked=[query for source,query in learning.build_queries('onepiece','graded_photo','PSA') if source=='ebay']
            self.assertEqual(ranked[0],favorite)

    def test_official_feedback_learns_identifier_but_unverified_does_not(self):
        rows=[
            {'source_id':'ebay_public','game':'onepiece','title':'ONE PIECE OP05-119 manga PSA 10',
             'certification_id':'12345678','official_result':True,'evidence_conflicts':[],
             '_learning_query':'site:ebay.com One Piece PSA graded card'},
            {'source_id':'ebay_public','game':'naruto','title':'NARUTO CP-999 unverified seller claim',
             'certification_id':'87654321','official_result':False,
             '_learning_query':'site:ebay.com Naruto PSA graded card'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            with self.paths(Path(directory)):
                result=learning.record_official_feedback(rows)
                snapshot=learning.learning_snapshot()
        self.assertEqual(result['official_verified'],1)
        self.assertEqual(result['identifiers_learned'],1)
        self.assertIn('OP05-119',snapshot['verified_identifiers']['onepiece'])
        self.assertNotIn('PSA10',snapshot['verified_identifiers']['onepiece'])
        self.assertNotIn('CP-999',snapshot['verified_identifiers']['naruto'])
        self.assertTrue(rows[0]['official_result'])
        self.assertFalse(rows[1]['official_result'])
        self.assertTrue(snapshot['policy']['query_learning_cannot_change_trust'])

    def test_repeated_official_feedback_is_idempotent(self):
        row={'source_id':'ebay','game':'onepiece','title':'ONE PIECE OP05-119 PSA 10',
             'company':'PSA','certification_id':'12345678','url':'https://www.ebay.com/itm/1',
             'official_result':True,'evidence_conflicts':[],
             '_learning_query':'site:ebay.com One Piece PSA graded card'}
        with tempfile.TemporaryDirectory() as directory:
            with self.paths(Path(directory)):
                first=learning.record_official_feedback([row])
                second=learning.record_official_feedback([dict(row)])
                snapshot=learning.learning_snapshot()
        self.assertEqual(first['official_verified'],1)
        self.assertEqual(second['official_verified'],0)
        self.assertEqual(second['duplicates_ignored'],1)
        self.assertEqual(snapshot['official_feedback'],1)
        self.assertEqual(snapshot['duplicate_feedback_ignored'],1)

    def test_measurement_ready_feedback_improves_only_verified_photo_route(self):
        good={'source_id':'ebay','game':'pokemon','company':'BGS','title':'BGS Pokemon SV1-001',
              'certification_id':'12345678','url':'https://www.ebay.com/itm/bgs-1','official_result':True,
              'measurement_photo_ready':True,'evidence_conflicts':[],'_learning_query':'site:ebay.com BGS Pokemon slab'}
        unverified={**good,'url':'https://www.ebay.com/itm/bgs-2','official_result':False}
        with tempfile.TemporaryDirectory() as directory:
            with self.paths(Path(directory)):
                result=learning.record_official_feedback([good,unverified])
                snapshot=learning.learning_snapshot()
        self.assertEqual(result['measurement_ready'],1)
        self.assertEqual(snapshot['measurement_ready_feedback'],1)
        self.assertEqual(snapshot['grader_coverage']['BGS']['measurement_ready'],1)
        self.assertTrue(snapshot['policy']['measurement_quality_feedback'])

    def test_stale_query_yields_to_recent_productive_query(self):
        now=1_800_000_000
        stale={'runs':10,'raw':10,'accepted':10,'images':10,'verified':10,'errors':0,
               'elapsed_total':1,'last_at':now-180*86400}
        recent={'runs':10,'raw':10,'accepted':8,'images':8,'verified':6,'errors':0,
                'elapsed_total':2,'last_at':now}
        with mock.patch.object(learning.time,'time',return_value=now):
            self.assertGreater(learning._query_score(recent,20),learning._query_score(stale,20))

    def test_failed_route_keeps_recovery_state_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.paths(Path(directory)):
                learning.record_collection_cycle('ebay','naruto',[{'query':'q1','raw':0,'accepted':0,'errors':1,'elapsed':2}],raw=0,accepted=0,errors=1,elapsed=2)
                first=learning.learning_snapshot()
                self.assertEqual(learning.route_run_count('ebay','naruto'),1)
                learning.record_collection_cycle('ebay','naruto',[{'query':'q2','raw':5,'accepted':3,'images':2,'errors':0,'elapsed':1}],raw=5,accepted=3,images=2,errors=0,elapsed=1)
                second=learning.learning_snapshot()
        self.assertEqual(first['recovery_routes'],1)
        self.assertEqual(second['recovery_routes'],0)
        self.assertEqual(second['productive_routes'],1)

    def test_concurrent_observations_are_not_lost_or_corrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.paths(root):
                def observe(index):
                    learning.record_collection_cycle('ebay','pokemon',[{'query':f'q{index}','raw':2,'accepted':1,'images':1,'errors':0,'elapsed':0.1}],raw=2,accepted=1,images=1)
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(observe,range(12)))
                payload=json.loads(learning.LEARNING.read_text(encoding='utf-8'))
                snapshot=learning.learning_snapshot()
        self.assertEqual(payload['graded_photo_routes']['ebay|pokemon']['runs'],12)
        self.assertEqual(snapshot['query_runs'],12)
        self.assertEqual(snapshot['queries_tracked'],12)
        self.assertTrue(snapshot['policy']['cross_process_lock'])

    def test_corrupt_primary_recovers_from_last_good_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.paths(root):
                learning.LEARNING.write_text('{broken',encoding='utf-8')
                learning.LEARNING_BACKUP.write_text(json.dumps({'schema_version':2,'graded_photo_routes':{
                    'ebay|onepiece':{'source_id':'ebay','game':'onepiece','runs':7,'accepted':4,'consecutive_failures':0}
                }}),encoding='utf-8')
                self.assertEqual(learning.route_run_count('ebay','onepiece'),7)

    def test_exclusive_state_lock_blocks_overlap_and_recovers_stale_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'state.json'
            lock=target.with_suffix('.json.lock')
            with exclusive_file_lock(target):
                with self.assertRaises(TimeoutError):
                    with exclusive_file_lock(target,timeout_seconds=0):
                        pass
            self.assertFalse(lock.exists())
            lock.write_text('{}',encoding='utf-8');old=time.time()-120
            os.utime(lock,(old,old))
            with exclusive_file_lock(target,stale_seconds=60):
                self.assertTrue(lock.exists())
            self.assertFalse(lock.exists())


if __name__=='__main__':
    unittest.main()
