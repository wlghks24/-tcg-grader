"""Historical review documents retain their exact bytes after root cleanup."""
from pathlib import Path
import subprocess,unittest
from unittest.mock import patch
import sync_v376_successor_test_support as sync

class ArchivedReviewTests(unittest.TestCase):
    def test_review_documents_keep_original_evidence(self):
        for name,digest in sync.V652_ARCHIVED_REVIEWS.items():
            path=sync._reviewed_document_path(self,name)
            self.assertEqual(path,sync.ROOT/'docs/archive'/name)
            self.assertEqual(path.read_bytes(),subprocess.check_output(['git','show','328782f6b92835c4aab39224bb0c6c5c6b3e0067:'+name],cwd=sync.ROOT))
    def test_tampered_archived_document_fails(self):
        original=Path.read_bytes
        for name in sync.V652_ARCHIVED_REVIEWS:
            path=sync.ROOT/'docs/archive'/name
            def changed(p):return original(p)+b'changed' if p==path else original(p)
            with self.subTest(name=name),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(AssertionError):sync._reviewed_document_path(self,name)
