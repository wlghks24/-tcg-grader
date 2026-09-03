import unittest
import urllib.error
from email.message import Message
from pathlib import Path
import multi_route_event_discovery as routes


class MultiRouteEventDiscoveryTests(unittest.TestCase):
    def test_every_game_region_has_official_route(self):
        expected={(game,region) for game in routes.GAMES for region in routes.REGIONS}
        self.assertTrue(expected.issubset(set(routes.OFFICIAL_ROUTES)))
        for key in expected:
            self.assertGreaterEqual(len(routes.OFFICIAL_ROUTES[key]),1)
            self.assertTrue(all(url.startswith('https://') for url in routes.OFFICIAL_ROUTES[key]))

    def test_query_families_cover_major_information_types(self):
        for lang in ('ko','ja','en'):
            self.assertTrue({'release','reprint','event','tournament','popup','promo','collab','movie','stock'}.issubset(routes.QUERY_FAMILIES[lang]))

    def test_independent_provider_routes_exist(self):
        # Search route names are intentionally distinct so one provider outage
        # does not remove all public discovery paths.
        text=Path(routes.__file__).read_text(encoding='utf-8')
        for marker in ('bing_topic','bing_official','bing_partner','official_anchor','ddg_fallback'):
            self.assertIn(marker,text)

    def test_partner_domains_are_not_automatically_official(self):
        for host in routes.PARTNER_HOSTS:
            if host not in routes.OFFICIAL_HOSTS:
                self.assertNotIn(host, routes.OFFICIAL_HOSTS)

    def test_query_contains_game_and_multiple_families(self):
        q=routes._query('포켓몬 카드','KR')
        self.assertIn('포켓몬',q)
        self.assertIn('출시',q)
        self.assertIn('프로모',q)
        self.assertIn('재입고',q)

    def test_topic_queries_are_isolated_and_have_full_matrix(self):
        q=routes._query('원피스 카드','US',topic='movie')
        self.assertIn('movie',q)
        self.assertNotIn('tournament',q)
        self.assertEqual(len(routes.COVERAGE_TOPICS),10)
        self.assertIn('reprint',routes.COVERAGE_TOPICS)
        self.assertIn('merch',routes.COVERAGE_TOPICS)
        self.assertIn('anniversary',routes.COVERAGE_TOPICS)

    def test_verified_learned_terms_can_expand_a_topic_query(self):
        q=routes._query('원피스 카드','KR',topic='merch',extra_terms=('JUMP SHOP','센트럴'))
        self.assertIn('"JUMP SHOP"',q)
        self.assertIn('센트럴',q)

    def test_press_routes_remain_discovery_only(self):
        for host in routes.PRESS_HOSTS:
            self.assertNotIn(host,routes.OFFICIAL_HOSTS)

    def test_official_match_is_scoped_to_game_and_region(self):
        self.assertTrue(routes._official_for('나루토 카드','US','www.naruto-cardgame.com'))
        self.assertFalse(routes._official_for('포켓몬 카드','US','www.naruto-cardgame.com'))

    def test_rate_limit_reports_retry_after_without_bypass(self):
        headers=Message(); headers['Retry-After']='120'
        error=urllib.error.HTTPError('https://www.bing.com',429,'rate limited',headers,None)
        summary=routes._error_summary('Bing',error)
        self.assertIn('HTTP 429',summary)
        self.assertIn('Retry-After=120',summary)
        self.assertIn('cooldown-required',summary)

    def test_unverified_candidate_does_not_resolve_verified_gap(self):
        rows=[{
            'game':'원피스 카드','region':'KR','search_topic':'reprint',
            'source':'https://example.com/reprint-rumor','verified':False,
        }]
        candidate=routes._topic_coverage(rows)
        verified=routes._topic_coverage(rows,verified_only=True)
        key='원피스 카드/KR/reprint'
        self.assertEqual(candidate[key],1)
        self.assertEqual(verified[key],0)

    def test_verified_official_candidate_resolves_verified_gap(self):
        rows=[{
            'game':'원피스 카드','region':'KR','search_topic':'reprint',
            'source':'https://onepiece-cardgame.kr/topics.do','verified':True,
            'official_domain_match':True,
        }]
        verified=routes._topic_coverage(rows,verified_only=True)
        self.assertEqual(verified['원피스 카드/KR/reprint'],1)

    def test_verified_coverage_matrix_keeps_all_expected_cells(self):
        coverage=routes._topic_coverage([],verified_only=True)
        self.assertEqual(
            len(coverage),
            len(routes.GAMES)*len(routes.REGIONS)*len(routes.COVERAGE_TOPICS),
        )
        self.assertTrue(all(value==0 for value in coverage.values()))


if __name__=='__main__':
    unittest.main()
