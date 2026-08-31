import json
from pathlib import Path
import tempfile
import unittest

import verified_slab_training_archive_v152 as archive


class VerifiedSlabTrainingArchiveV152Tests(unittest.TestCase):
    def _row(self, *, registration_id='manual-20260901010000-abcdef123456', company='PSA', game='onepiece', grade=10.0, cert='160600294', official=True, manual_reference=False):
        row = {
            'registration_id': registration_id,
            'company': company,
            'game': game,
            'claimed_grade': grade,
            'certification_id': cert,
            'image_path': 'GRADE_TRAINING_INBOX/manual/202609/front.jpg',
            'back_image_path': 'GRADE_TRAINING_INBOX/manual/202609/back.jpg',
            'image_sha256': 'front-sha',
            'back_image_sha256': 'back-sha',
            'official_result': official,
            'verification_state': 'verified' if official else 'manual_official_proof_matched',
            'updated_at': '2026-09-01T01:00:00Z',
        }
        if manual_reference:
            row.update({
                'official_result': False,
                'manual_official_proof_registered': True,
                'manual_official_proof_state': 'matched',
            })
        return row

    def test_official_front_back_pair_is_archived_by_company_and_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            archive_root = Path(tmp) / 'archive'
            folder = source / 'GRADE_TRAINING_INBOX' / 'manual' / '202609'
            folder.mkdir(parents=True)
            (folder / 'front.jpg').write_bytes(b'front-image')
            (folder / 'back.jpg').write_bytes(b'back-image')
            payload = archive.sync_rows([self._row()], target_root=archive_root, source_root=source)
            self.assertEqual(payload['summary']['verified_pairs'], 1)
            self.assertEqual(payload['summary']['by_company']['PSA'], 1)
            self.assertTrue((archive_root / '.nomedia').is_file())
            pair_dirs = list((archive_root / 'PSA' / 'onepiece').iterdir())
            self.assertEqual(len(pair_dirs), 1)
            self.assertTrue((pair_dirs[0] / 'front.jpg').is_file())
            self.assertTrue((pair_dirs[0] / 'back.jpg').is_file())
            meta = json.loads((pair_dirs[0] / '학습정보.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['verification_kind'], 'live_official_verified')
            self.assertFalse(meta['raw_grade_calibration_eligible'])

    def test_manual_official_reference_is_reference_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            archive_root = Path(tmp) / 'archive'
            folder = source / 'GRADE_TRAINING_INBOX' / 'manual' / '202609'
            folder.mkdir(parents=True)
            (folder / 'front.jpg').write_bytes(b'front-image')
            (folder / 'back.jpg').write_bytes(b'back-image')
            row = self._row(company='BGS', game='pokemon', cert='0016988990', official=False, manual_reference=True)
            payload = archive.sync_rows([row], target_root=archive_root, source_root=source)
            entry = payload['entries'][0]
            self.assertEqual(entry['verification_kind'], 'manual_official_reference')
            self.assertEqual(entry['learning_eligibility'], 'reference_only_pending_live_official_verification')
            self.assertFalse(entry['official_result'])

    def test_unverified_registration_is_pruned_from_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            archive_root = Path(tmp) / 'archive'
            folder = source / 'GRADE_TRAINING_INBOX' / 'manual' / '202609'
            folder.mkdir(parents=True)
            (folder / 'front.jpg').write_bytes(b'front-image')
            (folder / 'back.jpg').write_bytes(b'back-image')
            row = self._row()
            first = archive.sync_rows([row], target_root=archive_root, source_root=source)
            self.assertEqual(first['summary']['verified_pairs'], 1)
            unverified = dict(row)
            unverified['official_result'] = False
            unverified['verification_state'] = 'completed_unverified'
            second = archive.sync_rows([unverified], target_root=archive_root, source_root=source, prune=True)
            self.assertEqual(second['summary']['verified_pairs'], 0)
            self.assertEqual(second['summary']['pruned'], 1)


if __name__ == '__main__':
    unittest.main()
