# W501–W600 | Six original source/test scopes, not a 100-version certificate

**Baseline protected main:** `6c78831bbb6e188717f86ef90243a836d2e0b67a`. **Parent selected W401 review:** PR #909, exact initial head `219149ad9720f1d5fcbb5f5646da24a977e01256`; inherited finding IDs 17+7=24 are preserved without replacing either source record. Physical Lenovo remains unverified; no release, source patch, or market data is published.

| Version | Examined real Git source/test object | What this establishes | What it does NOT establish |
|---|---|---|---|
| V503 | `test_market_links_v503.py` + `multi_market_prices.js` | HTTPS/allowlist hostile-URL fixture assertions and `safeMarketHref` source | Live provider redirect, link integrity or actual item stock |
| V516 | `test_grade_collection_handoff_v516.py` + `tcg_local_collection_v505.js` | Manual prefill, game/region/card number fixture, unsaved-data confirm source | Lenovo storage persist/readback and actual touchscreen confirmation |
| V546 | `test_static_publish_permission_denied_v546.py` + static publish workflow | Simulated GitHub HTTP403 creates a hard failure, candidate branch is retained | Real GitHub Actions role permission, actual PR publisher acceptance |
| V563 | `test_tcg_artifact_verifier_v563.py` + offline artifact verifier | 17-JSON package, tamper, symlink/ZIP misuse tests; validator explicitly returns `device_imported=False` | Actual tablet import, independent Drive readback or live sources |
| V566 | `test_tcg_card_detail_v566.py` + `tcg_card_detail_v566.js` | Saved JSON/Node fixture and CSP/static source sanity | Real device screen rendering, user navigation and performance |
| V599 | `test_official_product_catalog_v599.py` + 53-row official specification catalog | Product type/pack count/MSRP official URL domain assertions | Verified sale price, product authenticity readback, inventory or availability |

Read-only provenance audit `execution/historical_v501_v600_forensics.py` pins all 12 objects at the exact protected main Git tree, parses Python tests as AST (no importing original collector/test code), validates 53 static catalog rows, validates both parent ledgers with Git blob SHAs, and insists on **24 prior + 7 new = 31 separate scoped finding IDs**. The independent delta `execution/evidence/W501_V503_V599_FINDINGS_DELTA.json` only adds W501-F001..F007 with `EVIDENCE_GAP_NOT_A_PROVEN_RUNTIME_DEFECT`. All quality scores remain null.

**Review outcome:** Only six selected historical version scopes and 12 source/test blob identities have been inspected. We have NOT established that V501–V600 corresponds to 100 releases, run those historical modules on a Lenovo, or completed any of these six versions end-to-end. Local deterministic tests of the *forensic evaluator* are separate evidence from tests of runtime functionality.

### Next concrete work after CI
1. Compare V503/516/546/563/566/599 test assertions against current live source and commit history; identify any actual regression and code-accurate first bad SHA.
2. Verify the remaining main/PR tokens V501–V600, separating original historical version from current modified file and proving branch/tag provenance where possible.
3. For a reproduced defect, create a bounded candidate patch; run watched-path preflight (PR #904) and register reviewed successor instead of altering old assertion pins. Require target CI, full Sync, CodeQL, integrity, security, and real Lenovo evidence where appropriate.
4. Carry W501-F001..F007 with earlier unresolved P0/P1 findings to W601–W700. Do not use a blank release record to invent a score.

No direct GitHub Actions historical workflow dispatches, external-source fetch, training or tablet device operations were performed by this evidence reviewer.
