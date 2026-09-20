#!/usr/bin/env python3
from __future__ import annotations

import threading
import time
import unittest
from collections import Counter, defaultdict
from unittest import mock
from urllib.parse import urlsplit

import update_market_prices_parallel_v260 as p


class MarketPricePrefetchV260Tests(unittest.TestCase):
    def test_cross_host_overlap_never_overlaps_same_host(self):
        lock = threading.Lock()
        active_by_host = defaultdict(int)
        max_by_host = defaultdict(int)
        total_active = 0
        max_total = 0

        def fetch(url):
            nonlocal total_active, max_total
            host = (urlsplit(url).hostname or "").lower()
            with lock:
                active_by_host[host] += 1
                max_by_host[host] = max(max_by_host[host], active_by_host[host])
                total_active += 1
                max_total = max(max_total, total_active)
            time.sleep(0.025)
            with lock:
                active_by_host[host] -= 1
                total_active -= 1
            return f"body:{url}"

        cache, stats = p.prefetch(fetcher=fetch, max_workers=4)
        self.assertEqual(len(cache), len(p.FIXED_URLS))
        self.assertEqual(stats["network_calls"], len(p.FIXED_URLS))
        self.assertTrue(all(value == 1 for value in max_by_host.values()))
        self.assertGreaterEqual(max_total, 2)
        self.assertEqual(stats["same_host_parallelism"], 1)

    def test_run_fetches_each_fixed_url_once_then_reuses_memory_cache(self):
        calls = Counter()

        def fetch(url):
            calls[url] += 1
            return f"payload:{url}"

        def canonical_main():
            # Canonical collector should see identical fetch semantics, but no second
            # network call for the fixed URLs preloaded by the wrapper.
            for url in p.FIXED_URLS:
                self.assertEqual(p.base.fetch(url), f"payload:{url}")
            return {"entries": {}}

        saved = []
        with mock.patch.object(p.base, "fetch", side_effect=fetch), \
             mock.patch.object(p.base, "main", side_effect=canonical_main), \
             mock.patch.object(p.base, "atomic_save", side_effect=lambda db: saved.append(dict(db))):
            db = p.run()

        self.assertEqual(sum(calls.values()), len(p.FIXED_URLS))
        self.assertTrue(all(count == 1 for count in calls.values()))
        perf = db["market_collection_performance"]
        self.assertEqual(perf["network_calls"], len(p.FIXED_URLS))
        self.assertEqual(perf["cache_hits"], len(p.FIXED_URLS))
        self.assertEqual(perf["duplicate_network_requests_added"], 0)
        self.assertEqual(perf["same_host_parallelism"], 1)
        self.assertTrue(saved)

    def test_prefetch_failure_is_preserved_not_converted_to_fake_data(self):
        broken = p.FIXED_URLS[0]

        def fetch(url):
            if url == broken:
                raise TimeoutError("provider timeout")
            return "ok"

        cache, _stats = p.prefetch(fetcher=fetch, max_workers=4)
        self.assertFalse(cache[broken]["ok"])
        self.assertIsInstance(cache[broken]["error"], TimeoutError)
        self.assertIsNone(cache[broken]["payload"])


if __name__ == "__main__":
    unittest.main()
