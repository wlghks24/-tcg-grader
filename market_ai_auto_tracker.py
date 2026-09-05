#!/usr/bin/env python3
"""Market-focused AI auto tracker with bounded, fail-closed self-healing.

This module is the market/price reliability observer for wlghks24/-tcg-grader.
It does not generate source code from web/search/error text. It combines:
- deterministic market integration invariants,
- existing Main SELFREFINE error/research ledgers,
- bounded known-repair rules,
- local rollback when a repair cannot be re-verified,
- strict changed-file allowlisting before any GitHub workflow may publish a repair.

External documentation influenced the design, but runtime web text is advisory only.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, atomic_write_text, safe_read_text

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "MARKET_AI_TRACKER_REPORT.json"
STATE = ROOT / "MARKET_AI_TRACKER_STATE.json"
SCHEMA = 1
MAX_FINDINGS = 200
MAX_OUTPUT = 12_000

DESIGN_REFERENCES = {
    "github_actions_security": "https://docs.github.com/en/code-security/tutorials/secure-your-organization/protect-against-threats",
    "github_rest_rate_limits": "https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api",
    "github_rest_best_practices": "https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api",
    "github_actions_concurrency": "https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency",
    "github_actions_schedule": "https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows",
    "github_pages_build_api": "https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build",
}

MARKET_PATH_HINTS = (
    "market", "price", "pricing", "valuation", "sold", "sale", "collector",
    "kream", "snkrdunk", "pricecharting", "justtcg", "pavilion", "tcgdex",
)
MARKET_REQUIRED_FILES = (
    "multi_market_price_collector.py",
    "multi_market_prices.js",
    "multi_market_prices.css",
    "index.html",
    "tcg_updater.py",
)
AUTO_REPAIR_PATHS = {
    "index.html",
    "tcg_updater.py",
    ".gitignore",
}
TRACKER_WORKFLOW = ".github/workflows/market-ai-auto-tracker.yml"
CSS_TAG_RE = re.compile(
    r"""<link\b[^>]*\bhref=["']multi_market_prices\.css(?:\?[^"']*)?["'][^>]*>""",
    re.IGNORECASE,
)
JS_TAG_RE = re.compile(
    r"""<script\b[^>]*\bsrc=["']multi_market_prices\.js(?:\?[^"']*)?["'][^>]*>\s*</script>""",
    re.IGNORECASE,
)
ROUTE_MARKER = "if path=='/api/multi-market-prices':"
STATIC_ANCHOR = "'auto_market_center.js','auto_market_center.css'"
STATIC_WITH_MARKET = (
    "'auto_market_center.js','auto_market_center.css',"
    "'multi_market_prices.js','multi_market_prices.css'"
)
ROUTE_ANCHOR = "        if path=='/api/grading-proxy-costs':\n"
ROUTE_BLOCK = """        if path=='/api/multi-market-prices':
            qs=parse_qs(parsed.query)
            q=(qs.get('q',[''])[0] or '')[:160]
            region=(qs.get('region',['ALL'])[0] or 'ALL')[:8]
            game=(qs.get('game',['ALL'])[0] or 'ALL')[:40]
            force=qs.get('force',['0'])[0]=='1'
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처','items':[]},403)
            try:
                from multi_market_price_collector import search_multi_market
                return self.json(search_multi_market(q,region=region,game=game,force=force))
            except Exception:
                return self.json({'ok':False,'error':'다중마켓 시세수집 엔진 오류','items':[]},500)
