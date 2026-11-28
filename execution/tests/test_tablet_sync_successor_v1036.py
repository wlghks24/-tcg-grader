"""V1036 exact retention reentry sync; source evidence only, not release approval."""
import copy
from execution.git_validation_cache import head_validation_request
from execution.tablet_tool_recovery_successor_20261127 import reviewed_tool_descendants
import hashlib
import json
import unittest
from unittest.mock import patch
from execution.tests.test_tablet_sync_successor_v1035 import (
    ROOT, BASE, CANDIDATE as PREVIOUS, NAME, git, live, load, require, watched, validate_v1035,
)

CANDIDATE = 'd31254c5ee1f82dcd14727bb94a6b1b53074ac00'
FILES = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1036.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1036_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1036.json","execution/tests/test_tablet_sync_successor_v1036.py"]
PRIOR = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1035.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1035_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1035.json"]
META = {"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1036.json":"aa6204511a70e8066c3469625aafd6a326df3569dd6c0ae6719f6d222e3eb91d","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1036_delta.json":"bf6cbe87ba337a73354c12f8d376663dafa71e8f3b5fa383ab8cf2753dd2c175","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1036.json":"c0d798795a90e8b0cc0c6add26c49df1618715dfe31585f5f0f82ffeb3913115"}
PRIOR_META = {"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1035.json":"8b45e1db15a90000bf927ea15881c094ae69771d4d76996a6c9f5f892850bc1a","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1035_delta.json":"9fc748d788647767c324d0ffa62b9584daec364e6a8f3aab3b0f3b6408936216","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1035.json":"d349de2f17f7d7ea276bee02e8e0ad538be750fcebbe5bda1d7151418ed638ae"}
PINS = {"execution/event_retention_20261123.py":{"blob":"29d0b8a92734486ea1ddeefa74fcccaea94f3a48","sha256":"ee6efa29524d30378cf2ce1429871ce102aefb924d4438fd10bc4849c7d7417a","bytes":9114},"execution/official_cinema_news_20261123.py":{"blob":"87dc3db03a1e936b7d481756642f550b0181e138","sha256":"3c1164d331b9c950ff91f8789345f68e4c185bd16f03ca29edc6ea67ac3fe6e8","bytes":14529},"execution/official_event_watchlist_20261123.py":{"blob":"ca54669b53e6649acd7ab16fe3da800152e27e0a","sha256":"5cb49e0dd1e055e7351d8fae9b9d18eee4a5ecb9607eff114228c2ccb8c2825d","bytes":2893},"execution/tablet_event_filters_20261122.py":{"blob":"aeaceba7a2d38827fb16265098c830362dd26852","sha256":"038ce693133651dd31076166ea6abecc4e6858d0ab6b1ab76a035d6c796d7cb2","bytes":6278},"execution/tablet_event_refresh_20261123.js":{"blob":"e92cfa3ddc18632c06dbf733cc857b4dd6410816","sha256":"b83bf4c2470807ec02fb7a94d4787a2cb08f11742d5f502f0c368a5f09201228","bytes":5442},"execution/tablet_event_summary_v890.py":{"blob":"6982e96a172224f396f08c3eb8ed0a6f758437b9","sha256":"8ae8c5ea6cd53f9ba01bbcc7a284687aa241c4133935912e26591ef23280f6af","bytes":9298},"execution/tablet_menu_shell_v903.js":{"blob":"b741b7dcd633c8bb94e5fa7dc8e5c6c092c6123f","sha256":"d612179f89f97cd92fe331ec8efd6532cb80883352a4960136adfdd43de899a1","bytes":25070},"execution/tablet_menu_shell_v903.py":{"blob":"1cb0c97ea99c03ded1706858ed0ce7ee672c3242","sha256":"69c7532847cd8c11e4fc733ca38e35f73afd6a955ab0df1bb901c50d067c1742","bytes":31035},"execution/tablet_workspace_truth_20261123.py":{"blob":"5708d7bf64d2c82e174237ec779758a22009e971","sha256":"22aa112e635010c18db283e177a97cd224fc049ddeeaf4d40bcf3550750b17d6","bytes":2539},"multi_market_price_collector.py":{"blob":"6de4171fc595e45c42dfd1e11d261eb1258c98b1","sha256":"dc0c157fc3408310124a486f465aea5cc6c0ab6d3247c147c5b073c2bc95be6c","bytes":61837},"tablet_autonomy_dashboard_v400.js":{"blob":"068eb20aace21b5324dff0a9bc0117bf0659a0f6","sha256":"d330172107e4870880b8d77d8117ce944264a6f84baf869b339c04be501fddab","bytes":83660},"update_promo_events.py":{"blob":"5cae5ea6b1887da4731cc02d7ca0813a2188f9ba","sha256":"50d6ef03e6aab4f27a623a2dc5718b8622cb06ead80cd4fd1f7cc0e60115e2c7","bytes":78247}}


