#!/usr/bin/env python3
# v243 rerun after correcting the failure-classifier regression test signature.
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
    replace_once(
        "grading_company_watch.py",
        '        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",\n',
        '        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",\n'
        '        # Match the existing bounded read contract at the HTTP layer too.\n'
        '        # This is a transfer-size limit, not a 403/429 retry or access bypass.\n'
        '        "Range": f"bytes=0-{MAX_PAGE_BYTES - 1}",\n',
    )
    replace_once(
        "safe_runtime.py",
        '            raise ValueError("unapproved host")\n',
        '            # Host-only detail is safe to expose and lets provider maintenance\n'
        '            # redirects be distinguished without following or allowlisting them.\n'
        '            raise ValueError(f"unapproved host: {host}")\n',
    )
    replace_once(
        "grading_company_watch.py",
        '    if "unapproved host" in message:\n        return "redirect_unapproved_host"\n',
        '    if "beckett-maintenance-page.s3.amazonaws.com" in message:\n'
        '        return "provider_maintenance_redirect"\n'
        '    if "unapproved host" in message:\n'
        '        return "redirect_unapproved_host"\n',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
