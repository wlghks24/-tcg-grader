#!/usr/bin/env python3
"""Offline scenario training for faster, safer TCG error diagnosis.

The lab feeds bounded text fixtures only to the deterministic classifier.  It
does not touch production error occurrence counters, execute learned text,
access the network, or perform the simulated destructive actions.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import auto_repair_engine as engine
from safe_runtime import atomic_write_json, safe_read_bytes


ROOT = Path(__file__).resolve().parent
PROFILE_PATH = ROOT / "scenario_learning_profiles.json"
ENGINE_VERSION = "v134-root-cause-partial-outcome"


def _case(case_id: str, family: str, detail: str, code: str, subtype: str | None,
          retry: bool, equivalent_group: str | None = None) -> dict[str, Any]:
    return {"id": case_id, "family": family, "detail": detail, "code": code,
            "subtype": subtype, "retry": retry,
            "equivalent_group": equivalent_group or case_id}


SCENARIOS = (
    _case("net-timeout-read", "network_timeout", "TimeoutError: official source read timed out after 30 seconds", "NETWORK_TIMEOUT", "general", True, "net-timeout"),
    _case("net-timeout-connect", "network_timeout", "connection timeout while opening official HTTPS source", "NETWORK_TIMEOUT", "general", True, "net-timeout"),
    _case("net-timeout-ko", "network_timeout", "공식 출처 응답 시간초과 180초", "NETWORK_TIMEOUT", "general", True, "net-timeout"),
    _case("net-timeout-card-price", "network_timeout", "market price source timed out after 90.0 seconds", "NETWORK_TIMEOUT", "general", True, "net-timeout"),
    _case("process-timeout-subprocess", "process_timeout", "subprocess.TimeoutExpired: collector exceeded 120 seconds", "PROCESS_TIMEOUT", "subprocess", True, "process-timeout"),
    _case("process-timeout-worker", "process_timeout", "worker process timeout while collecting six jobs", "PROCESS_TIMEOUT", "worker", True),
    _case("process-timeout-job", "process_timeout", "update job 작업 제한시간 초과", "PROCESS_TIMEOUT", "update-job", True),
    *tuple(_case(f"http-{status}", "http_response", f"HTTPError: HTTP Error {status} from official source",
                 "NETWORK_HTTP_ERROR",
                 "rate-limit-429" if status == 429 else
                 f"access-{status}" if status in {401, 403} else
                 f"missing-{status}" if status in {404, 410} else
                 "transient-server" if status in {408, 425, 500, 502, 503, 504} else
                 f"client-{status}" if 400 <= status < 500 else f"server-{status}",
                 status in {408, 425, 429, 500, 502, 503, 504},
                 "http-transient" if status in {408, 425, 500, 502, 503, 504} else None)
           for status in (400, 401, 403, 404, 408, 410, 425, 429, 500, 501, 502, 503, 504)),
    _case("conn-dns-gai", "network_connection", "gaierror: DNS name resolution failed", "NETWORK_CONNECTION_ERROR", "dns-resolution", True, "dns"),
    _case("conn-dns-text", "network_connection", "DNS lookup failed for official host", "NETWORK_CONNECTION_ERROR", "dns-resolution", True, "dns"),
    _case("conn-refused", "network_connection", "ConnectionError: connection refused", "NETWORK_CONNECTION_ERROR", "connection-refused", True),
    _case("conn-temporary", "network_connection", "일시 확인불가 112개", "NETWORK_CONNECTION_ERROR", "temporary-unavailable", True),
    _case("conn-url", "network_connection", "URLError: official source unavailable", "NETWORK_CONNECTION_ERROR", "url-connection", True),
    _case("tls-certificate", "network_tls", "SSLError: certificate verify failed", "NETWORK_TLS_ERROR", "certificate", False, "tls-cert"),
    _case("tls-ko-certificate", "network_tls", "TLS 인증서 검증 오류", "NETWORK_TLS_ERROR", "certificate", False, "tls-cert"),
    _case("tls-protocol", "network_tls", "ssl.SSLError: wrong TLS protocol version", "NETWORK_TLS_ERROR", "tls-protocol", False),
    _case("code-name-fetch", "internal_code", "NameError: name 'fetch_prices' is not defined", "INTERNAL_CODE_ERROR", "nameerror:fetch_prices", False),
    _case("code-name-save", "internal_code", "NameError: name 'save_prices' is not defined", "INTERNAL_CODE_ERROR", "nameerror:save_prices", False),
    _case("code-import-module", "internal_code", "ModuleNotFoundError: No module named 'collector_core'", "INTERNAL_CODE_ERROR", "modulenotfounderror:collector_core", False),
    _case("code-import-symbol", "internal_code", "ImportError: cannot import name 'safe_merge'", "INTERNAL_CODE_ERROR", "importerror:safe_merge", False),
    _case("code-attribute", "internal_code", "AttributeError: module has no attribute 'collect_prices'", "INTERNAL_CODE_ERROR", "attributeerror:collect_prices", False),
    _case("code-index", "internal_code", "IndexError: list index out of range", "INTERNAL_CODE_ERROR", "indexerror", False),
    _case("code-assert", "internal_code", "AssertionError: release contract failed", "INTERNAL_CODE_ERROR", "assertionerror", False),
    _case("syntax-basic", "syntax", "SyntaxError: invalid syntax at line 18", "INTERNAL_SYNTAX_ERROR", "syntax", False, "syntax"),
    _case("syntax-indent", "syntax", "IndentationError: unexpected indent", "INTERNAL_SYNTAX_ERROR", "indentation", False),
    _case("syntax-tabs", "syntax", "TabError: inconsistent use of tabs and spaces", "INTERNAL_SYNTAX_ERROR", "mixed-indentation", False),
    _case("security-ssrf", "security", "SSRF private IP target blocked", "SECURITY_POLICY_BLOCK", "private-network-target", False),
    _case("security-private-dns", "security", "private DNS resolution blocked", "SECURITY_POLICY_BLOCK", "private-network-target", False),
    _case("security-origin", "security", "허용되지 않은 요청 출처 Origin 차단", "SECURITY_POLICY_BLOCK", "origin-policy", False),
    _case("security-symlink", "security", "심볼릭 링크 저장 경로 차단", "SECURITY_POLICY_BLOCK", "symlink-path", False),
    _case("security-traversal", "security", "path traversal 경로탈출 차단", "SECURITY_POLICY_BLOCK", "path-traversal", False),
    _case("file-missing-releases", "filesystem", "FileNotFoundError: releases.json no such file", "FILE_MISSING", "missing:releases.json", False),
    _case("file-missing-prices", "filesystem", "FileNotFoundError: market_prices.json no such file", "FILE_MISSING", "missing:market_prices.json", False),
    _case("file-missing-generic", "filesystem", "필수 파일 없음", "FILE_MISSING", "missing-file", False),
    _case("file-permission-releases", "filesystem", "PermissionError: permission denied releases.json", "FILE_PERMISSION_ERROR", "permission:releases.json", False),
    _case("file-permission-prices", "filesystem", "PermissionError: permission denied market_prices.json", "FILE_PERMISSION_ERROR", "permission:market_prices.json", False),
    _case("file-permission-ko", "filesystem", "저장 폴더 권한 오류", "FILE_PERMISSION_ERROR", "permission-file", False),
    _case("schema-json-decode", "data_schema", "JSONDecodeError: expecting property name", "DATA_SCHEMA_ERROR", "json-decode", False),
    _case("schema-duplicate", "data_schema", "duplicate JSON key detected", "DATA_SCHEMA_ERROR", "duplicate-key", False),
    _case("schema-key-name", "data_schema", "KeyError: 'name' required field", "DATA_SCHEMA_ERROR", "missing-field:name", False),
    _case("schema-key-region", "data_schema", "KeyError: 'region' required field", "DATA_SCHEMA_ERROR", "missing-field:region", False),
    _case("schema-required", "data_schema", "필수값 누락 in collected JSON", "DATA_SCHEMA_ERROR", "missing-required-field", False),
    _case("promo-required-official-fields", "data_schema", "ValueError: 행사 공식 출처·국가·날짜 정확도 또는 필수 자료가 잘못되었습니다", "DATA_SCHEMA_ERROR", "missing-required-field", False),
    _case("schema-general", "data_schema", "JSON 구조 오류", "DATA_SCHEMA_ERROR", "schema", False),
    _case("value-type", "data_value", "TypeError: expected number but received list", "DATA_VALUE_ERROR", "typeerror", False),
    _case("value-range", "data_value", "ValueError: number outside allowed range", "DATA_VALUE_ERROR", "range", False),
    _case("value-overflow", "data_value", "OverflowError: numeric value too large", "DATA_VALUE_ERROR", "overflowerror", False),
    _case("value-nan", "data_value", "ValueError: NaN value rejected", "DATA_VALUE_ERROR", "nonfinite", False),
    _case("source-parser-price", "source_structure", "price parser 패턴 0건", "SOURCE_STRUCTURE_CHANGED", None, False),
    _case("source-parser-event", "source_structure", "event parser 확인 실패", "SOURCE_STRUCTURE_CHANGED", None, False),
    _case("source-parser-read", "source_structure", "official product page parse 읽지 못함", "SOURCE_STRUCTURE_CHANGED", None, False),
    _case("release-official-page-empty", "source_structure", "ValueError: 공식 페이지에서 신뢰 가능한 출시정보를 읽지 못했습니다", "SOURCE_STRUCTURE_CHANGED", None, False),
    _case("exchange-jpy", "exchange_rate", "환율 JPY_KRW 범위 오류", "EXCHANGE_RATE_VALIDATION", "general", False),
    _case("exchange-usd", "exchange_rate", "exchange rate USD_KRW invalid unit", "EXCHANGE_RATE_VALIDATION", "general", False),
    _case("exchange-collected-value", "exchange_rate", "ValueError: 원화 환산 환율 수집값이 허용 범위를 벗어났습니다", "EXCHANGE_RATE_VALIDATION", "general", False),
    _case("lock-database", "concurrency", "database is locked during atomic save", "CONCURRENCY_CONFLICT", "database-lock", True),
    _case("lock-process", "concurrency", "다른 프로세스의 오류학습 저장 잠금 대기", "CONCURRENCY_CONFLICT", "process-lock", True),
    _case("lock-write", "concurrency", "concurrent write conflict while replacing report", "CONCURRENCY_CONFLICT", "write-conflict", True),
    _case("resource-disk", "resource", "OSError ENOSPC: no space left on device", "RESOURCE_EXHAUSTION", "disk-space", False),
    _case("resource-memory", "resource", "MemoryError: out of memory", "RESOURCE_EXHAUSTION", "memory", False),
    _case("resource-files", "resource", "OSError EMFILE: too many open files", "RESOURCE_EXHAUSTION", "file-descriptors", False),
    _case("resource-ko", "resource", "디스크 공간 부족", "RESOURCE_EXHAUSTION", "disk-space", False),
    _case("limit-depth", "data_limit", "JSON too deeply nested 중첩 깊이 제한 초과", "DATA_LIMIT_ERROR", "depth", False),
    _case("limit-recursion", "data_limit", "RecursionError: JSON nesting exceeded", "DATA_LIMIT_ERROR", "depth", False),
    _case("limit-size", "data_limit", "payload too large size limit exceeded", "DATA_LIMIT_ERROR", "size", False),
    _case("limit-nodes", "data_limit", "JSON too many nodes 항목 수 제한", "DATA_LIMIT_ERROR", "node-count", False),
    _case("integrity-checksum", "data_integrity", "checksum mismatch after download", "DATA_INTEGRITY_ERROR", "checksum", False, "checksum"),
    _case("integrity-sha", "data_integrity", "SHA256 mismatch for package", "DATA_INTEGRITY_ERROR", "checksum", False, "checksum"),
    _case("integrity-truncated", "data_integrity", "truncated file unexpected EOF", "DATA_INTEGRITY_ERROR", "truncated", False),
    _case("integrity-ko", "data_integrity", "원자저장 결과 불완전 저장", "DATA_INTEGRITY_ERROR", "truncated", False),
    _case("runtime-collector", "runtime", "RuntimeError: collector returned invalid internal state", "RUNTIME_ERROR", None, False),
    _case("runtime-render", "runtime", "RuntimeError: browser workflow state failed", "RUNTIME_ERROR", None, False),
    _case("unknown-new", "unclassified", "NovelCollectorFault: opaque vendor response", "UNCLASSIFIED_ERROR", "general", False),
    _case("unknown-ko", "unclassified", "새로운 종류의 예외 신호", "UNCLASSIFIED_ERROR", "general", False),
    # v90: alternate exception messages and operational edge cases.  These are
    # deterministic text fixtures only; no scenario executes code or network I/O.
    _case("net-timeout-socket", "network_timeout", "socket.timeout: read operation timed out", "NETWORK_TIMEOUT", "general", True, "net-timeout"),
    _case("net-timeout-open", "network_timeout", "official source open timeout after 45 seconds", "NETWORK_TIMEOUT", "general", True, "net-timeout"),
    _case("process-exit-code", "process_execution", "CalledProcessError: collector returned non-zero exit status 2", "PROCESS_EXECUTION_ERROR", "nonzero-exit", False, "process-nonzero"),
    _case("process-exit-ko", "process_execution", "수집 프로세스 nonzero exit 종료코드 3", "PROCESS_EXECUTION_ERROR", "nonzero-exit", False, "process-nonzero"),
    _case("process-signal", "process_execution", "collector terminated by signal 9", "PROCESS_EXECUTION_ERROR", "signal", False),
    _case("http-status-format-503", "http_response", "status code 503 from official source", "NETWORK_HTTP_ERROR", "transient-server", True, "http-transient"),
    _case("http-timeout-precedence-408", "http_response", "HTTP status code 408 timed out", "NETWORK_HTTP_ERROR", "transient-server", True, "http-transient"),
    _case("http-status-409", "http_response", "official source status code 409 conflict", "NETWORK_HTTP_ERROR", "client-409", False),
    _case("http-status-413", "http_response", "official source status code 413 payload too large", "NETWORK_HTTP_ERROR", "client-413", False),
    _case("http-status-422", "http_response", "official source status code 422 unprocessable entity", "NETWORK_HTTP_ERROR", "client-422", False),
    _case("http-status-451", "http_response", "official source status code 451 unavailable for legal reasons", "NETWORK_HTTP_ERROR", "client-451", False),
    _case("http-status-505", "http_response", "official source status code 505 version not supported", "NETWORK_HTTP_ERROR", "server-505", False),
    _case("http-rate-limit-text", "http_response", "rate limit exceeded by official source", "NETWORK_HTTP_ERROR", "rate-limit-no-status", True),
    _case("http-redirect-loop", "http_response", "HTTPError: redirect loop after 10 redirects", "NETWORK_HTTP_ERROR", "redirect-loop", False),
    _case("conn-reset", "network_connection", "ConnectionResetError: connection reset by peer", "NETWORK_CONNECTION_ERROR", "connection-reset", True),
    _case("conn-aborted", "network_connection", "ConnectionAbortedError: software caused connection abort", "NETWORK_CONNECTION_ERROR", "connection-aborted", True),
    _case("conn-broken-pipe", "network_connection", "BrokenPipeError: broken pipe while downloading", "NETWORK_CONNECTION_ERROR", "broken-pipe", True),
    _case("conn-host-unreachable", "network_connection", "OSError: official host unreachable", "NETWORK_CONNECTION_ERROR", "unreachable", True, "conn-unreachable"),
    _case("conn-network-unreachable", "network_connection", "network unreachable for official source", "NETWORK_CONNECTION_ERROR", "unreachable", True, "conn-unreachable"),
    _case("tls-expired", "network_tls", "SSLCertVerificationError: certificate expired", "NETWORK_TLS_ERROR", "certificate-expired", False),
    _case("tls-hostname", "network_tls", "TLS certificate hostname mismatch", "NETWORK_TLS_ERROR", "certificate-hostname", False),
    _case("tls-self-signed", "network_tls", "SSL certificate self-signed unknown CA", "NETWORK_TLS_ERROR", "certificate-untrusted", False),
    _case("code-unbound-symbol", "internal_code", "UnboundLocalError: local variable 'prices' referenced before assignment", "INTERNAL_CODE_ERROR", "unboundlocalerror:prices", False),
    _case("code-zero-division", "internal_code", "ZeroDivisionError: division by zero in valuation", "INTERNAL_CODE_ERROR", "zerodivisionerror", False),
    _case("code-not-implemented", "internal_code", "NotImplementedError: grading adapter missing", "INTERNAL_CODE_ERROR", "notimplementederror", False),
    _case("security-unsafe-scheme", "security", "security blocked non-HTTPS unsafe scheme", "SECURITY_POLICY_BLOCK", "unsafe-scheme", False),
    _case("security-url-credentials", "security", "security blocked credentials in URL", "SECURITY_POLICY_BLOCK", "url-credentials", False),
    _case("security-host-header", "security", "invalid Host header blocked", "SECURITY_POLICY_BLOCK", "host-header", False),
    _case("security-method", "security", "security blocked method policy violation", "SECURITY_POLICY_BLOCK", "method-policy", False),
    _case("security-xss", "security", "XSS script injection input blocked", "SECURITY_POLICY_BLOCK", "script-injection", False),
    _case("security-csrf", "security", "security blocked CSRF Origin request", "SECURITY_POLICY_BLOCK", "origin-policy", False, "security-origin"),
    _case("file-missing-enoent", "filesystem", "OSError ENOENT while reading releases.json", "FILE_MISSING", "missing:releases.json", False, "file-missing-releases"),
    _case("file-readonly-prices", "filesystem", "OSError: Read-only file system: market_prices.json", "FILE_PERMISSION_ERROR", "permission:market_prices.json", False, "file-permission-prices"),
    _case("file-eacces-releases", "filesystem", "OSError EACCES writing releases.json", "FILE_PERMISSION_ERROR", "permission:releases.json", False, "file-permission-releases"),
    _case("path-is-directory", "file_path", "IsADirectoryError: market_prices.json is a directory", "FILE_PATH_ERROR", "is-directory", False),
    _case("path-not-directory", "file_path", "NotADirectoryError: parent is not a directory", "FILE_PATH_ERROR", "not-directory", False),
    _case("path-cross-device", "file_path", "OSError EXDEV: cross-device atomic replace", "FILE_PATH_ERROR", "cross-device", False),
    _case("encoding-decode", "data_encoding", "UnicodeDecodeError: utf-8 codec cannot decode byte 0xff", "DATA_ENCODING_ERROR", "decode", False, "encoding-decode"),
    _case("encoding-invalid-utf8", "data_encoding", "invalid UTF-8 cannot decode official response", "DATA_ENCODING_ERROR", "decode", False, "encoding-decode"),
    _case("encoding-encode", "data_encoding", "UnicodeEncodeError: cannot encode surrogate", "DATA_ENCODING_ERROR", "encode", False),
    _case("schema-nonstandard-number", "data_schema", "standard JSON rejected NaN Infinity", "DATA_SCHEMA_ERROR", "nonstandard-number", False),
    _case("schema-wrong-root", "data_schema", "JSON top-level list but object required", "DATA_SCHEMA_ERROR", "wrong-root-type", False),
    _case("value-boolean", "data_value", "TypeError: authenticity boolean expected, not string false", "DATA_VALUE_ERROR", "boolean", False),
    _case("value-grade-range", "data_value", "ValueError: grade score 범위 오류", "DATA_VALUE_ERROR", "range", False),
    _case("value-coordinate", "data_value", "ValueError: coordinate out of range", "DATA_VALUE_ERROR", "range", False),
    _case("value-negative-price", "data_value", "ValueError: negative price out of range", "DATA_VALUE_ERROR", "range", False),
    _case("source-captcha", "source_access", "official source CAPTCHA challenge", "SOURCE_ACCESS_CHALLENGE", "captcha", False),
    _case("source-bot-challenge", "source_access", "Cloudflare challenge bot challenge page", "SOURCE_ACCESS_CHALLENGE", "bot-challenge", False),
    _case("lock-version", "concurrency", "optimistic version conflict during atomic write", "CONCURRENCY_CONFLICT", "version-conflict", True, "version-conflict"),
    _case("lock-stale-version", "concurrency", "stale version detected by optimistic lock", "CONCURRENCY_CONFLICT", "version-conflict", True, "version-conflict"),
    _case("resource-thread", "resource", "RuntimeError: can't start new thread", "RESOURCE_EXHAUSTION", "thread-limit", False),
    _case("resource-process", "resource", "BlockingIOError EAGAIN: resource temporarily unavailable", "RESOURCE_EXHAUSTION", "process-limit", False),
    _case("integrity-stale-cache", "data_integrity", "cache generation mismatch from stale cache", "DATA_INTEGRITY_ERROR", "stale-cache", False),
    # v91: cross-platform exception forms, damaged archives, cancellation,
    # response media types, and deliberately combined precedence cases.
    _case("platform-win-reset", "network_connection", "ConnectionResetError: [WinError 10054] an existing connection was forcibly closed", "NETWORK_CONNECTION_ERROR", "connection-reset", True),
    _case("platform-win-refused", "network_connection", "ConnectionRefusedError: [WinError 10061] no connection could be made", "NETWORK_CONNECTION_ERROR", "connection-refused", True),
    _case("platform-win-dns", "network_connection", "socket.gaierror: [WinError 11001] getaddrinfo failed", "NETWORK_CONNECTION_ERROR", "dns-resolution", True, "dns"),
    _case("platform-win-access", "filesystem", "PermissionError: [WinError 5] Access is denied: releases.json", "FILE_PERMISSION_ERROR", "permission:releases.json", False, "file-permission-releases"),
    _case("platform-win-disk", "resource", "OSError: [WinError 112] There is not enough space on the disk", "RESOURCE_EXHAUSTION", "disk-space", False, "resource-disk"),
    _case("platform-win-sharing", "concurrency", "PermissionError: [WinError 32] sharing violation while replacing report", "CONCURRENCY_CONFLICT", "sharing-violation", True),
    _case("platform-android-readonly", "filesystem", "OSError: Read-only file system: /storage/emulated/0/market_prices.json", "FILE_PERMISSION_ERROR", "permission:market_prices.json", False, "file-permission-prices"),
    _case("platform-macos-emfile", "resource", "OSError: [Errno 24] Too many open files: market_prices.json", "RESOURCE_EXHAUSTION", "file-descriptors", False, "resource-files"),
    _case("platform-linux-enospc", "resource", "OSError: [Errno 28] No space left on device", "RESOURCE_EXHAUSTION", "disk-space", False, "resource-disk"),
    _case("platform-win-missing-file", "filesystem", "FileNotFoundError: [WinError 2] The system cannot find the file specified: releases.json", "FILE_MISSING", "missing:releases.json", False, "file-missing-releases"),
    _case("platform-win-missing-path", "filesystem", "FileNotFoundError: [WinError 3] The system cannot find the path specified: market_prices.json", "FILE_MISSING", "missing:market_prices.json", False, "file-missing-prices"),
    _case("platform-win-path-long", "file_path", "OSError: [WinError 206] The filename or extension is too long", "FILE_PATH_ERROR", "path-too-long", False),
    _case("compression-gzip", "data_compression", "gzip.BadGzipFile: Not a gzipped file", "DATA_COMPRESSION_ERROR", "gzip", False),
    _case("compression-zip", "data_compression", "zipfile.BadZipFile: File is not a zip file", "DATA_COMPRESSION_ERROR", "zip", False),
    _case("compression-crc", "data_compression", "Bad CRC-32 for file market_prices.json", "DATA_COMPRESSION_ERROR", "crc", False),
    _case("compression-bomb", "data_compression", "DecompressionBombError: archive expansion ratio exceeds limit", "DATA_COMPRESSION_ERROR", "expansion-bomb", False),
    _case("compression-central-directory", "data_compression", "BadZipFile: end of central directory record not found", "DATA_COMPRESSION_ERROR", "zip", False),
    _case("compression-unsupported", "data_compression", "unsupported compression method 99 in archive", "DATA_COMPRESSION_ERROR", "unsupported-method", False),
    _case("cancel-asyncio", "process_cancelled", "asyncio.exceptions.CancelledError: collector task cancelled", "PROCESS_CANCELLED", "task-cancelled", False, "task-cancelled"),
    _case("cancel-keyboard", "process_cancelled", "KeyboardInterrupt: user interrupted verification", "PROCESS_CANCELLED", "user-interrupt", False, "user-interrupt"),
    _case("cancel-ko-task", "process_cancelled", "사용자가 수집 작업 취소 요청", "PROCESS_CANCELLED", "task-cancelled", False, "task-cancelled"),
    _case("cancel-futures", "process_cancelled", "concurrent.futures.CancelledError: future was cancelled", "PROCESS_CANCELLED", "task-cancelled", False, "task-cancelled"),
    _case("cancel-ko-user", "process_cancelled", "사용자 인터럽트로 검증 중단", "PROCESS_CANCELLED", "user-interrupt", False, "user-interrupt"),
    _case("encoding-bom", "data_encoding", "JSONDecodeError: Unexpected UTF-8 BOM", "DATA_ENCODING_ERROR", "bom", False),
    _case("encoding-cp949-decode", "data_encoding", "UnicodeDecodeError: cp949 codec cannot decode byte 0x80", "DATA_ENCODING_ERROR", "decode", False, "encoding-decode"),
    _case("encoding-surrogate-encode", "data_encoding", "UnicodeEncodeError: utf-8 codec cannot encode surrogate", "DATA_ENCODING_ERROR", "encode", False),
    _case("encoding-charset-mismatch", "data_encoding", "response charset mismatch: declared euc-kr but bytes are utf-8", "DATA_ENCODING_ERROR", "charset-mismatch", False),
    _case("content-html-json", "source_content_type", "content-type text/html returned instead of expected JSON", "SOURCE_CONTENT_TYPE_ERROR", "html-instead-of-json", False),
    _case("content-unsupported-media", "source_content_type", "HTTP 415 Unsupported Media Type from official source", "SOURCE_CONTENT_TYPE_ERROR", "unsupported-media", False),
    _case("content-missing-header", "source_content_type", "missing Content-Type header on official JSON response", "SOURCE_CONTENT_TYPE_ERROR", "missing-header", False),
    _case("content-text-plain", "source_content_type", "content-type text/plain but application/json expected", "SOURCE_CONTENT_TYPE_ERROR", "content-type", False),
    _case("content-ko-mismatch", "source_content_type", "공식 응답 콘텐츠 타입 불일치 JSON 필요", "SOURCE_CONTENT_TYPE_ERROR", "content-type", False),
    _case("tls-not-yet-valid", "network_tls", "SSLCertVerificationError: certificate is not yet valid", "NETWORK_TLS_ERROR", "certificate-not-yet-valid", False),
    _case("tls-expired-variant", "network_tls", "certificate verify failed: certificate has expired", "NETWORK_TLS_ERROR", "certificate-expired", False),
    _case("tls-hostname-variant", "network_tls", "SSL hostname does not match official source certificate", "NETWORK_TLS_ERROR", "certificate-hostname", False),
    _case("tls-self-signed-variant", "network_tls", "certificate verify failed: self signed certificate", "NETWORK_TLS_ERROR", "certificate-untrusted", False),
    _case("lock-file-exists", "concurrency", "FileExistsError: updater.lock already exists", "CONCURRENCY_CONFLICT", "lock-exists", True),
    _case("lock-broken-barrier", "concurrency", "threading.BrokenBarrierError: collector barrier broken", "CONCURRENCY_CONFLICT", "barrier-broken", True),
    _case("lock-database-busy", "concurrency", "sqlite3.OperationalError: database busy", "CONCURRENCY_CONFLICT", "database-lock", True, "lock-database"),
    _case("lock-compare-swap", "concurrency", "compare-and-swap conflict while publishing generation", "CONCURRENCY_CONFLICT", "version-conflict", True, "version-conflict"),
    _case("lock-version-number", "concurrency", "optimistic version conflict: expected 17 actual 18", "CONCURRENCY_CONFLICT", "version-conflict", True, "version-conflict"),
    _case("lock-timeout-variant", "concurrency", "TimeoutError: lock acquisition timeout during atomic save", "CONCURRENCY_CONFLICT", "process-lock", True, "lock-process"),
    _case("value-decimal", "data_value", "decimal.InvalidOperation: invalid decimal conversion", "DATA_VALUE_ERROR", "decimal", False),
    _case("value-floating", "data_value", "FloatingPointError: invalid floating point operation", "DATA_VALUE_ERROR", "floating-point", False),
    _case("schema-root-array", "data_schema", "JSON top-level array received but object required", "DATA_SCHEMA_ERROR", "wrong-root-type", False),
    _case("schema-trailing-json", "data_schema", "JSONDecodeError: Extra data after valid JSON document", "DATA_SCHEMA_ERROR", "json-decode", False),
    _case("schema-duplicate-variant", "data_schema", "duplicate key card_name in JSON object", "DATA_SCHEMA_ERROR", "duplicate-key", False),
    _case("schema-nan-variant", "data_schema", "nonstandard JSON number NaN is not permitted", "DATA_SCHEMA_ERROR", "nonstandard-number", False),
    _case("security-dns-rebinding", "security", "DNS rebinding detected for official host to 127.0.0.1", "SECURITY_POLICY_BLOCK", "private-network-target", False),
    _case("security-cors-origin", "security", "CORS Origin not allowed by policy", "SECURITY_POLICY_BLOCK", "origin-policy", False, "security-origin"),
    _case("security-csrf-origin", "security", "CSRF Origin validation failed", "SECURITY_POLICY_BLOCK", "origin-policy", False, "security-origin"),
    _case("security-zip-slip", "security", "zip-slip path traversal attempt blocked", "SECURITY_POLICY_BLOCK", "path-traversal", False),
    _case("security-file-scheme", "security", "security blocked unsafe scheme file://etc/passwd", "SECURITY_POLICY_BLOCK", "unsafe-scheme", False),
    _case("security-embedded-credentials", "security", "security blocked credentials in URL https://user:token-SECRET@example.invalid/data", "SECURITY_POLICY_BLOCK", "url-credentials", False),
    _case("security-forged-host", "security", "forged Host header rejected by allowlist", "SECURITY_POLICY_BLOCK", "host-header", False),
    _case("security-script-tag", "security", "script injection blocked: <script>alert(1)</script>", "SECURITY_POLICY_BLOCK", "script-injection", False),
    _case("precedence-syntax-http", "syntax", "SyntaxError: invalid syntax followed by HTTP status 503", "INTERNAL_SYNTAX_ERROR", "syntax", False, "syntax"),
    _case("precedence-security-timeout", "security", "security blocked private IP target after connection timeout", "SECURITY_POLICY_BLOCK", "private-network-target", False),
    _case("precedence-memory-reset", "resource", "MemoryError: out of memory after connection reset", "RESOURCE_EXHAUSTION", "memory", False),
    _case("precedence-http-payload", "http_response", "HTTP status code 413: payload too large", "NETWORK_HTTP_ERROR", "client-413", False, "http-status-413"),
    _case("precedence-encoding-json", "data_encoding", "UnicodeDecodeError while parsing malformed JSON", "DATA_ENCODING_ERROR", "decode", False, "encoding-decode"),
    _case("precedence-permission-json", "filesystem", "PermissionError while writing JSON file market_prices.json", "FILE_PERMISSION_ERROR", "permission:market_prices.json", False, "file-permission-prices"),
    _case("precedence-cancel-timeout", "process_cancelled", "CancelledError: collector task cancelled after timeout", "PROCESS_CANCELLED", "task-cancelled", False, "task-cancelled"),
    _case("precedence-captcha-blocked", "source_access", "official source CAPTCHA challenge security blocked", "SOURCE_ACCESS_CHALLENGE", "captcha", False, "source-captcha"),
    # v92: environment, dependency, temporal, and persistent-storage failures.
    _case("config-env-missing", "configuration", "ConfigurationError: required environment variable TCG_PORT is missing", "CONFIGURATION_ERROR", "missing-environment", False, "config-env"),
    _case("config-env-ko", "configuration", "필수 환경변수 누락 TCG_UPDATE_INTERVAL", "CONFIGURATION_ERROR", "missing-environment", False, "config-env"),
    _case("config-port-range", "configuration", "invalid configuration: port must be between 1 and 65535", "CONFIGURATION_ERROR", "invalid-port", False, "config-port"),
    _case("config-malformed", "configuration", "ConfigError: malformed configuration file settings.toml", "CONFIGURATION_ERROR", "malformed-file", False, "config-malformed"),
    _case("config-unknown-option", "configuration", "unknown configuration option auto_retry_forever", "CONFIGURATION_ERROR", "unknown-option", False),
    _case("config-boolean", "configuration", "ConfigurationError: boolean expected for TCG_AUTO_UPDATE", "CONFIGURATION_ERROR", "invalid-value", False),
    _case("config-empty-url", "configuration", "invalid configuration: official base URL is empty", "CONFIGURATION_ERROR", "invalid-value", False),
    _case("config-retry-range", "configuration", "invalid configuration: retry count out of range", "CONFIGURATION_ERROR", "invalid-value", False),
    _case("dependency-conflict", "dependency", "DependencyConflict: urllib3 3.0 is incompatible with requests 2.31", "DEPENDENCY_ERROR", "version-conflict", False, "dependency-version"),
    _case("dependency-python", "dependency", "Requires-Python >=3.11 but running Python 3.9", "DEPENDENCY_ERROR", "runtime-version", False, "dependency-runtime"),
    _case("dependency-abi", "dependency", "ImportError: binary ABI mismatch for native extension", "DEPENDENCY_ERROR", "abi-mismatch", False, "dependency-abi"),
    _case("dependency-wheel", "dependency", "UnsupportedWheel: wheel is not supported on this platform", "DEPENDENCY_ERROR", "unsupported-wheel", False, "dependency-wheel"),
    _case("dependency-package-version", "dependency", "package version conflict: cryptography incompatible with OpenSSL", "DEPENDENCY_ERROR", "version-conflict", False, "dependency-version"),
    _case("dependency-runtime-missing", "dependency", "required runtime dependency unavailable: sqlite3 extension", "DEPENDENCY_ERROR", "missing-runtime-dependency", False),
    _case("dependency-openssl", "dependency", "OpenSSL version incompatible with current cryptography package", "DEPENDENCY_ERROR", "version-conflict", False, "dependency-version"),
    _case("dependency-python-ko", "dependency", "Python 최소 버전 3.11 필요 현재 버전 3.9", "DEPENDENCY_ERROR", "runtime-version", False, "dependency-runtime"),
    _case("time-invalid-iso", "data_time", "ValueError: Invalid isoformat string 2026-13-40", "DATA_TIME_ERROR", "date-parse", False, "time-parse"),
    _case("time-naive-zone", "data_time", "TimezoneError: naive datetime where timezone-aware required", "DATA_TIME_ERROR", "timezone", False, "time-zone"),
    _case("time-clock-skew", "data_time", "system clock skew exceeds certificate tolerance", "DATA_TIME_ERROR", "clock-skew", False, "time-clock"),
    _case("time-order", "data_time", "event end date precedes start date", "DATA_TIME_ERROR", "date-order", False, "time-order"),
    _case("time-invalid-ko", "data_time", "잘못된 날짜 형식 2026년 14월 35일", "DATA_TIME_ERROR", "date-parse", False, "time-parse"),
    _case("time-offset", "data_time", "invalid timezone UTC offset +25:00", "DATA_TIME_ERROR", "timezone", False, "time-zone"),
    _case("time-range", "data_time", "event date range out of range for supported year", "DATA_TIME_ERROR", "date-range", False),
    _case("time-leap", "data_time", "invalid date 2027-02-29 is not a leap day", "DATA_TIME_ERROR", "date-parse", False, "time-parse"),
    _case("storage-sqlite", "storage_corruption", "sqlite3.DatabaseError: database disk image is malformed", "STORAGE_CORRUPTION_ERROR", "sqlite-corrupt", False, "storage-sqlite"),
    _case("storage-wal", "storage_corruption", "SQLite WAL checksum mismatch after crash", "STORAGE_CORRUPTION_ERROR", "wal-corrupt", False, "storage-wal"),
    _case("storage-index", "storage_corruption", "database index corruption detected", "STORAGE_CORRUPTION_ERROR", "index-corrupt", False, "storage-index"),
    _case("storage-page", "storage_corruption", "SQLite database page checksum failed", "STORAGE_CORRUPTION_ERROR", "page-checksum", False, "storage-page"),
    _case("storage-ko", "storage_corruption", "오류학습 데이터베이스 손상 감지", "STORAGE_CORRUPTION_ERROR", "sqlite-corrupt", False, "storage-sqlite"),
    _case("storage-not-database", "storage_corruption", "sqlite3.DatabaseError: file is not a database", "STORAGE_CORRUPTION_ERROR", "sqlite-corrupt", False, "storage-sqlite"),
    _case("storage-header", "storage_corruption", "database header invalid after interrupted write", "STORAGE_CORRUPTION_ERROR", "sqlite-corrupt", False, "storage-sqlite"),
    _case("storage-recovery-log", "storage_corruption", "recovery log corrupt after unexpected shutdown", "STORAGE_CORRUPTION_ERROR", "wal-corrupt", False, "storage-wal"),
    _case("variant-config-path-posix", "configuration", "ConfigError: malformed configuration file /tmp/run-a/settings.toml", "CONFIGURATION_ERROR", "malformed-file", False, "config-malformed"),
    _case("variant-config-path-win", "configuration", r"ConfigError: malformed configuration file C:\\work\\run-b\\settings.toml", "CONFIGURATION_ERROR", "malformed-file", False, "config-malformed"),
    _case("variant-config-port", "configuration", "invalid configuration port 8765", "CONFIGURATION_ERROR", "invalid-port", False, "config-port"),
    _case("variant-config-env", "configuration", "required environment variable TCG_PORT not set", "CONFIGURATION_ERROR", "missing-environment", False, "config-env"),
    _case("variant-dependency-version", "dependency", "DependencyConflict package version conflict 9.8 versus 1.2", "DEPENDENCY_ERROR", "version-conflict", False, "dependency-version"),
    _case("variant-dependency-runtime", "dependency", "Requires Python 3.12, current Python version 3.10", "DEPENDENCY_ERROR", "runtime-version", False, "dependency-runtime"),
    _case("variant-dependency-abi", "dependency", "ABI mismatch for x86_64 binary interface", "DEPENDENCY_ERROR", "abi-mismatch", False, "dependency-abi"),
    _case("variant-dependency-wheel", "dependency", "unsupported wheel package_build_99.whl on Android", "DEPENDENCY_ERROR", "unsupported-wheel", False, "dependency-wheel"),
    _case("variant-time-parse", "data_time", "Invalid isoformat string 2030-00-00 at row 918", "DATA_TIME_ERROR", "date-parse", False, "time-parse"),
    _case("variant-time-zone", "data_time", "timezone-aware datetime required with invalid timezone", "DATA_TIME_ERROR", "timezone", False, "time-zone"),
    _case("variant-time-clock", "data_time", "system clock skew 7200 seconds", "DATA_TIME_ERROR", "clock-skew", False, "time-clock"),
    _case("variant-time-order", "data_time", "event end date before start date in row 42", "DATA_TIME_ERROR", "date-order", False, "time-order"),
    _case("variant-storage-path", "storage_corruption", "database disk image is malformed: /tmp/a/learning.db", "STORAGE_CORRUPTION_ERROR", "sqlite-corrupt", False, "storage-sqlite"),
    _case("variant-storage-wal-path", "storage_corruption", r"SQLite WAL file corrupt: C:\\data\\learning.db-wal", "STORAGE_CORRUPTION_ERROR", "wal-corrupt", False, "storage-wal"),
    _case("variant-storage-index", "storage_corruption", "corrupt database index idx_error_group_42", "STORAGE_CORRUPTION_ERROR", "index-corrupt", False, "storage-index"),
    _case("variant-storage-page", "storage_corruption", "database page checksum mismatch page 8192", "STORAGE_CORRUPTION_ERROR", "page-checksum", False, "storage-page"),
    _case("precedence-syntax-config", "syntax", "SyntaxError invalid syntax while reading malformed configuration", "INTERNAL_SYNTAX_ERROR", "syntax", False, "syntax"),
    _case("precedence-security-config", "security", "security blocked private IP from invalid configuration", "SECURITY_POLICY_BLOCK", "private-network-target", False),
    _case("precedence-memory-storage", "resource", "MemoryError while opening database disk image is malformed", "RESOURCE_EXHAUSTION", "memory", False),
    _case("precedence-storage-timeout", "storage_corruption", "database disk image is malformed after operation timeout", "STORAGE_CORRUPTION_ERROR", "sqlite-corrupt", False, "storage-sqlite"),
    _case("precedence-dependency-http", "dependency", "DependencyConflict package incompatible with runtime after HTTP status 503", "DEPENDENCY_ERROR", "version-conflict", False, "dependency-version"),
    _case("precedence-cancel-config", "process_cancelled", "CancelledError while loading invalid configuration", "PROCESS_CANCELLED", "task-cancelled", False, "task-cancelled"),
    _case("precedence-time-tls", "data_time", "system clock skew caused certificate validation failure", "DATA_TIME_ERROR", "clock-skew", False, "time-clock"),
    _case("precedence-permission-config", "filesystem", "PermissionError reading malformed configuration file releases.json", "FILE_PERMISSION_ERROR", "permission:releases.json", False, "file-permission-releases"),
    # v93: UI navigation, static/PWA assets, APIs and external-link launch contracts.
    _case("link-button-missing", "link_runtime", "MissingButtonBinding: v20apply handler has no button", "LINK_RUNTIME_ERROR", "button-binding", False, "link-button"),
    _case("link-button-variant", "link_runtime", "버튼 연결 누락: approval action id changed", "LINK_RUNTIME_ERROR", "button-binding", False, "link-button"),
    _case("link-anchor-missing", "link_runtime", "BrokenAnchorError: data-home-target points to missing section", "LINK_RUNTIME_ERROR", "anchor-target", False, "link-anchor"),
    _case("link-anchor-ko", "link_runtime", "화면 이동 대상 누락: update panel target not found", "LINK_RUNTIME_ERROR", "anchor-target", False, "link-anchor"),
    _case("link-static-404", "link_runtime", "StaticAsset404: manifest.webmanifest is absent from public files", "LINK_RUNTIME_ERROR", "static-asset", False, "link-static"),
    _case("link-static-variant", "link_runtime", "StaticAsset404 icon.svg route returned 404", "LINK_RUNTIME_ERROR", "static-asset", False, "link-static"),
    _case("link-api-route", "link_runtime", "ApiRouteMismatch: frontend /api/feature-audit has no server handler", "LINK_RUNTIME_ERROR", "api-route-method", False, "link-api"),
    _case("link-api-method", "link_runtime", "LinkContractError API method mismatch GET versus POST", "LINK_RUNTIME_ERROR", "api-route-method", False, "link-api"),
    _case("link-worker-asset", "link_runtime", "ServiceWorkerAssetMismatch: cached JSON is not publicly served", "LINK_RUNTIME_ERROR", "pwa-asset", False, "link-pwa"),
    _case("link-manifest-target", "link_runtime", "ManifestTargetMissing: start URL index.html does not exist", "LINK_RUNTIME_ERROR", "pwa-asset", False, "link-pwa"),
    _case("link-opener", "link_runtime", "UnsafeBlankOpener: target blank link is missing noopener", "LINK_RUNTIME_ERROR", "new-window", False, "link-window"),
    _case("link-popup", "link_runtime", "PopupBlockedLink: delayed multi-tab window launch was blocked", "LINK_RUNTIME_ERROR", "new-window", False, "link-window"),
    _case("link-template", "link_runtime", "ExternalUrlTemplateError: search URL contains duplicate query placeholder", "LINK_RUNTIME_ERROR", "external-template", False, "link-template"),
    _case("link-template-ko", "link_runtime", "링크 계약 오류 ExternalUrlTemplateError malformed official URL", "LINK_RUNTIME_ERROR", "external-template", False, "link-template"),
    # v94: browser camera, automatic front/back capture and image hand-off contracts.
    _case("camera-permission", "camera_runtime", "CameraPermissionDenied: user denied camera access", "CAMERA_RUNTIME_ERROR", "permission", False, "camera-permission"),
    _case("camera-permission-ko", "camera_runtime", "카메라 권한 거부 상태에서 자동촬영 시작 실패", "CAMERA_RUNTIME_ERROR", "permission", False, "camera-permission"),
    _case("camera-secure-context", "camera_runtime", "CameraSecureContextError: getUserMedia requires HTTPS", "CAMERA_RUNTIME_ERROR", "secure-context", False, "camera-secure"),
    _case("camera-media-unavailable", "camera_runtime", "getUserMedia unavailable on insecure origin", "CAMERA_RUNTIME_ERROR", "secure-context", False, "camera-secure"),
    _case("camera-not-found", "camera_runtime", "CameraNotFound: no video input device", "CAMERA_RUNTIME_ERROR", "unavailable", False, "camera-unavailable"),
    _case("camera-busy", "camera_runtime", "CameraStreamConflict: camera is already in use", "CAMERA_RUNTIME_ERROR", "unavailable", False, "camera-unavailable"),
    _case("camera-frame-zero", "camera_runtime", "CameraFrameUnavailable: video width is zero", "CAMERA_RUNTIME_ERROR", "frame-read", False, "camera-frame"),
    _case("camera-frame-read", "camera_runtime", "CameraFrameReadError: canvas could not read video frame", "CAMERA_RUNTIME_ERROR", "frame-read", False, "camera-frame"),
    _case("camera-encode", "camera_runtime", "CameraEncodeError: canvas toBlob returned null", "CAMERA_RUNTIME_ERROR", "encode", False, "camera-encode"),
    _case("camera-canvas", "camera_runtime", "CameraCanvasError: 2d context unavailable during capture", "CAMERA_RUNTIME_ERROR", "encode", False, "camera-encode"),
    _case("camera-duplicate-side", "camera_runtime", "DuplicateSideCapture: same front frame stored as back", "CAMERA_RUNTIME_ERROR", "duplicate-side", False, "camera-duplicate"),
    _case("camera-duplicate-side-ko", "camera_runtime", "앞뒷면 중복 촬영: 앞면이 뒷면으로 다시 저장됨", "CAMERA_RUNTIME_ERROR", "duplicate-side", False, "camera-duplicate"),
    _case("camera-file-handoff", "camera_runtime", "CameraFileHandoffError: captured blob did not reach analyzer", "CAMERA_RUNTIME_ERROR", "file-handoff", False, "camera-handoff"),
    _case("camera-data-transfer", "camera_runtime", "DataTransferUnavailable: iOS capture file handoff failed", "CAMERA_RUNTIME_ERROR", "file-handoff", False, "camera-handoff"),
    _case("camera-request-race", "camera_runtime", "CameraRequestRace: late permission result replaced current stream", "CAMERA_RUNTIME_ERROR", "lifecycle", False, "camera-lifecycle"),
    _case("camera-resource-leak", "camera_runtime", "CameraResourceLeak: hidden page kept camera stream active", "CAMERA_RUNTIME_ERROR", "lifecycle", False, "camera-lifecycle"),
    # v95: image quality gates, repeated internal-border centering and multi-angle scratch evidence.
    _case("vision-input-small", "vision_measurement", "VisionImageSizeError: image width 320 is below safe measurement size", "VISION_MEASUREMENT_ERROR", "input", False, "vision-input"),
    _case("vision-input-large", "vision_measurement", "VisionImageSizeError: image has more than 16000000 pixels", "VISION_MEASUREMENT_ERROR", "input", False, "vision-input"),
    _case("vision-input-length", "vision_measurement", "VisionImageDataError: RGBA pixel data length mismatch", "VISION_MEASUREMENT_ERROR", "input", False, "vision-input"),
    _case("vision-input-format", "vision_measurement", "사진 픽셀 형식 오류 VisionImageDataError", "VISION_MEASUREMENT_ERROR", "input", False, "vision-input"),
    _case("vision-quality-resolution", "vision_measurement", "VisionQualityGate: minimum dimension is below 480 pixels", "VISION_MEASUREMENT_ERROR", "quality", False, "vision-quality"),
    _case("vision-quality-blur", "vision_measurement", "VisionBlurError: Laplacian sharpness is below 25", "VISION_MEASUREMENT_ERROR", "quality", False, "vision-quality"),
    _case("vision-quality-underexposed", "vision_measurement", "VisionExposureError: mean luminance is below 45", "VISION_MEASUREMENT_ERROR", "quality", False, "vision-quality"),
    _case("vision-quality-overexposed", "vision_measurement", "VisionExposureError: clipped highlights exceed safe range", "VISION_MEASUREMENT_ERROR", "quality", False, "vision-quality"),
    _case("vision-quality-glare", "vision_measurement", "VisionGlareError: specular reflection ratio exceeds 0.07", "VISION_MEASUREMENT_ERROR", "quality", False, "vision-quality"),
    _case("vision-quality-shadow", "vision_measurement", "VisionQualityGate: illumination tile range exceeds 105", "VISION_MEASUREMENT_ERROR", "quality", False, "vision-quality"),
    _case("vision-border-missing", "vision_measurement", "VisionBorderDetectionError: four repeated internal boundaries were not found", "VISION_MEASUREMENT_ERROR", "border", False, "vision-border"),
    _case("vision-border-borderless", "vision_measurement", "VisionBorderless: full-art card has no reliable internal border", "VISION_MEASUREMENT_ERROR", "border", False, "vision-border"),
    _case("vision-border-low-contrast", "vision_measurement", "내부 보더 검출 실패: contrast strength below threshold", "VISION_MEASUREMENT_ERROR", "border", False, "vision-border"),
    _case("vision-border-inconsistent", "vision_measurement", "VisionCenteringGate: boundary support found on fewer than five scan lines", "VISION_MEASUREMENT_ERROR", "border", False, "vision-border"),
    _case("vision-perspective-trapezoid", "vision_measurement", "VisionPerspectiveError: top and bottom card widths differ by 18 percent", "VISION_MEASUREMENT_ERROR", "perspective", False, "vision-perspective"),
    _case("vision-perspective-rotation", "vision_measurement", "VisionPerspectiveError: excessive rotation caused unstable border positions", "VISION_MEASUREMENT_ERROR", "perspective", False, "vision-perspective"),
    _case("vision-perspective-ko", "vision_measurement", "원근 왜곡 및 과도한 기울기 때문에 센터링 계산 중지", "VISION_MEASUREMENT_ERROR", "perspective", False, "vision-perspective"),
    _case("vision-surface-no-oblique", "vision_measurement", "VisionObliqueMissing: no oblique-light image for scratch confirmation", "VISION_MEASUREMENT_ERROR", "surface-confidence", False, "vision-surface-confidence"),
    _case("vision-surface-glare", "vision_measurement", "VisionScratchConfidenceError: glare overlaps linear scratch candidates", "VISION_MEASUREMENT_ERROR", "surface-confidence", False, "vision-surface-confidence"),
    _case("vision-surface-art-line", "vision_measurement", "VisionScratchConfidenceError: printed artwork line cannot be separated from scratch", "VISION_MEASUREMENT_ERROR", "surface-confidence", False, "vision-surface-confidence"),
    _case("vision-surface-ko", "vision_measurement", "사선광 증거 부족 상태에서 미세 스크래치 확정 금지", "VISION_MEASUREMENT_ERROR", "surface-confidence", False, "vision-surface-confidence"),
    _case("vision-engine-missing", "vision_measurement", "VisionEngineMissing: grading_vision_engine.js did not load", "VISION_MEASUREMENT_ERROR", "engine", False, "vision-engine"),
    _case("vision-engine-canvas", "vision_measurement", "VisionCanvasError: browser 2d context unavailable", "VISION_MEASUREMENT_ERROR", "engine", False, "vision-engine"),
    _case("vision-engine-browser", "vision_measurement", "VisionBrowserCanvasUnavailable: document canvas API missing", "VISION_MEASUREMENT_ERROR", "engine", False, "vision-engine"),
)


FAMILY_GUIDANCE = {
    "network_timeout": (20, ["출처별 최근 성공시간과 현재 제한시간을 비교합니다."], ["동일 출처가 연속 실패하면 현재 실행의 추가 재시도를 중단합니다."]),
    "process_timeout": (10, ["종료되지 않은 하위 프로세스와 프로세스 그룹을 먼저 확인합니다."], ["하위 프로세스가 정리되지 않으면 재실행하지 않습니다."]),
    "process_execution": (5, ["종료코드·신호와 비식별화한 stderr를 먼저 확인합니다."], ["동일한 결정적 종료코드는 자동 재시도하지 않습니다."]),
    "process_cancelled": (1, ["사용자 중단과 작업 취소 신호를 구분하고 종료 상태를 확인합니다."], ["취소된 작업을 사용자 확인 없이 자동 재시작하지 않습니다."]),
    "http_response": (20, ["HTTP 상태와 Retry-After 존재 여부를 먼저 확인합니다."], ["401·403·404·410은 같은 주소를 자동 재시도하지 않습니다."]),
    "network_connection": (20, ["DNS·Wi-Fi·공식 호스트 접근을 분리 확인합니다."], ["사설주소 또는 비공식 주소로 우회하지 않습니다."]),
    "network_tls": (10, ["기기 시각과 인증서 호스트 일치를 확인합니다."], ["인증서 검증을 끄지 않습니다."]),
    "source_access": (4, ["응답이 공식 콘텐츠인지 CAPTCHA·봇 확인 화면인지 구분합니다."], ["자동 우회나 CAPTCHA 해제를 실행하지 않습니다."]),
    "internal_code": (5, ["문법·import 검사 후 실패 함수를 격리 실행합니다."], ["같은 결정적 예외는 네트워크 재시도하지 않습니다."]),
    "syntax": (5, ["py_compile에서 보고한 최초 오류 줄부터 확인합니다."], ["문법 검사가 통과하기 전 프로그램을 실행하지 않습니다."]),
    "security": (1, ["허용목록·DNS·Origin·실제 파일형식을 먼저 확인합니다."], ["보안차단을 자동 완화하거나 우회하지 않습니다."]),
    "filesystem": (5, ["대상 파일명·정상백업·심볼릭 링크 여부를 확인합니다."], ["검증된 정상백업이 없으면 빈 파일을 생성하지 않습니다."]),
    "file_path": (4, ["파일·디렉터리 형식과 동일 파일시스템 여부를 확인합니다."], ["잘못된 경로를 자동 삭제하거나 변경하지 않습니다."]),
    "data_encoding": (7, ["응답 문자셋·원본 바이트·UTF-8 변환 지점을 확인합니다."], ["디코딩 실패를 대체문자로 조용히 저장하지 않습니다."]),
    "data_compression": (3, ["압축 형식·CRC·압축 해제 비율을 저장 전에 확인합니다."], ["손상되거나 과도하게 팽창하는 압축파일을 자동 해제하지 않습니다."]),
    "source_content_type": (4, ["Content-Type과 실제 응답 시작 바이트가 기대 형식인지 비교합니다."], ["HTML이나 알 수 없는 형식을 JSON으로 강제 저장하지 않습니다."]),
    "data_schema": (8, ["표준 JSON·필수 필드·중복 키를 검사합니다."], ["손상 결과를 운영 파일에 저장하지 않습니다."]),
    "data_value": (8, ["자료형·유한수·허용범위를 확인합니다."], ["비정상 값을 임의 기본값으로 시세에 반영하지 않습니다."]),
    "source_structure": (15, ["공식 페이지의 현재 구조와 기존 선택자를 비교합니다."], ["검증 필드가 없으면 기존 정상자료를 유지합니다."]),
    "exchange_rate": (8, ["JPY_KRW·USD_KRW 단위와 범위를 함께 검사합니다."], ["한 통화라도 비정상이면 새 환율 세트를 반영하지 않습니다."]),
    "concurrency": (10, ["잠금 소유 프로세스와 원자저장 진행 여부를 확인합니다."], ["살아 있는 프로세스의 잠금을 시간만으로 삭제하지 않습니다."]),
    "resource": (3, ["디스크·메모리·열린 파일 한도를 먼저 측정합니다."], ["자원 부족 상태에서 새 저장을 반복하지 않습니다."]),
    "data_limit": (2, ["바이트·노드 수·중첩 깊이 중 초과 항목을 확인합니다."], ["제한 초과 입력을 학습 메모리에도 저장하지 않습니다."]),
    "data_integrity": (3, ["파일 크기·SHA-256·JSON 완전성을 비교합니다."], ["불일치 파일을 정상백업으로 승격하지 않습니다."]),
    "configuration": (4, ["필수 환경변수·포트·설정파일·허용 옵션을 확인합니다."], ["비밀값을 기록하거나 임의 설정으로 자동 대체하지 않습니다."]),
    "dependency": (3, ["Python·패키지·ABI·플랫폼 호환 조합을 확인합니다."], ["실행 중 패키지를 자동 설치하거나 버전을 임의 변경하지 않습니다."]),
    "data_time": (4, ["ISO 날짜·시간대·시계 오차·시작/종료 순서를 확인합니다."], ["잘못된 날짜를 임의 현재시각으로 바꾸지 않습니다."]),
    "storage_corruption": (2, ["SQLite 본체·WAL·인덱스·페이지 체크섬과 정상백업을 확인합니다."], ["손상 저장소를 덮어쓰거나 정상백업으로 승격하지 않습니다."]),
    "link_runtime": (2, ["버튼 ID·화면 대상·정적파일·API·서비스워커 연결을 한 번에 대조합니다."], ["연결 계약이 통과하기 전 링크를 자동 대체하거나 재시도하지 않습니다."]),
    "camera_runtime": (2, ["카메라 권한·보안 주소·프레임·앞뒷면 전환·파일 전달·스트림 해제를 순서대로 확인합니다."], ["권한을 우회하거나 실패한 촬영을 자동 분석값으로 사용하지 않습니다."]),
    "vision_measurement": (2, ["해상도·초점·노출·반사·원근·외곽/내부 보더·사선광 증거를 순서대로 확인합니다."], ["품질 또는 반복 경계 기준이 통과하지 않으면 등급을 생성하지 않습니다."]),
    "runtime": (8, ["실패 함수와 입력을 최소 범위로 격리합니다."], ["동일 결정적 오류의 무제한 재실행을 금지합니다."]),
    "unclassified": (25, ["비식별화한 예외형·함수·입력 범위를 기록합니다."], ["전용 회귀검사가 생기기 전 자동조치를 확대하지 않습니다."]),
}


def _profile_key(analysis: dict) -> str:
    return f"{analysis['code']}|{analysis['error_subtype']}"


def _safe_output(path: str | Path | None) -> Path:
    target = Path(path or PROFILE_PATH)
    if target.resolve(strict=False).parent != ROOT or target.name != PROFILE_PATH.name:
        raise ValueError("시나리오 프로필은 지정된 프로젝트 파일에만 저장할 수 있습니다.")
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("시나리오 프로필 심볼릭 링크 경로를 차단했습니다.")
    return target


def build_profiles(output: str | Path | None = None) -> dict[str, Any]:
    target = _safe_output(output)
    profiles: dict[str, dict[str, Any]] = {}
    results = []
    group_expectations: dict[str, str] = {}
    failures = []
    for scenario in SCENARIOS:
        analysis = engine.analyze_error(scenario["detail"], use_scenario_profile=False)
        actual = (analysis["code"], analysis["error_subtype"], analysis["bounded_retry_allowed"])
        expected = (scenario["code"], scenario["subtype"], scenario["retry"])
        subtype_ok = scenario["subtype"] is None or analysis["error_subtype"] == scenario["subtype"]
        ok = analysis["code"] == scenario["code"] and subtype_ok and analysis["bounded_retry_allowed"] is scenario["retry"]
        group_id = engine.error_group_key(analysis)
        prior = group_expectations.setdefault(scenario["equivalent_group"], group_id)
        if prior != group_id:
            ok = False
        results.append({"id": scenario["id"], "family": scenario["family"], "ok": ok,
                        "expected": expected, "actual": actual, "group_id": group_id})
        if not ok:
            failures.append(scenario["id"])
            continue
        key = _profile_key(analysis)
        priority, checks, stops = FAMILY_GUIDANCE[scenario["family"]]
        profile = profiles.setdefault(key, {
            "profile_id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
            "code": analysis["code"], "error_subtype": analysis["error_subtype"],
            "http_status": analysis["http_status"], "http_statuses": [],
            "verified": True, "scenario_count": 0, "scenario_ids": [], "families": [],
            "diagnostic_priority": priority, "first_checks": [],
            "fast_resolution_steps": list(analysis["resolution_steps"]),
            "verification_steps": list(analysis["verification_steps"]),
            "stop_conditions": [], "bounded_retry_allowed": analysis["bounded_retry_allowed"],
        })
        if profile["bounded_retry_allowed"] is not analysis["bounded_retry_allowed"]:
            failures.append(scenario["id"])
            continue
        profile["scenario_count"] += 1
        profile["scenario_ids"].append(scenario["id"])
        if scenario["family"] not in profile["families"]:
            profile["families"].append(scenario["family"])
        profile["diagnostic_priority"] = min(profile["diagnostic_priority"], priority)
        for value in checks:
            if value not in profile["first_checks"]:
                profile["first_checks"].append(value)
        for value in stops:
            if value not in profile["stop_conditions"]:
                profile["stop_conditions"].append(value)
        if isinstance(analysis["http_status"], int) and analysis["http_status"] not in profile["http_statuses"]:
            profile["http_statuses"].append(analysis["http_status"])
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    report = {
        "version": 1, "engine": ENGINE_VERSION, "generated_at": now,
        "training_only": True, "scenario_count": len(SCENARIOS),
        "successful_scenarios": len(SCENARIOS) - len(set(failures)),
        "failed_scenarios": sorted(set(failures)),
        "family_count": len({row["family"] for row in SCENARIOS}),
        "verified_profile_count": len(profiles), "profiles": profiles,
        "safety": {
            "production_memory_modified": False, "operational_occurrences_modified": False,
            "network_accessed": False, "scenario_text_executed": False,
            "advisory_only": True, "retry_permission_can_only_be_narrowed": True,
        },
        "automation_policy": "검증된 안내만 제공 · 문자열/생성코드 실행 금지",
        "results_sha256": hashlib.sha256(json.dumps(
            results, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest(),
        "results": results,
    }
    if failures:
        return report
    # Successful per-case rows are reproducible from SCENARIOS and consume no
    # runtime lookup value. Persist their digest instead to keep the package small.
    persisted = dict(report)
    persisted.pop("results", None)
    atomic_write_json(target, persisted, suffix=".scenario.tmp")
    return report


def run_lab() -> dict[str, Any]:
    memory_before = hashlib.sha256(safe_read_bytes(engine.MEMORY)).hexdigest() if engine.MEMORY.exists() else None
    report = build_profiles()
    memory_after = hashlib.sha256(safe_read_bytes(engine.MEMORY)).hexdigest() if engine.MEMORY.exists() else None
    loaded = engine.load_scenario_profiles(PROFILE_PATH)
    report["production_memory_unchanged"] = memory_before == memory_after
    report["loaded_profile_count"] = len(loaded["profiles"])
    report["ok"] = (not report["failed_scenarios"] and report["production_memory_unchanged"]
                    and loaded["ok"] and report["loaded_profile_count"] == report["verified_profile_count"])
    return report


if __name__ == "__main__":
    outcome = run_lab()
    print(json.dumps({key: outcome[key] for key in (
        "ok", "scenario_count", "successful_scenarios", "failed_scenarios",
        "family_count", "verified_profile_count", "loaded_profile_count",
        "production_memory_unchanged")}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if outcome["ok"] else 1)
