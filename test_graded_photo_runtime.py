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

    def test_json_read_cache_invalidates_after_file_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'changing.json'
            path.write_text('{"value":1}',encoding='utf-8')
            tcg_updater.clear_json_file_cache()
            self.assertEqual(tcg_updater.load_json_file(path,{})['value'],1)
            path.write_text('{"value":200}',encoding='utf-8')
            self.assertEqual(tcg_updater.load_json_file(path,{})['value'],200)

    def test_dashboard_avoids_background_refresh_and_stops_finished_polling(self):
        source=(ROOT/'graded_photo_dashboard.js').read_text(encoding='utf-8')
        self.assertIn("document.visibilityState==='visible'",source)
        self.assertIn('manualVerificationFinished(payload,registrationId)',source)
        self.assertNotIn('rows.filter(r=>companyOf(r)===c)',source)

    def test_collection_trigger_is_post_only(self):
        status,payload=request_json(urllib.request.Request(self.base+'/api/run-graded-photo-collection'))
        self.assertEqual(status,405)
        self.assertFalse(payload['ok'])

    def test_cross_site_trigger_is_rejected(self):
        request=urllib.request.Request(self.base+'/api/run-graded-photo-collection',data=b'{}',method='POST',
                                       headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with mock.patch.object(tcg_updater,'_start_graded_photo_collection') as start:
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
