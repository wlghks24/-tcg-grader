# V899: preserving tablet boot wiring and collection diagnosis

The owner device reports the unified V898 routes and revision correctly, but its boot script still selects the legacy updater. Image receipt: 22 scanned, 13 saved, 5 errors, deferred; metadata_enriched=0 counts existing-photo updates only. Canonical records/pending work are not proof that every image and card has been linked. Thirty attempted event cells and four discovery leads do not establish full TCG event coverage.

## Changes
- Explicit owner-run boot helper accepts only the exact reproduced original or exact patched boot script. It preserves supervision, diagnostic logging, log rotation, and retry delay. It requires reviewed Git source and a passing running-server readback, stages and backs up outside boot/, checks shell syntax, replaces atomically, and checks hash/execute permission. Candidate boot starts the reviewed unified launcher; the old main updater remains available as a separate reviewed operation. Normal data collection remains in the unified runtime.
- Supervisor checks the running revision and adapter route, independently of provider/data/model readiness, to avoid restart storms on rate limits or insufficient labels.
- Read-only report distinguishes existing metadata updates, inventory field presence, pending exact-image/metadata/identity work, fixed error-message hints, and event attempted/fresh/partial/failed/stale/unsearched states. It prints aggregate values only. Error-message counts may not equal collector errors. Metadata field presence does not establish printed edition, photo identity, or grade.

## Evidence and boundaries
37 offline tests pass on Python 3.12.14 (temporary files/Git, shell syntax and mocked HTTP). Independent boot review found no major blocker; missing execute permission was subsequently made a failed status exit and regression tested. Selected-source preflight HIGH=0/MEDIUM=0; optional ruff/bandit/gitleaks/actionlint unavailable. Full repository validation is delegated to the existing current-head CI; source delivery remains draft until those checks pass.

No actual tablet boot, touch/camera, image pixel/edition review, collection-cycle generation proof, model training or reboot has been run by these tests. File installation is not reboot verification. Provider 403/429 cooldowns and evidence gates remain enforced. This change does not increase quotas or pretend pending external data was collected.
