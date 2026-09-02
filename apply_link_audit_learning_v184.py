#!/usr/bin/env python3
from pathlib import Path


def patch_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{label}: patch anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    patch_once(
        "auto_repair_engine.py",
        '''        if "redirect loop" in lowered or "too many redirects" in lowered:\n            return "redirect-loop", http_status\n        if http_status is None and any(value in lowered for value in ("rate limit", "too many requests", "요청 제한")):\n            return "rate-limit-no-status", None\n''',
        '''        if "redirect loop" in lowered or "too many redirects" in lowered:\n            return "redirect-loop", http_status\n        if http_status is None and any(value in lowered for value in (\n            "미보정 깨진 링크", "깨진 링크", "unrepaired broken link", "broken external link"\n        )):\n            return "broken-link-no-status", None\n        if http_status is None and any(value in lowered for value in ("rate limit", "too many requests", "요청 제한")):\n            return "rate-limit-no-status", None\n''',
        "HTTP broken-link subtype",
    )

    patch_once(
        "auto_repair_engine.py",
        '''        (("httperror", "http error", "http <n>", "status code", "rate limit", "too many requests", "요청 제한", "redirect loop", "too many redirects"),\n         "NETWORK_HTTP_ERROR", "HTTP 응답 오류",\n''',
        '''        (("httperror", "http error", "http <n>", "status code", "rate limit", "too many requests", "요청 제한", "redirect loop", "too many redirects",\n          "미보정 깨진 링크", "깨진 링크", "unrepaired broken link", "broken external link"),\n         "NETWORK_HTTP_ERROR", "HTTP 응답 오류",\n''',
        "HTTP broken-link classifier",
    )

    patch_once(
        "auto_repair_engine.py",
        '''    if code == "NETWORK_HTTP_ERROR":\n        retry_allowed = http_status in {408, 425, 429, 500, 502, 503, 504} or subtype == "rate-limit-no-status"\n        if http_status in {401, 403}:\n            title = "HTTP 접근 권한 오류"\n''',
        '''    if code == "NETWORK_HTTP_ERROR":\n        retry_allowed = http_status in {408, 425, 429, 500, 502, 503, 504} or subtype == "rate-limit-no-status"\n        if subtype == "broken-link-no-status":\n            title = "외부 링크 주소 소멸·변경 오류"\n            cause = "GET 재확인까지 거친 외부 링크가 보정되지 않은 상태로 남아 공식 주소 변경 또는 삭제 확인이 필요합니다."\n            steps = ("미보정 URL과 참조 파일·필드를 확인합니다.", "공식 사이트의 현재 공개 주소를 검증합니다.", "검증된 대체 주소가 없으면 기존 자료를 유지하고 해당 링크만 확인 필요로 남깁니다.")\n        elif http_status in {401, 403}:\n            title = "HTTP 접근 권한 오류"\n''',
        "HTTP broken-link guidance",
    )

    patch_once(
        "auto_update_all.py",
        "        unresolved_broken=max(0,broken-repaired)\n",
        "        unresolved_broken=int(lr.get('unresolved_broken',max(0,broken-repaired)) or 0)\n",
        "link report unresolved count",
    )

    patch_once(
        "error_scenario_lab.py",
        '''           for status in (400, 401, 403, 404, 408, 410, 425, 429, 500, 501, 502, 503, 504)),\n    _case("conn-dns-gai", "network_connection", "gaierror: DNS name resolution failed", "NETWORK_CONNECTION_ERROR", "dns-resolution", True, "dns"),\n''',
        '''           for status in (400, 401, 403, 404, 408, 410, 425, 429, 500, 501, 502, 503, 504)),\n    _case("external-link-unrepaired", "http_response", "외부 링크 검사 — 미보정 깨진 링크 4개", "NETWORK_HTTP_ERROR", "broken-link-no-status", False, "http-broken-link"),\n    _case("external-link-broken", "http_response", "broken external link remains unrepaired", "NETWORK_HTTP_ERROR", "broken-link-no-status", False, "http-broken-link"),\n    _case("conn-dns-gai", "network_connection", "gaierror: DNS name resolution failed", "NETWORK_CONNECTION_ERROR", "dns-resolution", True, "dns"),\n''',
        "broken-link training scenarios",
    )

    print("[OK] v184 link audit learning patch prepared")


if __name__ == "__main__":
    main()
