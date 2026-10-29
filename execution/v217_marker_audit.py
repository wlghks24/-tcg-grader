"""Read-only V217 marker-spoof audit; never certifies runtime URL safety."""
from __future__ import annotations
import ast
import io
import tokenize

MARKERS = {
    "multi_route_event_discovery.py": ("MAX_PUBLIC_SEARCH_URL_CHARS = 1900", "def _bounded_bing_request(", "q, url = _bounded_bing_request("),
    "social_event_discovery.py": ("MAX_PUBLIC_SEARCH_URL_CHARS = 1900", "Google News query exceeds safe URL budget"),
    "collection_learning_hardening_v144.py": ("MAX_PUBLIC_SEARCH_URL_CHARS = 1900", "public social query exceeds safe URL budget"),
}

def inspect(relative: str, source: str) -> dict[str, object]:
    if relative not in MARKERS:
        return {"status": "OUT_OF_SCOPE", "safe": False}
    try:
        list(tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source)
    except (SyntaxError, tokenize.TokenError, IndentationError, UnicodeError) as exc:
        return {"status": "INVALID_SOURCE", "safe": False, "reason": type(exc).__name__}
    names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assignments = [node for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))]
    limit = any(
        isinstance(target, ast.Name) and target.id == "MAX_PUBLIC_SEARCH_URL_CHARS"
        and isinstance(value, ast.Constant) and type(value.value) is int and value.value == 1900
        for node in assignments
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        for value in [node.value]
    )
    expected = {
        "multi_route_event_discovery.py": "_bounded_bing_request",
        "social_event_discovery.py": "_google_news_url",
        "collection_learning_hardening_v144.py": "_v144_ddg_social_one",
    }[relative]
    has_call = (
        any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_bounded_bing_request"
            for fn in tree.body if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            and fn.name == "_bing_one" for n in ast.walk(fn))
        if relative == "multi_route_event_discovery.py" else True
    )
    if not limit or expected not in names or not has_call:
        return {"status": "MISSING_STRUCTURAL_GUARD", "safe": False,
                "limit_defined": limit, "function_defined": expected in names,
                "call_found": has_call}
    return {"status": "REVIEW_REQUIRED", "safe": False,
            "reason": "AST shape alone cannot prove bounded URL on every runtime path"}
