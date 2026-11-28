"""Exact official-event discovery and user-requested retention successor; source proof, never device approval."""
from pathlib import Path
import hashlib
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git, immutable_source_evidence
ROOT=Path(__file__).resolve().parents[1]
from execution.event_validation_reads_20261123 import live_request, read_live
EXPECTED = {'baseline_commit': '87b89076743a341f2713fc551fe2a02755497f6e',
 'candidate_commit': '73c467e7aaf126d4aab007c836131f32f6bbb170',
 'baseline': {'update_promo_events.py': {'blob': 'c739d3a9644bc0adff75937e1c9b7456267b3b66',
                                         'sha256': '8507270fc9c76f04dfaff26b20aca7ee0a2c05c32a86f110a33ad46f2641bc04',
                                         'bytes': 74267},
              'execution/tablet_event_summary_v890.py': {'blob': '4179e49d1cd6217638bc57df690b63f8adbba52e',
                                                         'sha256': '3f655b09b9cb07f161aa44b64d73ea73437a9c189083a82d2896a7703c531030',
                                                         'bytes': 8372},
              'execution/tablet_menu_shell_v903.py': {'blob': '1aba857abe5aae220feb71627f7b9b9a8e7ad7fe',
                                                      'sha256': 'ce484eed95e9ebb0cc9c02896292248522b3d9c53b92b7fe1c315526f3192679',
                                                      'bytes': 30792},
              'execution/tablet_event_filters_20261122.py': {'blob': '6714e081125be07e08dea398e0fb2cedaad713b5',
                                                             'sha256': '6620931085feb7efffc31ca7c5a3530564d6ab03dd83a8f2c85fec8785b89fd1',
                                                             'bytes': 4326}},
 'files': {'execution/event_retention_20261123.py': {'blob': '261c85c50e79f9a5a031294521ca8c4017be8dad',
                                                     'sha256': '2c365a4127ea6dd2ca40800605e7eeb94e4404b48863a15b4645a74fd31254c5',
                                                     'bytes': 4923},
           'execution/official_cinema_news_20261123.py': {'blob': '87dc3db03a1e936b7d481756642f550b0181e138',
                                                          'sha256': '3c1164d331b9c950ff91f8789345f68e4c185bd16f03ca29edc6ea67ac3fe6e8',
                                                          'bytes': 14529},
           'execution/official_event_watchlist_20261123.py': {'blob': 'ca54669b53e6649acd7ab16fe3da800152e27e0a',
                                                              'sha256': '5cb49e0dd1e055e7351d8fae9b9d18eee4a5ecb9607eff114228c2ccb8c2825d',
                                                              'bytes': 2893},
           'execution/tablet_event_filters_20261122.py': {'blob': 'aeaceba7a2d38827fb16265098c830362dd26852',
                                                          'sha256': '038ce693133651dd31076166ea6abecc4e6858d0ab6b1ab76a035d6c796d7cb2',
                                                          'bytes': 6278},
           'execution/tablet_event_refresh_20261123.js': {'blob': 'e92cfa3ddc18632c06dbf733cc857b4dd6410816',
                                                          'sha256': 'b83bf4c2470807ec02fb7a94d4787a2cb08f11742d5f502f0c368a5f09201228',
                                                          'bytes': 5442},
           'execution/tablet_event_summary_v890.py': {'blob': '6982e96a172224f396f08c3eb8ed0a6f758437b9',
                                                      'sha256': '8ae8c5ea6cd53f9ba01bbcc7a284687aa241c4133935912e26591ef23280f6af',
                                                      'bytes': 9298},
           'execution/tablet_menu_shell_v903.py': {'blob': '1cb0c97ea99c03ded1706858ed0ce7ee672c3242',
                                                   'sha256': '69c7532847cd8c11e4fc733ca38e35f73afd6a955ab0df1bb901c50d067c1742',
                                                   'bytes': 31035},
           'execution/tests/test_event_collection_pipeline_20261123.py': {'blob': 'd1080f43693093a4c9c5d71855a66df3f023aadb',
                                                                          'sha256': '197e8d20faf81f38fb86ca9b532db1c097dd3dc21fe9f2c5ed1ada96f75ee319',
                                                                          'bytes': 7497},
           'execution/tests/test_event_retention_20261123.py': {'blob': '5541b5276f10aa1f4423f73585cd54ca7e4ad23a',
                                                                'sha256': '10f65dbb186b9c31fcbf5e3a818033723ef78c933f7c935444cb11446f83e520',
                                                                'bytes': 8110},
           'execution/tests/test_official_cinema_news_20261123.py': {'blob': 'a067d9ad43923e73bec08c82e33fdbeaa947d202',
                                                                     'sha256': '8295c6e75e5417419eb8fed8cbcda0deb17ce614042c2565be32e0d08d2d0955',
                                                                     'bytes': 14266},
           'execution/tests/test_tablet_event_refresh_20261123.js': {'blob': '67ad08f1038ad8c5f2a557868ada6548b9cdf8e3',
                                                                     'sha256': '25f0efb02cf04b80e4c2c63541937711f6a48bc071d270b66c8f74a95066319a',
                                                                     'bytes': 6416},
           'execution/tests/test_tablet_event_refresh_20261123.py': {'blob': 'c8cdbdb5ecf4d5a279b1a8fadcead5205a574007',
                                                                     'sha256': '32523f6299a4a9908a14586c4177790852e6642da0c11fb49419cc0e7b1d137f',
                                                                     'bytes': 4877},
           'integrity_manifest.json': {'blob': 'a7ee0dc64ff202eaa4500450a7790771ab939ade',
                                       'sha256': 'cc868057a3c29c10c7a756b34f9aace8aabcca2a91c47d125653bd556dafea5d',
                                       'bytes': 315910},
           'test_grading_self_learning.py': {'blob': '8d43ff6c8c6be16f3e899b4ce580a6e1f32c49c9',
                                             'sha256': '461ee08c6ec33ca13bd4d7856993a1eaf4514c49965454a24b9ec5c3d88c7acf',
                                             'bytes': 9051},
           'update_promo_events.py': {'blob': '5cae5ea6b1887da4731cc02d7ca0813a2188f9ba',
                                      'sha256': '50d6ef03e6aab4f27a623a2dc5718b8622cb06ead80cd4fd1f7cc0e60115e2c7',
                                      'bytes': 78247}},
 'live_paths': ['update_promo_events.py',
                'execution/tablet_event_summary_v890.py',
                'execution/tablet_menu_shell_v903.py',
                'execution/tablet_event_filters_20261122.py',
                'execution/event_retention_20261123.py',
                'execution/official_cinema_news_20261123.py',
                'execution/official_event_watchlist_20261123.py',
                'execution/tablet_event_refresh_20261123.js'],
 'physical_tablet_verified': False,
 'runtime_data_modified': False}

