#!/usr/bin/env python3
import json, unittest
from pathlib import Path
import tablet_runtime_manifest as runtime

ROOT=Path(__file__).resolve().parent
POLICY=ROOT/"RUNTIME_TOPOLOGY_POLICY_V441.json"

class RuntimeTopologyV441(unittest.TestCase):
 def load(self):
  return json.loads(POLICY.read_text(encoding="utf-8"))
 def test_exact_active_topology(self):
  p=self.load()["active_topology"]
  self.assertTrue(p["tablet"]["active"]);self.assertTrue(p["github"]["active"]);self.assertTrue(p["google_drive"]["active"])
  self.assertFalse(p["pc_runtime"]["active"]);self.assertFalse(p["external_cloud_compute"]["active"])
  self.assertEqual({"tablet","github","google_drive"},{k for k,v in p.items() if v["active"]})
 def test_drive_is_transport_not_compute(self):
  p=self.load();roles=set(p["active_topology"]["google_drive"]["roles"])
  self.assertNotIn("compute",roles);self.assertNotIn("training",roles)
  self.assertTrue(p["invariants"]["google_drive_is_storage_transport_not_compute"])
 def test_tablet_bundle_has_drive_and_no_windows_runtime(self):
  p=self.load();files=set(runtime.ACTIVE_RUNTIME_FILES)
  for name in p["required_tablet_drive_files"]: self.assertIn(name,files)
  for name in files:
   self.assertFalse(any(name.lower().endswith(s) for s in p["forbidden_active_runtime_suffixes"]),name)
   self.assertFalse(any(name.startswith(x) for x in p["forbidden_active_runtime_prefixes"]),name)
 def test_required_operating_files_exist(self):
  for name in self.load()["required_tablet_drive_files"]:
   self.assertTrue((ROOT/name).is_file(),name)
  self.assertTrue((ROOT/".github/workflows/tablet-gdrive-sync-guard.yml").is_file())
  self.assertTrue((ROOT/".github/workflows/github-skills-quality-v438.yml").is_file())
  self.assertTrue((ROOT/".github/workflows/android-updater-guard.yml").is_file())
 def test_pc_guard_is_legacy_only_not_active_bundle(self):
  files=set(runtime.ACTIVE_RUNTIME_FILES)
  self.assertNotIn("START_TCG_UPDATER.bat",files)
  self.assertNotIn("TCG_SERVER_AUTO_RUN.cmd",files)
  self.assertNotIn("PC_SERVER_AUTO_START_INSTALL.bat",files)
if __name__=="__main__":unittest.main(verbosity=2)
