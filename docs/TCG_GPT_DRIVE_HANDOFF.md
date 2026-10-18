# TCG verified 17-JSON -> Drive handoff — operations

The main repository's GPT TCG Drive Package workflow **generates and uploads a GitHub Actions artifact**, but the tablet checks Google Drive's `TCG_Grader_Sync/to_tablet`. These are not equivalent.

This separate workflow reacts only to a successful `GPT TCG Drive Package` run from the trusted repo's `main`. It verifies the producer HEAD matches current main; downloads only that run's named artifact; verifies the manifest's exact main SHA, expected output count, hashes and archive contents; uploads the immutable archive before the manifest using the existing `tablet_gdrive_publish.upload_package`; and does a Drive read-back. An archive-only partial upload is not eligible on tablet.

**Required user-only GitHub secret**: `TCG_RCLONE_CONFIG_B64` with a base64-encoded, authorized `rclone.conf` for the `gdrive:` remote. Do not paste OAuth credentials into GitHub code, PRs, ChatGPT chats, screenshots or logs. If the secret is absent, the handoff reports `HOLD_MISSING_DRIVE_SECRET` and publishes nothing.

A green Drive handoff **is not proof of tablet installation**. Tablet Termux must separately have the approved Drive receiver and cron running, apply matching SHA/schema-signed 17 JSON and write a receipt in `TCG_Grader_Sync/receipts`. Existing producer still blocks on stale / PSA 403 / BGS 429 source errors and must remain fail-closed; successful package generation is a prerequisite.

No root-level files added. Main code and data unchanged by this workflow itself. GitHub branch protection and normal PR review remain required.
