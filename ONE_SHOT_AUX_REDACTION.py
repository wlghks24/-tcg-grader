#!/usr/bin/env python3
"""One-shot patch for the remaining auxiliary error-report redaction gap."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "auto_update_all.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """            except Exception as exc:
                msg=f'{type(exc).__name__}: {exc}'; errors.append(msg)
""",
        """            except Exception as exc:
                msg=diagnostic_exception(exc,1200); errors.append(msg)
""",
        "aux exception redaction",
    )
    text = replace_once(
        text,
        """        errors=[str(x) for x in (extra.get('errors') or []) if str(x).strip()]
""",
        """        errors=[auto_repair_engine.redact_sensitive(x,600) for x in (extra.get('errors') or []) if str(x).strip()]
""",
        "integration payload error redaction",
    )
    PATH.write_text(text, encoding="utf-8")
    print("auxiliary error redaction patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
