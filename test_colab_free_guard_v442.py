import unittest
from pathlib import Path
import colab_free_guard_v442 as g
class V442(unittest.TestCase):
 def setUp(self): self.p=g.load_policy(); self.start=100.0
 def test_paid_paths_forbidden(self):
  for k in ("paid_features_allowed","compute_units_purchase_allowed","gcp_billing_project_allowed","github_write_allowed","tablet_auto_apply_allowed"):
   self.assertFalse(self.p[k])
 def test_budget_stops_before_hard_limit(self):
  b=g.session_budget(self.start,self.p,now_monotonic=self.start+(66*60));self.assertTrue(b["must_stop"])
 def test_large_input_refused(self):
  ok,why=g.can_start_job(self.start,5,self.p["limits"]["max_input_bytes"]+1,self.p,now_monotonic=self.start);self.assertFalse(ok);self.assertEqual("INPUT_BUDGET",why)
 def test_long_job_refused(self):
  ok,why=g.can_start_job(self.start,31,1,self.p,now_monotonic=self.start);self.assertFalse(ok);self.assertEqual("JOB_BUDGET",why)
if __name__=="__main__":unittest.main()
