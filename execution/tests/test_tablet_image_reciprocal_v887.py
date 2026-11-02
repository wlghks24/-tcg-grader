"""V887 private two-way repair plan: data-driven, no network or photo mutation."""
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from execution.tablet_image_reciprocal_v887 import plan, write_private_plan

I = 'a' * 32
S = 'b' * 32
S2 = 'c' * 32
SUPPORTED = {('pokemon', 'JP'): 'TCGdex', ('onepiece', 'JP'): 'PunkRecords'}


def image(**kwargs):
    return {'id': I, 'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
            'product_codes': ['SV1S001'], 'provider': 'TCGdex',
            'source_id': 'pokemon/ja/sv1s-001', 'card_metadata': {'card_code': 'sv1s-001'}, **kwargs}


def source(**kwargs):
    return {'source_record_id': S, 'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
            'product_codes': ['SV1S001'], 'source_health': 'HEALTHY', **kwargs}


def report(images=None, sources=None, tasks=None, **summary):
    return {'ok': True, 'summary': {'source_limit_reached': False, 'queue_truncated': False, **summary},
            'source_errors': [], 'local_catalog': images if images is not None else [image()],
            'source_catalog': sources if sources is not None else [source()],
            'gap_queue': tasks if tasks is not None else [
                {'direction': 'IMAGE_NEEDS_METADATA', 'image_id': I,
                 'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
                 'reason': 'NO_EXACT_IDENTIFIER_MATCH'}]}


