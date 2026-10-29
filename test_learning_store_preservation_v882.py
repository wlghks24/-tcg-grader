"""Regression: preserve existing learning evidence, fail closed on corrupt JSON.

Uses temporary storage and a mocked HTTP handler: no device, network or model training.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tcg_updater as updater
import vision_calibration
import grading_accuracy_v99


class LearningStorePreservationTests(unittest.TestCase):
    def post(self, directory: Path, original, incoming):
        storage = directory / 'learning_store.json'
        if original is not None:
            storage.write_text(json.dumps(original) if isinstance(original,dict) else original,
                               encoding='utf-8')
        handler = object.__new__(updater.Handler)
        handler.path='/api/learning-store'
        handler._require_request_host=lambda:True
        handler._require_mutation_origin=lambda:True
        handler._read_json_body=lambda max_bytes=1000000:incoming
        replies=[]
        handler.json=lambda data,status=200:replies.append((data,status))
        with mock.patch.object(updater,'LEARNING_STORE',str(storage)), \
             mock.patch.object(updater,'BASE',str(directory)), \
             mock.patch.object(vision_calibration,'train_file',return_value={'profiles':{}}), \
             mock.patch.object(grading_accuracy_v99,'train_company_calibration',return_value={}):
            updater.clear_json_file_cache()
            updater.Handler.do_POST(handler)
            updater.clear_json_file_cache()
        return storage,replies

    def test_preserves_unknown_stored_proof_but_not_injected_client_fields(self):
        legacy={'version':2,'updated_at':None,'v99_validation':[],
                'v30_validation':[],'v11_validation':[],
                'confirmed_samples':[{'certification_id':'ABCD123','verified':'false'}],
                'calibration':{'PSA':{'min_samples':5}},
                'bgs_subgrade_summary':{'n':3},
                'future_evidence':{'seal':'keep'}}
        with tempfile.TemporaryDirectory() as td:
            path,replies=self.post(Path(td),legacy,{
                'v99_validation':[],
                'confirmed_samples':[{'client':'injected'}],
                'arbitrary_new_key':'untrusted'})
            self.assertTrue(replies[0][0]['ok'])
            payload=json.loads(path.read_text(encoding='utf-8'))
            for name in ['confirmed_samples','calibration','bgs_subgrade_summary','future_evidence']:
                self.assertEqual(payload[name],legacy[name])
            self.assertNotIn('arbitrary_new_key',payload)
            self.assertEqual(json.loads(Path(str(path)+'.bak').read_text(encoding='utf-8'))['future_evidence'],legacy['future_evidence'])

    def test_corrupted_current_store_does_not_get_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            path,replies=self.post(Path(td),'{"confirmed_samples": [',{'v99_validation':[]})
            self.assertEqual(400,replies[0][1])
            self.assertEqual('{"confirmed_samples": [',path.read_text(encoding='utf-8'))
            self.assertFalse(Path(str(path)+'.bak').exists())

    def test_non_object_current_json_does_not_get_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            path,replies=self.post(Path(td),'[]',{'v99_validation':[]})
            self.assertEqual(400,replies[0][1])
            self.assertEqual('[]',path.read_text(encoding='utf-8'))

    def test_missing_current_store_initializes_without_extra_proof(self):
        with tempfile.TemporaryDirectory() as td:
            path,replies=self.post(Path(td),None,{'v99_validation':[]})
            self.assertTrue(replies[0][0]['ok'])
            payload=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual([],payload['v99_validation'])
            self.assertNotIn('confirmed_samples',payload)


if __name__=='__main__':unittest.main()
