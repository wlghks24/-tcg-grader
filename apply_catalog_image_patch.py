#!/usr/bin/env python3
"""Compatibility entrypoint for reviewed BOX image catalog synchronization."""
from __future__ import annotations
import json
from tools.catalog_reviewed_sync import sync, _load_manifest, _catalog_bounds, _object_name, _set_box_image

if __name__ == "__main__":
    print(json.dumps(sync(), ensure_ascii=False, indent=2))
