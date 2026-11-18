"""Explain only the two exact watched V1018 descendants; never suppress unknown paths."""
from execution.workspace_review_successor_v1018 import validate_workspace_review_v1018
PATHS=frozenset(('index.html','verify_browser_runtime.js'))
def reviewed_workspace_scope_v1018(paths):
    result=set(paths)&PATHS
    for name in result:
        assert validate_workspace_review_v1018(name)
    return result
