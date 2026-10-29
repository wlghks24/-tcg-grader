"""Read-only routing of repository-registered TCG skills; never execute SKILL.md."""
from __future__ import annotations

import hashlib
from pathlib import Path

# Registered first-party local skills. They are guides, not executable plugins.
SKILL_RULES = {
    "tcg-skill-router": "ALL",
    "tcg-code-review": "ALL",
    "tcg-regression-recovery": "REGRESSION",
    "tcg-test-gap-audit": "ALL",
    "tcg-mistake-proofing": "ALL",
    "tcg-agent-security": "SECURITY",
    "tcg-supply-chain": "INTEGRITY",
    "tcg-pwa-runtime-audit": "PWA",
    "tcg-local-browser-qa": "BROWSER",
    "tcg-tablet-ui": "UI",
    "tcg-ui-finish-gate": "UI",
    "tcg-visual-regression": "UI",
}
MAX_SKILL_BYTES = 45_000


def registered_skills(repo: Path, paths: list[str], git_reader,
                      risk_hints: list[dict] | None = None) -> list[dict]:
    hints = risk_hints or []
    context = {"ALL", "REGRESSION", "INTEGRITY"}
    if hints:
        context.add("SECURITY")
    if any(x.endswith(("sw.js", "manifest.webmanifest")) for x in paths):
        context.update({"PWA", "BROWSER"})
    if any(x.endswith(("index.html", "tablet.html")) for x in paths):
        context.add("UI")
    result = []
    for skill, category in SKILL_RULES.items():
        name = ".github/skills/" + skill + "/SKILL.md"
        item = {"name": skill, "path": name, "use_for": category,
                "state": "NOT_REGISTERED_IN_CHECKED_HEAD"}
        if name in paths:
            blob = git_reader(repo, "cat-file", "blob", "HEAD:" + name,
                              limit=MAX_SKILL_BYTES + 1)
            if len(blob) > MAX_SKILL_BYTES:
                item["state"] = "TOO_LARGE_SKILL_REVIEW_REQUIRED"
            else:
                try:
                    body = blob.decode("utf-8")
                    # Merely inspect the metadata: skill markdown is never executed.
                    if not body.startswith("---\n") or "\nname: " not in body[:350]:
                        item["state"] = "BAD_SKILL_METADATA_REVIEW_REQUIRED"
                    else:
                        item.update({"state": "ROUTED_READ_ONLY" if category in context
                                     else "AVAILABLE_NOT_APPLICABLE",
                                     "sha256": hashlib.sha256(blob).hexdigest(),
                                     "size_bytes": len(blob)})
                except UnicodeDecodeError:
                    item["state"] = "NON_UTF8_SKILL_REVIEW_REQUIRED"
        result.append(item)
    return result
