"""Review-only guide relocation preserves exact main bytes and live entrypoints."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[2]
GUIDES=("AGENT_SKILL_SOURCES.md","ANDROID_TABLET_SETUP.md","GPT_DATA_ENGINE_GUIDE.md",
"TCG_INTEGRATED_MANAGEMENT.md","TABLET_COLLECTION_PUBLISH.md","WORKFLOW_PUBLISH_SAFETY_V363.md",
"GRAPHIFY_CHATGPT_GUIDE.md","TABLET_GDRIVE_SYNC.md")
BASE="6ce814e70ecbeca7ee2c659e6bb7c479f2d8bccc"
class DocumentLocationTests(unittest.TestCase):
    def test_guide_bytes_and_live_entrypoints(self):
        for name in GUIDES:
            with self.subTest(name=name):
                original=subprocess.check_output(["git","show",BASE+":"+name],cwd=ROOT)
                self.assertFalse((ROOT/name).exists())
                self.assertEqual(original,(ROOT/"docs/tablet"/name).read_bytes())
        for name in ("main","tcg_updater.py","tablet_runtime_manifest.py",
                     "tablet_image_library_v1.py","tablet_image_auto_v2.py",
                     "tablet_catalog_auto_reflect_v43.py","tablet_collection_image_bridge_v42.py"):
            self.assertTrue((ROOT/name).is_file(),name)
