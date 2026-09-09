import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path
from unittest import mock

import tcg_updater
import tcg_updater_v135


ROOT=Path(__file__).resolve().parent


def request_json(request):
    try:
        with urllib.request.urlopen(request,timeout=5) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code,json.loads(exc.read().decode('utf-8'))


class GradedPhotoRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler=partial(tcg_updater.Handler,directory=str(ROOT))
        cls.server=tcg_updater.QuietThreadingHTTPServer(('127.0.0.1',0),handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)

    def test_status_and_static_snapshot_are_available(self):
        status,payload=request_json(urllib.request.Request(self.base+'/api/graded-photo-collection-status'))
        self.assertEqual(status,200)
        self.assertIn(payload['state'],{'idle','queued','running','completed','failed'})
        status,payload=request_json(urllib.request.Request(self.base+'/graded_photo_candidates.json'))
        self.assertEqual(status,200)
        self.assertEqual(payload['engine'],'v123-verified-multisource-photo-collection')
        self.assertEqual(payload['summary']['raw_grade_calibration_eligible'],0)

    def test_precollect_stage_skips_manual_raw_photos_and_logs_but_keeps_learning_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'source'; target=root/'stage'
            source.mkdir()
            (source/'collector.py').write_text('print("ok")\n',encoding='utf-8')
            (source/'collection_learning_memory.json').write_text('{"ok":true}',encoding='utf-8')
            (source/'TCG_RUNTIME.log').write_text('x'*100,encoding='utf-8')
            inbox=source/'GRADE_TRAINING_INBOX'; inbox.mkdir()
            (inbox/'large-photo.jpg').write_bytes(b'x'*4096)
            tcg_updater._safe_stage_copy(source,target)
            self.assertTrue((target/'collector.py').is_file())
            self.assertTrue((target/'collection_learning_memory.json').is_file())
            self.assertFalse((target/'TCG_RUNTIME.log').exists())
            self.assertFalse((target/'GRADE_TRAINING_INBOX').exists())

    def test_json_read_cache_reuses_parse_and_returns_isolated_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cached.json'
            path.write_text('{"items":[{"value":1}]}',encoding='utf-8')
            tcg_updater.clear_json_file_cache()
            original=tcg_updater.safe_read_text
            with mock.patch.object(tcg_updater,'safe_read_text',wraps=original) as reader:
                first=tcg_updater.load_json_file(path,{})
                second=tcg_updater.load_json_file(path,{})
                first['items'][0]['value']=99
                third=tcg_updater.load_json_file(path,{})
            self.assertEqual(reader.call_count,1)
            self.assertEqual(second['items'][0]['value'],1)
            self.assertEqual(third['items'][0]['value'],1)

    def test_json_cache_hit_is_promoted_to_mru(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            paths=[root/f'{name}.json' for name in ('a','b','c')]
            for index,path in enumerate(paths,1):
                path.write_text(json.dumps({'value':index}),encoding='utf-8')
            original_limit=tcg_updater.JSON_FILE_CACHE_LIMIT
            tcg_updater.JSON_FILE_CACHE_LIMIT=2
            tcg_updater.clear_json_file_cache()
            original=tcg_updater.safe_read_text
            try:
                with mock.patch.object(tcg_updater,'safe_read_text',wraps=original) as reader:
                    tcg_updater.load_json_file(paths[0],{})
                    tcg_updater.load_json_file(paths[1],{})
                    tcg_updater.load_json_file(paths[0],{})  # promote a to MRU
                    tcg_updater.load_json_file(paths[2],{})  # evicts b, not a
                    tcg_updater.load_json_file(paths[0],{})
                    tcg_updater.load_json_file(paths[1],{})  # b must be parsed again
                self.assertEqual(reader.call_count,4)
                self.assertIn(str(paths[0].resolve()),tcg_updater.JSON_FILE_CACHE)
            finally:
                tcg_updater.JSON_FILE_CACHE_LIMIT=original_limit
                tcg_updater.clear_json_file_cache()

    def test_v135_dashboard_bundle_cache_reuses_bytes_and_invalidates_on_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            names=('graded_photo_dashboard.js','manual_dual_photo_bridge.js','manual_official_verify_bridge.js','pending_official_candidate_bridge_v161.js')
            for index,name in enumerate(names):
                (root/name).write_text(f'// {index}\n',encoding='utf-8')
            with tcg_updater_v135.DASHBOARD_BUNDLE_LOCK:
                tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['signature']=None
                tcg_updater_v135.DASHBOARD_BUNDLE_CACHE['body']=None
            first=tcg_updater_v135._dashboard_bundle_body(root)
            second=tcg_updater_v135._dashboard_bundle_body(root)
            self.assertIs(first,second)
            (root/names[0]).write_text('// changed\n',encoding='utf-8')
            third=tcg_updater_v135._dashboard_bundle_body(root)
            self.assertNotEqual(first,third)
            self.assertIn(b'changed',third)

    def test_json_read_cache_invalidates_after_file_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'changing.json'
            path.write_text('{"value":1}',encoding='utf-8')
            tcg_updater.clear_json_file_cache()
            self.assertEqual(tcg_updater.load_json_file(path,{})['value'],1)
            path.write_text('{"value":200}',encoding='utf-8')
            self.assertEqual(tcg_updater.load_json_file(path,{})['value'],200)

    def test_collection_neural_health_status_reuses_unchanged_file_signature(self):
        import verified_collection_neural
        import verified_collection_job_neural
        with tcg_updater.COLLECTION_NEURAL_STATUS_LOCK:
            tcg_updater.COLLECTION_NEURAL_STATUS_CACHE['signature']=None
            tcg_updater.COLLECTION_NEURAL_STATUS_CACHE['value']=None
        query={'ok':True,'active':False,'label_count':7,'minimum_labels':1000}
        job={'ok':True,'active':False,'label_count':9,'minimum_labels':1000}
        signatures=[('same',),('same',),('changed',)]
        with mock.patch.object(tcg_updater,'_collection_neural_signature',side_effect=signatures), \
             mock.patch.object(verified_collection_neural,'status',return_value=query) as query_status, \
             mock.patch.object(verified_collection_job_neural,'status',return_value=job) as job_status:
            first=tcg_updater.collection_neural_status()
            second=tcg_updater.collection_neural_status()
            third=tcg_updater.collection_neural_status()
        self.assertEqual(first['label_count'],16)
        self.assertEqual(second['label_count'],16)
        self.assertEqual(third['label_count'],16)
        self.assertEqual(query_status.call_count,2)
        self.assertEqual(job_status.call_count,2)
        self.assertTrue(first['status_cache_by_file_signature'])

    def test_collection_neural_status_isolates_strategy_failures(self):
        import verified_collection_neural
        import verified_collection_job_neural
        with tcg_updater.COLLECTION_NEURAL_STATUS_LOCK:
            tcg_updater.COLLECTION_NEURAL_STATUS_CACHE['signature']=None
            tcg_updater.COLLECTION_NEURAL_STATUS_CACHE['value']=None
        healthy_job={'ok':True,'active':True,'label_count':1200,'minimum_labels':1000,'reason':'active'}
        with mock.patch.object(tcg_updater,'_collection_neural_signature',return_value=('isolated-fault',)), \
             mock.patch.object(verified_collection_neural,'status',side_effect=ValueError('corrupt query model')), \
             mock.patch.object(verified_collection_job_neural,'status',return_value=healthy_job):
            result=tcg_updater.collection_neural_status()
        self.assertFalse(result['ok'])
        self.assertTrue(result['active'])
        self.assertEqual(result['label_count'],1200)
        self.assertEqual(result['query_strategy']['reason'],'query-neural-state-error')
        self.assertTrue(result['job_strategy']['ok'])
        self.assertTrue(result['job_strategy']['active'])
        self.assertTrue(result['independent_strategy_fault_isolation'])
        with tcg_updater.COLLECTION_NEURAL_STATUS_LOCK:
            self.assertIsNone(tcg_updater.COLLECTION_NEURAL_STATUS_CACHE['value'])

    def test_job_snapshots_are_isolated_without_json_roundtrip(self):
        source=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        self.assertNotIn('json.loads(json.dumps(UPDATE_JOB',source)
        self.assertNotIn('json.loads(json.dumps(GRADED_PHOTO_JOB',source)
        self.assertNotIn('json.loads(json.dumps(PHOTO_REVALIDATION_JOB',source)
        with tcg_updater.UPDATE_JOB_LOCK:
            original=tcg_updater.UPDATE_JOB.get('report')
            tcg_updater.UPDATE_JOB['report']={'nested':[1]}
        try:
            snapshot=tcg_updater._job_snapshot()
            snapshot['report']['nested'][0]=99
            self.assertEqual(tcg_updater._job_snapshot()['report']['nested'][0],1)
            json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
        finally:
            with tcg_updater.UPDATE_JOB_LOCK:
                tcg_updater.UPDATE_JOB['report']=original

    def test_dashboard_avoids_background_refresh_and_stops_finished_polling(self):
        source=(ROOT/'graded_photo_dashboard.js').read_text(encoding='utf-8')
        self.assertIn("document.visibilityState==='visible'",source)
        self.assertIn('manualVerificationFinished(payload,registrationId)',source)
        self.assertIn('앞면 + 뒷면 8구역 등록하기',source)
        self.assertIn('gpdManualBackPhoto',source)
        self.assertIn('gpdManualFrontOblique',source)
        self.assertIn('총 8구역 정밀검사',source)
        self.assertIn('기존 등록사진 전체 재검증',source)
        self.assertIn('/api/run-existing-photo-revalidation',source)
        self.assertIn("credentials:'same-origin'",source)
        self.assertIn('재검증 상태 응답 형식 오류',source)
        self.assertIn('재검증 제한시간 초과',source)
        self.assertIn("grade:gradeText===''?null:Number(gradeText)",source)
        self.assertNotIn('id="gpdManualCompany" required',source)
        self.assertNotIn('rows.filter(r=>companyOf(r)===c)',source)
        self.assertIn("typeof canvas.toBlob==='function'",source)
        self.assertIn('blob.size>6_000_000',source)
        self.assertIn('async function decodedPhoto(file)',source)
        self.assertIn('await jpegDataUrl(canvas,quality)',source)
        self.assertNotIn('termCount=Object.values',source)
        self.assertNotIn('rows.filter(isVerified)',source)
        self.assertNotIn('rows.filter(isReferenceLearning)',source)
        self.assertNotIn('rows.filter(isRawEligible)',source)
        self.assertIn('for(const r of sourceRows)',source)
        self.assertIn('강화 수집 상태 응답 형식 오류',source)
        self.assertIn('강화 수집 제한시간 초과 · 서버 작업은 계속되므로 상태를 다시 확인하세요.',source)

    def test_updater_source_is_valid_utf8(self):
        source=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        self.assertIn('def load_json_file(',source)
        self.assertIn('self._read_json_body(33000000)',source)

    def test_grade_result_exposes_safe_correction_and_manual_photo_buttons(self):
        source=(ROOT/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="openGradeCorrection"',source)
        self.assertIn('id="openManualGradedPhoto"',source)
        self.assertIn('function openGradeCorrectionRegistration()',source)
        self.assertIn('누적 오차 보정자료는 공식 감정 결과 확인이 필요합니다.',source)
        self.assertIn('manual_fallback_guides_coverage_only',
                      (ROOT/'detailed_collection_intelligence.py').read_text(encoding='utf-8'))

    def test_collection_trigger_is_post_only(self):
        status,payload=request_json(urllib.request.Request(self.base+'/api/run-graded-photo-collection'))
        self.assertEqual(status,405)
        self.assertFalse(payload['ok'])

    def test_existing_photo_revalidation_status_and_same_origin_trigger(self):
        status,payload=request_json(urllib.request.Request(self.base+'/api/graded-photo-revalidation-status'))
        self.assertEqual(status,200)
        self.assertIn(payload['state'],{'idle','queued','running','completed','failed'})
        accepted={'ok':True,'accepted':True,'job_id':'revalidation-test','job':{'state':'queued'}}
        request=urllib.request.Request(self.base+'/api/run-existing-photo-revalidation',data=b'{}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':self.base})
        with mock.patch.object(tcg_updater,'_start_existing_photo_revalidation',return_value=(accepted,202)) as start:
            status,payload=request_json(request)
        self.assertEqual(status,202)
        self.assertEqual(payload['job_id'],'revalidation-test')
        start.assert_called_once_with()

    def test_cross_site_trigger_is_rejected(self):
        request=urllib.request.Request(self.base+'/api/run-graded-photo-collection',data=b'{}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with mock.patch.object(tcg_updater,'_start_graded_photo_collection') as start:
            status,payload=request_json(request)
        self.assertEqual(status,403)
        self.assertFalse(payload['ok'])
        start.assert_not_called()

    def test_cross_site_existing_photo_revalidation_is_rejected(self):
        request=urllib.request.Request(self.base+'/api/run-existing-photo-revalidation',data=b'{}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with mock.patch.object(tcg_updater,'_start_existing_photo_revalidation') as start:
            status,payload=request_json(request)
        self.assertEqual(status,403)
        self.assertFalse(payload['ok'])
        start.assert_not_called()

    def test_same_origin_trigger_starts_background_job(self):
        accepted={'ok':True,'accepted':True,'job_id':'test-job','job':{'state':'queued'}}
        request=urllib.request.Request(self.base+'/api/run-graded-photo-collection',data=b'{}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':self.base})
        with mock.patch.object(tcg_updater,'_start_graded_photo_collection',return_value=(accepted,202)) as start:
            status,payload=request_json(request)
        self.assertEqual(status,202)
        self.assertTrue(payload['accepted'])
        start.assert_called_once_with()

    def test_manual_registration_status_endpoint(self):
        expected={'ok':True,'registrations':[],'summary':{'total':0}}
        with mock.patch('manual_graded_photo_registration.public_registry',return_value=expected):
            status,payload=request_json(urllib.request.Request(self.base+'/api/graded-photo-manual-registrations'))
        self.assertEqual(status,200)
        self.assertEqual(payload['summary']['total'],0)

    def test_manual_registration_is_same_origin_post_only(self):
        status,payload=request_json(urllib.request.Request(self.base+'/api/graded-photo-manual-registration'))
        self.assertEqual(status,405)
        request=urllib.request.Request(self.base+'/api/graded-photo-manual-registration',data=b'{}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with mock.patch('manual_graded_photo_registration.register') as register:
            status,payload=request_json(request)
        self.assertEqual(status,403)
        register.assert_not_called()

    def test_same_origin_manual_registration_starts_background_verification(self):
        registration={'registration_id':'manual-20260830123456-abcdef123456'}
        request=urllib.request.Request(self.base+'/api/graded-photo-manual-registration',data=b'{"test":true}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':self.base})
        with mock.patch('manual_graded_photo_registration.register',return_value={'ok':True,'duplicate':False,'registration':registration}) as register, \
             mock.patch.object(tcg_updater,'_background_manual_photo_processing') as background:
            status,payload=request_json(request)
        self.assertEqual(status,202)
        self.assertEqual(payload['registration']['registration_id'],registration['registration_id'])
        register.assert_called_once()
        background.assert_called_once_with(registration['registration_id'])


if __name__=='__main__':
    unittest.main()
