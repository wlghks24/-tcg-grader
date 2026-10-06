import unittest
from tcg_channel_reach_v435 import Endpoint,classify_probe,route,source_evidence
class V435(unittest.TestCase):
 def test_health_states(self):
  self.assertEqual("RATE_LIMITED",classify_probe(http_status=429));self.assertEqual("AUTH_REQUIRED",classify_probe(http_status=401,auth_required=True));self.assertEqual("DEGRADED",classify_probe(http_status=None,error_code="TIMEOUT"))
 def test_fallback_same_lineage_not_double_counted(self):
  es=[Endpoint("official_web","https://a.example/news","game-official",1),Endpoint("rss","https://a.example/rss","game-official",2),Endpoint("reddit","https://r.example/game","community",3)]
  x=route(es,{"https://a.example/news":{"http_status":500},"https://a.example/rss":{"http_status":200},"https://r.example/game":{"http_status":200}})
  self.assertEqual(2,len(x["selected"]));self.assertEqual({"game-official","community"},{r["lineage_key"] for r in x["selected"]})
 def test_blocked_never_selected(self):
  x=route([Endpoint("x","https://x.example/game","social")],{"https://x.example/game":{"http_status":403}});self.assertEqual("HOLD",x["status"])
 def test_crosscheck_needs_two_lineages(self):
  x=source_evidence([{"lineage_key":"a","state":"HEALTHY","confidence":.9},{"lineage_key":"a","state":"HEALTHY","confidence":.8}]);self.assertFalse(x["crosscheck_ready"])
if __name__=="__main__":unittest.main()
