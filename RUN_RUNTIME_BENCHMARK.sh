#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python runtime_device_benchmark.py --label android-termux "$@"
