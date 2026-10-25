# V673: model input safety and local evidence collection

## Reviewed baseline

The latest integrated source candidate is PR #836, HEAD
`17001bab74ff862fa488ed65792d545d5b68e261`, targeting protected main
`c5bf5608b87b19d72e5b9f73a3aa0a466230f397`. Its 20 main-targeted workflows
finished successfully. PR #814 at `172dddb0` is an earlier part of this stack.
The attached 11.27-second recording shows the prior CI report and instructions;
it does not show execution on Lenovo or provide a runtime receipt.

## Findings and repair

| Finding | Reproduced impact | Repair |
| --- | --- | --- |
| Non-string task such as a list or dictionary | Model metric predicate raises TypeError | Reject before dictionary lookup |
| Integer metric outside float range, including extra metrics | Model metric predicate raises OverflowError | Return rejection instead of aborting selection |
| Prior diagnostic entrypoint may create a log directory | Not a strictly read-only observation | Standalone stdlib collector, no runtime imports or commands |
| Fresh cached build SHA could be mistaken for live process identity | Incorrect device readiness conclusion | Report it as cached observation; keep physical verification false |

The first two findings were reproduced against the original source. The five new
behavior tests generated 29 failing subtests on the original and all passed after
the repair. No model selection thresholds, label minima, calibration, promotion
policy, historical proof JSON or V669 fixture bytes were relaxed.

Local combined behavior/provenance suite: **65/65 passed**, including 21
read-only collector tests. Architecture tests: **7/7 passed**. Repository
integrity, the 1,745-entry integrity manifest, three-layer architecture audit and
Main SELFREFINE self-test passed. These are test results for the changed scope,
not a score for model recognition accuracy or proof of device behavior.

Cross-review additionally reproduced potential Git trace-file writes and clean
filter execution during a nominal status read. The collector strips inherited
Git environment variables, disables index refresh and fsmonitor, rejects filter
configuration before status, and ignores nested submodule checkouts. Tests check
that neither the trace file nor the filter marker is created.

The immutable source repair is commit
`3973ca5baf1bcd1a90d1a7717ca3af268efa2860`. The V673 successor pins exact source
and test bytes and retains V670 ancestry. New diagnostics are supplemental tools;
the installed tablet entrypoint is unchanged.

## Local diagnostic use

The collector is a single Python file and requires no third-party package. It
does not install, update, collect data, train, start a server, send signals, access
the network, or import the runtime. It reads only selected cached JSON files and
Git metadata. It never opens arbitrary filenames listed inside those JSON files.
It emits a bounded JSON report to standard output. Missing, unsafe, stale,
mismatched or malformed observations are reported as HOLD.

From a checkout containing this file:

```bash
PYTHONDONTWRITEBYTECODE=1 python execution/tablet_readonly_preflight.py --repo "$HOME/-tcg-grader"
```

For an older installed checkout, the same standalone file can be saved to the
tablet's Download directory and run without changing the installed source:

```bash
PYTHONDONTWRITEBYTECODE=1 python "$HOME/storage/downloads/tablet_readonly_preflight.py" --repo "$HOME/-tcg-grader"
```

To save the report for review, explicitly redirect stdout to a chosen new local
file. The collector itself does not write a report or create directories.

The report deliberately omits raw Git remote URLs, local paths, device serials,
free-text errors, arbitrary status fields and credentials. A cached observation
is not proof of a running process, cold start, usable backup or verified restore.
An unknown backup/restore result remains unknown. Even a complete preflight
does not authorize deployment or model promotion.

## Acceptance and remaining evidence

Behavior tests must cover valid and malformed metrics, all validation/holdout
positions, hostile status files, stale/future timestamps, wrong repository
binding, symlink/FIFO rejection, and unchanged input/index bytes. Source lineage,
integrity, architecture and relevant full CI gates must pass on the new head.
The existing V669 model safety workflow also executes V673 and supplemental
execution/tests explicitly. Reusing it avoids an unnecessary second workflow.

Actual Lenovo execution, cold-start stability, recovery/restore and held-out
card recognition accuracy still require real device and independently reviewed
photo evidence. No physical-device PASS or arbitrary overall 95/100 score is
inferred from source tests. Main merge and tablet installation remain HOLD under
the existing instructions until those requirements are satisfied.
