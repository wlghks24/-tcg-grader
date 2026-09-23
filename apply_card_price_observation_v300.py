#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parent

valuation = root / "card_grading_valuation.py"
text = valuation.read_text(encoding="utf-8")
if "import datetime as dt\n" not in text:
    text = text.replace("import ast\n", "import ast\nimport datetime as dt\n", 1)
old = '''    observed_on = str(value.get("observed_on") or "").strip()\n    observed_period = str(value.get("observed_period") or "").strip()\n    if not observed_on and not observed_period:\n        return None\n    result = {"source": source[:500], "price_type": price_type}\n'''
new = '''    observed_on = str(value.get("observed_on") or "").strip()\n    observed_period = str(value.get("observed_period") or "").strip()\n    if not observed_on and not observed_period:\n        return None\n    today = dt.datetime.now(dt.timezone.utc).date()\n    if observed_on:\n        try:\n            observed_date = dt.date.fromisoformat(observed_on)\n        except ValueError:\n            return None\n        # One-day tolerance avoids rejecting a legitimate local-calendar date near UTC midnight.\n        if observed_date > today + dt.timedelta(days=1):\n            return None\n    if observed_period:\n        if not re.fullmatch(r"\\d{4}-\\d{2}", observed_period):\n            return None\n        try:\n            period_date = dt.date.fromisoformat(observed_period + "-01")\n        except ValueError:\n            return None\n        if (period_date.year, period_date.month) > (today.year, today.month):\n            return None\n    result = {"source": source[:500], "price_type": price_type}\n'''
if old not in text:
    raise SystemExit("valuation observation block not found")
text = text.replace(old, new, 1)
valuation.write_text(text, encoding="utf-8")

gate = root / "collection_verification_gate.py"
text = gate.read_text(encoding="utf-8")
old = '''                    if observed_on:\n                        try:\n                            dt.date.fromisoformat(observed_on)\n                        except ValueError:\n                            reasons.append("invalid_observed_on")\n                    elif observed_period:\n                        if not re.fullmatch(r"\\d{4}-\\d{2}", observed_period):\n                            reasons.append("invalid_observed_period")\n                    else:\n                        reasons.append("missing_observed_time")\n'''
new = '''                    if observed_on:\n                        try:\n                            observed_date = dt.date.fromisoformat(observed_on)\n                        except ValueError:\n                            reasons.append("invalid_observed_on")\n                        else:\n                            if observed_date > now.date() + dt.timedelta(days=1):\n                                reasons.append("future_observed_on")\n                    elif observed_period:\n                        if not re.fullmatch(r"\\d{4}-\\d{2}", observed_period):\n                            reasons.append("invalid_observed_period")\n                        else:\n                            try:\n                                period_date = dt.date.fromisoformat(observed_period + "-01")\n                            except ValueError:\n                                reasons.append("invalid_observed_period")\n                            else:\n                                if (period_date.year, period_date.month) > (now.year, now.month):\n                                    reasons.append("future_observed_period")\n                    else:\n                        reasons.append("missing_observed_time")\n'''
if old not in text:
    raise SystemExit("collection gate observation block not found")
text = text.replace(old, new, 1)
gate.write_text(text, encoding="utf-8")
