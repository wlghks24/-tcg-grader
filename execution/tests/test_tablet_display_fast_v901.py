"""Temporary PNG/WebP fixtures and fake library only; no HTTP/device/runtime."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from execution import tablet_display_fast_v901 as fast

IMAGE_ID = 'a' * 32


def photo_bytes(*, size=(80, 120), color=(20, 80, 140), fmt='PNG', orientation=None):
    output = io.BytesIO()
    image = Image.new('RGB', size, color)
    if fmt == 'PNG':
        # A valid deliberately large fixture permits a much smaller cached view.
        image.save(output, format=fmt, compress_level=0)
    elif orientation is not None:
        exif = Image.Exif(); exif[274] = orientation
        image.save(output, format=fmt, exif=exif)
    else:
        image.save(output, format=fmt, lossless=True)
    return output.getvalue()


class FakeLibrary:
    ID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
    MAX_IMAGE_BYTES = 5 * 1024 * 1024

    def __init__(self, root, raw):
        self.root = root
        self.LOCK = threading.RLock()
        self.source = root / 'original.png'
        self.source.write_bytes(raw)
        self.expected = hashlib.sha256(raw).hexdigest()
        self.mime = 'image/png'
        self.calls = 0
        self.before_second = None

    def storage_root(self):
        return self.root

    def get_image(self, ident):
        if ident != IMAGE_ID:
            raise FileNotFoundError('unknown fixture')
        self.calls += 1
        if self.calls == 2 and self.before_second:
            self.before_second()
        raw = self.source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.expected:
            raise ValueError('source integrity failure')
        return self.mime, raw


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = photo_bytes()
        self.library = FakeLibrary(self.root, self.original)
        self.mock_library = patch.object(fast, 'library', self.library)
        self.mock_library.start(); self.addCleanup(self.mock_library.stop)
        self.source_sha = hashlib.sha256(self.original).hexdigest()
        self.key = hashlib.sha256(('v888-view-1:' + self.source_sha).encode()).hexdigest()
        self.cache = self.root / 'display_cache_v888'
        self.meta_path = self.cache / (self.key + '.json')
        self.view_path = self.cache / (self.key + '.view')

    def cache_view(self, *, view=None, stats=None):
        self.cache.mkdir(exist_ok=True)
        view = photo_bytes(fmt='WEBP') if view is None else view
        with Image.open(io.BytesIO(view)) as checked:
            width, height = checked.size
        values = {'source_bytes': len(self.original), 'stored_bytes': len(view),
                  'width': width, 'height': height, 'encoding': 'webp-lossless',
                  'original_preserved': True, 'resized': False,
                  'readability_review_required': True, 'psnr_db': 99.0}
        if stats:
            values.update(stats)
        meta = {'source_sha256': self.source_sha, 'view_sha256': hashlib.sha256(view).hexdigest(),
                'stats': values}
        self.view_path.write_bytes(view)
        self.meta_path.write_text(json.dumps(meta))
        return view

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file() and not path.is_symlink()}

    def assert_original(self):
        actual, stats = fast.read_display(IMAGE_ID)
        self.assertEqual(self.original, actual)
        self.assertFalse(stats['cache_hit'])
        self.assertTrue(stats['original_preserved'])
        self.assertTrue(stats['compression_deferred'])
        return stats

    def test_miss_returns_original_without_creating_any_cache(self):
        before = self.snapshot()
        self.assert_original()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.cache.exists())
        self.assertEqual(2, self.library.calls)

    def test_valid_smaller_cache_returns_view_and_preserves_source_and_files(self):
        view = self.cache_view()
        before = self.snapshot()
        actual, stats = fast.read_display(IMAGE_ID)
        self.assertEqual(view, actual)
        self.assertTrue(stats['cache_hit'])
        self.assertFalse(stats['compression_deferred'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(2, self.library.calls)

    def test_http_path_never_encodes_even_when_cache_absent_or_invalid(self):
        for cache in (False, True):
            if cache:
                self.cache_view()
                self.meta_path.write_bytes(b'broken')
            with patch.object(Image.Image, 'save', side_effect=AssertionError('encoding forbidden')):
                self.assert_original()

    def test_hash_corruption_and_missing_half_cache_fall_back_without_repair(self):
        for corrupt in ('source_sha256', 'view_sha256', 'view', 'meta', 'missing_view', 'missing_meta'):
            with self.subTest(corrupt=corrupt):
                self.library.calls = 0
                self.cache_view()
                if corrupt in ('source_sha256', 'view_sha256'):
                    meta = json.loads(self.meta_path.read_text()); meta[corrupt] = '0' * 64
                    self.meta_path.write_text(json.dumps(meta))
                elif corrupt == 'view': self.view_path.write_bytes(b'corrupt')
                elif corrupt == 'meta': self.meta_path.write_text('[]')
                elif corrupt == 'missing_view': self.view_path.unlink()
                else: self.meta_path.unlink()
                before = self.snapshot()
                self.assert_original()
                self.assertEqual(before, self.snapshot())

    def test_stats_require_exact_integer_lengths_dimensions_and_preservation_flags(self):
        invalid = [{'source_bytes': True}, {'stored_bytes': 1}, {'width': True}, {'height': 119},
                   {'original_preserved': 1}, {'resized': 0}, {'resized': True}]
        for stats in invalid:
            with self.subTest(stats=stats):
                self.library.calls = 0
                self.cache_view(stats=stats)
                self.assert_original()

    def test_forged_self_consistent_resized_view_cannot_pass(self):
        self.cache_view(view=photo_bytes(size=(40, 60), fmt='WEBP'))
        self.assert_original()

    def test_cache_must_be_strictly_smaller_than_original(self):
        self.cache_view(view=self.original)
        self.assert_original()

    def test_duplicate_keys_nan_and_oversized_metadata_fall_back(self):
        for payload in (b'{"stats":{},"stats":{}}', b'{"stats":{"psnr_db":NaN}}', b' ' * 4097):
            self.library.calls = 0
            self.cache_view(); self.meta_path.write_bytes(payload)
            self.assert_original()

    def test_oversized_cache_file_is_not_loaded_or_rewritten(self):
        self.cache_view()
        with self.view_path.open('wb') as stream:
            stream.truncate(self.library.MAX_IMAGE_BYTES + 1)
        self.assert_original()
        self.assertEqual(self.library.MAX_IMAGE_BYTES + 1, self.view_path.stat().st_size)

    def test_cache_file_and_directory_symlinks_fall_back_without_following(self):
        self.cache_view()
        external = self.root / 'external-secret'; external.write_bytes(b'private')
        for path in (self.view_path, self.meta_path):
            original = path.read_bytes()
            path.unlink(); path.symlink_to(external)
            self.library.calls = 0
            self.assert_original()
            self.assertEqual(b'private', external.read_bytes())
            path.unlink(); path.write_bytes(original)
        moved = self.root / 'moved-cache'; self.cache.rename(moved); self.cache.symlink_to(moved, target_is_directory=True)
        self.library.calls = 0
        self.assert_original()

    def test_deletion_before_read_is_not_replaced_by_cached_view(self):
        self.cache_view(); self.library.source.unlink()
        with self.assertRaises(FileNotFoundError): fast.read_display(IMAGE_ID)

    def test_deletion_during_read_prevents_both_cache_hit_and_original_fallback(self):
        for cache in (False, True):
            self.library.calls = 0; self.library.source.write_bytes(self.original)
            if cache: self.cache_view()
            self.library.before_second = self.library.source.unlink
            with self.assertRaises(FileNotFoundError): fast.read_display(IMAGE_ID)

    def test_legitimate_source_change_during_read_cannot_return_old_source_or_view(self):
        self.cache_view()
        def change():
            current = photo_bytes(color=(70, 80, 90))
            self.library.source.write_bytes(current)
            self.library.expected = hashlib.sha256(current).hexdigest()
        self.library.before_second = change
        with self.assertRaisesRegex(ValueError, '변경'): fast.read_display(IMAGE_ID)

    def test_integrity_failure_before_or_during_read_never_revives_cache(self):
        self.cache_view()
        self.library.source.write_bytes(b'bad original')
        with self.assertRaisesRegex(ValueError, 'integrity'): fast.read_display(IMAGE_ID)
        self.library.source.write_bytes(self.original); self.library.calls = 0
        self.library.before_second = lambda: self.library.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity'): fast.read_display(IMAGE_ID)

    def test_unreadable_original_is_not_replaced_by_cache(self):
        self.cache_view()
        self.library.source.write_bytes(b'not an image')
        self.library.expected = hashlib.sha256(b'not an image').hexdigest()
        with self.assertRaises(ValueError): fast.read_display(IMAGE_ID)

    def test_source_mime_must_match_decoded_format(self):
        self.library.mime = 'image/jpeg'
        with self.assertRaises(ValueError): fast.read_display(IMAGE_ID)

    def test_source_and_view_pixel_limits_fail_before_expensive_decode(self):
        with patch.object(fast, 'MAX_PIXELS', 100):
            with self.assertRaisesRegex(ValueError, '픽셀'): fast.read_display(IMAGE_ID)
        self.cache_view()
        source_shape = fast._shape
        def check(data, **kwargs):
            if data != self.original:
                with patch.object(fast, 'MAX_PIXELS', 100):
                    return source_shape(data, **kwargs)
            return source_shape(data, **kwargs)
        with patch.object(fast, '_shape', side_effect=check):
            self.assert_original()

    def test_multiframe_original_and_cache_are_rejected(self):
        def animated(fmt):
            output = io.BytesIO()
            Image.new('RGB', (80, 120), 'red').save(output, format=fmt, save_all=True,
                append_images=[Image.new('RGB', (80, 120), 'blue')], duration=100)
            return output.getvalue()
        self.cache_view(view=animated('WEBP'))
        self.assert_original()
        source = animated('PNG')
        self.library.source.write_bytes(source); self.library.expected = hashlib.sha256(source).hexdigest()
        self.library.calls = 0
        with self.assertRaisesRegex(ValueError, '프레임'): fast.read_display(IMAGE_ID)

    def test_exif_rotated_source_matches_normalized_cached_dimensions(self):
        raw = photo_bytes(size=(80, 120), fmt='JPEG', orientation=6)
        self.library.source.write_bytes(raw); self.library.expected = hashlib.sha256(raw).hexdigest()
        self.library.mime = 'image/jpeg'
        self.original = raw; self.source_sha = self.library.expected
        self.key = hashlib.sha256(('v888-view-1:' + self.source_sha).encode()).hexdigest()
        self.meta_path = self.cache / (self.key + '.json'); self.view_path = self.cache / (self.key + '.view')
        view = self.cache_view(view=photo_bytes(size=(120, 80), fmt='WEBP'))
        actual, stats = fast.read_display(IMAGE_ID)
        self.assertEqual(view, actual)
        self.assertTrue(stats['cache_hit'])
        self.assertEqual((120, 80), (stats['width'], stats['height']))

    def test_invalid_identifier_is_refused_before_library_access(self):
        for ident in (None, [], '../private', IMAGE_ID + '/x'):
            with self.assertRaises(ValueError): fast.read_display(ident)
        self.assertEqual(0, self.library.calls)

    def test_simultaneous_requests_decode_at_most_two_images(self):
        lock, entered_two, release = threading.Lock(), threading.Event(), threading.Event()
        counters = {'active': 0, 'peak': 0, 'total': 0}

        class Opened:
            format, width, height, n_frames, size = 'PNG', 80, 120, 1, (80, 120)
            def __enter__(self):
                with lock:
                    counters['active'] += 1
                    counters['total'] += 1
                    counters['peak'] = max(counters['peak'], counters['active'])
                    if counters['active'] == 2:
                        entered_two.set()
                return self
            def __exit__(self, *args):
                with lock:
                    counters['active'] -= 1
            def load(self):
                if not release.wait(3):
                    raise AssertionError('test decode release timed out')

        with patch.object(fast.Image, 'open', side_effect=lambda _: Opened()) as opened:
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [pool.submit(fast._shape, self.original) for _ in range(6)]
                try:
                    self.assertTrue(entered_two.wait(2), 'two decode slots should start')
                    with lock:
                        self.assertEqual(2, counters['active'])
                    self.assertEqual(2, opened.call_count, 'remaining requests wait before Image.open')
                finally:
                    release.set()
                self.assertEqual([(80, 120, 'image/png')] * 6, [future.result(timeout=3) for future in futures])
        self.assertEqual({'active': 0, 'peak': 2, 'total': 6}, counters)


if __name__ == '__main__':
    unittest.main()
