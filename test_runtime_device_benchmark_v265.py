from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import performance_baseline_guard
import runtime_device_benchmark
import runtime_sre_metrics


class _EtagHandler(BaseHTTPRequestHandler):
    etag = '"fixture-v1"'
    body = b'fixture-body'

    def log_message(self, *_args):
        return

    def do_GET(self):
        if self.path == '/api/runtime-metrics':
            payload = json.dumps({
                'ok': True,
                'metrics': {
                    'http': {
                        'process_rss_bytes': 1024,
                    },
                },
            }).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.headers.get('If-None-Match') == self.etag:
            self.send_response(304)
            self.send_header('ETag', self.etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('ETag', self.etag)
        self.send_header('Content-Length', str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)


class RuntimeDeviceBenchmarkV265Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), _EtagHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_percentile_is_interpolated_and_bounded(self):
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(runtime_device_benchmark.percentile(values, 0.0), 1.0)
        self.assertEqual(runtime_device_benchmark.percentile(values, 1.0), 4.0)
        self.assertAlmostEqual(runtime_device_benchmark.percentile(values, 0.5), 2.5)

    def test_revalidation_probe_proves_304_without_body(self):
        result = runtime_device_benchmark.revalidation_probe(self.base, '/index.html', 2.0)
        self.assertTrue(result['etag_present'])
        self.assertEqual(result['revalidated_status'], 304)
        self.assertEqual(result['revalidated_bytes'], 0)
        self.assertTrue(result['body_transfer_saved'])

    def test_runtime_metrics_add_resource_observability_without_new_cardinality(self):
        metrics = runtime_sre_metrics.RuntimeMetrics()
        first = metrics.request_started()
        metrics.request_finished(first)
        snap = metrics.snapshot()
        self.assertEqual(snap['cardinality'], 'fixed')
        self.assertIn('process_rss_bytes', snap['http'])
        self.assertIn('process_cpu_percent_since_last_snapshot', snap['http'])
        self.assertIn('python_thread_count', snap['http'])
        self.assertIn('logical_cpu_count', snap['http'])
        self.assertGreaterEqual(snap['http']['python_thread_count'], 1)
        self.assertGreaterEqual(snap['http']['logical_cpu_count'], 0)

    def test_baseline_guard_detects_latency_regression(self):
        baseline = {
            'schema_version': 1,
            'system': {'machine': 'same'},
            'concurrent_health_probe': {'latency_ms': {'p95': 10, 'p99': 12}, 'error_rate': 0},
            'runtime_metrics_after': {'metrics': {'http': {'process_rss_bytes': 1000}}},
            'index_revalidation': {'body_transfer_saved': True},
            'dashboard_revalidation': {'body_transfer_saved': True},
        }
        candidate = {
            'schema_version': 1,
            'system': {'machine': 'same'},
            'concurrent_health_probe': {'latency_ms': {'p95': 14, 'p99': 16}, 'error_rate': 0},
            'runtime_metrics_after': {'metrics': {'http': {'process_rss_bytes': 1000}}},
            'index_revalidation': {'body_transfer_saved': True},
            'dashboard_revalidation': {'body_transfer_saved': True},
        }
        result = performance_baseline_guard.compare(baseline, candidate)
        self.assertFalse(result['ok'])
        self.assertIn('p95_ms', {row['metric'] for row in result['failures']})

    def test_baseline_guard_records_new_304_as_improvement(self):
        baseline = {
            'schema_version': 1,
            'system': {'machine': 'same'},
            'concurrent_health_probe': {'latency_ms': {'p95': 10, 'p99': 12}, 'error_rate': 0},
            'runtime_metrics_after': {'metrics': {'http': {'process_rss_bytes': 1000}}},
            'index_revalidation': {'body_transfer_saved': False},
            'dashboard_revalidation': {'body_transfer_saved': False},
        }
        candidate = {
            'schema_version': 1,
            'system': {'machine': 'same'},
            'concurrent_health_probe': {'latency_ms': {'p95': 9, 'p99': 11}, 'error_rate': 0},
            'runtime_metrics_after': {'metrics': {'http': {'process_rss_bytes': 1000}}},
            'index_revalidation': {'body_transfer_saved': True},
            'dashboard_revalidation': {'body_transfer_saved': True},
        }
        result = performance_baseline_guard.compare(baseline, candidate)
        self.assertTrue(result['ok'])
        self.assertEqual({row['metric'] for row in result['notes'] if row['status'] == 'improved-to-304'}, {'index_revalidation', 'dashboard_revalidation'})


if __name__ == '__main__':
    unittest.main()
