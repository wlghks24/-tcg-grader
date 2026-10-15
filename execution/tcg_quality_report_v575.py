#!/usr/bin/env python3
"""V575 decision-driven, offline-friendly TCG quality dashboard.

Inputs: V573 static evidence audit, optionally a previously saved audit JSON.
Outputs: self-contained HTML and/or JSON into caller-selected local paths.
Never edits source files, imports market providers, claims real sales or runs AI APIs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys
import tempfile
import os

from tcg_system_audit_v573 import ROOT, audit

PRIORITIES = {"P0": 0, "P1": 1, "P2": 2}
LABELS = {"P0": "차단 오류", "P1": "데이터·기능 보완", "P2": "사용성·성능"}
MAX_PROPOSALS = 16


def percent(numerator: object, denominator: object) -> float | None:
    if (type(numerator) is not int or type(denominator) is not int
            or denominator <= 0 or not 0 <= numerator <= denominator):
        return None
    return round(numerator * 100 / denominator, 1)


def proposals_for(audit_result: dict) -> list[dict]:
    m = audit_result["metrics"]
    total = m["static_box_products"]
    joined = m["static_box_price_exact_matches"]
    prices = m["box_market_entries"]
    sold = m["market_box_with_sale_evidence"]
    missing_links = m["market_box_unconfirmed_links"]
    missing_cn = [r for r in ("CN-S", "CN-T")
                  if not m["static_box_by_country"].get(r, 0)]
    queue = []

    def add(key: str, priority: str, title: str, evidence: str,
            action: str, proof: str, category: str) -> None:
        queue.append({
            "id": key, "priority": priority, "category": category,
            "title": title, "evidence": evidence, "proposed_action": action,
            "acceptance_test": proof, "status": "HOLD - review before changing production",
        })

    if audit_result["blocking_errors"]:
        add("safety-gate", "P0", "먼저 안전 차단 원인 해결",
            f"입력 무결성·상품 식별 위반 {len(audit_result['blocking_errors'])}건",
            "실패한 상품 식별·출처를 격리하고 최소 범위로 수정",
            "P0 감사 오류 0건 + 기존 회귀·보안 검사 통과", "안전")
    if sold < prices:
        add("verified-sales", "P1", "BOX 실거래 근거 자동화",
            f"완료거래 증빙이 포함된 BOX 가격 항목 {sold}/{prices}개",
            "공식 허용 데이터 제공자만 사용; 상품·미개봉·통화·거래일·판매 ID를 확인하고 중복 계보를 제거. 근거 없으면 추천가 HOLD",
            "독립 거래 출처 2곳 검증 + 중복·취소·호가 차단 테스트", "가격")
    if joined < total:
        add("product-matching", "P1", "BOX와 시세 자동 매칭 보완",
            f"기본 BOX 가격 연결 {joined}/{total}개",
            "게임·국가·언어·세트 코드·미개봉 단품 식별자를 통합하고 미연결 건을 자동 후보로 생성",
            "혼합 상품 오매칭 0건, 연결 전후 실제 증가 건수 기록", "수집")
    if missing_cn:
        add("chinese-editions", "P1", "중국 간체·번체 별도 수집",
            "기본 BOX 화면에 없는 국가 구분: " + ", ".join(missing_cn),
            "CN-S와 CN-T는 서로 다른 판본·판매처·사진 출처로 분리해 WATCH 수집; 승인 전 실거래로 표시 금지",
            "국가 분리·동일명 충돌·원본 출처·회귀 테스트", "범위")
    if missing_links:
        add("source-health", "P1", "출처 상태 자동 재검증",
            f"확인 보류 중인 BOX 링크 {missing_links}개",
            "타임아웃·404·약관 제한·새 링크를 분류하고 지수 백오프로 재검사; 확인 전 가격 최신 주장 금지",
            "정상/실패/403/429/오프라인/재시도 제한 테스트", "안전")
    for index, issue in enumerate(audit_result["usability_followups"][:4]):
        add(f"ux-{index+1}", "P2", "태블릿 사용성 점검",
            str(issue)[:180],
            "검증된 UI 선택 상태·탭 포커스·명확한 오류/빈 상태를 점검하고 최소 수정",
            "360/430/800/1280 폭의 실제 렌더·터치·접근성 검사", "UI")
    add("physical-tablet", "P2", "Lenovo 실기기 검증 준비",
        "CI 통과는 실기기 실행·저장·오프라인 안정성을 보증하지 않음",
        "사용자 단말에서 터치, 이미지, 화면 오버플로, 앱 재시작, 캐시 갱신과 성능을 측정",
        "실기기 실행 기록·재현 로그·최종 사용자 승인", "기기")
    return sorted(queue[:MAX_PROPOSALS], key=lambda x: (PRIORITIES[x["priority"]], x["id"]))


def build(audit_result: dict, baseline: dict | None = None) -> dict:
    m = audit_result["metrics"]
    connection = percent(m["static_box_price_exact_matches"], m["static_box_products"])
    sale_presence = percent(m["market_box_with_sale_evidence"], m["box_market_entries"])
    previous = baseline.get("metrics") if isinstance(baseline, dict) else None
    changes = {}
    if isinstance(previous, dict):
        for name in ("static_box_price_exact_matches", "static_box_products",
                     "market_box_unconfirmed_links", "market_box_with_sale_evidence"):
            old, new = previous.get(name), m.get(name)
            if type(old) is int and type(new) is int and old >= 0 and new >= 0:
                changes[name] = {"before": old, "after": new, "delta": new - old}
    return {
        "schema_version": "v575",
        "audit_at_kst": audit_result["audit_at_kst"],
        "source_scope": audit_result["verification_scope"],
        "decision": "BLOCK" if audit_result["blocking_errors"] else "HOLD",
        "decision_reason": ("P0 위반으로 병합 금지" if audit_result["blocking_errors"]
                            else "가격·실기기 증거 부족, 배포 승인 불가"),
        "data_complete": bool(audit_result["data_complete"]),
        "device_verified": False,
        "scores": {"static_box_price_linkage_pct": connection,
                   "box_rows_with_evidence_pct": sale_presence,
                   "overall_quality_score": None},
        "metrics": m,
        "proposals": proposals_for(audit_result),
        "observed_issues": {
            "P0": list(audit_result["blocking_errors"]),
            "P1": list(audit_result["coverage_gaps"]),
            "P2": list(audit_result["usability_followups"]),
        },
        "changes_from_baseline": changes,
        "method": "static local-source audit; deterministic risk ranking; no automated code rewriting",
    }


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _metric(label: str, value: str, note: str) -> str:
    return (f'<article class="metric"><div class="metric-label">{_esc(label)}</div>'
            f'<div class="metric-value">{_esc(value)}</div>'
            f'<div class="metric-note">{_esc(note)}</div></article>')


def render_html(report: dict) -> str:
    m = report["metrics"]
    scores = report["scores"]
    pct = scores["static_box_price_linkage_pct"]
    fraction = f"{pct:g}%" if pct is not None else "미측정"
    bar = str(pct if pct is not None else 0)
    status = report["decision"]
    items = []
    for idx, item in enumerate(report["proposals"], 1):
        cls = item["priority"].lower()
        items.append(
            '<details class="task"><summary>'
            f'<span class="task-n">{idx:02d}</span><span class="pill {cls}">{_esc(item["priority"])}</span>'
            f'<span class="task-title">{_esc(item["title"])}</span>'
            '<span class="chevron" aria-hidden="true">▾</span></summary>'
            f'<div class="task-body"><p class="evidence">{_esc(item["evidence"])}</p>'
            '<div class="task-grid">'
            f'<div><b>개선 제안</b><p>{_esc(item["proposed_action"])}</p></div>'
            f'<div><b>합격 조건</b><p>{_esc(item["acceptance_test"])}</p></div>'
            '</div><small>현 상태: 검토 제안 · 코드 자동 수정/배포 없음</small></div></details>'
        )
    issues = []
    for label in ("P0", "P1", "P2"):
        vals = report["observed_issues"][label]
        lis = "".join(f"<li>{_esc(x)}</li>" for x in vals) or "<li>이번 정적 검사에서 발견하지 못함</li>"
        issues.append(f'<section class="issue"><h3><span class="pill {label.lower()}">{label}</span>'
                      f' {LABELS[label]} · {len(vals)}건</h3><ul>{lis}</ul></section>')
    diffs = []
    nice_names = {
        "static_box_price_exact_matches": "정확히 연결된 BOX 가격",
        "static_box_products": "기본 BOX 목록",
        "market_box_unconfirmed_links": "출처 확인 보류",
        "market_box_with_sale_evidence": "거래 증빙 포함 BOX",
    }
    for key, change in report["changes_from_baseline"].items():
        delta = change["delta"]
        diffs.append(f'<div class="diff"><span>{_esc(nice_names.get(key,key))}</span>'
                     f'<b>{change["before"]} → {change["after"]} '
                     f'({_esc(("+" if delta > 0 else "") + str(delta))})</b></div>')
    comparison = "".join(diffs) if diffs else '<p class="muted">이전 점검 결과가 없어 개선량을 추정하지 않았습니다.</p>'
    cards = "".join([
        _metric("분석 등록 게임", str(m["registry_games"]), "상품 등록 수와 별개"),
        _metric("기본 BOX", str(m["static_box_products"]), "정적 목록 기준"),
        _metric("시세 연결", f'{m["static_box_price_exact_matches"]}/{m["static_box_products"]}',
                "게임·국가·제품명 일치"),
        _metric("완료거래 증빙", str(m["market_box_with_sale_evidence"]), "실제 거래가 검증 아님"),
    ])
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>TCG 품질 진단 · V575</title>
<style>
:root{{--ink:#142238;--muted:#607086;--bg:#f3f6fb;--surface:#fff;--line:#dce5f1;
--blue:#2355cf;--blue-soft:#eaf0ff;--orange:#a85410;--red:#ac3144;--green:#147a56}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Noto Sans KR",sans-serif}}
body::before{{content:"";display:block;position:absolute;inset:0 0 auto;height:320px;
background:linear-gradient(135deg,#132c56,#1c4e90 65%,#335cc0);z-index:-1}}
.shell{{width:min(1040px,100%);margin:0 auto;padding:24px 18px 68px}}
.eyebrow{{color:#bfdaff;font-size:12px;font-weight:750;letter-spacing:.08em}}
.hero{{color:#fff;padding:24px 12px 30px}}
.hero h1{{font-size:clamp(26px,5vw,40px);line-height:1.2;margin:10px 0}}
.hero p{{color:#d5e5ff;margin:0;max-width:700px;word-break:keep-all}}
.meta{{display:flex;flex-wrap:wrap;gap:8px;margin-top:17px;color:#e0eafa;font-size:12px}}
.meta span{{background:#ffffff1a;border:1px solid #ffffff3b;padding:5px 10px;border-radius:100px}}
.panel{{border:1px solid var(--line);background:var(--surface);border-radius:22px;padding:22px;
box-shadow:0 10px 32px #102a4b0e;margin:0 0 18px;min-width:0}}
.top{{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}}
h2{{font-size:19px;line-height:1.3;margin:0 0 12px;letter-spacing:-.025em}}
h3{{font-size:15px;margin:0 0 10px}}
p{{margin:7px 0}}
.muted{{color:var(--muted);font-size:13px}}
.notice{{border:1px solid #ecd5c8;background:#fff9f2;border-radius:12px;padding:12px 14px;color:#86512f;font-size:13px}}
.pill{{display:inline-flex;align-items:center;justify-content:center;min-width:43px;border-radius:7px;padding:3px 8px;
font-size:11px;font-weight:900;white-space:nowrap}}
.p0{{background:#fff0f2;color:var(--red)}}.p1{{background:#fff2df;color:#91510c}}
.p2{{background:#eef3ff;color:#2e55af}}.hold{{background:#fff1db;color:#865000}}
.status{{font-size:13px;font-weight:700;color:#99561c}}
.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}
.metric{{background:#f8faff;border:1px solid #e4ebf4;border-radius:15px;padding:16px 14px;min-width:0}}
.metric-label{{font-size:12px;color:var(--muted);font-weight:700}}
.metric-value{{font-size:clamp(20px,3vw,26px);line-height:1.5;font-weight:850;font-variant-numeric:tabular-nums}}
.metric-note{{font-size:11px;color:#6f7f90;word-break:keep-all}}
.bar{{height:11px;background:#e8edf5;border-radius:30px;overflow:hidden;margin:10px 0 4px}}
.bar i{{height:100%;display:block;background:linear-gradient(90deg,#2865d5,#4c93d9);border-radius:30px;width:{bar}%}}
.scoreline{{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}}
.scoreline b{{font-size:26px;font-variant-numeric:tabular-nums}}
.task{{border:1px solid var(--line);border-radius:13px;background:#fff;margin:9px 0;overflow:hidden}}
.task summary{{list-style:none;display:flex;align-items:center;gap:10px;padding:13px 14px;cursor:pointer;min-height:54px}}
.task summary::-webkit-details-marker{{display:none}}
.task summary:focus-visible{{outline:3px solid #5d84e9;outline-offset:-3px}}
.task[open] summary{{background:#f9fbff;border-bottom:1px solid var(--line)}}
.task-n{{color:#8494a9;font-size:12px;font-weight:900}}
.task-title{{font-weight:750;flex:1;word-break:keep-all}}.chevron{{color:#8998a9}}
.task[open] .chevron{{transform:rotate(180deg)}}
.task-body{{padding:15px 16px;color:#3d5068;font-size:13px}}
.evidence{{font-weight:700;color:#995514}}
.task-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:12px 0}}
.task-grid>div{{background:#f6f9fd;border-radius:10px;padding:11px 12px;min-width:0}}
.task-grid b{{font-size:12px;color:#183e78}}.task-grid p{{margin:5px 0;word-break:keep-all}}
.task-body small{{color:var(--muted)}}
.issues{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
.issue{{border:1px solid var(--line);border-radius:13px;padding:13px 14px;min-width:0}}
.issue ul{{padding-left:18px;color:#516176;margin:0;font-size:12px;overflow-wrap:anywhere}}
.issue li{{margin:6px 0}}
.diff{{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid #eef0f5;font-size:13px}}
.diff b{{font-variant-numeric:tabular-nums}}
.footer{{color:#687789;text-align:center;font-size:12px;margin-top:24px;word-break:keep-all}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,minmax(0,1fr))}}.issues{{grid-template-columns:1fr}}}}
@media(max-width:520px){{.shell{{padding:10px 12px 44px}}.hero{{padding:23px 3px 26px}}.panel{{padding:16px;border-radius:17px}}
.task-grid{{grid-template-columns:1fr}}.task summary{{gap:7px;padding:12px 10px}}
.task-title{{font-size:13px}}.metric{{padding:12px 10px}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
@media print{{body::before{{display:none}}.hero,.hero p,.eyebrow{{color:#12213a}}.panel{{box-shadow:none;break-inside:avoid}}details.task{{break-inside:avoid}}}}
</style></head><body>
<main class="shell">
<header class="hero">
<div class="eyebrow">LOCAL QUALITY INTELLIGENCE / V575</div>
<h1>TCG 품질 진단 보고서</h1>
<p>카드 · BOX · 수집 · UI · 태블릿 상태를 서로 다른 근거로 평가하고, 검증할 수 있는 수정 후보부터 정리합니다.</p>
<div class="meta"><span>분석일 { _esc(report["audit_at_kst"]) }</span><span>소스: 로컬 저장소</span><span>실기기 검증 별도</span></div>
</header>
<section class="panel" aria-label="최종 품질 판정">
<div class="top"><h2>현재 판정</h2><span class="pill hold">{_esc(status)}</span></div>
<p class="status">{_esc(report["decision_reason"])}</p>
<div class="notice">자동 확인은 정적 파일과 저장된 증거에 한정됩니다. 판매완료 거래·상품 정품·실제 구매 가능 여부·Lenovo 터치 동작은 별도 검증이 필요합니다. 근거 없는 95점/100점 합격은 표시하지 않습니다.</div>
</section>
<section class="panel"><h2>데이터 연결 현황</h2><div class="metrics">{cards}</div>
<div class="scoreline" style="margin-top:19px"><span>기본 BOX 시세 정확 매칭</span><b>{_esc(fraction)}</b></div>
<div class="bar" role="img" aria-label="BOX 시세 연결 { _esc(fraction) }"><i></i></div>
<p class="muted">이 수치는 가격의 실거래 검증률이 아닌, 상품 식별 기준의 저장된 가격 연결률입니다.</p></section>
<section class="panel"><div class="top"><h2>자동 선정 개선 후보 · {len(report["proposals"])}건</h2><span class="pill p1">검토 후보</span></div>
<p class="muted">문제의 심각도와 실제 데이터 공백을 기준으로 정렬했습니다. 각 항목을 펼치면 이유·수정 방향·합격 조건이 나옵니다.</p>
{"".join(items)}</section>
<section class="panel"><h2>검증된 문제 세부 목록</h2><div class="issues">{"".join(issues)}</div></section>
<section class="panel"><h2>직전 검사 대비</h2>{comparison}</section>
<footer class="footer">V575 · 단말에서도 열리는 단일 HTML · 외부 이미지/스크립트/유료 API 없음 · source 변경/자동 배포 없음</footer>
</main></body></html>"""


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tempname = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                         prefix=".quality-", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            tempname = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tempname, path)
    finally:
        if tempname:
            Path(tempname).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write self-contained offline TCG quality report")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--html-out", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--baseline-json", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if not args.html_out and not args.json_out:
        parser.error("choose --html-out and/or --json-out")
    try:
        data = audit(args.root)
        previous = json.loads(args.baseline_json.read_text(encoding="utf-8")) if args.baseline_json else None
        report = build(data, previous)
        if args.html_out:
            _atomic_text(args.html_out, render_html(report))
        if args.json_out:
            _atomic_text(args.json_out, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"TCG_QUALITY_REPORT_HOLD: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("TCG_QUALITY_REPORT_WRITTEN", report["decision"],
          len(report["proposals"]), "proposals")
    return 1 if args.strict and report["decision"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
