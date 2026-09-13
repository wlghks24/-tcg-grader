from __future__ import annotations

from pathlib import Path
import json
import sys


def patch() -> None:
    path = Path('grading_company_watch.py')
    text = path.read_text(encoding='utf-8')

    old_url = 'https://taggrading.com/pages/pricing'
    new_url = 'https://taggrading.com/collections/grading-services-official'
    if text.count(old_url) != 1:
        raise SystemExit(f'expected exactly one TAG pricing URL, found {text.count(old_url)}')
    text = text.replace(old_url, new_url, 1)

    anchor = '''def _window(text: str, alias: str, radius: int = 420) -> str | None:\n    match = re.search(re.escape(alias), text, re.I)\n    if not match:\n        return None\n    # Never look behind the matched service label: a preceding tier's fee can\n    # otherwise be attached to the next tier after a service-table redesign.\n    return text[match.start():min(len(text), match.end() + radius)]\n'''
    helper = anchor + '''\n\ndef _tag_service_window(text: str, alias: str, radius: int = 520) -> str | None:\n    \"\"\"Return one TAG product-card segment without leaking the next tier's status.\n\n    TAG's official Shopify collection renders each grading tier as a repeated\n    \"Quick buy ... GRADING | <tier> ...\" card. Bounding the window at the next\n    card prevents a later tier's Sold Out state from contaminating the current one.\n    \"\"\"\n    pattern = re.compile(\n        rf\"(?i)(?:quick\\s+buy\\s+)?(?:tag\\s+)?grading\\s*\\|\\s*{re.escape(alias)}\\b\"\n    )\n    match = pattern.search(text)\n    if not match:\n        return _window(text, alias, radius)\n    next_card = re.search(r\"(?i)\\bquick\\s+buy\\b|(?:tag\\s+)?grading\\s*\\|\", text[match.end():])\n    end = min(len(text), match.end() + radius)\n    if next_card:\n        end = min(end, match.end() + next_card.start())\n    return text[match.start():end]\n'''
    if text.count(anchor) != 1:
        raise SystemExit('expected _window anchor exactly once')
    text = text.replace(anchor, helper, 1)

    old_loop = '''        for alias in sorted(aliases, key=len, reverse=True):\n            win = _window(text, alias)\n            if win:\n                best = (alias, win)\n                break\n'''
    new_loop = '''        for alias in sorted(aliases, key=len, reverse=True):\n            win = (\n                _tag_service_window(text, alias)\n                if (company, market) == (\"TAG\", \"US\")\n                else _window(text, alias)\n            )\n            if win:\n                best = (alias, win)\n                break\n'''
    if text.count(old_loop) != 1:
        raise SystemExit('expected parse_services alias loop exactly once')
    text = text.replace(old_loop, new_loop, 1)

    old_availability = '''        fee = _price(win, currency)\n        availability = _availability(win)\n        turnaround = _turnaround(win)\n'''
    new_availability = '''        fee = _price(win, currency)\n        availability = _availability(win)\n        if (company, market) == (\"TAG\", \"US\") and fee is not None and availability == \"unknown\":\n            # On TAG's official service collection, an individual tier card carrying\n            # a Quick buy control and no Sold Out marker is currently orderable.\n            if re.search(r\"(?i)\\bquick\\s+buy\\b\", win):\n                availability = \"open\"\n        turnaround = _turnaround(win)\n'''
    if text.count(old_availability) != 1:
        raise SystemExit('expected fee/availability block exactly once')
    text = text.replace(old_availability, new_availability, 1)
    path.write_text(text, encoding='utf-8')

    test = Path('test_grading_company_watch_v215.py')
    t = test.read_text(encoding='utf-8')
    marker = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
    if t.count(marker) != 1:
        raise SystemExit('test file footer anchor missing')
    addition = r'''

    def test_tag_official_collection_layout_parses_price_and_stock_per_tier(self):
        source = "https://taggrading.com/collections/grading-services-official"
        text = (
            "TAG GRADING SERVICES OFFICIAL "
            "Quick buy GRADING | BASIC From $22.00 USD Sold Out "
            "Quick buy GRADING | STANDARD From $39.00 USD Sold Out "
            "Quick buy GRADING | EXPRESS $79.00 USD Sold Out "
            "Quick buy GRADING | PRIORITY $149.00 USD "
            "Quick buy GRADING | WALKTHROUGH $299.00 USD"
        )
        rows = watch.parse_services("TAG", "US", "USD", text, source)
        by = {row["name"]: row for row in rows}
        self.assertEqual(set(by), {"Basic", "Standard", "Express", "Priority", "Walkthrough"})
        self.assertEqual(by["Basic"]["fee"], 22.0)
        self.assertEqual(by["Standard"]["fee"], 39.0)
        self.assertEqual(by["Express"]["fee"], 79.0)
        self.assertEqual(by["Priority"]["fee"], 149.0)
        self.assertEqual(by["Walkthrough"]["fee"], 299.0)
        self.assertEqual(by["Basic"]["availability"], "paused")
        self.assertEqual(by["Standard"]["availability"], "paused")
        self.assertEqual(by["Express"]["availability"], "paused")
        self.assertEqual(by["Priority"]["availability"], "open")
        self.assertEqual(by["Walkthrough"]["availability"], "open")
        self.assertTrue(all(row["source"] == source for row in rows))

    def test_tag_pricing_source_uses_official_service_collection_without_widening_hosts(self):
        spec = next(row for row in watch.WATCH_SOURCES["TAG"] if row["id"] == "tag-pricing")
        self.assertEqual(spec["url"], "https://taggrading.com/collections/grading-services-official")
        self.assertTrue(watch._source_host_allowed(spec["url"]))
        self.assertNotIn("help.taggrading.com", watch.ALLOWED_HOSTS)
'''
    t = t.replace(marker, addition + marker, 1)
    test.write_text(t, encoding='utf-8')


def live_validate() -> None:
    import grading_company_watch as watch

    source = next(row for row in watch.WATCH_SOURCES['TAG'] if row['id'] == 'tag-pricing')['url']
    raw = watch._fetch_raw(source)
    rows = watch.parse_services('TAG', 'US', 'USD', watch._text(raw), source)
    names = {row['name'] for row in rows}
    required = {'Basic', 'Standard', 'Express', 'Priority', 'Walkthrough'}
    if not required.issubset(names):
        raise SystemExit(f'live TAG parse incomplete: {sorted(names)}')
    if any(row.get('fee') is None for row in rows if row['name'] in required):
        raise SystemExit('live TAG parse missing fee')
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        live_validate()
    else:
        patch()
