# Workflow Publish Safety v363

This change removes legacy GitHub Actions paths that wrote directly to `main`.
Write-capable workflows now publish a unique candidate branch and open or reuse a pull request through `scripts/publish_candidate_pr.sh`.

The shared publisher fails closed when `main` advances, when no candidate commit exists, when any required check fails or times out, or when GitHub rejects the merge. Force push and admin bypass are not permitted.

The required verification chain is: Tablet GPT TCG Grader Main Alignment, Repository Integrity Guard, Main SELFREFINE, Deep SELFREFINE Guard, Exhaustive SELFREFINE Guard, Tablet Termux Main Guard, and Android Updater Guard.
