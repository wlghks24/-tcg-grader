#!/usr/bin/env python3
"""Bounded link/runtime contract audit for the TCG web application.

The verifier does not contact external sites.  It proves that local navigation,
button bindings, static assets, service-worker assets, API route names and every
stored external URL are structurally valid.  Live external reachability remains
the responsibility of ``validate_external_links.py`` so DNS/firewall failures
cannot be mistaken for application defects.
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from safe_runtime import safe_read_text, validate_public_https_url


ROOT = Path(__file__).resolve().parent
LINK_DATA_FILES = (
    "releases.json", "market_prices.json", "market_watch.json",
    "promo_events.json", "supplementary_candidates.json",
    "purchase_sources.json", "purchase_signals.json",
    "web_discovery_candidates.json", "tcg_live_data.json",
)


class _Inventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.button_ids: set[str] = set()
        self.fragments: list[str] = []
        self.local_assets: set[str] = set()
        self.data_targets: list[str] = []
        self.unsafe_schemes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
            if tag.lower() == "button":
                self.button_ids.add(element_id)
        for key in ("data-home-target", "data-update-target", "data-top-panel"):
            if values.get(key):
                self.data_targets.append(values[key])
        for key in ("href", "src"):
            raw = values.get(key, "").strip()
            if not raw or "${" in raw or raw.startswith(("data:", "blob:")):
                continue
            lowered = raw.lower()
            if lowered.startswith(("javascript:", "file:", "ftp:")):
                self.unsafe_schemes.append(raw)
            elif raw.startswith("#"):
                if len(raw) > 1:
                    self.fragments.append(urllib.parse.unquote(raw[1:]))
            elif not urllib.parse.urlsplit(raw).scheme and not raw.startswith("//"):
                self.local_assets.add(urllib.parse.urlsplit(raw).path.lstrip("./"))


def _walk_urls(value: Any, path: str = "root"):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                yield child, key, item
            yield from _walk_urls(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_urls(item, f"{path}[{index}]")


def _validate_external_url(url: str) -> str:
    concrete = url.replace("{query}", "TCG")
    if url.count("{query}") > 1:
        raise ValueError("검색 URL의 {query} 표시는 한 번만 허용됩니다.")
    validate_public_https_url(concrete)
    parsed = urllib.parse.urlsplit(concrete)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("공개 HTTPS 주소 형식이 아닙니다.")
    if parsed.port not in (None, 443):
        raise ValueError("HTTPS 기본 포트 외 주소는 허용하지 않습니다.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".localhost")):
        raise ValueError("로컬 호스트 주소는 외부 링크로 허용하지 않습니다.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("사설·예약 IP 주소는 외부 링크로 허용하지 않습니다.")
    return host


def audit_link_contract(root: str | Path | None = None) -> dict[str, Any]:
    base = Path(root).resolve() if root is not None else ROOT
    page = safe_read_text(base / "index.html")
    identity_handlers = safe_read_text(base / "card_identity_recognition.js") if (base / "card_identity_recognition.js").is_file() else ""
    dynamic_templates = safe_read_text(base / "graded_photo_dashboard.js") if (base / "graded_photo_dashboard.js").is_file() else ""
    handler_source = page + "\n" + identity_handlers
    server = safe_read_text(base / "tcg_updater.py")
    worker = safe_read_text(base / "sw.js")
    manifest = json.loads(safe_read_text(base / "manifest.webmanifest"))

    parser = _Inventory()
    parser.feed(page)
    # The graded-photo dashboard is intentionally created after page load by a
    # local, service-worker-pinned script. Include literal IDs from that trusted
    # template so real dynamic controls are not reported as missing elements.
    parser.ids.update(re.findall(r"\bid=['\"]([A-Za-z][A-Za-z0-9_.:-]{0,79})['\"]", dynamic_templates))
    if parser.unsafe_schemes:
        raise AssertionError(f"위험한 화면 링크: {parser.unsafe_schemes[:3]}")

    referenced_ids = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", handler_source))
    referenced_ids.update(re.findall(r"\bS\(\s*['\"]([^'\"]+)['\"]\s*\)", page))
    referenced_ids.update(re.findall(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)", page))
    missing_ids = sorted(referenced_ids - parser.ids)
    if missing_ids:
        raise AssertionError(f"존재하지 않는 화면 ID 참조: {missing_ids}")
    missing_targets = sorted(set(parser.fragments + parser.data_targets) - parser.ids)
    if missing_targets:
        raise AssertionError(f"존재하지 않는 화면 이동 대상: {missing_targets}")

    unbound_buttons = [button_id for button_id in sorted(parser.button_ids)
                       if handler_source.count(button_id) < 2]
    if unbound_buttons:
        raise AssertionError(f"동작 연결이 없는 버튼: {unbound_buttons}")
    for selector in ("[data-simple-game]", "[data-purchase-channel]", "[data-top-panel]",
                     ".home-launch-btn", ".box-kb-country", ".update-menu-btn",
                     ".update-panel-close"):
        if selector not in page:
            raise AssertionError(f"버튼 그룹 연결 누락: {selector}")

    blank_anchors = re.findall(r"<a\b[^>]*\btarget=['\"]_blank['\"][^>]*>", page, re.I)
    insecure_blank = [tag for tag in blank_anchors
                      if not re.search(r"\brel=['\"][^'\"]*\bnoopener\b[^'\"]*\bnoreferrer\b", tag, re.I)]
    if insecure_blank:
        raise AssertionError(f"새 창 opener 보호 누락: {insecure_blank[:2]}")
    if "window.open(" in page:
        raise AssertionError("팝업 차단에 취약한 다중 window.open 연결이 남아 있습니다.")

    public_match = re.search(r"PUBLIC_STATIC_FILES\s*=\s*\{([\s\S]*?)\n\}", server)
    if not public_match:
        raise AssertionError("서버 공개 정적파일 목록을 찾지 못했습니다.")
    public_files = set(re.findall(r"['\"]([^'\"]+)['\"]", public_match.group(1)))
    expected_assets = set(parser.local_assets)
    expected_assets.update(re.findall(
        r"['\"`]([A-Za-z0-9_.-]+\.(?:json|svg|webmanifest))(?:[?${}'\"`]|$)", page,
    ))
    expected_assets.update({urllib.parse.urlsplit(str(manifest.get("start_url", ""))).path.lstrip("./")})
    expected_assets.update(str(row.get("src", "")).lstrip("./") for row in manifest.get("icons", []) if isinstance(row, dict))
    expected_assets.discard("")
    missing_assets = sorted(name for name in expected_assets if not (base / name).is_file())
    unpublished_assets = sorted(name for name in expected_assets if name not in public_files and name != "index.html")
    if missing_assets or unpublished_assets:
        raise AssertionError(f"정적파일 연결 오류: missing={missing_assets}, unpublished={unpublished_assets}")

    core_match = re.search(r"const CORE=\[([\s\S]*?)\];", worker)
    if not core_match:
        raise AssertionError("서비스워커 CORE 목록을 찾지 못했습니다.")
    core_assets = {name.lstrip("./") for name in re.findall(r"['\"]([^'\"]+)['\"]", core_match.group(1))}
    core_assets.discard("")
    if any(not (base / name).is_file() for name in core_assets):
        raise AssertionError("서비스워커에 존재하지 않는 파일이 연결돼 있습니다.")
    if not expected_assets <= core_assets | {"index.html"}:
        raise AssertionError(f"서비스워커 캐시 누락: {sorted(expected_assets - core_assets - {'index.html'})}")

    front_api = set(re.findall(r"['\"`](/api/[a-z0-9-]+)", page, re.I))
    missing_api = sorted(route for route in front_api if route not in server)
    if missing_api:
        raise AssertionError(f"화면-서버 API 연결 누락: {missing_api}")
    for route in ("/api/update", "/api/run-auto-update", "/api/retry-failed",
                  "/api/grade-card", "/api/learning-store", "/api/apply"):
        if route in page and route not in server:
            raise AssertionError(f"POST API 연결 누락: {route}")

    external_urls: dict[str, str] = {}
    for match in re.finditer(r"https://[^\s'\"<>`]+", page):
        url = match.group(0).rstrip(")]};,.")
        if "${" not in url:
            external_urls[f"index.html:{match.start()}"] = url
    for filename in LINK_DATA_FILES:
        data = json.loads(safe_read_text(base / filename))
        for item_path, _, url in _walk_urls(data, filename):
            external_urls[item_path] = url
    hosts = set()
    for item_path, url in external_urls.items():
        try:
            hosts.add(_validate_external_url(url))
        except (ValueError, TypeError) as exc:
            raise AssertionError(f"외부 링크 형식 오류 {item_path}: {exc}") from exc

    health = json.loads(safe_read_text(base / "link_health_report.json"))
    if int(health.get("broken", 0)) > int(health.get("repaired", 0)):
        raise AssertionError("자동보정되지 않은 404/410 외부 링크가 남아 있습니다.")
    return {
        "ok": True,
        "button_count": len(parser.button_ids),
        "referenced_id_count": len(referenced_ids),
        "internal_target_count": len(parser.fragments) + len(parser.data_targets),
        "static_asset_count": len(expected_assets),
        "service_worker_asset_count": len(core_assets),
        "frontend_api_count": len(front_api),
        "external_reference_count": len(external_urls),
        "external_host_count": len(hosts),
        "confirmed_broken_count": int(health.get("broken", 0)),
        "network_transient_count": int(health.get("transient", 0)),
    }


if __name__ == "__main__":
    print(json.dumps(audit_link_contract(), ensure_ascii=False, indent=2))
