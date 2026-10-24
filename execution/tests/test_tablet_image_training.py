"""Fixtures test mechanics only; never become production learning labels."""
import hashlib,io,json,tempfile,time,unittest
from pathlib import Path
from PIL import Image
from execution import tablet_image_training as t

class ImageTrainingTests(unittest.TestCase):
    def fixture(self,root):
        buffer=io.BytesIO();Image.new('RGB',(64,64),(10,60,100)).save(buffer,format='PNG');data=buffer.getvalue()
        (root/'raw.png').write_bytes(data)
        row={'review_method':'local_human_raw_photo_pair','mode':'raw','game':'pokemon','language':'JP','company':'PSA','certification_id':'123','card_identity':'set/card','image':'raw.png','image_sha256':hashlib.sha256(data).hexdigest()}
        manifest=root/'input.json';manifest.write_text(json.dumps({'schema':1,'rows':[row]}))
        return row,manifest,{'PSA|123':{'verified':True,'grade':9}}

    def test_real_photo_admission_and_official_registry_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);row,m,reg=self.fixture(root)
            rows,rejected=t.load_rows(root,m,reg)
            self.assertEqual(1,len(rows));self.assertEqual({},rejected);self.assertEqual(192,len(rows[0]['x']))
            self.assertEqual([],t.load_rows(root,m,{})[0])
            row['mode']='slab';m.write_text(json.dumps({'schema':1,'rows':[row]}))
            self.assertIn('RAW_PHOTO_PAIR_REVIEW_REQUIRED',t.load_rows(root,m,reg)[1])

    def test_admitted_values_accumulate_and_never_enable_live_grading(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);row,m,reg=self.fixture(root)
            first=t.run(root,m,root/'out',train=True,registry=reg)
            self.assertEqual(1,first['accepted_photos']);self.assertFalse(first['production_model_changed'])
            self.assertTrue(all(not r['training_attempted'] for r in first['models']))
            self.assertTrue(all(r['rows_remaining']==999 for r in first['models']))
            (root/'raw.png').unlink() # Historical feature receipt remains auditable.
            second=t.run(root,m,root/'out',registry=reg)
            self.assertEqual(1,second['accepted_photos'])
            changed=t.run(root,m,root/'out',registry={})
            self.assertEqual(0,changed['accepted_photos'])

    def test_duplicate_hash_and_path_escape_do_not_add_labels(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);row,m,reg=self.fixture(root)
            m.write_text(json.dumps({'schema':1,'rows':[row,row]}))
            rows,errors=t.load_rows(root,m,reg)
            self.assertEqual(1,len(rows));self.assertEqual(1,errors['DUPLICATE_PHOTO_OR_CERT'])
            with self.assertRaises(ValueError):t.checked_path(root,'../photo.png')

    def test_neural_optimization_and_budget(self):
        rows=[{'x':[0.]*192,'grade':1,'identity':'a'},{'x':[1.]*192,'grade':10,'identity':'b'}]*20
        grade=t.fit(rows,'grade',[],time.monotonic()+20)
        self.assertLess(t.predict(grade,rows[0]['x'])[0],t.predict(grade,rows[1]['x'])[0])
        identity=t.fit(rows,'identity',['a','b'],time.monotonic()+20)
        self.assertEqual(1,t.metrics(identity,rows)['accuracy'])
        with self.assertRaises(TimeoutError):t.fit(rows,'grade',[],time.monotonic()-1)
