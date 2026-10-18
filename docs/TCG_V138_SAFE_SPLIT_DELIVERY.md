# TCG V13.8 — safe split of video fixes and verified GPT→tablet transfer

## Why this patch is separate from PR #719
Historical V351–V566 sync tests pin the exact earlier approved bytes of index.html, grading_company_updates.json and the original GPT package workflow. Do not bypass their scope guards or modify those files without a separately audited successor. The CSS title/collector input fix, verified Drive relay, and tablet receiver diagnostics can be reviewed independently.

## Changes
1. The existing social event collector rejects CSS fragments as event titles, including false 'verified' rows, without falsely filtering ordinary articles about CSS.
2. The Termux status command checks GitHub-updater and Drive JSON receiver separately, and reports HOLD if credentials, scheduled receiver, or verified receipt are absent. Existing data is never discarded on failed preflight.
3. An isolated workflow_run relay reads only a successful package artifact emitted by the existing GPT TCG Drive Package workflow **from main**. It does not execute downloaded scripts. It requires that the source SHA still equal the latest protected main HEAD, checks the exact 17-JSON schema/hashes, and uploads bundle before manifest with Drive read-back verification.
4. The GH repository secret TCG_RCLONE_CONFIG_B64 must be configured by the account owner and the existing producer must succeed. Missing credentials produce a HOLD rather than a false tablet-delivered status.

## Not claimed
No direct ChatGPT scheduled task output publishing has been verified, and no Lenovo device receipt proves auto-install. Original video frame 00:00–02:38 UI & V1–V12 parity remain open in PR #719 / gap audit. Existing contaminated static JSON is intentionally **not** edited in this fail-closed patch because frozen approved snapshots must remain immutable; next verified publication must create an explicitly reviewed successor.
