#!/usr/bin/env python3
"""V668: test local observation contract with mocked time (no real 30 min)."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tcg_lenovo_termux_probe_v668 import soak,atomic_json,proc_metrics,MAX_SECONDS
class OfflineDeviceProbeV668(unittest.TestCase):
 def test_bounded_soak_and_no_false_device_approval(self):
  t=[0.0]
  def clock():return t[0]
  def sleep(seconds):t[0]+=seconds
  def sample():return {"memory":{"MemAvailable_kib":555555},
                       "free_disk_mib":1024,"load_avg_1m":0.1}
  value=soak(65,clock=clock,sleeper=sleep,collector=sample)
  self.assertEqual(65,value["requested_seconds"])
  self.assertEqual("OBSERVED_LOCALLY_NOT_REBOOT_OR_UI_PROOF",value["status"])
  self.assertGreaterEqual(len(value["samples"]),3)
  with self.assertRaises(ValueError):soak(MAX_SECONDS+1)
  self.assertEqual("NOT_REQUESTED",soak(0)["status"])
 def test_safe_atomic_report_serialization(self):
  with TemporaryDirectory() as d:
   target=Path(d)/"qa"/"result.json"
   atomic_json(target,{"status":"HOLD_PENDING_ACTUAL_DEVICE_AND_RELEASE_REVIEW",
                       "main_merge_approved":False,"remote_qa_proven":False})
   obj=json.loads(target.read_text(encoding="utf-8"))
   self.assertFalse(obj["main_merge_approved"])
   self.assertFalse(obj["remote_qa_proven"])
   self.assertFalse(target.with_name(target.name+".tmp").exists())
   alias=Path(d)/"link"
   alias.symlink_to(target)
   with self.assertRaises(ValueError):atomic_json(alias,{"ok":True})
 def test_generic_platform_metric_is_not_android_claim(self):
  data=proc_metrics()
  self.assertIn("android_termux_likely",data)
  self.assertIn("node_available",data)
  self.assertIsInstance(data["android_termux_likely"],bool)
if __name__=="__main__":unittest.main(verbosity=2)