def git(*args):return read_git(ROOT,*args)

def pinned(ref,name,pin):
    raw=git('show',ref+':'+name)
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    return raw

@head_validation_request()
@live_request
def validate_events_collection_successor(name,prior_digest):
    e=EXPECTED
    assert name in e['baseline'] and prior_digest==e['baseline'][name]['sha256']
    base,candidate=e['baseline_commit'],e['candidate_commit']
    reviewed_files=immutable_source_evidence(ROOT,e,git,pinned)
    git('merge-base','--is-ancestor',candidate,'HEAD')
    for path in e['live_paths']:
        pin=e['files'][path];reviewed=reviewed_files[path]
        target=ROOT/path
        assert target.is_file() and not target.is_symlink()
        current=read_live(target)
        if path=='execution/tablet_menu_shell_v903.py' and current!=reviewed:
            assert git('show','HEAD:'+path)==current
            from execution.tablet_tool_recovery_successor_20261127 import validate_tablet_tool_recovery
            assert validate_tablet_tool_recovery(path,pin['sha256'],repo=ROOT)
        elif path=='execution/event_retention_20261123.py' and current!=reviewed:
            assert git('show','HEAD:'+path)==current
            from execution.retention_reentry_successor_20261123 import validate_retention_reentry_successor
            assert validate_retention_reentry_successor(path,pin['sha256'])
        else:
            assert pinned('HEAD',path,pin)==reviewed
            assert current==reviewed
    assert e['physical_tablet_verified'] is False and e['runtime_data_modified'] is False
    return True
