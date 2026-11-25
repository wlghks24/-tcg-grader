"""Exact retention source transition; does not grant deployment authority."""
import hashlib
from pathlib import Path
import re

NAME = 'execution/event_retention_20261123.py'
BASE = 'b76592b2435005314512a3bb4a14e3ebd3a497e8'
CANDIDATE = 'cbf53671310d0181e2aa35667fe9d51ff2d33781'
OLD = ('e21e2245f40ff738e254694f80e0ff10c5ecc28c', '889c309d10c69a696a1a1c7f50cc751d6efedc412c4f8bd9759292bc1b43b630', 7790)
NEW = ('be158663075bb557a5db0574eefd7b19f35e7b03', '9d2899038596f24a99db915d7a0d199768a0fdb72c38e13480881a7fb8bc7d55', 8096)


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def mode(pin):
    return ('100644 blob '+pin[0]+'\t'+NAME+'\0').encode()


def pinned(git, revision, pin):
    require(git('ls-tree','-z',revision,'--',NAME) == mode(pin), 'retention tree pin mismatch')
    raw = git('show',revision+':'+NAME)
    require((hashlib.sha256(raw).hexdigest(),len(raw)) == pin[1:], 'retention bytes pin mismatch')
    return raw


def _verify(root, git, read_current, previous, base, candidate, old, new, successor=None):
    require(all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (base,candidate)), 'unbound retention commit')
    require(git('rev-list','--parents','-n','1',candidate).decode().split() == [candidate,base], 'wrong retention parent')
    git('merge-base','--is-ancestor',candidate,'HEAD')
    require(git('diff','--no-renames','--name-only','-z',base,candidate) == NAME.encode()+b'\0', 'unexpected retention transition paths')
    require(pinned(git,base,old) == previous, 'wrong retention predecessor')
    reviewed = pinned(git,candidate,new)
    if successor is not None:
        next_base, next_candidate, next_pin = successor
        git('merge-base','--is-ancestor',candidate,next_base)
        return _verify(root,git,read_current,reviewed,next_base,next_candidate,new,next_pin)
    require(pinned(git,'HEAD',new) == reviewed, 'unreviewed committed retention source')
    root = Path(root)
    target = root/NAME
    require(all(not root.joinpath(*Path(NAME).parts[:i]).is_symlink() for i in range(1,len(Path(NAME).parts)+1)) and target.is_file(), 'unsafe live retention source')
    require(read_current(NAME) == reviewed, 'unreviewed live retention source')
    return reviewed


REENTRY = ('8717e817507327c7cccd171d4bbd74d4f040ecf6',
           'd31254c5ee1f82dcd14727bb94a6b1b53074ac00',
           ('29d0b8a92734486ea1ddeefa74fcccaea94f3a48', 'ee6efa29524d30378cf2ce1429871ce102aefb924d4438fd10bc4849c7d7417a', 9114))


def validate_future_marker_successor(root, git, read_current, previous):
    successor = None if git('ls-tree','-z','HEAD','--',NAME) == mode(NEW) else REENTRY
    return _verify(root,git,read_current,previous,BASE,CANDIDATE,OLD,NEW,successor)


def validate_retention_reentry_successor(root, git, read_current, previous):
    base, candidate, pin = REENTRY
    git('merge-base','--is-ancestor',CANDIDATE,base)
    return _verify(root,git,read_current,previous,base,candidate,NEW,pin)
