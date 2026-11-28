"""Review-only focused regressions for existing purchase and grading modules."""
import unittest
import urllib.error
from unittest.mock import Mock, patch

import grading_company_watch as base
import grading_company_watch_resilient as resilient
import update_purchase_sources as purchase
import tcg_game_registry as registry

PSA = "https://www.psacard.com/services/tradingcardgrading"
BGS = "https://www.beckett.com/grading"
CGC = "https://www.cgccards.com/submit/services-fees/cgc-grading/"


class PurchaseProviderBoundaryTests(unittest.TestCase):
    def test_nested_purchase_game_is_rejected_as_value_error(self):
        for games in ([["Pokemon"]], [{"game": "Pokemon"}]):
            with self.subTest(games=games), self.assertRaises(ValueError):
                purchase.normalize_source({"name": "fixture", "region": "KR",
                                           "type": "official", "games": games})

    def test_registry_routes_regenerate_without_claiming_inventory(self):
        rows = purchase.ensure_registry_tcg_sources([])
        for game in registry.enabled_games("purchase", root=purchase.ROOT):
            for region in game["regions"]:
                if region not in purchase.REGIONS:
                    continue
                matching = [r for r in rows if r["games"] == [game["purchase_value"]]
                            and r["region"] == region]
                self.assertEqual({"official", "marketplace", "map"},
                                 {r["type"] for r in matching})
                self.assertEqual(3, len(matching))
                self.assertTrue(all(r["inventory_verified"] is False for r in matching))
        self.assertEqual(rows, purchase.ensure_registry_tcg_sources(rows))

    def test_same_provider_host_scope(self):
        self.assertEqual({"psacard.com", "www.psacard.com"},
                         base._provider_redirect_hosts(PSA))
        self.assertEqual({"beckett.com", "www.beckett.com", "maintenance.beckett.com"},
                         resilient._request_allowed_hosts(BGS))

    def test_cross_provider_injected_response_is_rejected(self):
        with self.assertRaises(ValueError):
            resilient._collector_fetch(PSA, requester=lambda _: ("wrong company", CGC))

    def test_maintenance_status_not_promoted_to_pricing(self):
        with self.assertRaises(resilient.BeckettMaintenanceRedirect):
            resilient._collector_fetch(BGS, requester=lambda _: ("maintenance", "https://maintenance.beckett.com/"))

    def test_invalid_destination_rejected(self):
        for url in ("http://www.psacard.com/", "https://user@www.psacard.com/",
                    "https://www.psacard.com:444/", "https://maintenance.beckett.com/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                resilient._collector_fetch(PSA, requester=lambda _: ("bad", url))

    def test_403_remains_failure(self):
        error = urllib.error.HTTPError(PSA, 403, "Forbidden", None, None)
        with patch.object(resilient, "safe_urlopen", side_effect=error) as request:
            with self.assertRaises(urllib.error.HTTPError):
                resilient._request(PSA)
            self.assertEqual(1, request.call_count)

    def test_final_cross_company_body_not_consumed(self):
        response = Mock()
        response.geturl.return_value = CGC
        manager = Mock()
        manager.__enter__ = Mock(return_value=response)
        manager.__exit__ = Mock(return_value=False)
        with patch.object(resilient, "safe_urlopen", return_value=manager) as request:
            with self.assertRaises(ValueError):
                resilient._request(PSA)
            self.assertEqual({"psacard.com", "www.psacard.com"},
                             request.call_args.kwargs["allowed_hosts"])
            response.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
