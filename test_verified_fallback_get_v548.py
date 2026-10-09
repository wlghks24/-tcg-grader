#!/usr/bin/env python3
"""V548: GET-only, fail-closed official and same-host fallback recovery."""
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import validate_external_links as links

OLD="https://pokemonkorea.co.kr/"
GOOD="https://pokemonkorea.com/"
NOW="2026-10-09T00:00:00+00:00"

class FallbackGetProofV548(unittest.TestCase):
    def check_fallback(self, response, *, confirmed="GET", target=OLD, max_probes=16):
        row={"source":target}
        tasks={target:[("promo_events.json",row,"source")]}
        results={target:{"state":"broken","code":410,"confirmed_by":confirmed}}
        calls=[]
        def fake_probe(url, request_timeout=None, *, get_only=False):
            calls.append((url,get_only))
            return response
        with patch.object(links,"probe",side_effect=fake_probe):
            stats=links._verify_broken_link_fallbacks(tasks,results,5,max_probes=max_probes)
        counts,details=links._apply_results(tasks,results,NOW,require_verified_fallback=True)
        return row,counts,details,stats,calls

    def test_410_fallback_get_410_is_not_repaired(self):
        row,count,details,stats,calls=self.check_fallback({"state":"broken","code":410,"confirmed_by":"GET"})
        self.assertEqual(row["source"],OLD)
        self.assertEqual(count["repaired"],0)
        self.assertEqual(count["unresolved_broken"],1)
        self.assertEqual(len(details),1)
        self.assertEqual(calls,[(GOOD,True)])
        self.assertEqual(stats["rejected"],1)

    def test_blocked_or_transient_fallback_never_hides_broken_link(self):
        for state in ("restricted","transient","blocked"):
            with self.subTest(state=state):
                row,count,details,_,_=self.check_fallback({"state":state,"code":403})
                self.assertEqual(row["source"],OLD)
                self.assertEqual(count["unresolved_broken"],1)
                self.assertTrue(details)

    def test_verified_get_200_replaces_with_navigation_home_not_item_proof(self):
        row,count,details,stats,calls=self.check_fallback(
            {"state":"ok","code":200,"final_url":GOOD}
        )
        self.assertEqual(row["source"],GOOD)
        self.assertEqual(row["original_source"],OLD)
        self.assertIn("공식 홈",row["link_status"])
        self.assertEqual(count["repaired"],1)
        self.assertEqual(count["unresolved_broken"],0)
        self.assertEqual(details,[])
        self.assertEqual(stats["verified"],1)
        self.assertEqual(calls,[(GOOD,True)])

    def test_missing_get_confirmation_and_exhausted_budget(self):
        row,count,_,stats,calls=self.check_fallback(
            {"state":"ok","code":200,"final_url":GOOD},confirmed="HEAD"
        )
        self.assertEqual(count["unresolved_broken"],1)
        self.assertFalse(calls)
        row,count,_,stats,calls=self.check_fallback(
            {"state":"ok","code":200,"final_url":GOOD},max_probes=0
        )
        self.assertEqual(count["unresolved_broken"],1)
        self.assertEqual(stats["budget_exhausted"],1)
        self.assertFalse(calls)

    def test_redirect_to_another_host_cannot_approve_fallback(self):
        row,count,details,stats,calls=self.check_fallback(
            {"state":"ok","code":200,"final_url":"https://example.com/landing"}
        )
        self.assertEqual(row["source"],OLD)
        self.assertEqual(count["unresolved_broken"],1)
        self.assertEqual(stats["rejected"],1)

    def test_search_template_keeps_function_and_never_becomes_home(self):
        url="https://pokemoncard.co.kr/search?q={query}"
        row={"url_template":url}
        tasks={url:[("purchase_sources.json",row,"url_template")]}
        results={url:{"state":"broken","code":404,"confirmed_by":"GET"}}
        with patch.object(links,"probe") as mock:
            stats=links._verify_broken_link_fallbacks(tasks,results,5)
        count,details=links._apply_results(tasks,results,NOW,require_verified_fallback=True)
        self.assertEqual(row["url_template"],url)
        self.assertEqual(count["unresolved_broken"],1)
        self.assertEqual(stats["eligible"],0)
        mock.assert_not_called()

    def test_get_only_never_accepts_head_success(self):
        class FakeOpener:
            def open(self,req,timeout=None):
                if req.get_method()=="HEAD":
                    raise AssertionError("HEAD was incorrectly used to verify fallback")
                raise urllib.error.HTTPError(req.full_url,410,"gone",{},None)
        with patch.object(links,"_resolve_public",return_value=None), patch.object(
            urllib.request,"build_opener",return_value=FakeOpener()
        ):
            result=links.probe(GOOD,request_timeout=5,get_only=True)
        self.assertEqual(result["state"],"broken")
        self.assertEqual(result["confirmed_by"],"GET")

if __name__=="__main__":
    unittest.main()
