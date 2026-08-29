import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class SocialStockIntegrationTests(unittest.TestCase):
    def test_watch_accounts_are_untrusted_and_role_separated(self):
        data=json.loads((ROOT/'social_source_registry.json').read_text(encoding='utf-8'))
        by={x.get('username'):x for x in data.get('watch_accounts',[]) if isinstance(x,dict)}
        for name in ('pokemon_korea_official','poke_vending_machine','ttosatda'):
            self.assertIn(name,by); self.assertFalse(by[name].get('trusted'))
        self.assertIn('event',by['pokemon_korea_official'].get('role',''))
        self.assertIn('stock',by['poke_vending_machine'].get('role',''))

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
