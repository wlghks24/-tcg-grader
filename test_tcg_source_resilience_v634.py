#!/usr/bin/env python3
"""V633–V634 free-source reliability tests: 30 games and all HTTP failure classes."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.error import HTTPError, URLError

import tcg_source_audit_v633 as audit

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class SourceResilienceV633V634(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def get(name):
            return json.loads((ROOT/name).read_text(encoding="utf-8"))
        cls.reg=get("tcg_game_registry.json")
        cls.intake=get("tcg_user_research_intake_v625.json")
        cls.base=get("tcg_official_product_catalog_v599.json")
        cls.supp=get("tcg_official_product_supplement_v630.json")

    def test_offline_plan_preserves_30_and_all_338_candidates(self):
        report=audit.plan(self.reg,self.intake,self.base,self.supp)
        self.assertEqual(30,report["games"])
        self.assertEqual(90,report["market_search_scopes"])
        self.assertEqual(55,report["declared_scopes"])
        self.assertEqual(63,report["official_product_samples"])
        self.assertEqual(36,report["declared_official_sample_gaps"])
        self.assertEqual((198,42,60,38),(
            report["product_candidate_count"],report["upcoming_candidate_count"],
            report["hit_candidate_count"],report["promo_candidate_count"]))
        self.assertEqual(90,len(report["scopes"]))
        self.assertEqual(30,len({row["game_id"] for row in report["scopes"]}))
        self.assertEqual(36,sum(r["priority"]=="P0_DECLARED_GAP" for r in report["scopes"]))
        self.assertEqual(35,sum(r["priority"]=="P2_EXPLORATORY" for r in report["scopes"]))
        self.assertTrue(all(r["price_evidence"]=="NONE" for r in report["scopes"]))
        self.assertTrue(all(all(x["status"]=="USER_SUBMITTED_UNVERIFIED" for x in r["product_name_candidates"])
                            for r in report["scopes"]))
        self.assertTrue(all(r["source_search"].startswith("https://www.google.com/search?")
                            for scope in report["scopes"] for r in scope["product_name_candidates"]
                            if r["source_search"]))

    def test_link_safety_and_search_unicode(self):
        for value in ("http://x.example/p","https://127.0.0.1/a","https://localhost/a",
                      "https://user:pass@example.com/","https://example.com:444/a",
                      "https://example.com/#frag","javascript:alert(1)","https://example.test/a"):
            self.assertFalse(audit.safe_https(value),value)
        self.assertTrue(audit.safe_https("https://onepiece-cardgame.kr/products/"))
        url=audit.manufacturer_search("https://onepiece-cardgame.kr/products/","新たなる皇帝","OP-09")
        self.assertIn("google.com/search",url)
        self.assertIn("OP-09",url)
        backup=audit.manufacturer_search("https://onepiece-cardgame.kr/products/","新たなる皇帝",engine="bing")
        self.assertTrue(backup.startswith("https://www.bing.com/search?"))
        with self.assertRaises(ValueError):audit.manufacturer_search("https://example.com","test",engine="unknown")

    def test_link_failures_dont_become_false_product_deletions(self):
        expected={200:"HTTP_OK_NOT_CONTENT_VERIFIED",301:"REDIRECT_REVIEW",
                  404:"BROKEN_LINK_REVIEW",410:"BROKEN_LINK_REVIEW",
                  401:"ACCESS_RESTRICTED_UNVERIFIED",403:"ACCESS_RESTRICTED_UNVERIFIED",
                  429:"RATE_LIMIT_PAUSE",500:"TEMPORARY_FAILURE",502:"TEMPORARY_FAILURE",
                  503:"TEMPORARY_FAILURE",504:"TEMPORARY_FAILURE"}
        for code,status in expected.items():
            with self.subTest(http_code=code):
                self.assertEqual(status,audit.classify(code))
        self.assertNotEqual("BROKEN_LINK_REVIEW",audit.classify(429))

    def test_probe_uses_bounded_get_no_redirect_and_reports_http_error(self):
        class Response:
            status=200
            def geturl(self):return "https://example.com/a"
            def getcode(self):return 200
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Good:
            def open(self,req,timeout):
                self_outer.assertEqual("GET",req.get_method())
                self_outer.assertEqual(6,timeout)
                self_outer.assertEqual("bytes=0-2047",req.get_header("Range"))
                return Response()
        self_outer=self
        self.assertEqual("HTTP_OK_NOT_CONTENT_VERIFIED",audit.probe_one(
            "https://example.com/a",opener=Good())["status"])
        class Bad:
            def __init__(self,code):self.code=code
            def open(self,req,timeout):
                raise HTTPError(req.full_url,self.code,"test",{"Retry-After":"180"},None)
        r=audit.probe_one("https://example.com/a",opener=Bad(429))
        self.assertEqual(("RATE_LIMIT_PAUSE","180"),(r["status"],r["retry_after"]))
        self.assertEqual("BROKEN_LINK_REVIEW",audit.probe_one(
            "https://example.com/a",opener=Bad(404))["status"])
        class NetworkError:
            def open(self,req,timeout):
                raise URLError("intermittent")
        self.assertEqual("NETWORK_OR_UNKNOWN_UNVERIFIED",audit.probe_one(
            "https://example.com/a",opener=NetworkError())["status"])
        self.assertEqual("INVALID_URL",audit.probe_one("http://unsafe.test",opener=Good())["status"])

    def test_tested_static_ui_preserves_safe_links_and_30_game_access(self):
        js=(ROOT/"tcg_source_research_v634.js").read_text(encoding="utf-8")
        link=(ROOT/"tcg_source_routes_v633.js").read_text(encoding="utf-8")
        html=(ROOT/"tcg_source_research_v634.html").read_text(encoding="utf-8")
        official=(ROOT/"official_box_catalog_v626.js").read_text(encoding="utf-8")
        for marker in ("researchGame","researchRegion","researchPriority","researchResults","researchNext"):
            self.assertIn('id="'+marker+'"',html)
        self.assertIn('Content-Security-Policy',html)
        self.assertIn('tcg_source_routes_v633.js',html)
        self.assertIn('tcg_source_research_v634.js',html)
        self.assertIn('tcg_source_routes_v633.js',(ROOT/"official_box_catalog_v626.html").read_text(encoding="utf-8"))
        self.assertIn('원문 404·접속 실패 시 제조사 사이트 검색',official)
        self.assertNotIn('.innerHTML',js)
        self.assertNotIn('.innerHTML',link)
        self.assertIn('textContent',js)

    @unittest.skipUnless(NODE,"Node runtime unavailable")
    def test_browser_all_90_scopes_and_fallbacks_without_truncation(self):
        code=r"""
