"""V1035 exact repository metadata/source sync; no CI or device approval."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from execution.tests.test_tablet_sync_successor_v1034 import validate_v1034_sync

ROOT = Path(__file__).resolve().parents[2]
BASE = '9b96d702e128f65afc0b4ef80e288f2ab86a409c'
CANDIDATE = 'cbf53671310d0181e2aa35667fe9d51ff2d33781'
PREVIOUS = 'ebe077c18aee08b8466f4cd7f2b41216f3b3d813'
NAME = 'execution/event_retention_20261123.py'
FILES = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1035.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1035_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1035.json","execution/tests/test_tablet_sync_successor_v1035.py"]
PRIOR = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1034.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1034_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1034.json"]
META = {"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1035.json":"8b45e1db15a90000bf927ea15881c094ae69771d4d76996a6c9f5f892850bc1a","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1035_delta.json":"9fc748d788647767c324d0ffa62b9584daec364e6a8f3aab3b0f3b6408936216","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1035.json":"d349de2f17f7d7ea276bee02e8e0ad538be750fcebbe5bda1d7151418ed638ae"}
PRIOR_META = {"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1034.json":"f4e309a86424e1aa2c366cb08b090981eb231782d0091216c42280e46bb53652","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1034_delta.json":"12a3b8c99590445158da7394a2dc73883f5b804a888e6ff7bf6f44b1b4dc0f87","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1034.json":"3a182b927fa71ce9f3f828dde865af2544af12e952c21d2ffbbae6b305cdaec3"}
PINS = {"execution/event_retention_20261123.py":{"blob":"be158663075bb557a5db0574eefd7b19f35e7b03","sha256":"9d2899038596f24a99db915d7a0d199768a0fdb72c38e13480881a7fb8bc7d55","bytes":8096},"execution/official_cinema_news_20261123.py":{"blob":"87dc3db03a1e936b7d481756642f550b0181e138","sha256":"3c1164d331b9c950ff91f8789345f68e4c185bd16f03ca29edc6ea67ac3fe6e8","bytes":14529},"execution/official_event_watchlist_20261123.py":{"blob":"ca54669b53e6649acd7ab16fe3da800152e27e0a","sha256":"5cb49e0dd1e055e7351d8fae9b9d18eee4a5ecb9607eff114228c2ccb8c2825d","bytes":2893},"execution/tablet_event_filters_20261122.py":{"blob":"aeaceba7a2d38827fb16265098c830362dd26852","sha256":"038ce693133651dd31076166ea6abecc4e6858d0ab6b1ab76a035d6c796d7cb2","bytes":6278},"execution/tablet_event_refresh_20261123.js":{"blob":"e92cfa3ddc18632c06dbf733cc857b4dd6410816","sha256":"b83bf4c2470807ec02fb7a94d4787a2cb08f11742d5f502f0c368a5f09201228","bytes":5442},"execution/tablet_event_summary_v890.py":{"blob":"6982e96a172224f396f08c3eb8ed0a6f758437b9","sha256":"8ae8c5ea6cd53f9ba01bbcc7a284687aa241c4133935912e26591ef23280f6af","bytes":9298},"execution/tablet_menu_shell_v903.js":{"blob":"b741b7dcd633c8bb94e5fa7dc8e5c6c092c6123f","sha256":"d612179f89f97cd92fe331ec8efd6532cb80883352a4960136adfdd43de899a1","bytes":25070},"execution/tablet_menu_shell_v903.py":{"blob":"1cb0c97ea99c03ded1706858ed0ce7ee672c3242","sha256":"69c7532847cd8c11e4fc733ca38e35f73afd6a955ab0df1bb901c50d067c1742","bytes":31035},"execution/tablet_workspace_truth_20261123.py":{"blob":"5708d7bf64d2c82e174237ec779758a22009e971","sha256":"22aa112e635010c18db283e177a97cd224fc049ddeeaf4d40bcf3550750b17d6","bytes":2539},"multi_market_price_collector.py":{"blob":"6de4171fc595e45c42dfd1e11d261eb1258c98b1","sha256":"dc0c157fc3408310124a486f465aea5cc6c0ab6d3247c147c5b073c2bc95be6c","bytes":61837},"tablet_autonomy_dashboard_v400.js":{"blob":"068eb20aace21b5324dff0a9bc0117bf0659a0f6","sha256":"d330172107e4870880b8d77d8117ce944264a6f84baf869b339c04be501fddab","bytes":83660},"update_promo_events.py":{"blob":"5cae5ea6b1887da4731cc02d7ca0813a2188f9ba","sha256":"50d6ef03e6aab4f27a623a2dc5718b8622cb06ead80cd4fd1f7cc0e60115e2c7","bytes":78247}}


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def git(*args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=ROOT, timeout=90)


def live(name):
    p = ROOT/name
    require(all(not ROOT.joinpath(*Path(name).parts[:i]).is_symlink() for i in range(1,len(Path(name).parts)+1)) and p.is_file(), 'unsafe path: '+name)
    return p.read_bytes()


def load(name, digest):
    raw = live(name)
    require(hashlib.sha256(raw).hexdigest() == digest, 'metadata pin: '+name)
    return json.loads(raw)


def watched(contract, older, newer):
    w=contract['freshness_watch']
    names=git('diff','--no-renames','--name-only','-z',older,newer).decode().split('\0')
    return sorted(p for p in names if p and p not in w['exclude_paths'] and (p in w['exact_paths'] or p.startswith(tuple(w['path_prefixes']))))


def check_source(contract):
    for a,b in ((BASE,CANDIDATE),(PREVIOUS,CANDIDATE),(CANDIDATE,'HEAD')):
        git('merge-base','--is-ancestor',a,b)
    require(watched(contract,BASE,CANDIDATE)==sorted(PINS),'candidate watched scope')
    require(watched(contract,PREVIOUS,CANDIDATE)==[NAME],'unexpected V1034 transition')
    require(watched(contract,CANDIDATE,'HEAD')==[],'new watched change requires successor')
    for name,pin in PINS.items():
        entry=('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
        raw=git('show',CANDIDATE+':'+name)
        require((hashlib.sha256(raw).hexdigest(),len(raw))==(pin['sha256'],pin['bytes']),'source digest: '+name)
        require(git('ls-tree','-z',CANDIDATE,'--',name)==entry==git('ls-tree','-z','HEAD','--',name),'source tree: '+name)
        require(live(name)==raw==git('show','HEAD:'+name),'live source: '+name)


def validate_v1035():
    prior,old_delta,old_receipt=(load(n,PRIOR_META[n]) for n in PRIOR)
    for name in PRIOR:
        require(git('show',CANDIDATE+':'+name)==live(name),'prior source metadata changed')
    c,d,r=(load(n,META[n]) for n in FILES[:3])
    require(c['prior_contract']==PRIOR[0] and c['prior_delta_snapshot']==PRIOR[1], 'prior lineage')
    require([c['delta_snapshot'],c['receiver_receipt'],c['verification_test']]==FILES[1:],'generation paths')
    for k in ('schema_version','rules','share_policy','current_required_merge_prs'):
        require(c[k]==prior[k],'policy: '+k)
    w=copy.deepcopy(prior['freshness_watch'])
    w['exclude_paths']=sorted(set(w['exclude_paths'])|set(FILES))
    require(c['freshness_watch']==w,'watch policy drift')
    require(c['prior_required_lesson_count']==prior['current_required_lesson_count'] and c['delta_required_lesson_count']==len(d['lessons'])==1 and c['current_required_lesson_count']==c['prior_required_lesson_count']+1,'lesson counts')
    q=c['candidate_sync']
    require(q['base_main_sha']==d['source_main_sha']==r['source_main_sha']==BASE,'base')
    require(q['candidate_commit']==q['functional_candidate_commit']==CANDIDATE,'candidate')
    require(q['generation_files']==FILES and q['watched_paths']==sorted(PINS),'candidate scope')
    require(q['requires_exact_watched_path_match'] is True and q['post_merge_coverage_allowed'] is True,'scope flags')
    for k,field in (('reviewed_blobs','blob'),('reviewed_sha256','sha256'),('reviewed_bytes','bytes')):
        require(q[k]=={n:p[field] for n,p in PINS.items()},'candidate pins: '+k)
    digest=hashlib.sha256(json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(d['prior_delta']==PRIOR[1] and d['prior_lesson_digest_sha256']==r['prior_lesson_digest_sha256']==old_delta['lesson_digest_sha256'],'prior lesson digest')
    require(digest==d['lesson_digest_sha256']==r['delta_lesson_digest_sha256'],'lesson digest')
    require(r['accepted_lesson_ids']==[x['lesson_id'] for x in d['lessons']] and r['source_snapshots']==[FILES[1]],'receipt lessons')
    require(d['covered_merges']==[] and d['share_policy']==old_delta['share_policy'] and r['alignment_policy']==old_receipt['alignment_policy'],'merge or policy drift')
    v=r['verification']
    require(r['status']=='SYNCED_VERIFIED' and v['verified_result']=='TABLET_GPT_TCG_GRADER_MATCH' and v['contract_version']=='v1035' and v['verification_test']==FILES[3],'receipt metadata')
    require(v['device_reverification_required'] is True,'device recheck required')
    for k in ('source_code_and_fixture_review_verified','physical_tablet_runtime_verified','physical_drive_readback_verified','model_training_authorized','raw_grading_calibration_modified','main_merge_authorized'):
        require(v[k] is False,'false approval: '+k)
    require(validate_v1034_sync()==sorted(PINS),'previous source proof')
    check_source(c)
    return sorted(PINS)


class TabletSyncV1035Tests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(sorted(PINS),validate_v1035())

    def test_metadata_tamper(self):
        original=live
        for name in FILES[:3]+PRIOR:
            with self.subTest(name=name),patch(__name__+'.live',side_effect=lambda n:original(n)+(b' ' if n==name else b'')),self.assertRaises(AssertionError):
                validate_v1035()

    def test_extra_watched_change(self):
        original=watched
        with patch(__name__+'.watched',side_effect=lambda c,a,b:original(c,a,b)+(['update_promo_events.py'] if a==CANDIDATE and b=='HEAD' else [])),self.assertRaises(AssertionError):
            validate_v1035()

    def test_live_tamper(self):
        original=live
        with patch(__name__+'.live',side_effect=lambda n:original(n)+(b'x' if n==NAME else b'')),self.assertRaises(AssertionError):
            validate_v1035()

    def test_committed_tamper(self):
        original=git
        with patch(__name__+'.git',side_effect=lambda *a:original(*a)+(b'x' if a==('show','HEAD:'+NAME) else b'')),self.assertRaises(AssertionError):
            validate_v1035()

    def test_missing_history(self):
        original=git
        def fail(*args):
            if args[:2]==('merge-base','--is-ancestor'):
                raise subprocess.CalledProcessError(1,args)
            return original(*args)
        with patch(__name__+'.git',side_effect=fail),self.assertRaises(subprocess.CalledProcessError):
            validate_v1035()


if __name__=='__main__': unittest.main()
