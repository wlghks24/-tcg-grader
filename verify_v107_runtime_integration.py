#!/usr/bin/env python3
"""v107 로컬 서버·PWA·문서·의존성·보안 통합 회귀검사."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path

import tcg_updater


ROOT = Path(__file__).resolve().parent
VERSION = "v109-card-identity-ocr-learning"


def fetch_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> dict:
    checks: list[dict] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    check(
        "public_allowlist",
        "social_event_candidates.json" in tcg_updater.PUBLIC_STATIC_FILES,
        "SNS/Google 후보 JSON이 로컬 서버 공개 목록에 포함됨",
    )

    handler = partial(tcg_updater.Handler, directory=str(ROOT))
    server = tcg_updater.QuietThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, health = fetch_json(f"{base}/api/health")
        check(
            "health_version",
            status == 200 and health.get("ok") is True and health.get("integrated_version") == VERSION,
            "서버 상태 API가 v109 통합버전을 반환함",
        )
        status, candidates = fetch_json(f"{base}/social_event_candidates.json")
        check(
            "social_feed_http",
            status == 200 and isinstance(candidates.get("items"), list),
            "화면이 사용하는 SNS/Google 후보 JSON을 실제 HTTP로 제공함",
        )
        status, _ = fetch_json(f"{base}/social_source_registry.json")
        check(
            "private_registry_blocked",
            status == 404,
            "내부 공식계정 레지스트리는 공개하지 않음",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    index = (ROOT / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
    service_worker = (ROOT / "sw.js").read_text(encoding="utf-8")
    check(
        "ui_pwa_version",
        "사전검사기 v109" in index
        and manifest.get("name") == "TCG 등급 사전검사기 v109"
        and "tcg-v109-card-identity-ocr-learning" in service_worker,
        "화면·manifest·서비스워커 버전이 일치함",
    )

    guide_versions = (79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 97, 98, 99)
    missing = [f"사용방법_v{version}.md" for version in guide_versions if not (ROOT / f"사용방법_v{version}.md").is_file()]
    mojibake = [path.name for path in ROOT.iterdir() if "∞" in path.name or "⌐" in path.name]
    check(
        "korean_guide_names",
        not missing and not mojibake,
        "한글 사용방법 파일 19개가 UTF-8 이름으로 존재하고 깨진 이름이 없음",
    )

    readme = (ROOT / "README_v31.md").read_text(encoding="utf-8")
    stale_launchers = (
        "정보자동업데이트.bat", "전체프로그램검사.bat", "자동실행_설치.bat",
        "자동실행_해제.bat", "기존버전_학습자료_가져오기.bat", "학습자료_백업.bat",
    )
    check(
        "current_documentation",
        "TCG Grader v109" in readme and not any(name in readme for name in stale_launchers),
        "현재 안내서가 영문 실행파일과 v109 검증 경로만 안내함",
    )

    required_headers = (
        "Content-Security-Policy", "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy", "X-Content-Type-Options",
        "Referrer-Policy", "Permissions-Policy",
    )
    header_server = tcg_updater.QuietThreadingHTTPServer(("127.0.0.1", 0), handler)
    header_thread = threading.Thread(target=header_server.serve_forever, daemon=True)
    header_thread.start()
    header_base = f"http://127.0.0.1:{header_server.server_address[1]}"
    try:
        request = urllib.request.Request(f"{header_base}/index.html")
        with urllib.request.urlopen(request, timeout=5) as response:
            headers = response.headers
            header_ok = all(headers.get(name) for name in required_headers)
    finally:
        header_server.shutdown()
        header_server.server_close()
        header_thread.join(timeout=3)
    check(
        "security_headers",
        header_ok and "object-src 'none'" in str(headers.get("Content-Security-Policy")),
        "로컬 서버가 CSP·교차출처·권한·MIME 보안 헤더를 제공함",
    )

    final_source = (ROOT / "verify_v107_final.py").read_text(encoding="utf-8")
    check(
        "portable_verification",
        "shutil.which(\"node\")" in final_source
        and "TCG_REQUIRE_NODE" in final_source
        and "skipped" in final_source,
        "Node.js 미설치 PC에서는 명확히 건너뛰고 개발 검증은 강제 가능함",
    )

    return {
        "version": VERSION,
        "ok": all(item["ok"] for item in checks),
        "passed": sum(item["ok"] for item in checks),
        "failed": sum(not item["ok"] for item in checks),
        "checks": checks,
    }


if __name__ == "__main__":
    report = main()
    print(json.dumps(report, ensure_ascii=False, indent=2))
