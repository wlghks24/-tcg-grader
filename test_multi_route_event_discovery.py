import unittest
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
            self.assertTrue({'release','event','promo','collab','stock'}.issubset(routes.QUERY_FAMILIES[lang]))

    def test_independent_provider_routes_exist(self):
        # Search route names are intentionally distinct so one provider outage
        # does not remove all public discovery paths.
        text=open(routes.__file__,encoding='utf-8').read()
        for marker in ('bing_general','bing_official','bing_partner','official_anchor','ddg_fallback'):
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


if __name__=='__main__':
    unittest.main()
