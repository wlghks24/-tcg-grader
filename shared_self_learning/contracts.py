from __future__ import annotations

from dataclasses import dataclass

ALLOWED_DOMAINS = {"main", "instagram_content"}


@dataclass(frozen=True)
class LearningObservation:
    """Non-executable observation shape shared by both domains.

    Algorithms may be shared. Persisted state is still namespaced per domain.
    """

    domain: str
    error_signature: str
    category: str
    evidence: str
    fix_rule: str

    def validate(self) -> None:
        if self.domain not in ALLOWED_DOMAINS:
            raise ValueError(f"unsupported learning domain: {self.domain}")
        if not self.error_signature:
            raise ValueError("error_signature is required")
        if len(self.evidence) > 1200:
            raise ValueError("evidence is too long")
        if len(self.fix_rule) > 300:
            raise ValueError("fix_rule is too long")


def namespaced_signature(domain: str, signature: str) -> str:
    if domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {domain}")
    if not signature:
        raise ValueError("signature is required")
    return f"{domain}:{signature}"
