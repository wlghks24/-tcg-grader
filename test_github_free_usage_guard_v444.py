import unittest
from pathlib import Path
import github_free_usage_guard_v444 as g
class V444(unittest.TestCase):
 def setUp(self):self.p=g.load()
 def test_public_standard_is_unmetered(self):
  r=g.evaluate(visibility="public",artifact_bytes=0,cache_bytes=0,billing=None,policy=self.p);self.assertEqual("READY_PUBLIC_STANDARD",r["status"]);self.assertIsNone(r["minutes_remaining"])
 def test_storage_wait(self):
  r=g.evaluate(visibility="public",artifact_bytes=self.p["storage"]["artifact_hard_bytes"],cache_bytes=0,billing=None,policy=self.p);self.assertEqual("QUOTA_WAIT",r["status"])
 def test_private_without_usage_waits(self):
  self.assertEqual("QUOTA_WAIT",g.evaluate(visibility="private",artifact_bytes=0,cache_bytes=0,billing=None,policy=self.p)["status"])
 def test_private_near_limit_waits(self):
  b={"usageItems":[{"product":"Actions","unitType":"minutes","grossQuantity":1900}]}
  self.assertEqual("QUOTA_WAIT",g.evaluate(visibility="private",artifact_bytes=0,cache_bytes=0,billing=b,policy=self.p)["status"])
 def test_current_workflows_only_standard_runners(self):self.assertTrue(g.audit_workflows(Path(__file__).resolve().parent,self.p)["ok"])
if __name__=="__main__":unittest.main()
