"""One live byte snapshot per outer proof request, discarded before the next.

This preserves V1002's single complete live scan when several historical
validators delegate to the same exact successor. Never cache trust across calls.
"""
from contextvars import ContextVar
from functools import wraps

_snapshot = ContextVar('event_proof_request_bytes', default=None)


def live_request(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _snapshot.get() is not None:
            return function(*args, **kwargs)
        token = _snapshot.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _snapshot.reset(token)
    return wrapped


def read_live(path):
    snapshot = _snapshot.get()
    if snapshot is None:
        return path.read_bytes()
    if path not in snapshot:
        snapshot[path] = path.read_bytes()
    return snapshot[path]
