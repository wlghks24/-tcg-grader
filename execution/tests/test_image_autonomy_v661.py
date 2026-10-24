import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from execution import tablet_image_autonomy as adapter,tablet_image_model_gate as gate,tablet_local_learning as learning,tablet_image_training as images

class ImageAutonomyTests(unittest.TestCase):
    def test_missing_labels_are_waiting_not_false_training_success(self):
        with tempfile.TemporaryDirectory() as d:
            r=adapter.run(root=Path(d),state=Path(d)/'state',train=True)
            self.assertEqual('WAITING_FOR_REVIEWED_RAW_PHOTOS',r['status'])
            self.assertFalse(r['production_model_changed'])

    def test_status_does_not_decode_images_and_train_uses_one_existing_call(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inbox=root/'GRADE_TRAINING_INBOX';inbox.mkdir()
            (inbox/'verified_raw_photos.json').write_text('{"schema":1,"rows":[]}')
            with patch.object(adapter,'resource_budget',return_value=None),patch.object(images,'run',return_value={'accepted_photos':0}) as work:
                self.assertEqual('WAITING_FOR_FIRST_SIX_HOUR_CYCLE',adapter.run(root=root,state=root/'state')['status'])
                work.assert_not_called()
                self.assertEqual('CHECKED',adapter.run(root=root,state=root/'state',train=True)['status'])
                self.assertEqual(1,work.call_count);self.assertTrue(work.call_args.kwargs['train'])

    def test_low_resources_defer_optional_image_work(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inbox=root/'GRADE_TRAINING_INBOX';inbox.mkdir()
            (inbox/'verified_raw_photos.json').write_text('{"schema":1,"rows":[]}')
            with patch.object(adapter,'resource_budget',return_value='LOW_AVAILABLE_MEMORY'),patch.object(images,'run') as work:
                self.assertEqual('DEFERRED_RESOURCE_BUDGET',adapter.run(root=root,state=root/'state',train=True)['status'])
                work.assert_not_called()

    def test_production_learning_route_calls_image_adapter_and_preserves_collection(self):
        with patch.object(adapter,'run',return_value={'status':'WAITING'}) as image:
            r=learning.run(train=True)
            image.assert_called_once_with(train=True)
            self.assertIn('query',r['models']);self.assertIn('job',r['models'])
            self.assertEqual({'status':'WAITING'},r['image_learning'])

    def test_both_splits_must_improve_and_overgrading_cannot_worsen(self):
        baseline={'mae':.4,'overgrade_rate':.05,'bias':0}
        good={'mae':.3,'overgrade_rate':.04,'bias':.1}
        self.assertTrue(gate.choose('grade',good,good,baseline,baseline))
        self.assertFalse(gate.choose('grade',good,dict(good,mae=.7),baseline,baseline))
        self.assertFalse(gate.acceptable('grade',dict(good,overgrade_rate=.06),baseline))
        self.assertFalse(gate.acceptable('grade',dict(good,mae=float('nan')),baseline))

    def test_probability_calibration_gate_and_atomic_backup(self):
        old={'accuracy':.8,'brier':.2,'ece':.1};new={'accuracy':.95,'brier':.1,'ece':.05}
        self.assertTrue(gate.acceptable('identity',new,old))
        self.assertFalse(gate.acceptable('identity',dict(new,ece=.3),old))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'champion';backup=Path(d)/'backup'
            gate.promote(path,backup,{'new':True},{'old':True})
            self.assertEqual({'old':True},json.loads(backup.read_text()))
            self.assertEqual({'new':True},json.loads(path.read_text()))

    def test_native_resolution_features_preserve_local_texture(self):
        import io
        from PIL import Image,ImageDraw
        def encode(image):
            b=io.BytesIO();image.save(b,format='PNG');return b.getvalue()
        plain=Image.new('RGB',(1024,1024),'gray');marked=plain.copy()
        ImageDraw.Draw(marked).line((0,512,1023,512),fill='white',width=1)
        a,b=images.pixels(encode(plain)),images.pixels(encode(marked))
        self.assertEqual(288,len(a));self.assertNotEqual(a[192:],b[192:])

    def test_regressed_advisory_champion_restores_recomputed_last_good(self):
        import math
        def model(grade):
            probability=(grade-1)/9
            return {'task':'grade','classes':[],'w':[[0.]],'b':[0.],'v':[[0.]],'c':[math.log(probability/(1-probability))]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);scope=('pokemon','JP','PSA');key=images.digest((scope,'grade'))[:20]
            def artifact(grade):return {'feature_schema':images.FEATURE_SCHEMA,'scope':scope,'task':'grade','model':model(grade),'production_enabled':False}
            (root/(key+'.champion.json')).write_text(json.dumps(artifact(9)))
            (root/(key+'.last-good.json')).write_text(json.dumps(artifact(5)))
            parts={name:[{'x':[.1],'grade':5,'identity':'card'}] for name in ('train','validation','holdout')}
            report={name:images.metrics(model(8),parts[name]) for name in ('validation','holdout')}
            images.compare_and_select(root,scope,'grade',model(8),parts,report,'fixture')
            self.assertEqual('ADVISORY_LAST_GOOD_RESTORED',report['selection'])
            restored=json.loads((root/(key+'.champion.json')).read_text())
            self.assertAlmostEqual(5,1+9*images.predict(restored['model'],[.1])[0])
            self.assertFalse(restored['production_enabled'])

    def test_new_inbox_batch_retains_prior_verified_features_until_explicit_forget(self):
        import hashlib,io
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=io.BytesIO();Image.new('RGB',(64,64),(20,60,120)).save(b,format='PNG')
            (root/'photo.png').write_bytes(b.getvalue())
            row={'review_method':'local_human_raw_photo_pair','mode':'raw','game':'pokemon','language':'JP','company':'PSA','certification_id':'123','card_identity':'set/card','image':'photo.png','image_sha256':hashlib.sha256(b.getvalue()).hexdigest()}
            manifest=root/'inbox.json';manifest.write_text(json.dumps({'schema':1,'rows':[row]}));registry={'PSA|123':{'verified':True,'grade':9}}
            first=images.run(root,manifest,root/'state',registry=registry)
            self.assertEqual(1,first['accepted_photos'])
            manifest.write_text('{"schema":1,"rows":[]}')
            self.assertEqual(1,images.run(root,manifest,root/'state',registry=registry)['accepted_photos'])
            cache=json.loads((root/'state'/'admitted_features_v2.json').read_text())
            manifest.write_text(json.dumps({'schema':1,'rows':[row],'forget_receipt_keys':list(cache)}))
            self.assertEqual(0,images.run(root,manifest,root/'state',registry=registry)['accepted_photos'])
