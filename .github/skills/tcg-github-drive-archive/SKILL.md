---
name: tcg-github-drive-archive
description: 'Archive old GitHub Actions artifacts to Google Drive when Actions artifact storage reaches 50%, verify Drive readback before deletion, and locate archived artifacts in Drive. Use for GitHub storage pressure, artifact migration, archive lookup, cleanup receipts, or restore requests.'
---

# GitHub Actions artifact → Google Drive archive

## Trigger and target
- Trigger archival when GitHub Actions artifact storage reaches 50% of the configured 500 MiB plan.
- Select oldest eligible artifacts until projected usage is at or below 40%.
- Keep at least the newest artifact for every artifact name.
- Artifacts younger than 24 hours are not eligible.

## What moves
- Archive GitHub Actions artifacts only.
- Never move/delete repository source files, Git history, branches, tags, releases, or current runtime files.
- GitHub Actions caches are disposable/rebuildable and are not archived to Drive.

## Transfer
- Destination folder name: `TCG_Grader_GitHub_Archive/artifacts`.
- Archive file naming: `github-artifact-{artifact_id}-{safe_name}.zip`.
- Drive file IDs/URLs are private and must not be written to the public repository.
- Record a public-safe receipt only after Drive upload and readback succeed.

## Deletion gate
Delete the GitHub artifact only when all are true:
1. V446 receipt validates.
2. Drive upload/readback was verified.
3. Current GitHub artifact id/name/size still match the receipt.
4. Artifact is at least 24 hours old.
5. A newer artifact with the same name remains on GitHub.

## Lookup
- Search Google Drive folder `TCG_Grader_GitHub_Archive/artifacts` using the original artifact name or the archive filename.
- If a GitHub artifact is absent, consult the V446 receipt ledger to derive its archive filename, then search Drive.
- Do not claim an archived file exists until Drive search/readback confirms it.
