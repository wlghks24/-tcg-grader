from pathlib import Path

watch = Path('grading_company_watch.py')
text = watch.read_text(encoding='utf-8')
anchor = '''def _load_previous(path: Path = OUT) -> dict:\n    try:\n        data = json.loads(safe_read_text(path, max_bytes=8_000_000))\n        return data if isinstance(data, dict) else {}\n    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):\n        return {}\n\n\ndef collect(previous: dict | None = None, fetcher=_fetch_raw) -> dict:\n'''
replacement = '''def _load_previous(path: Path = OUT) -> dict:\n    try:\n        data = json.loads(safe_read_text(path, max_bytes=8_000_000))\n        return data if isinstance(data, dict) else {}\n    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):\n        return {}\n\n\ndef _source_failure_class(exc: Exception) -> str:\n    \"\"\"Classify source failures without weakening the official-source gate.\"\"\"\n    code = getattr(exc, \"code\", None)\n    if code == 403:\n        return \"http_forbidden\"\n    if code == 429:\n        return \"rate_limited\"\n    message = str(exc).casefold()\n    if \"unapproved host\" in message:\n        return \"redirect_unapproved_host\"\n    if \"pricing parser yielded zero verified services\" in message:\n        return \"parser_no_verified_services\"\n    if \"official page body too short\" in message:\n        return \"source_body_invalid\"\n    return \"source_error\"\n\n\ndef collect(previous: dict | None = None, fetcher=_fetch_raw) -> dict:\n'''
if text.count(anchor) != 1:
    raise SystemExit('failure-class helper anchor mismatch')
text = text.replace(anchor, replacement, 1)
old = '''            except Exception as exc:\n                old_verified = bool(\n                    old.get(\"verified_official_source\") is True\n                    and old.get(\"signal_fingerprint\")\n                )\n'''
new = '''            except Exception as exc:\n                failure_class = _source_failure_class(exc)\n                old_verified = bool(\n                    old.get(\"verified_official_source\") is True\n                    and old.get(\"signal_fingerprint\")\n                )\n'''
if text.count(old) != 1:
    raise SystemExit('failure-class exception anchor mismatch')
text = text.replace(old, new, 1)
old = '''                retained.update({\n                    \"status\": \"degraded\", \"checked_at\": checked_at,\n                    \"last_error\": diagnostic_exception(exc), \"verified_official_source\": old_verified,\n                })\n'''
new = '''                retained.update({\n                    \"status\": \"degraded\", \"checked_at\": checked_at,\n                    \"last_error\": diagnostic_exception(exc), \"failure_class\": failure_class,\n                    \"verified_official_source\": old_verified,\n                })\n'''
if text.count(old) != 1:
    raise SystemExit('failure-class retained anchor mismatch')
text = text.replace(old, new, 1)
old = '''                health.append({\n                    \"source_id\": source_id, \"status\": \"degraded\", \"url\": spec[\"url\"],\n                    \"error\": diagnostic_exception(exc),\n                })\n'''
new = '''                health.append({\n                    \"source_id\": source_id, \"status\": \"degraded\", \"url\": spec[\"url\"],\n                    \"error\": diagnostic_exception(exc), \"failure_class\": failure_class,\n                })\n'''
if text.count(old) != 1:
    raise SystemExit('failure-class health anchor mismatch')
text = text.replace(old, new, 1)
watch.write_text(text, encoding='utf-8')

test = Path('test_grading_company_watch_v215.py')
t = test.read_text(encoding='utf-8')
footer = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
if t.count(footer) != 1:
    raise SystemExit('test footer anchor missing')
addition = r'''

    def test_source_failure_classes_keep_blocked_sources_distinct(self):
        class Blocked(Exception):
            code = 403

        class Limited(Exception):
            code = 429

        self.assertEqual(watch._source_failure_class(Blocked("forbidden")), "http_forbidden")
        self.assertEqual(watch._source_failure_class(Limited("rate limited")), "rate_limited")
        self.assertEqual(watch._source_failure_class(ValueError("unapproved host")), "redirect_unapproved_host")
        self.assertEqual(
            watch._source_failure_class(ValueError("pricing parser yielded zero verified services")),
            "parser_no_verified_services",
        )
        self.assertEqual(watch._source_failure_class(OSError("network down")), "source_error")

    def test_failure_class_is_persisted_in_source_and_health_rows(self):
        class Blocked(Exception):
            code = 403

        def fail(_url):
            raise Blocked("forbidden")

        out = watch.collect({}, fail)
        self.assertTrue(out["sources"])
        self.assertTrue(all(row.get("failure_class") == "http_forbidden" for row in out["sources"].values()))
        health = [row for company in out["companies"].values() for row in company["source_health"]]
        self.assertTrue(health)
        self.assertTrue(all(row.get("failure_class") == "http_forbidden" for row in health))
'''
t = t.replace(footer, addition + footer, 1)
test.write_text(t, encoding='utf-8')
