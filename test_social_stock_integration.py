import json
import unittest
from pathlib import Path
from unittest import mock

import collection_job_contract as contract
import social_event_discovery as discovery

ROOT = Path(__file__).resolve().parent


class SocialStockIntegrationTests(unittest.TestCase):
    def test_official_and_watch_accounts_keep_separate_trust_roles(self):
        data=json.loads((ROOT/'social_source_registry.json').read_text(encoding='utf-8'))
        official={x.get('username'):x for x in data.get('accounts',[]) if isinstance(x,dict)}
        watch={x.get('username'):x for x in data.get('watch_accounts',[]) if isinstance(x,dict)}
        self.assertIn('pokemon_korea_official',official)
        self.assertTrue(official['pokemon_korea_official'].get('trusted'))
        self.assertNotIn('pokemon_korea_official',watch)
        for name in ('poke_vending_machine','ttosatda'):
            self.assertIn(name,watch); self.assertFalse(watch[name].get('trusted'))
            self.assertIn('stock',watch[name].get('role',''))

    def test_manual_user_evidence_survives_high_volume_candidate_cap_without_trust_promotion(self):
        manual = {
            'game': '포켓몬 카드', 'region': 'KR', 'category': 'collaboration',
            'title': 'manual-evidence-retention-probe', 'source': 'https://example.com/manual-evidence',
            'source_kind': 'instagram_user_evidence', 'confidence': 0.46,
            'manual_user_evidence': True, 'verified': False, 'official_account_verified': False,
        }
        noise = [
            {
                'game': '포켓몬 카드', 'region': 'KR', 'category': 'collaboration',
                'title': f'high-confidence-{idx}', 'source': f'https://example.com/high-{idx}',
                'source_kind': 'public_search', 'confidence': 0.99 - idx * 0.001,
                'verified': False, 'official_account_verified': False,
            }
            for idx in range(12)
        ]
        with mock.patch.object(discovery, 'candidate_limit', return_value=5):
            merged = discovery.merge_candidates(noise + [manual])
        row = next(x for x in merged if x.get('title') == manual['title'])
        self.assertTrue(row.get('manual_user_evidence'))
        self.assertFalse(row.get('verified'))
        self.assertFalse(row.get('official_account_verified'))
        self.assertLessEqual(len(merged), 6)

    def test_step5_runs_social_stock_inside_purchase_job_without_extra_job(self):
        text=(ROOT/'update_purchase_sources.py').read_text(encoding='utf-8')
        self.assertIn('social_stock_discovery.main()',text)

        purchase_job=("구매처·링크 보안 확인", "update_purchase_sources", "purchase_sources.json")
        self.assertEqual(contract.JOB_COUNT,8)
        self.assertIn(purchase_job,contract.COLLECTION_JOBS)
        self.assertFalse(any(str(row[0]).startswith('SNS 재고') for row in contract.COLLECTION_JOBS))

        auto=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        self.assertIn('from collection_job_contract import COLLECTION_JOBS',auto)
        self.assertIn('JOBS = COLLECTION_JOBS',auto)

    def test_live_purchase_merges_social_but_keeps_unverified_label(self):
        text=(ROOT/'purchase_intelligence.py').read_text(encoding='utf-8')
        self.assertIn('# v112-social-stock-merge',text)
        self.assertIn('official_stock\": False',text)
        self.assertIn('SNS 재고제보',text)


if __name__=='__main__':
    unittest.main()
