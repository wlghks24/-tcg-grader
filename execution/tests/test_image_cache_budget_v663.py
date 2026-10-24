"""Exercise the actual serialized 4,000-row store, not a mirrored limit assertion."""
import hashlib,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from execution import tablet_image_training as images

class ImageCacheBudgetTests(unittest.TestCase):
    def test_full_admitted_store_can_be_read_on_the_next_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state';state.mkdir()
            row={'x':[i/255 for i in range(192)]+[i/97 for i in range(96)],'scope':['pokemon','CN-S','PSA'],'identity':'a'*180,'grade':9.5,'image_hash':'a'*64,'group':'b'*64,'cert_group':'c'*64,'receipt_key':'d'*64,'feature_digest':'e'*64,'source_sha256':'f'*64,'certification_id':'1234567890','split':'validation','feature_schema':2}
            path=state/'admitted_features_v2.json'
            path.write_text(json.dumps({str(i):row for i in range(4000)},indent=2))
            self.assertGreater(path.stat().st_size,25_000_000)
            manifest=root/'manifest';manifest.write_text('{"schema":1,"rows":[]}')
            # Admission is isolated here: the fixture is not production labels.
            with patch.object(images,'load_rows',return_value=([],{})) as admission:
                result=images.run(root,manifest,state,registry={})
                self.assertEqual(4000,len(admission.call_args.args[3]))
                self.assertEqual(0,result['accepted_photos'])

    def test_row_count_still_bounds_the_larger_store(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state';state.mkdir()
            (state/'admitted_features_v2.json').write_text(json.dumps({str(i):{} for i in range(4001)}))
            manifest=root/'manifest';manifest.write_text('{"schema":1,"rows":[]}')
            with self.assertRaisesRegex(ValueError,'INVALID_FEATURE_CACHE'):
                images.run(root,manifest,state,registry={})

    def test_photo_growth_after_stat_does_not_bypass_the_byte_limit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=io.BytesIO();Image.new('RGB',(64,64),'white').save(b,format='PNG')
            data=b.getvalue()+b' '*(images.MAX_BYTES+1)
            photo=root/'photo.png';photo.write_bytes(data)
            row={'review_method':'local_human_raw_photo_pair','mode':'raw','game':'pokemon','language':'JP','company':'PSA','certification_id':'123','card_identity':'set/card','image':'photo.png','image_sha256':hashlib.sha256(data).hexdigest()}
            manifest=root/'manifest';manifest.write_text(json.dumps({'schema':1,'rows':[row]}))
            original=Path.stat
            def before_growth(path,*args,**kwargs):
                result=original(path,*args,**kwargs)
                if path==photo:
                    fields=list(result);fields[6]=0;return os.stat_result(fields)
                return result
            with patch.object(Path,'stat',before_growth):
                rows,rejected=images.load_rows(root,manifest,{'PSA|123':{'verified':True,'grade':9}})
            self.assertEqual([],rows);self.assertTrue(rejected)
