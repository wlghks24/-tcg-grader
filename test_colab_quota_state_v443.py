import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile
import colab_quota_state_v443 as q

NOW=datetime(2026,10,7,5,0,tzinfo=timezone.utc)
class V443(unittest.TestCase):
 def test_unavailable_enters_wait(self):
  s=q.transition_after_probe(q.default_state(),gpu_available=False,backoff_minutes=[30,60],now=NOW)
  self.assertEqual("QUOTA_WAIT",s["status"]);self.assertEqual(1,s["failure_count"]);self.assertFalse(q.should_probe(s,now=NOW+timedelta(minutes=10)));self.assertTrue(q.should_probe(s,now=NOW+timedelta(minutes=31)))
 def test_backoff_and_recovery(self):
  s=q.default_state()
  for _ in range(3):s=q.transition_after_probe(s,gpu_available=False,backoff_minutes=[30,60,120],now=NOW)
  self.assertEqual(3,s["failure_count"])
  s=q.transition_after_probe(s,gpu_available=True,backoff_minutes=[30,60,120],now=NOW)
  self.assertEqual("READY",s["status"]);self.assertEqual(0,s["failure_count"]);self.assertIsNone(s["next_check_at"])
 def test_persist_checkpoint(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"state.json";s=q.set_checkpoint(q.default_state(),"checkpoints/cp1.json");q.save_state(p,s)
   self.assertEqual("checkpoints/cp1.json",q.load_state(p)["resume_checkpoint"])
if __name__=="__main__":unittest.main()
