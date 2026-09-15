#!/usr/bin/env python3
# One-shot narrowing patch: preserve global URL-validation error contracts and
# expose the target host only when a redirect is rejected by the allowlist.
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0 and new in text:
        print(f"{path}: already applied")
        return
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one patch target, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"{path}: patched")


def main() -> int:
    safe = "safe_runtime.py"
    replace_once(
        safe,
        '            # Host-only detail is safe to expose and lets provider maintenance\n'
        '            # redirects be distinguished without following or allowlisting them.\n'
        '            raise ValueError(f"unapproved host: {host}")\n',
        '            raise ValueError("unapproved host")\n',
    )
    replace_once(
        safe,
        '        require_public_https(absolute, self.allowed_hosts)\n'
        '        redirected = super().redirect_request(req, fp, code, msg, headers, absolute)\n',
        '        try:\n'
        '            require_public_https(absolute, self.allowed_hosts)\n'
        '        except ValueError as exc:\n'
        '            if str(exc) == "unapproved host":\n'
        '                host = (urllib.parse.urlsplit(absolute).hostname or "").rstrip(".").lower()\n'
        '                raise ValueError(f"unapproved host: {host}") from exc\n'
        '            raise\n'
        '        redirected = super().redirect_request(req, fp, code, msg, headers, absolute)\n',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
