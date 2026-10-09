#!/usr/bin/env python3
"""V549: local-only tests for bounded and evidence-honest external link resilience."""
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import validate_external_links as links

class _Success:
    status=200
    def __init__(self,url):self.url=url
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):return False

class _MethodOpener:
    def __init__(self,head_code,get_code=None):
        self.head_code=head_code
        self.get_code=get_code
        self.calls=[]
    def open(self,req,timeout=None):
        self.calls.append(req.get_method())
        code=self.head_code if req.get_method()=="HEAD" else self.get_code
        if code is not None:
            raise urllib.error.HTTPError(req.full_url,code,"test",{},None)
        return _Success(req.full_url)

class LinkSourceResilienceV549(unittest.TestCase):
    def _probe_with(self,head,get):
        fake=_MethodOpener(head,get)
        with patch.object(links,"_resolve_public",return_value=None),patch.object(
            urllib.request,"build_opener",return_value=fake
        ):
            outcome=links.probe("https://example.com/card",request_timeout=5)
        return outcome,fake.calls

    def test_head_403_get_200_is_not_false_restricted(self):
        result,calls=self._probe_with(403,None)
        self.assertEqual(result["state"],"ok")
        self.assertEqual(calls,["HEAD","GET"])

    def test_get_still_restricted_and_429_never_retried(self):
        result,calls=self._probe_with(403,403)
        self.assertEqual(result["state"],"restricted")
        self.assertEqual(calls,["HEAD","GET"])
        result,calls=self._probe_with(429,None)
        self.assertEqual(result["state"],"restricted")
        self.assertEqual(calls,["HEAD"])

    def test_418_412_are_access_denied_not_network_flakiness(self):
        for code in (412,418):
            with self.subTest(code=code):
                result,calls=self._probe_with(code,code)
                self.assertEqual(result["state"],"restricted")
                self.assertEqual(result["code"],code)
                self.assertEqual(calls,["HEAD","GET"])

    def test_invalid_search_template_400_remains_unverified(self):
        row={"url_template":"https://search.example/find?q={query}"}
        result={"state":"transient","code":400,"detail":"QUERY_TEMPLATE_REJECTED"}
        counts,_=links._apply_results({row["url_template"]:[("purchase_sources.json",row,"url_template")]},
                                       {row["url_template"]:result},"2026-10-09T00:00:00Z")
        self.assertEqual(counts["ok"],0)
        self.assertEqual(counts["transient"],1)
        self.assertIn("수동 점검",row["link_status"])
        self.assertEqual(row["url_template"],"https://search.example/find?q={query}")

    def test_worker_override_bounded_and_android_stays_light(self):
        with patch.dict(os.environ,{"TCG_LINK_WORKERS":"12"},clear=False),patch.object(
            links.os,"cpu_count",return_value=32
        ):
            self.assertEqual(links._worker_count(300),12)
            with patch.dict(os.environ,{"ANDROID_ROOT":"/system"},clear=False):
                self.assertEqual(links._worker_count(300),4)
        with patch.dict(os.environ,{"TCG_LINK_WORKERS":"999999"},clear=False),patch.object(
            links.os,"cpu_count",return_value=32
        ):
            self.assertEqual(links._worker_count(300),12)

    def test_host_spreading_preserves_urls_and_separates_provider(self):
        urls=[f"https://kream.co.kr/products/{n}" for n in range(12)]
        urls+= [f"https://store{n}.example/item" for n in range(12)]
        arranged=links._interleave_hosts(urls,separation=5)
        self.assertCountEqual(arranged,urls)
        self.assertEqual(len(arranged),len(urls))
        self.assertTrue(any("kream.co.kr" not in s for s in arranged[:4]))
        self.assertLessEqual(max(sum("kream.co.kr" in s for s in arranged[i:i+5])
                                 for i in range(len(arranged)-4)),5)

    def test_retry_one_per_host_only_for_transient(self):
        values={
            "https://example.com/a":{"state":"transient","code":503},
            "https://example.com/b":{"state":"transient","detail":"TimeoutError"},
            "https://another.example/c":{"state":"transient","code":500},
            "https://blocked.example/d":{"state":"restricted","code":429},
            "https://bad.example/e":{"state":"transient","code":400},
        }
        calls=[]
        def retry(url,request_timeout=None):
            calls.append(url)
            return {"state":"ok","code":200,"final_url":url}
        with patch.object(links,"probe",side_effect=retry),patch.object(links.time,"sleep"):
            report=links._retry_transient_once(values,5,max_probes=4)
        self.assertEqual(report["attempted"],2)
        self.assertEqual(report["recovered"],2)
        self.assertEqual(len(calls),2)
        self.assertEqual(values["https://example.com/b"]["state"],"transient")
        self.assertEqual(values["https://blocked.example/d"]["state"],"restricted")
        self.assertEqual(values["https://bad.example/e"]["code"],400)

    def test_failed_retry_keeps_stale_state_and_deadline_skips(self):
        url="https://example.com/a"
        initial={url:{"state":"transient","code":503}}
        with patch.object(links,"probe",return_value={"state":"transient","code":503}),patch.object(
            links.time,"sleep"
        ):
            stats=links._retry_transient_once(initial,5)
        self.assertEqual(stats["recovered"],0)
        self.assertTrue(initial[url]["retry_attempted"])
        self.assertEqual(initial[url]["state"],"transient")
        with patch.object(links,"probe") as mock:
            stats=links._retry_transient_once(initial,5,deadline=0)
        self.assertEqual(stats["attempted"],0)
        mock.assert_not_called()

    def test_retry_can_reclassify_confirmed_404_without_faking_success(self):
        url="https://example.com/a"
        values={url:{"state":"transient","code":502}}
        with patch.object(links,"probe",return_value={"state":"broken","code":404,"confirmed_by":"GET"}),patch.object(
            links.time,"sleep"
        ):
            stats=links._retry_transient_once(values,5)
        self.assertEqual(stats["reclassified_broken"],1)
        self.assertEqual(values[url]["state"],"broken")
        row={"url":url}
        counts,details=links._apply_results({url:[("market_watch.json",row,"url")]},values,"2026-10-09T00:00:00Z",
                                           require_verified_fallback=True)
        self.assertEqual(counts["unresolved_broken"],1)
        self.assertEqual(len(details),1)

if __name__=="__main__":
    unittest.main()
