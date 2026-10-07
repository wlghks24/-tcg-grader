---
name: tcg-runtime-topology
description: 'Enforce the TCG Grader operating topology: Lenovo/Android tablet runtime, GitHub/GitHub Actions control and verification, and Google Drive verified storage/transport. Use for deployment, runtime packaging, Drive sync, update/recovery, or infrastructure changes.'
---

# Tablet + GitHub + Google Drive Topology

## Active nodes
- Tablet/Termux is the only user runtime and UI/device node.
- GitHub is source control; GitHub Actions is the only remote compute/CI/QA node.
- Google Drive is verified storage, backup, bundle transport, history, and receipt exchange.

## Optional Colab accelerator
- Google Colab Free may run bounded candidate-only verification/learning under V442.
- It is not a required operating node and does not replace GitHub Actions or the tablet runtime.
- Outputs return through Drive as candidates/receipts and require normal GitHub CI before any delivery decision.

## Explicitly inactive
- Windows/PC runtime is not required for operation.
- Other separate external cloud compute/training nodes are not required.
- Legacy PC files may remain only for compatibility/regression and must never enter ACTIVE_RUNTIME_FILES.

## Drive safety
- Preserve exact-output manifests, SHA-256 verification, stale-manifest rejection, last-good rollback, and receipt semantics.
- Drive is data transport/storage, not a trusted code-execution source.
- Never apply a Drive payload that fails repository/main SHA, manifest, file-count, size, or hash gates.

## Change rules
- Runtime changes must keep tablet deployment self-contained.
- CI-heavy analysis belongs in GitHub Actions, not on the tablet.
- Keep tablet dependencies light; ship only validated runtime files/results.
- Never claim physical tablet deployment or Drive readback without direct evidence.
