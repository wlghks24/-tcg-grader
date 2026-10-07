---
name: tcg-free-quota
description: 'Keep TCG Grader optional cloud/CI work inside free limits. Use for Google Colab Free retry state, GitHub Actions public-standard runner policy, artifact/cache budgets, quota wait/recheck/resume, or private-repository fallback.'
---

# Free Quota Control

## Colab Free
- Account-specific remaining GPU quota is not treated as knowable unless Google exposes it directly.
- Persist QUOTA_WAIT state and next_check_at in Google Drive.
- Recheck only on the next manually started Colab session; no keep-alive, background polling, reconnect loop, or quota bypass.
- CPU-safe verification may continue while GPU-only work waits.
- Resume only bounded, allowlisted candidate work from a recorded checkpoint.

## GitHub Actions
- Public repository + standard GitHub-hosted runner is the preferred free path.
- Larger, unknown, or self-hosted runner labels are not allowed by the free policy.
- Check Actions artifact and cache usage on a six-hour cadence.
- Nonessential scheduled jobs must run the V444 preflight and enter quota wait when storage is near the configured reserve.
- When usage falls below the reserve, the next scheduled run may proceed automatically.
- If the repository becomes private, fail closed unless billing usage is available; use a conservative included-minute budget.

## Safety
- Do not buy Compute Units, larger runners, paid cloud capacity, or silently enable billing.
- Do not weaken verification to save quota.
- Do not claim a quota recovery time that the provider does not expose.
