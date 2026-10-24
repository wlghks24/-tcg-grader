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
