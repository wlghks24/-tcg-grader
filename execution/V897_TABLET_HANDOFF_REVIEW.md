# V897 — reviewed tablet handoff and HTTP readback

Source base: `96ed808772d8b2f8074b74f78158322230cf719b` (V896, all 13 existing CI workflows passed). This is a new candidate and needs its own current-head CI.

## Device evidence and scope

User-supplied readback confirms the old main generation is running on Termux, with one Android launcher owning the v135 Python server. Tracked modifications shown are root collection/learning JSON, not source files. PR #971's source changes do not overlap those runtime JSON paths. This is evidence for preparing a preserving transition, not evidence that the new UI is already installed.

No device connection is available to the development agent. No tablet command has been run by the agent. Raw user device output, photos and learning files are not uploaded.

## Delivery tools

1. `execution/apply_tablet_candidate_v897.py` is an explicit user-run handoff, supplied via the exact CI-reviewed Git commit. It does not fetch, merge main, reset, stash or force checkout.
   - Require full expected-base and target SHAs; exact repo root and HEAD, ancestor relation, support/workflow/manifest-only target changes, no deletions or runtime JSON updates.
   - Compare its own bytes to the target Git blob. Reject staged/source/overlapping local work, including **ignored** untracked collisions. Limit ignored checks to literal target paths, not photo trees. Both switch and rollback use `--no-overwrite-ignore`.
   - Confirm existing Pillow, Tesseract and Korean OCR, and refuse the old launcher's legacy Boot migration branch. Missing requirements cause HOLD **before stopping**; no package installation is attempted by this path.
   - Read the current launcher lock and confirm its PID command, exact script path and cwd. Signal only that launcher with TERM; its existing cleanup owns server/pair/RAW watchers. Wait for its lock and loopback listener to disappear; refuse an unknown/restarted owner.
   - Revalidate, back up current root JSON plus tracked diff and base SHA in an owner-private sibling folder; revalidate again, then normally detach at the exact target. Runtime JSON stays in the same worktree. External/private photos and nested runtime stores are not modified by checkout. They are not duplicated into the JSON backup.
   - Check the new code before starting. On code-check failure, attempt normal base checkout without replacing JSON. A delivery failure is reported with whether stopping completed and where the backup is; it is never called installed. Startup failures after exec still need device readback/recovery.
2. `execution/start_tablet_unified_v897.sh` hash-checks the immutable existing Android launcher and required manifest-pinned support modules, then delegates to that original launcher. No root source edits or second scheduler.
   - A Bash function dispatches only the final `python tcg_updater_v135.py` command to the V889 unified module. `exec` preserves the PID that original cleanup tracks. Other Python commands retain the real interpreter and original arguments.
   - Existing startup/bundle checks, single-server lock, wake lock, pair queue, cleanup, and RAW-learning watcher remain the original behavior. They can update/clean runtime state as before; this is **not** a promise that all runtime JSON remains byte-identical after normal server startup/collection.
   - Native requirement/legacy-Boot guards are repeated immediately before launch so the inherited package-install/Boot-rewrite branches are not deliberately entered. No grading threshold or model activation gate is bypassed. Existing approved learning watchers retain their own gates.
3. `execution/tablet_device_readback_v897.py` GETs only four fixed loopback routes: health, unified UI, all-game events and legacy feature directory. Proxies/redirects are disabled, each response prefix is bounded, and response bodies/private photo identifiers are not printed or saved.
   - Require full expected SHA, matching working-copy and startup-captured runtime SHA, valid attestation, healthy collection and specific new-route markers.
   - Report **HTTP_READBACK_OK_TOUCH_UNVERIFIED**, never physical verification, training success, completed image repair or completed event collection. Touch/camera and full collection need separate on-device evidence.

## Local evidence

- Python 3.12: **39 tests PASS** in two suites. Temporary Git histories prove dirty JSON/main refs preserved, normal rollback, staged/source/ignored collisions rejected and backups contain the current labels. No network/device processes.
- Actual Bash function/subprocess fixture proves other Python calls are forwarded and final server PID equals the original shell's tracked PID. The real TCG runtime and original launcher startup body are not run on the CI/development host.
- Readback fixtures cover old process/new worktree mismatch, incorrect routes/mime, malformed/oversized data, missing attestation, no private body leakage, redirects, unavailable service and touch/collection status kept unverified.
- Independent review reproduced an ignored-file overwrite bug; fixed with ignored collision detection plus checkout refusal, with two regression tests. It also identified same-basename process ambiguity and inherited installer/legacy-Boot side effects; exact-path and requirement guards were added and tested.
- Bash syntax and Python compilation PASS. Code Preflight v2 selected-source scan: 13 files, HIGH0/MEDIUM0, **HOLD** for partial repository scope/missing optional tools. Current-head full CI is recorded separately on PR #971.

## User-run sequence after all current-head CI passes

Fetch the known review branch through the official repository, require FETCH_HEAD to equal the reviewed full SHA, materialize the apply tool to a sibling user file, and run it with the observed full old-main SHA and exact target. The helper validates itself against Git before any stop/backup/switch. Do not pipe a network response directly into a shell.

The new server stays in the first Termux session. In a second Termux session run:

`python -m execution.tablet_device_readback_v897 --expected-sha REVIEWED_TARGET_SHA`

Then inspect unified cards/BOX/images, game/country filters, existing-feature navigation, capture/touch and actual image/event collection receipts. A 200 response alone is not completion.

This delivery is an **explicit candidate validation session**. Existing main and Boot/update scripts remain protected. Boot persistence and main release are not declared complete here; they require the device readback and subsequent reviewed delivery decision. No automatic branch merge, main push, scheduled-task change, cloud runtime, or remote device control is added.
