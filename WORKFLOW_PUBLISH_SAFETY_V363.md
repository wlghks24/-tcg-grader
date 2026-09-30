# Workflow Publish Safety v363

This change removes legacy GitHub Actions paths that wrote directly to `main`.
Write-capable workflows now publish a unique candidate branch and open or reuse a pull request through `scripts/publish_candidate_pr.sh`.

The shared publisher fails closed when `main` advances, when no candidate commit exists, when any required check fails or times out, or when GitHub rejects the merge. Force push and admin bypass are not permitted.

The required verification chain is: Tablet GPT TCG Grader Main Alignment, Repository Integrity Guard, Main SELFREFINE, Deep SELFREFINE Guard, Exhaustive SELFREFINE Guard, Tablet Termux Main Guard, and Android Updater Guard.

Tablet GPT sync generation v363 binds the newly watched `.github/workflows/runtime-optimization-hardening.yml` change to base main `5b18eb7c0c0721bcbedf6697e6254fe2e830f1e3` and candidate `9c11f5390aad2b59dee8f067bffb571102130203`; the generated sync quartet remains provenance-only and does not claim physical Tablet or Drive verification.

Historical v362 validation remains strict: when later watched changes exist it must discover the newest verified successor, re-check its digest and receipt, require exact candidate watched-path coverage, and fail if that successor itself leaves any watched change uncovered.

The v363 safety workflow itself is push/manual only on the exact `main` and `fix/remove-direct-main-publishers-v363-final` branches. No write token is reachable from a pull-request trigger and no wildcard branch is authorized for its write-capable reconciliation job.
