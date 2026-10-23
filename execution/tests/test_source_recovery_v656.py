"""Do not lose verified discovery identities on outages or starve rotating accounts."""
import datetime as dt
import math
import unittest
from unittest.mock import patch
import social_event_discovery as social
from execution import official_social_discovery as scoped
from execution.tests.test_source_collection_v655 import account

NOW=dt.datetime.now(dt.timezone.utc)
PAGE=('포켓몬 카드','KR','https://pokemonkorea.co.kr/news/2')
OTHER=('원피스 카드','KR','https://onepiece-cardgame.kr/')

def established(**changes):
    return {**account(), 'manual':False, 'verified_via_official_site':PAGE[2],
            'verified_at':(NOW-dt.timedelta(days=7)).isoformat(),**changes}

class RegistryRecoveryTests(unittest.TestCase):
    def refresh(self, rows, outcome):
        current={'accounts':rows,'watch_accounts':[{'trusted':False,'username':'fan'}]}
        with patch.object(social,'load_registry',return_value=current),patch.object(social,'OFFICIAL_DISCOVERY_PAGES',(PAGE,OTHER)),patch.object(social,'_fetch_official_page',side_effect=outcome),patch.object(social,'atomic_write_json') as write:
            result,errors=social.refresh_registry(force=True)
        write.assert_called_once();self.assertEqual(result,write.call_args.args[1])
        return result,errors
    def test_failed_exact_source_preserves_identity_without_renewing_verification(self):
        old=established()
        result,errors=self.refresh([old],lambda *page:([], 'HTTP 500') if page==PAGE else ([],None))
        self.assertEqual(1,result['retained_account_count']);self.assertEqual(1,len(errors))
        row=result['accounts'][0];self.assertEqual(old['verified_at'],row['verified_at'])
        self.assertEqual('DEFERRED',row['registry_refresh_state']);self.assertTrue(row['trusted'])
        self.assertEqual(1,scoped.select_accounts(result,NOW.timestamp())[1])
    def test_successful_page_without_account_link_does_not_keep_removed_identity(self):
        result,errors=self.refresh([established()],lambda *page:([],None))
        self.assertEqual([],result['accounts']);self.assertEqual(0,result['retained_account_count']);self.assertEqual([],errors)
    def test_failure_of_another_game_cannot_retain_this_identity(self):
        result,_=self.refresh([established()],lambda *page:([], 'offline') if page==OTHER else ([],None))
        self.assertEqual([],result['accounts'])
    def test_old_future_naive_and_missing_verification_are_not_retained(self):
        stamps=[(NOW-dt.timedelta(days=31)).isoformat(),(NOW+dt.timedelta(days=1)).isoformat(),NOW.replace(tzinfo=None).isoformat(),None,'invalid']
        for stamp in stamps:
            with self.subTest(stamp=stamp):
                self.assertEqual([],social._retained_registry_accounts({'accounts':[established(verified_at=stamp)]},[PAGE]))
    def test_untrusted_mismatching_or_unsafe_profile_is_not_retained(self):
        changes=[{'trusted':False},{'username':'spoof'}, {'platform':'x'}, {'profile_url':'http://instagram.com/pokemon_korea_official/'},{'profile_url':'https://127.0.0.1/profile'},{'verified_via_official_site':'https://evil.example/news/2'}, {'game':'원피스 카드'}, {'discovery_page_url':OTHER[2]}]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual([],social._retained_registry_accounts({'accounts':[established(**change)]},[PAGE]))
    def test_redirected_discovery_page_uses_recorded_input_and_scoped_evidence(self):
        row=established(discovery_page_url=PAGE[2],verified_via_official_site='https://www.pokemonkorea.co.kr/')
        self.assertEqual(1,len(social._retained_registry_accounts({'accounts':[row]},[PAGE])))
        row['verified_via_official_site']='https://onepiece-cardgame.kr/'
        self.assertEqual([],social._retained_registry_accounts({'accounts':[row]},[PAGE]))
    def test_new_confirmation_supersedes_retained_row_and_clears_deferred_marker(self):
        old=established();new={**old,'verified_at':NOW.isoformat()}
        result,_=self.refresh([old],lambda *page:([new],None) if page==PAGE else ([], 'offline'))
        self.assertEqual([new],result['accounts']);self.assertEqual(0,result['retained_account_count'])
    def test_manual_reviewed_accounts_and_untrusted_watchers_are_preserved(self):
        manual={**account(),'manual':True}
        result,_=self.refresh([manual],lambda *page:([], 'offline'))
        self.assertEqual([manual],result['accounts']);self.assertFalse(result['watch_accounts'][0]['trusted'])
    def test_page_exception_is_isolated_and_keeps_other_page_results(self):
        old=established();new=account('ONEPIECE_tcg_KR','원피스 카드',platform='x')
        def fetch(*page):
            if page==PAGE:raise RuntimeError('connection interrupted')
            return [new],None
        result,errors=self.refresh([old],fetch)
        self.assertEqual(2,len(result['accounts']));self.assertEqual(1,len(errors))
    def test_degraded_registry_retries_after_six_hours_without_waiting_one_week(self):
        good={'updated_at':(NOW-dt.timedelta(hours=7)).isoformat()}
        self.assertTrue(social._registry_fresh(good))
        self.assertFalse(social._registry_fresh({**good,'discovery_errors':['offline']}))
        self.assertTrue(social._registry_fresh({'updated_at':(NOW-dt.timedelta(hours=1)).isoformat(),'discovery_errors':['offline']}))
        self.assertFalse(social._registry_fresh({'updated_at':(NOW+dt.timedelta(days=1)).isoformat()}))
    def test_repeated_outages_never_extend_original_verification_age(self):
        old=established(verified_at=(NOW-dt.timedelta(days=29)).isoformat())
        retained=social._retained_registry_accounts({'accounts':[old]},[PAGE])[0]
        self.assertEqual(old['verified_at'],retained['verified_at'])
        retained['verified_at']=(NOW-dt.timedelta(days=31)).isoformat()
        self.assertEqual([],social._retained_registry_accounts({'accounts':[retained]},[PAGE]))

class FairRotationTests(unittest.TestCase):
    def test_matching_group_account_periods_cannot_starve_any_account(self):
        rows=[account(f'fixture{g}_{r}_{i}',game,region) for g,game in enumerate(social.GAMES) for r,region in enumerate(social.REGION_LANG) for i in range(9)]
        seen=set()
        for slot in range(math.ceil(len(rows)/scoped.MAX_ACCOUNTS)):
            selected,total=scoped.select_accounts({'accounts':rows},slot*21600)
            self.assertEqual(81,total);self.assertLessEqual(len(selected),6)
            self.assertEqual(len(selected),len({a['username'] for a in selected}))
            seen.update(a['username'] for a in selected)
        self.assertEqual({a['username'] for a in rows},seen)
    def test_current_registry_is_fully_visited_in_the_minimum_bounded_cycles(self):
        registry=social.load_registry();_,total=scoped.select_accounts(registry,NOW.timestamp())
        self.assertGreater(total,0);seen=set();slot=int(NOW.timestamp()//21600)
        for index in range(math.ceil(total/scoped.MAX_ACCOUNTS)):
            rows,_=scoped.select_accounts(registry,(slot+index)*21600)
            seen.update((a['game'],a['region'],a['platform'],a['username'].casefold()) for a in rows)
        self.assertEqual(total,len(seen))

if __name__=='__main__':unittest.main()
