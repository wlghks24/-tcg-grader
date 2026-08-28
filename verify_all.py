#!/usr/bin/env python3
"""Compatibility entry point for the current v109 release gate.

The historical v79-v99 assertions remain in verify_all_legacy_v99.py for
forensic reference only. They check removed aliases and old version strings,
so they do not decide current release health.
"""
from verify_v109_final import main


if __name__ == "__main__":
    raise SystemExit(main())
