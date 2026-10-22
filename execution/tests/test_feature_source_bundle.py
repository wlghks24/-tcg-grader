import tempfile
from pathlib import Path
import unittest
from zipfile import ZipFile
from execution.tablet_feature_source_bundle import bundle,REQUIRED

class SourceBundleTests(unittest.TestCase):
    def test_source_dependency_closure_excludes_images_json_and_models(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';repo.mkdir()
            (repo/REQUIRED[0]).write_text('import bridge_helper\n')
            (repo/REQUIRED[1]).write_text('pass\n')
            (repo/'bridge_helper.py').write_text('pass\n')
            for name in ('image.png','index.json','model.pkl','.env'):(repo/name).write_bytes(b'private')
            out=root/'sources.zip';names=bundle(repo,out)
            self.assertEqual(set(names),set(REQUIRED)|{'bridge_helper.py'})
            with ZipFile(out) as z:self.assertEqual(set(z.namelist()),set(names))
            with self.assertRaises(ValueError):bundle(repo,out)

    def test_missing_source_fails_before_writing_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'out.zip'
            with self.assertRaises(ValueError):bundle(root,out)
            self.assertFalse(out.exists())

    def test_symlink_dependency_cannot_export_external_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';repo.mkdir()
            (root/'external.py').write_text('private=True\n')
            (repo/REQUIRED[0]).write_text('import bridge_helper\n')
            (repo/REQUIRED[1]).write_text('pass\n')
            (repo/'bridge_helper.py').symlink_to(root/'external.py')
            with self.assertRaises(ValueError):bundle(repo,root/'out.zip')
            self.assertFalse((root/'out.zip').exists())

    def test_embedded_photo_is_not_silently_exported_inside_html(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in REQUIRED:(root/name).write_text('pass\n')
            (root/'index.html').write_text('<img src="data:image/png;base64,'+'A'*200+'">')
            with self.assertRaises(ValueError):bundle(root,root/'out.zip')
            self.assertFalse((root/'out.zip').exists())

    def test_explicit_partial_export_collects_current_ui_and_reports_missing_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'index.html').write_text('<main>Current UI</main>')
            (root/'photo.webp').write_bytes(b'private')
            out=root/'partial.zip';names=bundle(root,out,allow_partial=True)
            self.assertEqual(set(names),{'index.html','SOURCE_BUNDLE_STATUS.txt'})
            with ZipFile(out) as z:
                report=z.read('SOURCE_BUNDLE_STATUS.txt').decode()
                self.assertIn('PARTIAL_SOURCE_ONLY',report)
                for name in REQUIRED:self.assertIn(name,report)