@head_validation_request(share_objects=True)
def validate_v1036():
    prior, old_delta, old_receipt = (load(n, PRIOR_META[n]) for n in PRIOR)
    for name in PRIOR:
        require(git('show', CANDIDATE+':'+name)==live(name), 'prior metadata changed')
    c,d,r = (load(n, META[n]) for n in FILES[:3])
    require(c['prior_contract']==PRIOR[0] and c['prior_delta_snapshot']==PRIOR[1], 'prior lineage')
    require([c['delta_snapshot'],c['receiver_receipt'],c['verification_test']]==FILES[1:], 'generation paths')
    for k in ('schema_version','rules','share_policy','current_required_merge_prs'):
        require(c[k]==prior[k], 'policy: '+k)
    w=copy.deepcopy(prior['freshness_watch'])
    w['exclude_paths']=sorted(set(w['exclude_paths'])|set(FILES))
    require(c['freshness_watch']==w, 'watch policy drift')
    require(c['prior_required_lesson_count']==prior['current_required_lesson_count'] and
            c['delta_required_lesson_count']==len(d['lessons'])==1 and
            c['current_required_lesson_count']==c['prior_required_lesson_count']+1, 'lesson counts')
    q=c['candidate_sync']
    require(q['base_main_sha']==d['source_main_sha']==r['source_main_sha']==BASE, 'base')
    require(q['candidate_commit']==q['functional_candidate_commit']==CANDIDATE, 'candidate')
    require(q['generation_files']==FILES and q['watched_paths']==sorted(PINS), 'candidate scope')
    require(q['requires_exact_watched_path_match'] is True and q['post_merge_coverage_allowed'] is True, 'scope flags')
    for k,field in (('reviewed_blobs','blob'),('reviewed_sha256','sha256'),('reviewed_bytes','bytes')):
        require(q[k]=={n:p[field] for n,p in PINS.items()}, 'source pins: '+k)
    digest=hashlib.sha256(json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(d['prior_delta']==PRIOR[1] and d['prior_lesson_digest_sha256']==r['prior_lesson_digest_sha256']==old_delta['lesson_digest_sha256'], 'prior digest')
    require(digest==d['lesson_digest_sha256']==r['delta_lesson_digest_sha256'], 'lesson digest')
    require(r['accepted_lesson_ids']==[x['lesson_id'] for x in d['lessons']] and r['source_snapshots']==[FILES[1]], 'receipt lessons')
    require(d['covered_merges']==[] and d['share_policy']==old_delta['share_policy'] and r['alignment_policy']==old_receipt['alignment_policy'], 'policy drift')
    v=r['verification']
    require(r['status']=='SYNCED_VERIFIED' and v['verified_result']=='TABLET_GPT_TCG_GRADER_MATCH' and v['contract_version']=='v1036' and v['verification_test']==FILES[3], 'receipt metadata')
    require(v['device_reverification_required'] is True, 'device recheck required')
    for k in ('source_code_and_fixture_review_verified','physical_tablet_runtime_verified','physical_drive_readback_verified','model_training_authorized','raw_grading_calibration_modified','main_merge_authorized'):
        require(v[k] is False, 'false approval: '+k)
    require(validate_v1035()==sorted(PINS), 'previous generation')
    for older,newer in ((BASE,CANDIDATE),(PREVIOUS,CANDIDATE),(CANDIDATE,'HEAD')):
        git('merge-base','--is-ancestor',older,newer)
    require(watched(c,BASE,CANDIDATE)==sorted(PINS), 'candidate watched scope')
    require(watched(c,PREVIOUS,CANDIDATE)==[NAME], 'unexpected transition')
    post = watched(c,CANDIDATE,'HEAD')
    delegated = reviewed_tool_descendants(post, PINS, repo=ROOT, reader=git, current=live)
    require([name for name in post if name not in delegated]==[], 'unreviewed watched change')
    for name,pin in PINS.items():
        entry=('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
        raw=git('show',CANDIDATE+':'+name)
        require((hashlib.sha256(raw).hexdigest(),len(raw))==(pin['sha256'],pin['bytes']), 'source digest: '+name)
        require(git('ls-tree','-z',CANDIDATE,'--',name)==entry, 'candidate source tree: '+name)
        if name in delegated:
            require(live(name)==git('show','HEAD:'+name), 'uncommitted UI descendant: '+name)
        else:
            require(git('ls-tree','-z','HEAD','--',name)==entry, 'source tree: '+name)
            require(live(name)==raw==git('show','HEAD:'+name), 'live source: '+name)
    return sorted(PINS)


class TabletSyncV1036Tests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(sorted(PINS),validate_v1036())

    def test_extra_watched_change(self):
        original=watched
        with patch(__name__+'.watched',side_effect=lambda c,a,b:original(c,a,b)+(['update_promo_events.py'] if a==CANDIDATE and b=='HEAD' else [])),self.assertRaises(AssertionError):
            validate_v1036()

    def test_live_tamper(self):
        original=live
        with patch(__name__+'.live',side_effect=lambda n:original(n)+(b'x' if n==NAME else b'')),self.assertRaises(AssertionError):
            validate_v1036()

    def test_committed_tamper(self):
        original=git
        with patch(__name__+'.git',side_effect=lambda *a:original(*a)+(b'x' if a==('show','HEAD:'+NAME) else b'')),self.assertRaises(AssertionError):
            validate_v1036()

    def test_metadata_tamper(self):
        original=load
        with patch(__name__+'.load',side_effect=lambda n,d:original(n,'0'*64 if n==FILES[0] else d)),self.assertRaises(AssertionError):
            validate_v1036()


if __name__=='__main__': unittest.main()
