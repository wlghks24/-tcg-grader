#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import safe_runtime
import tcg_updater as core


def main() -> None:
    interval = core.AUTO_INTERVAL_SECONDS
    due = 1_000_000.0

    # One normal cycle keeps the original cadence.
    assert core.next_update_due(due, due + 1.0) == due + interval

    # A tablet that slept through several cycles must jump directly to the next
    # future slot instead of hammering collectors to catch up every missed run.
    woke_at = due + interval * 3 + 17.0
    next_due = core.next_update_due(due, woke_at)
    assert next_due > woke_at
    assert next_due == due + interval * 4

    server = core.QuietThreadingHTTPServer
    assert server.daemon_threads is True
    assert server.block_on_close is False
    assert 8 <= server.max_request_threads <= 128
    assert server.request_queue_size >= 16

    # Atomic replacement must also request a parent-directory fsync on POSIX.
    assert hasattr(safe_runtime, '_fsync_parent_directory')
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'state.json'
        safe_runtime.atomic_write_json(target, {'ok': True})
        assert target.read_text(encoding='utf-8').strip().startswith('{')

    print('[OK] v182 long-run runtime resilience')


if __name__ == '__main__':
    main()
