from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import library_slab_corpus as slab


class LibrarySlabCorpusTests(unittest.TestCase):
    def test_tag_technical_authentication_regression(self):
        self.assertEqual(slab.detect_company('TAG Technical Authentication'),'TAG')

    def test_unknown_company_cannot_select_certification_rules(self):
        self.assertIsNone(slab.normalize_cert('UNKNOWN','CERT 12345678'))

    def test_stable_sample_is_reproducible(self):
        paths=[Path(f'folder/{index}.jpg') for index in range(20)]
        self.assertEqual(slab.choose_paths(paths,5,42),slab.choose_paths(paths,5,42))
        self.assertEqual(len(slab.choose_paths(paths,5,42)),5)

    def test_adaptive_ocr_stops_after_fields_are_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path=Path(directory)/'slab.png'
            Image.new('RGB',(120,200),'white').save(image_path)
            outputs=[
                ('TAG Technical Authentication',''),
                ('TAG Technical Authentication and Grading CERT 123456 GRADE 10',None),
            ]
            with mock.patch.object(slab,'_run_tesseract',side_effect=outputs) as run:
                text,error,diagnostics=slab.ocr_label(image_path,'adaptive')
        self.assertIsNone(error)
        self.assertIn('123456',text)
        self.assertEqual(run.call_count,2)
        self.assertEqual(diagnostics['pass_count'],2)
        self.assertTrue(diagnostics['company_resolved'])
        self.assertTrue(diagnostics['cert_resolved'])
        self.assertTrue(diagnostics['grade_resolved'])

    def test_duplicate_reuses_ocr_but_never_adds_training_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'a').mkdir();(root/'b').mkdir()
            for path in (root/'a'/'one.png',root/'b'/'two.png'):
                Image.new('RGB',(80,120),'white').save(path)
            registry=root/'registry.json'
            registry.write_text(json.dumps({'certifications':[{
                'company':'PSA','certification_id':'12345678','grade':10,
                'officially_verified':True,'official_reference_url':'https://www.psacard.com/cert/12345678'
            }]}),encoding='utf-8')
            with mock.patch.object(slab,'ocr_label',return_value=(
                    'PSA GEM MT 10 CERT 12345678',None,
                    {'profile':'adaptive','passes_used':['p1'],'pass_count':1,
                     'company_resolved':True,'cert_resolved':True,'grade_resolved':True}
            )) as ocr:
                manifest,verified,queue=slab.build(root,registry,progress_every=0)
        self.assertEqual(ocr.call_count,1)
        self.assertEqual(manifest['summary']['exact_duplicate_files'],1)
        duplicate=next(row for row in manifest['records'] if row.get('exact_duplicate_of'))
        self.assertTrue(duplicate['official_result'])
        self.assertIsNone(duplicate['ocr_error'])
        self.assertFalse(duplicate['training_eligible'])
        self.assertEqual(len(verified['certifications']),1)
        self.assertEqual(verified['training_rows_written'],0)
        self.assertEqual(queue['records'],[])

    def test_unverified_certification_enters_lookup_queue_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);image_path=root/'candidate.png'
            Image.new('RGB',(80,120),'white').save(image_path)
            with mock.patch.object(slab,'ocr_label',return_value=(
                    'TAG Technical Authentication CERT 123456 GRADE 10',None,
                    {'profile':'fast','passes_used':['p1'],'pass_count':1,
                     'company_resolved':True,'cert_resolved':True,'grade_resolved':True}
            )):
                manifest,verified,queue=slab.build(root,progress_every=0,ocr_profile='fast')
        self.assertFalse(manifest['records'][0]['official_result'])
        self.assertEqual(verified['certifications'],[])
        self.assertEqual(queue['records'][0]['status'],'official_lookup_required')
        self.assertFalse(queue['records'][0]['training_eligible'])

    @unittest.skipUnless(hasattr(os,'symlink'),'symbolic links unavailable')
    def test_symbolic_link_image_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);outside=root/'outside.png';outside.write_bytes(b'not-an-image')
            inbox=root/'inbox';inbox.mkdir();link=inbox/'linked.png'
            try:link.symlink_to(outside)
            except OSError:self.skipTest('symbolic links not permitted')
            self.assertEqual(slab.iter_images(inbox),[])


if __name__=='__main__':
    unittest.main()
