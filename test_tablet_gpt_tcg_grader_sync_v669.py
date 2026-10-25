"""V669 exact predecessor model safety test, never production/device approval."""
import json,hashlib,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as h
ROOT=Path(__file__).resolve().parent
CP="TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V669.json"
FILE="execution/tablet_image_model_gate.py"
BASE="172dddb0c7f3100a8f12b8811ae84558e5ce8f26"
CAND="60cb98da7b65773146b446479c6bb0c10fe345f1"

def read(name):
 p=ROOT/name
 if not p.is_file() or p.is_symlink():raise AssertionError("INVALID_EVIDENCE")
 return json.loads(p.read_text(encoding="utf-8"))

class V669SafetyTests(unittest.TestCase):
 def test_exact_candidate_and_v661_immutable_proof(self):
  h._assert_v669_image_gate_successor(self)
  h.assert_v661_successor(self)
  self.assertFalse(h.V661_PROOF["deployment_allowed"])
  self.assertFalse(h.V669_IMAGE_GATE_PROOF["deployment_allowed"])
 def test_contract_delta_receipt_and_watched_scope(self):
  c=read(CP);old=read(c["prior_contract"]);d=read(c["delta_snapshot"])
  pd=read(c["prior_delta_snapshot"]);r=read(c["receiver_receipt"])
  q=c["candidate_sync"]
  self.assertEqual(c["rules"],old["rules"])
  self.assertEqual(c["current_required_merge_prs"],old["current_required_merge_prs"])
  self.assertEqual(c["current_required_lesson_count"],old["current_required_lesson_count"]+len(d["lessons"]))
  self.assertEqual(q["base_main_sha"],BASE);self.assertEqual(q["candidate_commit"],CAND)
  self.assertEqual(q["watched_paths"],[FILE])
  self.assertEqual(set(q["generation_files"]),{CP,c["delta_snapshot"],c["receiver_receipt"],c["verification_test"]})
  for name in ("exact_paths","path_prefixes","exclude_paths"):
   self.assertTrue(set(old["freshness_watch"][name])<=set(c["freshness_watch"][name]))
  digest=hashlib.sha256(json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
  self.assertEqual(digest,d["lesson_digest_sha256"]);self.assertEqual(digest,r["delta_lesson_digest_sha256"])
  self.assertEqual(pd["lesson_digest_sha256"],d["prior_lesson_digest_sha256"])
  self.assertEqual(pd["lesson_digest_sha256"],r["prior_lesson_digest_sha256"])
  self.assertEqual([x["lesson_id"] for x in d["lessons"]],r["accepted_lesson_ids"])
  self.assertEqual(r["source_main_sha"],BASE)
  self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
  self.assertFalse(r["verification"]["physical_drive_readback_verified"])
  changed=subprocess.check_output(["git","diff","--name-only","--no-renames",BASE,CAND],cwd=ROOT,text=True).splitlines()
  watch=c["freshness_watch"]
  relevant=sorted(x for x in changed if x not in watch["exclude_paths"] and
      (x in watch["exact_paths"] or any(x.startswith(z) for z in watch["path_prefixes"])))
  self.assertEqual(relevant,[FILE])
 def test_modified_current_bytes_or_forged_approval_hold(self):
  origin=h.V661_PROOF["candidate_commit"]
  self.assertEqual([],h.preserve_reviewed_v661_scope([FILE],origin))
  self.assertEqual([FILE],h.preserve_reviewed_v661_scope([FILE],origin,head=origin))
  original=Path.read_bytes
  with patch.object(Path,"read_bytes",lambda p:original(p)+b"unreviewed" if p==ROOT/FILE else original(p)):
   self.assertEqual([FILE],h.preserve_reviewed_v661_scope([FILE],origin))
   with self.assertRaises(AssertionError):h._assert_v669_image_gate_successor(self)
  before=h._read
  def fake(p):
   value=before(p)
   return {**value,"deployment_allowed":True} if str(p).endswith("image_model_gate_successor_v669.json") else value
  with patch.object(h,"_read",side_effect=fake):
   with self.assertRaises(AssertionError):h._assert_v669_image_gate_successor(self)

def load_tests(loader,tests,pattern):
 from execution.tests.test_tablet_image_model_gate_safety import ImageAdvisoryGateTests
 from execution.tests.test_grading_runtime_fallback_v256 import GradingRuntimeFallbackV256Tests
 tests.addTests(loader.loadTestsFromTestCase(ImageAdvisoryGateTests))
 tests.addTests(loader.loadTestsFromTestCase(GradingRuntimeFallbackV256Tests))
 return tests
