"""Exact source review for the existing registry/collection ordering repair."""
import hashlib,json
from pathlib import Path
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read, immutable_source_evidence
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=json.loads(r'''{"baseline_commit": "0f37a466e6b57aa68c600159eb733aea081c7471", "candidate_commit": "9887b8387c002e33cfe87b93d341d55213c8d8c0", "baseline": {"auto_update_all.py": {"blob": "97c710bc13987f55a179954f596c39b3972f075a", "sha256": "0c294e1bb1d41c51448f6e0b94fb2f33f6dff1866ae7eea4ed440d165abe8ba7", "bytes": 79767}}, "files": {"auto_update_all.py": {"blob": "8fcf51686dde7ec05fe23329fdb4ebdccdbe5a62", "sha256": "d99eb90a5b617d6eb0e8eca0c144c0d53be320c525cf22d363faddb4b3148da1", "bytes": 80176}, "execution/tests/test_registry_cycle_boundary_20261128.py": {"blob": "0d58961619d401b8e3c0c62e51072265cec02ff3", "sha256": "4f410a4f187e8f65b78d779b5cc6839e43c556ae7c64a219688b9e14eac189ee", "bytes": 2889}, "integrity_manifest.json": {"blob": "e95bd141bf569f4f2aa64585925607d7a7c32d7f", "sha256": "8d5fa35a43fb8f121b252c4971928b682cdee9107ba4a0b8f685e7d83ff602ba", "bytes": 324110}, "test_grading_self_learning.py": {"blob": "b1700ba66756fbd4dc5e4f281122a2f6fb50e8b7", "sha256": "ac3c9cd257b72fe15cf8d2bb18b55ddf93efae624d6c6caae08a336e18cac6a5", "bytes": 10262}}}''')
def git(*args): return read(ROOT,*args)
def pinned(ref,name,pin):
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode(),name
    raw=git('show',ref+':'+name)
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],name
    return raw
@head_validation_request(share_objects=True)
def validate_registry_cycle_successor(prior_digest):
    e=EXPECTED
    assert prior_digest==e['baseline']['auto_update_all.py']['sha256'],'wrong historical source'
    rows=immutable_source_evidence(ROOT,e,git,pinned)
    git('merge-base','--is-ancestor',e['candidate_commit'],'HEAD')
    manifest_path=ROOT/'integrity_manifest.json'
    assert not manifest_path.is_symlink()
    raw=manifest_path.read_bytes()
    assert git('show','HEAD:integrity_manifest.json')==raw,'uncommitted manifest'
    manifest=json.loads(raw)['files']
    for name in e['files']:
        if name=='integrity_manifest.json': continue
        p=ROOT/name
        assert p.is_file() and not p.is_symlink() and not p.parent.is_symlink(),name
        assert p.read_bytes()==rows[name],name
        assert pinned('HEAD',name,e['files'][name])==rows[name],name
        pin=e['files'][name]
        assert manifest[name]=={'bytes':pin['bytes'],'sha256':pin['sha256']},name
    name='execution/registry_cycle_successor_20261128.py'
    assert (ROOT/name).is_file() and not (ROOT/name).is_symlink()
    raw=(ROOT/name).read_bytes()
    assert git('show','HEAD:'+name)==raw,'uncommitted review source'
    assert manifest[name]=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    return True
