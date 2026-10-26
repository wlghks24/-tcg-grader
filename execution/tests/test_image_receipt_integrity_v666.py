"""Fixtures prove cached split/dedup integrity; never become production labels."""
import hashlib,io,json,tempfile,unittest
from pathlib import Path
from PIL import Image
from execution import tablet_image_training as images


class ImageReceiptIntegrityTests(unittest.TestCase):
    def fixture(self,root):
        rows=[];registry={}
        for index,color in enumerate(((10,60,100),(100,20,60))):
            buffer=io.BytesIO();Image.new('RGB',(64,64),color).save(buffer,format='PNG')
            data=buffer.getvalue();photo='photo'+str(index)+'.png';(root/photo).write_bytes(data)
            cert=str(123+index);registry['PSA|'+cert]={'verified':True,'grade':9}
            rows.append({'review_method':'local_human_raw_photo_pair','mode':'raw','game':'pokemon','language':'JP',
                         'company':'PSA','certification_id':cert,'card_identity':'set/card'+str(index),
                         'image':photo,'image_sha256':hashlib.sha256(data).hexdigest()})
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':1,'rows':rows}))
        result=images.run(root,manifest,root/'state',registry=registry)
        self.assertEqual(2,result['accepted_photos'])
        path=root/'state'/'admitted_features_v2.json';cache=json.loads(path.read_text())
        bad_key=next(k for k,v in cache.items() if v['certification_id']=='123')
        good_key=next(k for k in cache if k!=bad_key)
        return manifest,path,registry,cache,bad_key,good_key

    def test_split_and_dedup_tampering_are_excluded_in_both_cache_paths(self):
        for retained_only in (False,True):
            for field in ('split','group','cert_group','image_hash'):
                with self.subTest(retained_only=retained_only,field=field),tempfile.TemporaryDirectory() as d:
                    root=Path(d);manifest,path,registry,cache,bad,good=self.fixture(root)
                    good_before=cache[good]
                    cache[bad][field]=('holdout' if cache[bad]['split']!='holdout' else 'train') if field=='split' else '0'*64
                    path.write_text(json.dumps(cache))
                    if retained_only:manifest.write_text('{"schema":1,"rows":[]}')
                    result=images.run(root,manifest,root/'state',registry=registry)
                    reason='FEATURE_RECEIPT_IMAGE_HASH_MISMATCH' if field=='image_hash' else 'FEATURE_RECEIPT_PARTITION_MISMATCH'
                    self.assertEqual({reason:1},result['rejected'])
                    self.assertEqual(1,result['accepted_photos']);self.assertFalse(result['production_model_changed'])
                    saved=json.loads(path.read_text());self.assertEqual({good},set(saved));self.assertEqual(good_before,saved[good])

    def test_malformed_receipt_does_not_discard_other_valid_learning_values(self):
        for invalid in (None,[],{'scope':['pokemon']},{'scope':['pokemon','JP','PSA'],'x':None}):
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as d:
                root=Path(d);manifest,path,registry,cache,bad,good=self.fixture(root)
                cache[bad]=invalid;path.write_text(json.dumps(cache))
                result=images.run(root,manifest,root/'state',registry=registry)
                self.assertEqual(1,result['accepted_photos']);self.assertTrue(result['rejected'])
                self.assertEqual({good},set(json.loads(path.read_text())))

    def test_oversized_numeric_receipt_is_isolated_in_both_cache_paths(self):
        for retained_only in (False,True):
            for field in ('x','grade'):
                with self.subTest(retained_only=retained_only,field=field),tempfile.TemporaryDirectory() as d:
                    root=Path(d);manifest,path,registry,cache,bad,good=self.fixture(root)
                    good_before=cache[good]
                    if field=='x':cache[bad]['x'][0]=10**500
                    else:cache[bad]['grade']=10**500
                    path.write_text(json.dumps(cache))
                    if retained_only:manifest.write_text('{"schema":1,"rows":[]}')
                    result=images.run(root,manifest,root/'state',registry=registry)
                    self.assertEqual(1,result['accepted_photos']);self.assertTrue(result['rejected'])
                    saved=json.loads(path.read_text());self.assertEqual({good},set(saved));self.assertEqual(good_before,saved[good])

    def test_revoked_certificate_and_explicit_forget_still_remove_rows(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,path,registry,cache,bad,good=self.fixture(root)
            manifest.write_text(json.dumps({'schema':1,'rows':[],'forget_receipt_keys':[good]}))
            registry.pop('PSA|123')
            result=images.run(root,manifest,root/'state',registry=registry)
            self.assertEqual(0,result['accepted_photos']);self.assertEqual({},json.loads(path.read_text()))
            self.assertEqual({'RETAINED_CERT_REVOKED_OR_CHANGED':1},result['rejected'])

    def test_valid_receipts_survive_batch_change_and_missing_historical_photos(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,path,registry,cache,bad,good=self.fixture(root)
            for photo in root.glob('photo*.png'):photo.unlink()
            manifest.write_text('{"schema":1,"rows":[]}')
            result=images.run(root,manifest,root/'state',registry=registry)
            self.assertEqual(2,result['accepted_photos']);self.assertEqual({},result['rejected'])
            self.assertEqual(cache,json.loads(path.read_text()))
