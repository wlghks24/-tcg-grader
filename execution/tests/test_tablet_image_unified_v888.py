"""Real private-index roundtrip, exact identity, quota and compression regressions."""
import copy
import io
import threading
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library
from execution import tablet_image_unified_v888 as unified
from execution import tablet_image_recheck_review_v887 as adapter
from execution.tests.test_image_metadata_enrichment import ImageMetadataTests
from execution.tests.test_tablet_image_reciprocity_v887 import report, IMG, SRC


class RepairTests(ImageMetadataTests):
    def repair(self, detail, *, now=1000, state=None):
        state = auto._state(self.store) if state is None else state
        budget = auto.policy.Budget(state, lambda: None, clock=lambda: now)
        auto._BUDGET_CONTEXT.current = budget
        try:
            with patch.object(auto, 'fetch_json', return_value=detail) as fetch:
                result = unified.repair_existing(auto, self.store, state,
                    library._load(self.store)['items'], budget, threading.Event(), clock=lambda: now)
            return result, fetch, state
        finally:
            del auto._BUDGET_CONTEXT.current

    def test_set_only_photo_is_repaired_without_downloading_or_rewriting_photo(self):
        saved = self.save({'set_code': 'sv1s'})
        before = library.get_image(saved['id'])
        result, fetch, state = self.repair({'id': 'sv1s-001', 'localId': '001', 'set': {'id': 'sv1s'}})
        self.assertEqual((1, 1, 0), (result['attempted'], result['enriched'], result['pending']))
        fetch.assert_called_once_with('https://api.tcgdex.net/v2/ja/cards/sv1s-001')
        self.assertEqual(before, library.get_image(saved['id']))
        metadata = library.list_images()['items'][0]['card_metadata']
        self.assertEqual('001', metadata['card_number'])
        self.assertEqual('ja', metadata['language'])
        self.assertEqual({}, state['metadata_repairs'])

    def test_wrong_card_conflict_and_partial_detail_keep_retry_delay(self):
        saved = self.save({'set_code': 'sv1s'})
        for detail in ({'id': 'wrong'}, {'id': 'sv1s-001', 'set': {'id': 'other'}},
                       {'id': 'sv1s-001', 'set': {'id': 'sv1s'}}):
            with self.subTest(detail=detail):
                result, _, state = self.repair(detail)
                self.assertEqual(1, result['pending'])
                self.assertIn(saved['id'], state['metadata_repairs'])
                waiting, fetch, _ = self.repair(detail, state=state, now=1001)
                self.assertEqual(0, waiting['attempted'])
                fetch.assert_not_called()
        self.assertEqual('sv1s', library.list_images()['items'][0]['card_metadata']['set_code'])

    def test_no_budget_context_no_network_or_changes(self):
        self.save({})
        with self.assertRaises(ValueError), patch.object(auto, 'fetch_json') as fetch:
            unified.repair_existing(auto, self.store, {}, [], object(), threading.Event())
        fetch.assert_not_called()

    def test_tampered_photo_cannot_receive_metadata(self):
        self.save({})
        path = next((self.store / 'images').iterdir())
        path.write_bytes(path.read_bytes() + b'tamper')
        result, fetch, _ = self.repair({})
        self.assertEqual(0, result['attempted'])
        fetch.assert_not_called()

    def test_shared_real_quota_defers_before_http(self):
        self.save({})
        import time
        state = auto._state(self.store)
        state['image_budget_events'] = [{'at': time.time(), 'kind': 'request', 'provider': 'TCGdex', 'bytes': 0} for _ in range(80)]
        budget = auto.policy.Budget(state, lambda: None)
        auto._BUDGET_CONTEXT.current = budget
        try:
            with patch.object(auto.urllib.request, 'build_opener') as opener:
                result = unified.repair_existing(auto, self.store, state,
                    library._load(self.store)['items'], budget, threading.Event())
            opener.assert_not_called()
            self.assertTrue(result['deferred'])
            self.assertEqual(0, result['enriched'])
        finally:
            del auto._BUDGET_CONTEXT.current

    def test_actual_repaired_photo_is_immediately_available_in_unified_feed(self):
        saved = self.save({'set_code': 'sv1s'})
        self.repair({'id': 'sv1s-001', 'localId': '001', 'set': {'id': 'sv1s'}})
        result = adapter.read_live(self.repo)
        row = next(x for x in result['unified_catalog'] if x['image_id'] == saved['id'])
        self.assertEqual('001', row['card_metadata']['card_number'])
        page = unified.export_html(result)
        self.assertIn('data:image/', page)
        self.assertIn('001', page)


def paired_report():
    r = report(matches=[{'id': IMG, 'source_record_id': SRC, 'match': 'CODE_MATCH',
                         'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD'}])
    for row in r['local_catalog'] + r['source_catalog']:
        row.update(name='Test <script>alert(1)</script>', product_codes=['SV1S001'],
                   language='ja', printing='Normal', set_code='sv1s')
    r['local_catalog'][0]['card_metadata'] = {'card_number': '001', 'language': 'ja'}
    return r


