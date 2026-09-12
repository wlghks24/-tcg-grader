import copy
import unittest
from unittest.mock import Mock, patch
import grading_company_watch as watch
import auto_repair_engine as repair
from test_grading_watch_integration_v220 import GradingWatchIntegrationV220Tests

class ProvenanceTests(unittest.TestCase):
    def test_nested_external_urls_rejected(self):
        for field in ('announcements', 'history', 'recent_changes'):
            data = GradingWatchIntegrationV220Tests()._snapshot()
            data[field] = [{'url': 'https://example.com/fake', 'verified_official_source': True}]
            self.assertFalse(repair._valid_project_payload('grading_company_updates.json', data))

    def test_credentials_ports_and_invalid_ports_rejected(self):
        for url in ('https://user@www.psacard.com/', 'https://www.psacard.com:8443/', 'https://www.psacard.com:bad/'):
            self.assertFalse(watch._source_host_allowed(url))
            self.assertEqual([], watch.parse_services('PSA', 'US', 'USD', 'Standard $100', url))

    def test_tainted_last_good_is_not_promoted(self):
        spec = watch.WATCH_SOURCES['PSA'][0]
        previous = {'sources': {spec['id']: {'url': 'https://example.com/fake', 'verified_official_source': True, 'signal_fingerprint': 'old', 'services': [{'fee': 1}]}}, 'announcements': [{'url': 'https://example.com/fake', 'title': 'fake'}]}
        with patch.object(watch, 'WATCH_SOURCES', {'PSA': (spec,)}):
            data = watch.collect(previous, fetcher=Mock(side_effect=OSError('offline')))
        self.assertFalse(data['sources'][spec['id']]['verified_official_source'])
        self.assertEqual([], data['sources'][spec['id']]['services'])
        self.assertEqual([], data['announcements'])
        self.assertNotEqual('정상', data['collection_status'])
        self.assertEqual(1, len(data['collection_errors']))
        self.assertIn(spec['id'], data['collection_errors'][0])
        self.assertEqual(data['checked_at'], data['updated_at'])

if __name__ == '__main__':
    unittest.main()
