import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from execution import video_market_successor_20261123 as proof
from execution.tests.test_fx_successor_v1014 import validate_fx_successor_v1014
from execution.tests.test_video_runtime_successor_v997 import validate_v997_runtime


class VideoMarketSuccessorTests(unittest.TestCase):
    def run_proof(self, name='multi_market_price_collector.py'):
        return proof.validate_video_market_followup(name, proof.EXPECTED['baseline'][name]['sha256'])

    def test_exact_source_and_preserved_legacy_whole_set(self):
        for name in proof.EXPECTED['baseline']:
            self.assertTrue(self.run_proof(name))
        self.assertTrue(validate_fx_successor_v1014())
        self.assertTrue(validate_v997_runtime("tablet_autonomy_dashboard_v400.js"))

    def test_wrong_path_and_prior_digest_rejected(self):
        with self.assertRaises(AssertionError):proof.validate_video_market_followup('index.html','0'*64)
        with self.assertRaises(AssertionError):proof.validate_video_market_followup('multi_market_price_collector.py','0'*64)

    def test_live_files_reread_after_success(self):
        original=Path.read_bytes
        for name in proof.EXPECTED['live_paths']:
            self.assertTrue(self.run_proof())
            def changed(path):
                raw=original(path)
                return raw+b'x' if path==proof.ROOT/name else raw
            with patch.object(Path,'read_bytes',changed),self.assertRaises(AssertionError):self.run_proof()

    def test_live_symlinks_rejected(self):
        original=Path.is_symlink
        for name in proof.EXPECTED['live_paths']:
            with patch.object(Path,'is_symlink',lambda p:p==proof.ROOT/name or original(p)),self.assertRaises(AssertionError):self.run_proof()

    def test_extra_source_delta_rejected(self):
        original=proof.git
        def changed(*args):
            raw=original(*args)
            return raw+b'other.py\0' if args[0]=='diff' else raw
        with patch.object(proof,'git',changed),self.assertRaises(AssertionError):self.run_proof()

    def test_forged_pin_and_device_or_data_claim_rejected(self):
        for field,value in [('physical_tablet_verified',True),('runtime_data_modified',True)]:
            e=copy.deepcopy(proof.EXPECTED);e[field]=value
            with patch.object(proof,'EXPECTED',e),self.assertRaises(AssertionError):self.run_proof()
        e=copy.deepcopy(proof.EXPECTED);e['files'][e['live_paths'][0]]['sha256']='0'*64
        with patch.object(proof,'EXPECTED',e),self.assertRaises(AssertionError):self.run_proof()

    def test_committed_head_mutation_rejected(self):
        original=proof.git
        def changed(*args):
            raw=original(*args)
            return raw+b'x' if args[0]=='show' and args[1].startswith('HEAD:') else raw
        with patch.object(proof,'git',changed),self.assertRaises(AssertionError):self.run_proof()

    def test_unrelated_original_sibling_not_relaxed(self):
        original=Path.read_bytes
        def changed(path):
            raw=original(path)
            return raw+b'x' if path==proof.ROOT/'update_exchange_rates.py' else raw
        with patch.object(Path,'read_bytes',changed),self.assertRaises(AssertionError):validate_fx_successor_v1014()