"""
REPAIRABLE_CODES = {
    "MARKET_CSS_ASSET_MISSING",
    "MARKET_CSS_ASSET_DUPLICATE",
    "MARKET_JS_ASSET_MISSING",
    "MARKET_JS_ASSET_DUPLICATE",
    "MARKET_STATIC_ALLOWLIST_MISSING",
    "MARKET_API_ROUTE_MISSING",
    "MARKET_TRACKER_GITIGNORE_MISSING",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _finding(
    code: str,
    path: str,
    message: str,
    *,
    severity: str = "error",
    repairable: bool = False,
    evidence: str = "",
) -> dict[str, Any]:
    raw = f"{code}|{path}|{message}|{evidence[:400]}"
    return {
        "signature": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20],
        "code": code,
        "path": path,
        "message": message[:500],
        "severity": severity,
        "repairable": bool(repairable),
        "evidence": " ".join(str(evidence).split())[:800],
    }


def _read(path: Path, *, max_bytes: int = 4_000_000) -> str:
    return safe_read_text(path, max_bytes=max_bytes)


def _strict_json(path: Path) -> tuple[bool, str]:
    try:
        text = _read(path, max_bytes=20_000_000)
        json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ))
        return True, ""
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        return False, type(exc).__name__ + ": " + str(exc)[:300]


def _compile_python(path: Path) -> tuple[bool, str]:
    try:
        text = _read(path)
        ast.parse(text, filename=path.name)
        return True, ""
    except (OSError, UnicodeError, SyntaxError, ValueError, MemoryError) as exc:
        return False, type(exc).__name__ + ": " + str(exc)[:300]


def _market_related_path(relative: str) -> bool:
    low = str(relative).replace("\\", "/").lower()
    return any(token in low for token in MARKET_PATH_HINTS)


def _git_changed_paths(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD^", "HEAD"],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()][:500]


def scan_static(root: Path = ROOT) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for relative in MARKET_REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            findings.append(_finding(
                "MARKET_REQUIRED_FILE_MISSING",
                relative,
                "required market runtime file is missing or unsafe",
                severity="critical",
            ))

    html_path = root / "index.html"
    if html_path.is_file():
        try:
            html = _read(html_path)
            css_count = len(CSS_TAG_RE.findall(html))
            js_count = len(JS_TAG_RE.findall(html))
            if css_count == 0:
                findings.append(_finding(
                    "MARKET_CSS_ASSET_MISSING", "index.html",
                    "multi-market CSS asset tag is missing", repairable=True,
                ))
            elif css_count > 1:
                findings.append(_finding(
                    "MARKET_CSS_ASSET_DUPLICATE", "index.html",
                    "multi-market CSS asset tag is duplicated", repairable=True,
                    evidence=f"count={css_count}",
                ))
            if js_count == 0:
                findings.append(_finding(
                    "MARKET_JS_ASSET_MISSING", "index.html",
                    "multi-market JavaScript asset tag is missing", repairable=True,
                ))
            elif js_count > 1:
                findings.append(_finding(
                    "MARKET_JS_ASSET_DUPLICATE", "index.html",
                    "multi-market JavaScript asset tag is duplicated", repairable=True,
                    evidence=f"count={js_count}",
                ))
        except (OSError, UnicodeError, ValueError) as exc:
            findings.append(_finding(
                "MARKET_HTML_READ_FAILED", "index.html",
                "cannot validate market browser integration", severity="critical",
                evidence=type(exc).__name__,
            ))

    updater_path = root / "tcg_updater.py"
    if updater_path.is_file():
        ok, evidence = _compile_python(updater_path)
        if not ok:
            findings.append(_finding(
                "MARKET_UPDATER_PYTHON_INVALID", "tcg_updater.py",
                "tcg_updater.py does not parse as Python", severity="critical",
                evidence=evidence,
            ))
        try:
            updater = _read(updater_path)
            if "'multi_market_prices.js','multi_market_prices.css'" not in updater:
                findings.append(_finding(
                    "MARKET_STATIC_ALLOWLIST_MISSING", "tcg_updater.py",
                    "multi-market browser assets are not in the local server allowlist",
                    repairable=True,
                ))
            route_count = updater.count(ROUTE_MARKER)
            if route_count == 0:
                findings.append(_finding(
                    "MARKET_API_ROUTE_MISSING", "tcg_updater.py",
                    "multi-market API route is missing", repairable=True,
                ))
            elif route_count > 1:
                findings.append(_finding(
                    "MARKET_API_ROUTE_DUPLICATE", "tcg_updater.py",
                    "multi-market API route is duplicated; manual review required",
                    severity="critical",
                    evidence=f"count={route_count}",
                ))
        except (OSError, UnicodeError, ValueError) as exc:
            findings.append(_finding(
                "MARKET_UPDATER_READ_FAILED", "tcg_updater.py",
                "cannot validate local server market route", severity="critical",
                evidence=type(exc).__name__,
            ))

    collector_path = root / "multi_market_price_collector.py"
    if collector_path.is_file():
        ok, evidence = _compile_python(collector_path)
        if not ok:
            findings.append(_finding(
                "MARKET_COLLECTOR_PYTHON_INVALID",
                "multi_market_price_collector.py",
                "market collector does not parse as Python",
                severity="critical",
                evidence=evidence,
            ))
        else:
            collector = _read(collector_path)
            required_contracts = {
                "search_multi_market": "market search entry point",
                "Retry-After": "rate-limit Retry-After handling",
                "cooldown": "provider cooldown state",
                "diagnostic_exception": "bounded secret-safe error diagnostics",
            }
            for token, label in required_contracts.items():
                if token not in collector:
                    findings.append(_finding(
                        "MARKET_COLLECTOR_SAFETY_CONTRACT_MISSING",
                        "multi_market_price_collector.py",
                        f"collector safety contract missing: {label}",
                        severity="critical",
                        evidence=token,
                    ))

    for relative in ("market_prices.json", "market_watch.json"):
        path = root / relative
        if path.is_file():
            ok, evidence = _strict_json(path)
            if not ok:
                findings.append(_finding(
                    "MARKET_JSON_INVALID", relative,
                    "market JSON failed strict parsing", severity="critical",
                    evidence=evidence,
                ))

    workflow = root / TRACKER_WORKFLOW
    if workflow.is_file():
        try:
            text = _read(workflow)
            if "concurrency:" not in text or "cancel-in-progress: true" not in text:
                findings.append(_finding(
                    "MARKET_TRACKER_CONCURRENCY_GUARD_MISSING",
                    TRACKER_WORKFLOW,
                    "AI tracker workflow must serialize/cancel duplicate in-progress runs",
                    severity="critical",
                ))
            if "permissions:" not in text:
                findings.append(_finding(
                    "MARKET_TRACKER_PERMISSION_BOUNDARY_MISSING",
                    TRACKER_WORKFLOW,
                    "AI tracker workflow must declare explicit token permissions",
                    severity="critical",
                ))
            for match in re.finditer(r"(?m)^\s*-\s+uses:\s+([^\s]+)$", text):
                ref = match.group(1)
                if ref.startswith("actions/") and not re.search(r"@[0-9a-f]{40}$", ref):
                    findings.append(_finding(
                        "MARKET_TRACKER_ACTION_NOT_SHA_PINNED",
                        TRACKER_WORKFLOW,
                        "GitHub-owned action is not pinned to a full commit SHA",
                        severity="critical",
                        evidence=ref,
                    ))
        except (OSError, UnicodeError, ValueError) as exc:
            findings.append(_finding(
                "MARKET_TRACKER_WORKFLOW_READ_FAILED", TRACKER_WORKFLOW,
                "cannot validate tracker workflow", severity="critical",
                evidence=type(exc).__name__,
            ))

    gitignore = root / ".gitignore"
    if gitignore.is_file():
        ignored = set(_read(gitignore).splitlines())
        for name in (REPORT.name, STATE.name):
            if name not in ignored:
                findings.append(_finding(
                    "MARKET_TRACKER_GITIGNORE_MISSING", ".gitignore",
                    f"device-local tracker runtime file must be ignored: {name}",
                    repairable=True,
                    evidence=name,
                ))

    return findings[:MAX_FINDINGS]


def _canonicalize_html_assets(text: str) -> str:
    text = CSS_TAG_RE.sub("", text)
    text = JS_TAG_RE.sub("", text)
    css = '<link rel="stylesheet" href="multi_market_prices.css">'
    js = '<script src="multi_market_prices.js"></script>'
    if "</head>" not in text:
        raise ValueError("missing </head> anchor")
    text = text.replace("</head>", css + "\n</head>", 1)
    marker = '<script src="auto_market_center.js"></script>'
    if marker in text:
        text = text.replace(marker, marker + "\n" + js, 1)
    elif "</body>" in text:
        text = text.replace("</body>", js + "\n</body>", 1)
    else:
        raise ValueError("missing JavaScript insertion anchor")
    return text


def _repair_updater(text: str) -> str:
    route_count = text.count(ROUTE_MARKER)
    if route_count > 1:
        raise ValueError("duplicate API route requires manual review")
    if STATIC_WITH_MARKET not in text:
        if STATIC_ANCHOR not in text:
            raise ValueError("missing static asset allowlist anchor")
        text = text.replace(STATIC_ANCHOR, STATIC_WITH_MARKET, 1)
    if route_count == 0:
        if ROUTE_ANCHOR not in text:
            raise ValueError("missing API route anchor")
        text = text.replace(ROUTE_ANCHOR, ROUTE_BLOCK + ROUTE_ANCHOR, 1)
    return text


def repair_known_integration(root: Path = ROOT) -> dict[str, Any]:
    before = scan_static(root)
    repairable = [row for row in before if row.get("code") in REPAIRABLE_CODES]
    if not repairable:
        return {
            "attempted": False,
            "changed_files": [],
            "rolled_back": False,
            "remaining_findings": before,
        }

    snapshots: dict[str, str] = {}
    changed: list[str] = []
    for relative in AUTO_REPAIR_PATHS:
        path = root / relative
        snapshots[relative] = _read(path) if path.exists() else ""

    try:
        html_path = root / "index.html"
        html_before = snapshots["index.html"]
        html_after = _canonicalize_html_assets(html_before)
        if html_after != html_before:
            atomic_write_text(html_path, html_after, suffix=".market-ai.tmp")
            changed.append("index.html")

        updater_path = root / "tcg_updater.py"
        updater_before = snapshots["tcg_updater.py"]
        updater_after = _repair_updater(updater_before)
        if updater_after != updater_before:
            atomic_write_text(updater_path, updater_after, suffix=".market-ai.tmp")
            changed.append("tcg_updater.py")

        ignore_path = root / ".gitignore"
        ignore_before = snapshots[".gitignore"]
        lines = ignore_before.splitlines()
        for name in (REPORT.name, STATE.name):
            if name not in lines:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(name)
        ignore_after = "\n".join(lines) + ("\n" if lines else "")
        if ignore_after != ignore_before:
            atomic_write_text(ignore_path, ignore_after, suffix=".market-ai.tmp")
            changed.append(".gitignore")

        after = scan_static(root)
        blocking = [
            row for row in after
            if row.get("severity") == "critical" or row.get("code") in REPAIRABLE_CODES
        ]
        if blocking:
            raise ValueError("post-repair invariant verification failed")
        return {
            "attempted": True,
            "changed_files": sorted(set(changed)),
            "rolled_back": False,
            "remaining_findings": after,
        }
    except Exception as exc:
        for relative, text in snapshots.items():
            atomic_write_text(root / relative, text, suffix=".market-ai-rollback.tmp")
        return {
            "attempted": True,
            "changed_files": [],
            "rolled_back": True,
            "rollback_reason": type(exc).__name__ + ": " + str(exc)[:500],
            "remaining_findings": scan_static(root),
        }


def load_selfrefine_market_findings(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / "MAIN_SELFREFINE_ERROR_LEDGER.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(_read(path, max_bytes=5_000_000))
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        return []
    rows: list[dict[str, Any]] = []
    for row in payload.get("errors") or []:
        if not isinstance(row, dict) or row.get("state") != "open":
            continue
        relative = str(row.get("path") or "")
        family = str(row.get("information_family") or "")
        if family != "market_price" and not _market_related_path(relative):
            continue
        rows.append(_finding(
            "SELFREFINE_" + str(row.get("stage") or "UNKNOWN").upper(),
            relative,
            str(row.get("root_cause") or "open Main SELFREFINE market error"),
            severity="critical",
            evidence=str(row.get("evidence") or ""),
        ))
    return rows[:MAX_FINDINGS]


def _run(cmd: list[str], root: Path, timeout: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd, cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=max(1, min(timeout, 900)), check=False,
        )
        output = (proc.stdout or "")[-MAX_OUTPUT:]
        return {"command": cmd, "returncode": proc.returncode, "output": output}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "returncode": 124,
            "output": ("timeout: " + str(exc))[-MAX_OUTPUT:],
        }
    except OSError as exc:
        return {
            "command": cmd,
            "returncode": 127,
            "output": (type(exc).__name__ + ": " + str(exc))[-MAX_OUTPUT:],
        }


def run_regression(root: Path = ROOT) -> list[dict[str, Any]]:
    commands = [
        [sys.executable, "-m", "unittest", "-v",
         "test_market_ai_auto_tracker.py",
         "test_multi_market_price_collector.py",
         "test_market_reference_sources_v130.py",
         "test_apply_patch_idempotency.py"],
        [sys.executable, "repository_integrity_guard.py"],
    ]
    return [_run(cmd, root, 240) for cmd in commands]


def allowed_changed_paths() -> set[str]:
    allowed = set(AUTO_REPAIR_PATHS)
    try:
        import verified_code_repair_rules as rules
        for paths in rules.RULE_PATHS.values():
            allowed.update(str(path).replace("\\", "/") for path in paths)
    except Exception:
        pass
    return allowed


def current_diff_paths(root: Path = ROOT) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def assert_safe_diff(root: Path = ROOT) -> dict[str, Any]:
    changed = current_diff_paths(root)
    allowed = allowed_changed_paths()
    unsafe = sorted(path for path in changed if path not in allowed)
    return {
        "changed_paths": changed,
        "unsafe_paths": unsafe,
        "allowed": not unsafe,
        "allowlist_size": len(allowed),
    }


def _load_state(path: Path = STATE) -> dict[str, Any]:
    try:
        payload = json.loads(_read(path, max_bytes=2_000_000))
        if isinstance(payload, dict):
            return payload
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        pass
    return {"schema": SCHEMA, "runs": 0, "history": []}


def _save_state(result: dict[str, Any], path: Path = STATE) -> None:
    state = _load_state(path)
    state["schema"] = SCHEMA
    state["runs"] = min(1_000_000, int(state.get("runs") or 0) + 1)
    state["updated_at"] = _now()
    history = [row for row in (state.get("history") or []) if isinstance(row, dict)][-99:]
    history.append({
        "at": state["updated_at"],
        "head": result.get("git", {}).get("head"),
        "status": result.get("summary", {}).get("status"),
        "finding_signatures": [
            row.get("signature") for row in result.get("findings", [])[:40]
        ],
        "repair_changed_files": result.get("repair", {}).get("changed_files", []),
        "regression_pass": result.get("summary", {}).get("regression_pass"),
    })
    state["history"] = history
    atomic_write_json(path, state, suffix=".market-ai-state.tmp")


def _git_head(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False,
        )
        return proc.stdout.strip()[:40] if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def run_tracker(
    *,
    root: Path = ROOT,
    repair: bool = False,
    run_tests: bool = True,
    report_path: Path | None = None,
) -> dict[str, Any]:
    initial = scan_static(root)
    repair_result = (
        repair_known_integration(root)
        if repair else {
            "attempted": False,
            "changed_files": [],
            "rolled_back": False,
            "remaining_findings": initial,
        }
    )
    static_after = scan_static(root)
    selfrefine_rows = load_selfrefine_market_findings(root)
    findings = (static_after + selfrefine_rows)[:MAX_FINDINGS]
    regressions = run_regression(root) if run_tests else []
    regression_pass = all(row.get("returncode") == 0 for row in regressions)
    diff_safety = assert_safe_diff(root)
    blocking = [
        row for row in findings
        if row.get("severity") in {"critical", "error"}
    ]
    status = "pass"
    if blocking or not regression_pass or not diff_safety["allowed"]:
        status = "fail"

    result = {
        "schema": SCHEMA,
        "generated_at": _now(),
        "git": {
            "head": _git_head(root),
            "changed_since_parent": _git_changed_paths(root),
        },
        "summary": {
            "status": status,
            "initial_findings": len(initial),
            "open_findings": len(findings),
            "repair_attempted": bool(repair_result.get("attempted")),
            "repair_rolled_back": bool(repair_result.get("rolled_back")),
            "repair_changed_files": len(repair_result.get("changed_files") or []),
            "regression_pass": regression_pass,
            "safe_diff": bool(diff_safety.get("allowed")),
        },
        "findings": findings,
        "repair": repair_result,
        "regressions": regressions,
        "diff_safety": diff_safety,
        "design_references": DESIGN_REFERENCES,
        "safety": {
            "runtime_web_text_executable": False,
            "search_text_patch_generation": False,
            "known_deterministic_repairs_only": True,
            "repair_paths_allowlisted": True,
            "rollback_on_failed_local_verification": True,
            "full_regression_before_publish": True,
            "403_429_bypass": False,
            "github_rate_limit_retry_storm": False,
            "selfrefine_error_state_isolated": True,
            "unknown_error_auto_patch": False,
        },
    }
    target = report_path or REPORT
    atomic_write_json(target, result, suffix=".market-ai-report.tmp")
    _save_state(result, root / STATE.name)
    return result


def self_test(root: Path = ROOT) -> int:
    findings = scan_static(root)
    bad = [row for row in findings if row.get("severity") == "critical"]
    if bad:
        print(json.dumps(bad, ensure_ascii=False, indent=2))
        return 1
    assert all(url.startswith("https://docs.github.com/") for url in DESIGN_REFERENCES.values())
    assert REPORT.name in _read(root / ".gitignore").splitlines()
    assert STATE.name in _read(root / ".gitignore").splitlines()
    print("Market AI auto tracker self-test: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--assert-safe-diff", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.assert_safe_diff:
        result = assert_safe_diff(ROOT)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["allowed"] else 3
    if args.self_test:
        return self_test(ROOT)

    result = run_tracker(
        root=ROOT,
        repair=args.repair,
        run_tests=not args.no_tests,
        report_path=Path(args.report),
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if result["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