const assert=require('node:assert/strict');
const registry=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const sup=require('./tcg_official_product_supplement_v630.json');
const ui=require('./tcg_source_research_v634.js');
const routes=require('./tcg_source_routes_v633.js');
const data=ui.build(registry,intake,base,sup);
assert.deepEqual(data.summary,{games:30,searchScopes:90,declared:55,missing:36,
 official:63,product:198,upcoming:42,hit:60,promo:38});
assert.equal(ui.filtered(data.scopes,{priority:'MISSING'}).length,36);
assert.equal(ui.filtered(data.scopes,{priority:'EXPLORATORY'}).length,35);
assert.equal(ui.filtered(data.scopes,{game:'pokemon'}).length,3);
const gathered=[];
for(let i=0;i<15;i++)gathered.push(...ui.paginate(data.scopes,i).rows);
assert.equal(gathered.length,90);
assert.equal(ui.paginate(data.scopes,100).current,14);
for(const p of [...base.products,...sup.products]){
 const r=routes.sourceRoutes(p,registry);
 assert.ok(r,p.id);
 assert.equal(r.original,p.source);
 assert.ok(r.manufacturerSiteSearch.startsWith('https://www.google.com/search?q='));
 assert.ok(r.alternateSiteSearch.startsWith('https://www.bing.com/search?q='));
}
assert.equal(routes.classifyStatus(404),'BROKEN_LINK_REVIEW');
assert.equal(routes.classifyStatus(403),'ACCESS_RESTRICTED_UNVERIFIED');
assert.equal(routes.classifyStatus(429),'RATE_LIMIT_PAUSE');
assert.equal(routes.classifyStatus(502),'TEMPORARY_FAILURE');
assert.equal(routes.safeUrl('https://example.com:1234/path'),null);
let bad=JSON.parse(JSON.stringify(intake));
bad.records[0].status='VERIFIED';
assert.throws(()=>ui.build(registry,bad,base,sup));
"""
        res=subprocess.run([NODE,"-e",code],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
        self.assertEqual(0,res.returncode,res.stdout+"\n"+res.stderr)

    @unittest.skipUnless(NODE,"Node runtime unavailable")
    def test_node_checks(self):
        for src in ("tcg_source_routes_v633.js","tcg_source_research_v634.js","official_box_catalog_v626.js"):
            with self.subTest(src=src):
                result=subprocess.run([NODE,"--check",src],cwd=ROOT,text=True,
                    capture_output=True,check=False,timeout=15)
                self.assertEqual(0,result.returncode,result.stderr)


if __name__=="__main__":unittest.main(verbosity=2)
