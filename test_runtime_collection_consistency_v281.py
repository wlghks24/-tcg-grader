import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import collection_meta_learning as meta
import social_stock_discovery as stock

ROOT = Path(__file__).resolve().parent


class RuntimeCollectionConsistencyV281Tests(unittest.TestCase):
    def test_social_candidate_id_is_stable_across_python_hash_seeds(self):
        code = "\n".join([
            "import social_stock_discovery as s",
            "source={'username':'stable_shop','profile_url':'https://www.instagram.com/stable_shop','platform':'instagram','game':'Pokemon','region':'KR'}",
            "raw={'title':'재입고 재고 10개','summary':'판매중','url':'https://www.instagram.com/stable_shop/p/abc','provider':'bing_rss'}",
            "row=s._candidate_from_result(raw,source)",
            "print(row['id'])",
        ])
        ids = []
        for seed in ("1", "999"):
            env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT))
            ids.append(subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=env, text=True).strip())
        self.assertEqual(ids[0], ids[1])
        self.assertIn("stable_shop", ids[0])

    def test_malformed_social_learning_numbers_fail_safe(self):
        priority = stock._source_priority(
            {"username": "bad"},
            {"sources": {"bad": {"runs": "NaN", "accepted": "inf", "errors": "broken"}}},
        )
        self.assertEqual(priority[1], "bad")
        score, stale = stock.age_adjusted_score({"score": "NaN", "ttl_hours": "inf"})
        self.assertIsInstance(score, int)
        self.assertTrue(stale)

    def test_social_commit_preserves_two_concurrent_process_updates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            worker = "\n".join([
                "import sys",
                "from pathlib import Path",
                "import social_stock_discovery as s",
                "root=Path(sys.argv[1]); label=sys.argv[2]",
                "s.SIGNAL_DB=root/'signals.json'",
                "s.PURCHASE_SIGNAL_DB=root/'purchase.json'",
                "s.LEARNING_DB=root/'learning.json'",
                "row={'id':'id-'+label,'game':'Pokemon','region':'KR','source_username':'same','source_url':'https://www.instagram.com/same/p/'+label,'profile_url':'https://www.instagram.com/same','location':'store-'+label,'product':'box-'+label,'status':'in_stock_report','observed_at':s._now(),'confidence':0.5,'score':50,'ttl_hours':24,'verification_status':'social_unverified','official_stock':False,'realtime_stock':False}",
                "s._commit_results(discovered=[row],raw_total=1,errors=[],observations=[({'username':'same'},1,1,0,0.1)],sources_watched=1)",
            ])
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            a = subprocess.Popen([sys.executable, "-c", worker, str(root), "a"], cwd=ROOT, env=env)
            b = subprocess.Popen([sys.executable, "-c", worker, str(root), "b"], cwd=ROOT, env=env)
            self.assertEqual(a.wait(timeout=30), 0)
            self.assertEqual(b.wait(timeout=30), 0)
            signals = json.loads((root / "signals.json").read_text(encoding="utf-8"))
            learning = json.loads((root / "learning.json").read_text(encoding="utf-8"))
            self.assertEqual({row.get("location") for row in signals.get("items", [])}, {"store-a", "store-b"})
            self.assertEqual(learning["sources"]["same"]["runs"], 2)
            self.assertEqual(learning["sources"]["same"]["accepted"], 2)

    def test_meta_refresh_wraps_entire_transaction_in_exclusive_lock(self):
        calls = []

        @contextmanager
        def fake_lock(target, **kwargs):
            calls.append((Path(target), kwargs))
            yield

        with mock.patch.object(meta, "exclusive_file_lock", fake_lock), mock.patch.object(
            meta, "_refresh_profile_unlocked", return_value={"ok": True}
        ) as refresh:
            result = meta.refresh_profile()
        self.assertEqual(result, {"ok": True})
        refresh.assert_called_once_with()
        self.assertEqual(calls[0][0], meta.MEMORY)
        self.assertGreaterEqual(float(calls[0][1].get("timeout_seconds", 0)), 10.0)


if __name__ == "__main__":
    unittest.main()
