from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ALLOWED_DOMAINS = {"main", "instagram_content"}

_FORBIDDEN_EXECUTION_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:exec|eval|__import__|importlib(?:\.[A-Za-z_][A-Za-z0-9_]*)?|"
    r"runpy(?:\.[A-Za-z_][A-Za-z0-9_]*)?|pickle(?:\.[A-Za-z_][A-Za-z0-9_]*)?|"
    r"cloudpickle|joblib|marshal|compile|subprocess(?:\.[A-Za-z_][A-Za-z0-9_]*)?|"
    r"os\.system)"
    r"(?![A-Za-z0-9_])"
)


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
            raise_cycle = "fix_rule is too long"
            raise ValueError(raise_cycle)


def namespaced_signature(domain: str, signature: str) -> str:
    if domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {domain}")
    if not signature:
        raise ValueError("signature is required")
    return f"{domain}:{signature}"


def passive_exchange_violation(value: Any, path: str = "$") -> str | None:
    """Return a reason when passive exchange data contains execution markers."""

    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if _FORBIDDEN_RE := _FORBIDDEN_EXECUTION_RE.search(key_text):
                return f"{path}.{key_text}: forbidden execution marker {_FORBIDDEN_RE.group(0)!r}"
            found = passive_exchange_violation(item, f"{path}.{key_text}")
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = passive_exchange_violation(item, f"{path}[{index}]")
            if found:
                return found
        return None
    if isinstance(value, str):
        match = _FORBIDDEN_EXECUTION_RE.search(value)
        if match:
            return f"{path}: forbidden execution marker {match.group(0)!r}"
    return None


def assert_passive_exchange_payload(value: Any) -> None:
    violation = passive_exchange_violation(value)
    if violation:
        raise ValueError(f"crosscheck exchange rejected: {violation}")