class ReciprocalImageV887Tests(unittest.TestCase):
    def test_metadata_retry_with_exact_provider_origin_and_source_hint(self):
        result = plan(report(), SUPPORTED)
        self.assertTrue(result['ok'])
        self.assertEqual(result['summary']['image_to_catalog'], 1)
        self.assertEqual(result['actions'][0]['next_action'], 'RECHECK_ORIGIN_METADATA')
        self.assertEqual(result['actions'][0]['source_record_id_hint'], S)
        self.assertFalse(result['actions'][0]['auto_link'])
        self.assertFalse(result['automatic_image_replacement'])

    def test_missing_image_requery_only_for_configured_verified_provider_and_exact_code(self):
        task = {'direction': 'CATALOG_NEEDS_IMAGE', 'source_record_id': S,
                'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
                'reason': 'NO_UNIQUE_LOCAL_IMAGE'}
        result = plan(report(images=[], tasks=[task]), SUPPORTED)
        self.assertEqual(result['actions'][0]['next_action'], 'REQUERY_CONFIGURED_PROVIDER')
        self.assertEqual(result['collection_priorities'], [
            {'game_id': 'pokemon', 'region': 'JP', 'missing_images': 1}])
        self.assertFalse(result['actions'][0]['auto_download'])

    def test_source_is_unverified_or_missing_code_then_no_auto_priority(self):
        task = {'direction': 'CATALOG_NEEDS_IMAGE', 'source_record_id': S,
                'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
                'reason': 'NO_UNIQUE_LOCAL_IMAGE'}
        for changes, expected in [({'source_health': 'UNVERIFIED'}, 'REVERIFY_CATALOG_SOURCE'),
                                  ({'product_codes': []}, 'REVIEW_MISSING_EXACT_CODE')]:
            src = source();src.update(changes)
            with self.subTest(changes=changes):
                result = plan(report(images=[], sources=[src], tasks=[task]), SUPPORTED)
                self.assertEqual(result['actions'][0]['next_action'], expected)
                self.assertEqual(result['collection_priorities'], [])

    def test_wrong_country_or_game_does_not_borrow_image(self):
        task = {'direction': 'CATALOG_NEEDS_IMAGE', 'source_record_id': S,
                'game_id': 'pokemon', 'region': 'CN-S', 'kind': 'CARD',
                'reason': 'NO_UNIQUE_LOCAL_IMAGE'}
        data = source();data['region'] = 'CN-S'
        out = plan(report(sources=[data], images=[image()], tasks=[task]), SUPPORTED)
        self.assertEqual(out['actions'][0]['next_action'], 'FIND_SUPPORTED_OFFICIAL_SOURCE')
        self.assertEqual(out['collection_priorities'], [])

    def test_ambiguous_code_stays_review_only_and_one_hint_never_proves_link(self):
        task = {'direction': 'IMAGE_NEEDS_METADATA', 'image_id': I,
                'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
                'reason': 'AMBIGUOUS_CODE'}
        extra = source();extra['source_record_id'] = S2
        out = plan(report(sources=[source(), extra], tasks=[task]), SUPPORTED)
        self.assertEqual(out['actions'][0]['next_action'], 'REVIEW_CONFLICTING_IDENTITY')
        self.assertIsNone(out['actions'][0]['source_record_id_hint'])
        self.assertFalse(out['actions'][0]['auto_link'])

    def test_variant_conflicts_require_review_even_when_metadata_endpoint_exists(self):
        for reason in ('CARD_VARIANT_CONFLICT', 'CARD_SET_CONFLICT'):
            task = {'direction': 'IMAGE_NEEDS_METADATA', 'image_id': I,
                    'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD', 'reason': reason}
            out = plan(report(tasks=[task]), SUPPORTED)
            self.assertEqual(out['actions'][0]['next_action'], 'REVIEW_CONFLICTING_IDENTITY')

    def test_incomplete_sources_queue_and_duplicate_ids_are_fail_closed(self):
        inputs = [report(source_errors=1), report(queue_truncated=True),
                  report(source_limit_reached=True)]
        inputs[0]['source_errors'] = [{'dataset': 'releases.json', 'error': 'ValueError'}]
        inputs.append(report(sources=[source(), source()]))
        inputs.append(report(tasks=report()['gap_queue'] * 2))
        for x in inputs:
            with self.subTest(case=x['summary']):
                out = plan(x, SUPPORTED)
                self.assertFalse(out['ok'])
                self.assertEqual(out['actions'], [])

    def test_malformed_sources_and_gaps_cannot_generate_actions(self):
        bad = [report(sources=[source(product_codes=['-INVALID'])]),
               report(sources=[source(product_codes=['SV1S001', 12])]),
               report(tasks=[{'direction': 'IMAGE_NEEDS_METADATA', 'image_id': 'f' * 32,
                              'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
                              'reason': 'NO_EXACT_IDENTIFIER_MATCH'}]),
               report(tasks=[{'direction': 'CATALOG_NEEDS_IMAGE', 'source_record_id': S,
                              'game_id': 'pokemon', 'region': 'US', 'kind': 'CARD',
                              'reason': 'NO_UNIQUE_LOCAL_IMAGE'}])]
        for x in bad:
            self.assertFalse(plan(x, SUPPORTED)['ok'])

    def test_write_action_sidecar_is_private_atomic_and_does_not_touch_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'index.json').write_text('original index')
            (root / 'photo.png').write_bytes(b'source image bytes')
            class FakeLibrary:
                LOCK = threading.RLock()
                @staticmethod
                def _atomic_write(path, data):
                    temporary = path.with_name('temp.data')
                    temporary.write_bytes(data)
                    temporary.replace(path)
            result = write_private_plan(report(), SUPPORTED, root, FakeLibrary,
                            clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc))
            self.assertTrue(result['ok'])
            stored = json.loads((root / 'collection_repair_plan_v887.json').read_text())
            self.assertEqual(stored['actions'][0]['image_id'], I)
            self.assertFalse(stored['automatic_image_replacement'])
            self.assertEqual((root / 'index.json').read_text(), 'original index')
            self.assertEqual((root / 'photo.png').read_bytes(), b'source image bytes')
            original = (root / 'collection_repair_plan_v887.json').read_bytes()
            invalid = report();invalid['source_errors'] = [{'dataset': 'market_watch.json'}]
            self.assertFalse(write_private_plan(invalid, SUPPORTED, root, FakeLibrary)['ok'])
            self.assertEqual((root / 'collection_repair_plan_v887.json').read_bytes(), original)

    def test_symlink_sidecar_is_blocked_and_external_file_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);outside=root/'outside';outside.write_bytes(b'do-not-touch')
            (root/'collection_repair_plan_v887.json').symlink_to(outside)
            lib=SimpleNamespace(LOCK=threading.RLock(), _atomic_write=lambda *args: None)
            with self.assertRaises(ValueError):
                write_private_plan(report(), SUPPORTED, root, lib)
            self.assertEqual(outside.read_bytes(), b'do-not-touch')


if __name__ == '__main__':
    unittest.main()
