#!/usr/bin/env python3
import apply_source_gap_v6 as patch

patch.patch_provider_health()
patch.patch_routes()
patch.patch_multichannel()
patch.patch_social()
patch.patch_pipeline()
print("v6 source-only patch applied")