class UnifiedFeedTests(unittest.TestCase):
    def test_verified_photo_and_product_are_one_entity_with_reciprocal_fields(self):
        r = paired_report()
        before = copy.deepcopy(r)
        rows = unified.unified_feed(r)
        self.assertEqual(1, len(rows))
        self.assertEqual('VERIFIED_PAIR', rows[0]['link_status'])
        self.assertEqual('sv1s', rows[0]['card_metadata']['set_code'])
        self.assertEqual('001', rows[0]['catalog_overlay']['card_number'])
        self.assertEqual('verified_catalog', rows[0]['metadata_provenance']['set_code'])
        self.assertEqual(r, before)

    def test_incomplete_or_wrong_country_printing_and_code_never_merge(self):
        for field, value in [('region', 'US'), ('printing', 'Foil'), ('product_codes', ['OTHER']), ('source_health', 'UNVERIFIED')]:
            r = paired_report()
            r['source_catalog'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                unified.unified_feed(r)

    def test_unmatched_photo_and_catalog_use_one_feed_without_forced_merge(self):
        r = paired_report()
        r['catalog_matches'] = []
        rows = unified.unified_feed(r)
        self.assertEqual(2, len(rows))
        self.assertEqual({'NEEDS_EXACT_IDENTITY', 'NEEDS_IMAGE'}, {x['link_status'] for x in rows})

    def test_duplicate_link_rejected_and_html_escapes_external_names(self):
        r = paired_report()
        with patch.object(library, 'get_image', side_effect=ValueError('missing')):
            page = unified.export_html(r)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert(1)</script>', page)
        r['catalog_matches'] *= 2
        with self.assertRaises(ValueError):
            unified.unified_feed(r)

    def test_conflicting_information_is_not_silently_replaced(self):
        r = paired_report()
        r['source_catalog'][0]['card_metadata'] = {'card_number': '002'}
        rows = unified.unified_feed(r)
        self.assertEqual('001', rows[0]['card_metadata']['card_number'])
        self.assertEqual('METADATA_CONFLICT', rows[0]['link_status'])
        self.assertIsNone(rows[0]['catalog_overlay'])


class CompressionTests(unittest.TestCase):
    def fixture(self, size=(600, 840), transparent=False):
        image = Image.new('RGBA' if transparent else 'RGB', size, (200, 200, 200, 0) if transparent else 'white')
        draw = ImageDraw.Draw(image)
        for y in range(20, size[1] - 20, 25):
            draw.text((20, y), 'SV1S-001 / HP 100 / 1234567890', fill='black')
        buf = io.BytesIO()
        image.save(buf, format='PNG', compress_level=0)
        return buf.getvalue()

    def test_compression_is_smaller_full_resolution_and_original_unchanged(self):
        data = self.fixture()
        original = bytes(data)
        compressed, stats = unified.display_compression(data)
        self.assertLess(len(compressed), len(data) // 3)
        self.assertEqual(original, data)
        self.assertFalse(stats['resized'])
        self.assertTrue(stats['original_preserved'])
        self.assertTrue(stats['readability_review_required'])
        with Image.open(io.BytesIO(compressed)) as image:
            self.assertEqual((600, 840), image.size)
        self.assertGreaterEqual(stats['psnr_db'], 38)

    def test_small_and_transparent_photos_have_exact_pixel_preservation(self):
        for data in (self.fixture((200, 300)), self.fixture(transparent=True)):
            compressed, stats = unified.display_compression(data)
            with Image.open(io.BytesIO(data)) as left, Image.open(io.BytesIO(compressed)) as right:
                self.assertEqual(left.convert('RGBA').tobytes(), right.convert('RGBA').tobytes())
            self.assertIn(stats['encoding'], ('source', 'webp-lossless'))

    def test_invalid_and_oversized_input_rejected(self):
        for data in (b'', b'x' * (library.MAX_IMAGE_BYTES + 1), 'not bytes'):
            with self.assertRaises(ValueError):
                unified.display_compression(data)


class DisplayCacheTests(ImageMetadataTests):
    def test_cache_reuses_compressed_photo_and_keeps_original(self):
        self.png = CompressionTests().fixture()
        saved = self.save({})
        before = library.get_image(saved['id'])
        first, stats = unified.cached_display(saved['id'])
        self.assertFalse(stats['cache_hit'])
        with patch.object(unified, 'display_compression', side_effect=AssertionError('recompressed')):
            second, stats = unified.cached_display(saved['id'])
        self.assertTrue(stats['cache_hit'])
        self.assertEqual(first, second)
        self.assertEqual(before, library.get_image(saved['id']))

    def test_corrupt_cache_is_rebuilt_and_deleted_photo_not_resurrected(self):
        self.png = CompressionTests().fixture()
        saved = self.save({})
        first, _ = unified.cached_display(saved['id'])
        target = next((self.store / 'display_cache_v888').glob('*.view'))
        target.write_bytes(b'corrupted')
        second, stats = unified.cached_display(saved['id'])
        self.assertFalse(stats['cache_hit'])
        self.assertEqual(first, second)
        library.delete_image(saved['id'])
        with self.assertRaises(FileNotFoundError):
            unified.cached_display(saved['id'])

    def test_cache_directory_symlink_is_rejected(self):
        saved = self.save({})
        (self.store / 'display_cache_v888').symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            unified.cached_display(saved['id'])

    def test_damaged_measurements_rebuild_cache_instead_of_breaking_export(self):
        import json
        self.png = CompressionTests().fixture()
        saved = self.save({})
        unified.cached_display(saved['id'])
        path = next((self.store / 'display_cache_v888').glob('*.json'))
        meta = json.loads(path.read_text())
        meta['stats'] = {}
        path.write_text(json.dumps(meta))
        _, stats = unified.cached_display(saved['id'])
        self.assertFalse(stats['cache_hit'])
        self.assertEqual(600, stats['width'])
