"""Deterministic quota/real-codec tests: fixture images only, no external calls."""
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from execution import tablet_image_collection_policy as p


class Clock:
    def __init__(self):self.value=2_000_000_000.0
    def __call__(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class ImagePolicyTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.state={};self.writes=0
        def save():self.writes+=1
        self.budget=p.Budget(self.state,save,clock=self.clock,timer=self.clock)

    def test_requests_are_spaced_and_accounted_before_network(self):
        self.budget.reserve_request('A',self.clock.sleep)
        first=self.clock.value
        self.budget.reserve_request('A',self.clock.sleep)
        self.assertEqual(self.clock.value-first,2)
        self.assertEqual(self.budget.snapshot()['requests_last_24h'],2)
        self.assertEqual(self.writes,2)

    def test_request_spacing_survives_restart(self):
        self.budget.reserve_request('A',self.clock.sleep)
        restored=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        start=self.clock.value;restored.reserve_request('B',self.clock.sleep)
        self.assertEqual(self.clock.value-start,2)

    def test_daily_image_and_provider_limits_persist_across_runs(self):
        for provider in ['A','B','C','D','E','F']:
            for _ in range(24):self.budget.record_image(provider,100)
        again=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        with self.assertRaises(p.Deferred):again.can_save('G')
        self.assertEqual(again.snapshot()['saved_last_24h'],144)

    def test_aggregate_quota_increase_does_not_increase_provider_traffic(self):
        self.assertEqual((p.RUN_IMAGES,p.DAY_IMAGES),(36,144))
        self.assertEqual((p.PROVIDER_DAY_IMAGES,p.PROVIDER_DAY_REQUESTS),(24,80))
        self.assertEqual((p.REQUEST_SPACING,p.RUN_SECONDS,p.RUN_BYTES,p.DAY_BYTES),(2.0,180,24*1024*1024,96*1024*1024))
        for i in range(p.RUN_IMAGES):self.budget.record_image(str(i%2),100)
        with self.assertRaises(p.Deferred):self.budget.can_save('C')
        restored=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        restored.can_save('C')

    def test_403_cooldown_is_preserved_and_skips_metadata_listing(self):
        self.budget.block('A',403)
        restored=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        with self.assertRaises(p.Deferred):restored.can_save('A')
        restored.can_save('B')
        self.clock.sleep(6*3600+1)
        resumed=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        resumed.can_save('A')

    def test_one_provider_quota_does_not_block_other_providers(self):
        for _ in range(24):self.budget.record_image('A',100)
        again=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        with self.assertRaises(p.Deferred):again.can_save('A')
        again.can_save('B')

    def test_rolling_window_is_not_reset_at_midnight(self):
        for _ in range(24):self.budget.record_image('A',100)
        self.clock.sleep(6*3600)
        again=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        with self.assertRaises(p.Deferred):again.can_save('A')
        self.clock.sleep(18*3600+1)
        restored=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        restored.can_save('A');self.assertEqual(restored.snapshot()['saved_last_24h'],0)

    def test_retry_after_and_block_are_persisted_and_source_specific(self):
        self.budget.block('A',429,'7200')
        self.clock.sleep(3601)
        again=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        with self.assertRaises(p.Deferred):again.reserve_request('A',self.clock.sleep)
        again.reserve_request('B',self.clock.sleep)
        self.clock.sleep(3600)
        resumed=p.Budget(self.state,lambda:None,clock=self.clock,timer=self.clock)
        resumed.reserve_request('A',self.clock.sleep)

    def test_request_and_byte_budgets_cannot_be_exceeded(self):
        row=self.budget.reserve_request('A',self.clock.sleep)
        with patch.object(p,'RUN_BYTES',100):
            self.budget.add_bytes(row,100)
            self.assertEqual(self.budget.byte_allowance(),0)
            with self.assertRaises(p.Deferred):self.budget.add_bytes(row,1)
        with patch.object(p,'RUN_REQUESTS',1):
            with self.assertRaises(p.Deferred):self.budget.reserve_request('B',self.clock.sleep)

    def test_duration_limit_stops_more_requests(self):
        self.clock.sleep(p.RUN_SECONDS)
        with self.assertRaises(p.Deferred):self.budget.reserve_request('A',self.clock.sleep)
        with self.assertRaises(p.Deferred):self.budget.can_save('A')

    def test_corrupt_budget_state_fails_closed(self):
        for rows in [True,[{'at':float('nan'),'kind':'image','provider':'A','bytes':1}],
                     [{'at':self.clock()+1000,'kind':'image','provider':'A','bytes':1}]]:
            with self.assertRaises(p.Deferred):p.Budget({'image_budget_events':rows},lambda:None,clock=self.clock,timer=self.clock)

    def fixture(self):
        image=Image.new('RGBA',(600,825),(240,240,230,255));draw=ImageDraw.Draw(image)
        for y in range(30,800,17):draw.text((30,y),'Readable fixture card AB-123 0123456789',fill=(12,30,50,255))
        out=io.BytesIO();image.save(out,format='PNG',compress_level=0)
        return image,out.getvalue()

    def test_lossless_compression_preserves_every_pixel_and_resolution(self):
        image,data=self.fixture();stored,report=p.lossless_storage(data)
        self.assertLess(len(stored),len(data));self.assertEqual(report['encoding'],'webp-lossless')
        with Image.open(io.BytesIO(stored)) as result:
            self.assertEqual(result.size,image.size)
            self.assertEqual(result.convert('RGBA').tobytes(),image.tobytes())
        self.assertTrue(report['lossless']);self.assertFalse(report['resized'])

    def test_source_bytes_are_kept_if_codec_unavailable(self):
        _,data=self.fixture()
        with patch('PIL.features.check',return_value=False):stored,report=p.lossless_storage(data)
        self.assertEqual(stored,data);self.assertEqual(report['encoding'],'source')

    def test_oversized_and_invalid_images_are_not_converted(self):
        _,data=self.fixture()
        with patch.object(p,'MAX_PIXELS',100):
            with self.assertRaises(ValueError):p.lossless_storage(data)
        with self.assertRaises((ValueError,OSError)):p.lossless_storage(b'not an image')

    def test_already_compressed_jpeg_is_preserved_when_lossless_webp_is_larger(self):
        import random
        rgb=Image.frombytes('RGB',(80,80),random.Random(43).randbytes(80*80*3))
        source=io.BytesIO();rgb.save(source,format='JPEG',quality=60)
        data=source.getvalue();stored,report=p.lossless_storage(data)
        self.assertEqual(stored,data)
        self.assertEqual(report['encoding'],'source')
        self.assertEqual(report['stored_bytes'],len(data))
        self.assertFalse(report['resized'])
        self.assertTrue(report['readability_review_required'])
