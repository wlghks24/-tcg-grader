import json
import unittest
from pathlib import Path

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

    def test_pokopia_user_evidence_is_visible_but_unverified(self):
        data=json.loads((ROOT/'social_event_candidates.json').read_text(encoding='utf-8'))
        row=next(x for x in data.get('items',[]) if 'Pokopia' in str(x.get('title','')))
        self.assertEqual(row.get('dates'),['2026-09-12','2026-09-29'])
        self.assertEqual(row.get('location'),'무신사 메가스토어 성수')
        self.assertTrue(row.get('manual_user_evidence'))
        self.assertFalse(row.get('verified'))
        self.assertFalse(row.get('official_account_verified'))

    def test_step5_runs_social_stock_without_adding_job8(self):
        text=(ROOT/'update_purchase_sources.py').read_text(encoding='utf-8')
        self.assertIn('social_stock_discovery.main()',text)
        auto=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        self.assertIn('("구매처·링크 보안 확인", "update_purchase_sources", "purchase_sources.json")',auto)
        self.assertNotIn('("SNS 재고',auto)

    def test_live_purchase_merges_social_but_keeps_unverified_label(self):
        text=(ROOT/'purchase_intelligence.py').read_text(encoding='utf-8')
        self.assertIn('# v112-social-stock-merge',text)
        self.assertIn('official_stock": False',text)
        self.assertIn('SNS 재고제보',text)


if __name__=='__main__':
    unittest.main()
