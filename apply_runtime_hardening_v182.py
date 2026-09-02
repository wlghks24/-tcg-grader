#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding='utf-8')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: patch anchor missing')
    return text.replace(old, new, 1)


def patch_core() -> None:
    path = 'tcg_updater.py'
    text = read(path)

    anchor = "AUTO_INTERVAL_SECONDS=6*60*60\nPRECOLLECT_LEAD_SECONDS=30*60\n"
    replacement = """AUTO_INTERVAL_SECONDS=6*60*60
PRECOLLECT_LEAD_SECONDS=30*60


def next_update_due(previous_due, now=None):
    \"\"\"Return the next future cadence slot without replaying missed cycles.\"\"\"
    moment=time.time() if now is None else float(now)
    candidate=float(previous_due)+AUTO_INTERVAL_SECONDS
    if candidate<=moment:
        skipped=int((moment-candidate)//AUTO_INTERVAL_SECONDS)+1
        candidate+=skipped*AUTO_INTERVAL_SECONDS
    return candidate
"""
    if 'def next_update_due(' not in text:
        text = replace_once(text, anchor, replacement, 'schedule helper')

    text = replace_once(
        text,
        "        next_due=due_at+AUTO_INTERVAL_SECONDS\n",
        "        next_due=next_update_due(due_at,time.time())\n",
        'finalize next-run rebasing',
    )
    text = replace_once(
        text,
        "        due += AUTO_INTERVAL_SECONDS\n\nclass Handler(SimpleHTTPRequestHandler):\n",
        "        due = next_update_due(due,time.time())\n\nclass Handler(SimpleHTTPRequestHandler):\n",
        'auto loop catch-up guard',
    )

    old_server = """class QuietThreadingHTTPServer(ThreadingHTTPServer):
    \"\"\"브라우저가 응답 중 연결을 닫을 때 생기는 정상적인 reset/broken-pipe 로그를 억제한다.\"\"\"
    def handle_error(self, request, client_address):
"""
    new_server = """class QuietThreadingHTTPServer(ThreadingHTTPServer):
    \"\"\"Bounded local HTTP worker pool with quiet normal disconnect handling.\"\"\"
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    request_queue_size = 32
    max_request_threads = env_int('TCG_HTTP_MAX_THREADS', 32, 8, 128)

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(self.max_request_threads)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b'HTTP/1.1 503 Service Unavailable\\r\\n'
                    b'Connection: close\\r\\nRetry-After: 1\\r\\nContent-Length: 0\\r\\n\\r\\n'
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

    def handle_error(self, request, client_address):
"""
    if 'max_request_threads = env_int' not in text:
        text = replace_once(text, old_server, new_server, 'bounded HTTP server')

    write(path, text)


def patch_safe_runtime() -> None:
    path = 'safe_runtime.py'
    text = read(path)
    helper = """def _fsync_parent_directory(path: str | os.PathLike[str]) -> None:
    \"\"\"Best-effort directory fsync so an atomic rename survives sudden power loss.\"\"\"
    if os.name == 'nt':
        return
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
    descriptor = None
    try:
        descriptor = os.open(os.fspath(path), flags)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


"""
    if 'def _fsync_parent_directory(' not in text:
        anchor = 'def atomic_write_bytes(\n'
        if anchor not in text:
            raise SystemExit('safe_runtime atomic writer anchor missing')
        text = text.replace(anchor, helper + anchor, 1)
    text = replace_once(
        text,
        "        os.replace(temporary, target)\n",
        "        os.replace(temporary, target)\n        _fsync_parent_directory(target.parent)\n",
        'directory fsync',
    )
    write(path, text)


def patch_v135() -> None:
    path = 'tcg_updater_v135.py'
    text = read(path)
    if 'RUNTIME_DELIVERY_PATCH = 182' not in text:
        text = replace_once(
            text,
            'RUNTIME_PATCH = 143\n',
            'RUNTIME_PATCH = 143\nRUNTIME_DELIVERY_PATCH = 182\n',
            'v135 runtime delivery version',
        )
    if "'runtime_delivery_patch': RUNTIME_DELIVERY_PATCH" not in text:
        text = replace_once(
            text,
            "                'patch': RUNTIME_PATCH,\n",
            "                'patch': RUNTIME_PATCH,\n                'runtime_delivery_patch': RUNTIME_DELIVERY_PATCH,\n                'bounded_http_workers': True,\n                'sleep_resume_catchup_guard': True,\n                'atomic_parent_directory_fsync': True,\n",
            'v135 health metadata',
        )
    text = text.replace(
        "INSTALL_GRADE_LEARNING_V135.sh로 전체 갱신 후 다시 시작하세요: ",
        "GitHub main 전체 갱신 후 다시 시작하세요(태블릿: bash ANDROID_UPDATE_AND_START.sh): ",
    )
    write(path, text)


def main() -> None:
    patch_core()
    patch_safe_runtime()
    patch_v135()
    print('[OK] v182 long-run hardening prepared')


if __name__ == '__main__':
    main()
