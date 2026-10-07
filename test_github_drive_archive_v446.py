import unittest
from datetime import datetime,timezone
import github_drive_archive_v446 as a
NOW=datetime(2026,10,7,12,0,tzinfo=timezone.utc)
class V446(unittest.TestCase):
 def setUp(self):
  self.p=a.load_policy()
 def row(self,i,name,size,created):
  return {"id":i,"name":name,"size_in_bytes":size,"created_at":created,"expires_at":"2026-11-01T00:00:00Z","expired":False}
 def test_below_half_does_nothing(self):
  r=a.plan_archive([],self.p["trigger_bytes"]-1,self.p,now=NOW);self.assertEqual("BELOW_TRIGGER",r["status"])
 def test_keeps_newest_per_name_and_archives_oldest(self):
  p=dict(self.p);p["trigger_bytes"]=300;p["target_bytes"]=100;p["max_batch_bytes"]=999999999
  rows=[self.row(1,"report",120,"2026-10-01T00:00:00Z"),self.row(2,"report",120,"2026-10-06T00:00:00Z"),self.row(3,"other",120,"2026-10-02T00:00:00Z"),self.row(4,"other",120,"2026-10-06T01:00:00Z")]
  r=a.plan_archive(rows,480,p,now=NOW);self.assertEqual([1,3],[x["artifact_id"] for x in r["selected"]])
 def test_receipt_never_contains_drive_locator(self):
  row=self.row(7,"report",123,"2026-10-01T00:00:00Z")
  r=a.build_public_receipt(artifact=row,archive_file_name="github-artifact-7-report.zip",drive_readback_size=130,sha256="a"*64,uploaded_at="2026-10-07T12:00:00Z")
  self.assertNotIn("drive_file_id",r);self.assertNotIn("drive_url",r);a.validate_receipt(r,self.p)
 def test_fake_receipt_is_blocked(self):
  row=self.row(7,"report",123,"2026-10-01T00:00:00Z")
  r=a.build_public_receipt(artifact=row,archive_file_name="github-artifact-7-report.zip",drive_readback_size=130,sha256=None,uploaded_at="2026-10-07T12:00:00Z")
  r["drive_readback_verified"]=False
  with self.assertRaises(ValueError):a.validate_receipt(r,self.p)
 def test_source_metadata_must_match_before_delete(self):
  row=self.row(7,"report",123,"2026-10-01T00:00:00Z")
  r=a.build_public_receipt(artifact=row,archive_file_name="github-artifact-7-report.zip",drive_readback_size=130,sha256=None,uploaded_at="2026-10-07T12:00:00Z")
  self.assertTrue(a.source_matches_receipt(row,r));bad=dict(row);bad["size_in_bytes"]=124;self.assertFalse(a.source_matches_receipt(bad,r))
 def test_cleanup_requires_newer_copy(self):
  old=self.row(7,"report",123,"2026-10-01T00:00:00Z");new=self.row(8,"report",124,"2026-10-06T00:00:00Z")
  r=a.build_public_receipt(artifact=old,archive_file_name="github-artifact-7-report.zip",drive_readback_size=130,sha256=None,uploaded_at="2026-10-07T12:00:00Z")
  self.assertEqual((True,"OK"),a.cleanup_candidate_safe(old,r,[old,new],self.p,now=NOW))
  self.assertEqual((False,"NO_NEWER_COPY"),a.cleanup_candidate_safe(old,r,[old],self.p,now=NOW))
if __name__=="__main__":unittest.main()
