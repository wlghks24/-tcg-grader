#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

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

        # A fresh lock file whose recorded owner is already dead must be
        # recovered immediately. Long-lived Termux watchers use a two-hour
        # stale window, so waiting for age alone would break fast restart.
        dead_target = Path(folder) / 'dead-owner.json'
        dead_lock = dead_target.with_suffix(dead_target.suffix + '.lock')
        dead_lock.write_text(json.dumps({'pid': 424242, 'created_at': 'now'}), encoding='utf-8')
        with mock.patch.object(safe_runtime, '_process_is_alive', return_value=False):
            with safe_runtime.exclusive_file_lock(dead_target, timeout_seconds=0.01, stale_seconds=7200):
                assert dead_lock.exists()
        assert not dead_lock.exists()

        # Conversely, a confirmed live owner must never be stolen merely
        # because a competing process uses a zero timeout.
        live_target = Path(folder) / 'live-owner.json'
        live_lock = live_target.with_suffix(live_target.suffix + '.lock')
        live_lock.write_text(json.dumps({'pid': 434343, 'created_at': 'now'}), encoding='utf-8')
        with mock.patch.object(safe_runtime, '_process_is_alive', return_value=True):
            try:
                with safe_runtime.exclusive_file_lock(live_target, timeout_seconds=0.0, stale_seconds=60):
                    raise AssertionError('live lock unexpectedly stolen')
            except TimeoutError:
                pass
        live_lock.unlink(missing_ok=True)

    print('[OK] v182 long-run runtime resilience')


if __name__ == '__main__':
    main()
