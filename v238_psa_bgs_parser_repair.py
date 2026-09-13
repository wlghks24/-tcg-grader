from pathlib import Path

watch = Path('grading_company_watch.py')
text = watch.read_text(encoding='utf-8')

old_helpers = '''def _window(text: str, alias: str, radius: int = 420) -> str | None:\n    match = re.search(re.escape(alias), text, re.I)\n    if not match:\n        return None\n    # Never look behind the matched service label: a preceding tier's fee can\n    # otherwise be attached to the next tier after a service-table redesign.\n    return text[match.start():min(len(text), match.end() + radius)]\n\n\ndef _tag_service_window(text: str, alias: str, radius: int = 520) -> str | None:\n    \"\"\"Return one TAG product-card segment without leaking the next tier's status.\n\n    TAG's official Shopify collection renders each grading tier as a repeated\n    \"Quick buy ... GRADING | <tier> ...\" card. Bounding the window at the next\n    card prevents a later tier's Sold Out state from contaminating the current one.\n    \"\"\"\n    pattern = re.compile(\n        rf\"(?i)(?:quick\\s+buy\\s+)?(?:tag\\s+)?grading\\s*\\|\\s*{re.escape(alias)}\\b\"\n    )\n    match = pattern.search(text)\n    if not match:\n        return _window(text, alias, radius)\n    next_card = re.search(r\"(?i)\\bquick\\s+buy\\b|(?:tag\\s+)?grading\\s*\\|\", text[match.end():])\n    end = min(len(text), match.end() + radius)\n    if next_card:\n        end = min(end, match.end() + next_card.start())\n    return text[match.start():end]\n'''

new_helpers = '''def _window(text: str, alias: str, radius: int = 420) -> str | None:\n    match = re.search(re.escape(alias), text, re.I)\n    if not match:\n        return None\n    # Never look behind the matched service label: a preceding tier's fee can\n    # otherwise be attached to the next tier after a service-table redesign.\n    return text[match.start():min(len(text), match.end() + radius)]\n\n\ndef _nonoverlap_alias_match(text: str, alias: str, peer_aliases: tuple[str, ...]) -> re.Match[str] | None:\n    \"\"\"Find an alias without accepting a shorter label embedded in a peer tier.\n\n    PSA uses overlapping names such as Value / Value Plus / Value Max and\n    Express / Super Express. A plain substring search can silently duplicate the\n    longer tier under the shorter canonical name.\n    \"\"\"\n    pattern = re.compile(re.escape(alias), re.I)\n    lower_alias = alias.casefold()\n    peers = tuple(value for value in peer_aliases if value.casefold() != lower_alias)\n    for match in pattern.finditer(text):\n        start, end = match.span()\n        contaminated = False\n        for peer in peers:\n            folded = peer.casefold()\n            if folded.startswith(lower_alias):\n                tail = peer[len(alias):]\n                if tail and text[end:end + len(tail)].casefold() == tail.casefold():\n                    contaminated = True\n                    break\n            if folded.endswith(lower_alias):\n                head = peer[:-len(alias)]\n                if head and text[max(0, start - len(head)):start].casefold() == head.casefold():\n                    contaminated = True\n                    break\n        if not contaminated:\n            return match\n    return None\n\n\ndef _psa_service_window(text: str, alias: str, peer_aliases: tuple[str, ...], radius: int = 520) -> str | None:\n    \"\"\"Bound one PSA tier while rejecting overlapping service-name matches.\"\"\"\n    match = _nonoverlap_alias_match(text, alias, peer_aliases)\n    if not match:\n        return None\n    end = min(len(text), match.end() + radius)\n    next_starts = []\n    for peer in peer_aliases:\n        peer_match = _nonoverlap_alias_match(text[match.end():], peer, peer_aliases)\n        if peer_match:\n            next_starts.append(match.end() + peer_match.start())\n    if next_starts:\n        end = min(end, min(next_starts))\n    return text[match.start():end]\n\n\ndef _tag_service_window(text: str, alias: str, radius: int = 520) -> str | None:\n    \"\"\"Return one TAG product-card segment without leaking the next tier's status.\n\n    TAG's official Shopify collection renders each grading tier as a repeated\n    \"Quick buy ... GRADING | <tier> ...\" card. Bounding the window at the next\n    card prevents a later tier's Sold Out state from contaminating the current one.\n    \"\"\"\n    pattern = re.compile(\n        rf\"(?i)(?:quick\\s+buy\\s+)?(?:tag\\s+)?grading\\s*\\|\\s*{re.escape(alias)}\\b\"\n    )\n    match = pattern.search(text)\n    if not match:\n        return _window(text, alias, radius)\n    next_card = re.search(r\"(?i)\\bquick\\s+buy\\b|(?:tag\\s+)?grading\\s*\\|\", text[match.end():])\n    end = min(len(text), match.end() + radius)\n    if next_card:\n        end = min(end, match.end() + next_card.start())\n    return text[match.start():end]\n'''
if text.count(old_helpers) != 1:
    raise SystemExit('service-window helper anchor mismatch')
text = text.replace(old_helpers, new_helpers, 1)

old_parse = '''def parse_services(company: str, market: str, currency: str, text: str, source: str) -> list[dict]:\n    rows: list[dict] = []\n    for canonical, aliases in SERVICE_ALIASES.get((company, market), {}).items():\n        best: tuple[str, str] | None = None\n        for alias in sorted(aliases, key=len, reverse=True):\n            win = (\n                _tag_service_window(text, alias)\n                if (company, market) == (\"TAG\", \"US\")\n                else _window(text, alias)\n            )\n            if win:\n                best = (alias, win)\n                break\n        if not best:\n            continue\n        alias, win = best\n        fee = _price(win, currency)\n        availability = _availability(win)\n        if (company, market) == (\"TAG\", \"US\") and fee is not None and availability == \"unknown\":\n            # On TAG's official service collection, an individual tier card carrying\n            # a Quick buy control and no Sold Out marker is currently orderable.\n            if re.search(r\"(?i)\\bquick\\s+buy\\b\", win):\n                availability = \"open\"\n        turnaround = _turnaround(win)\n        max_value = _max_value(win, currency)\n        # A menu label alone is too weak to become a service fact.\n        if fee is None and turnaround is None and max_value is None and availability != \"paused\":\n            continue\n        row = {\n            \"name\": canonical, \"observed_label\": alias, \"currency\": currency,\n            \"availability\": availability, \"source\": source, \"verified_official_source\": True,\n            \"parser_version\": PARSER_VERSION,\n        }\n        if fee is not None:\n            row[\"fee\"] = fee\n        if turnaround is not None:\n            row[\"turnaround_business_days\"] = turnaround\n        if max_value is not None:\n            row[\"max_declared_or_insured_value\"] = max_value\n        rows.append(row)\n    return rows\n'''

new_parse = '''def _service_row(name: str, observed_label: str, currency: str, source: str, *,\n                 fee=None, turnaround=None, max_value=None, availability: str = \"unknown\") -> dict:\n    row = {\n        \"name\": name, \"observed_label\": observed_label, \"currency\": currency,\n        \"availability\": availability, \"source\": source, \"verified_official_source\": True,\n        \"parser_version\": PARSER_VERSION,\n    }\n    if fee is not None:\n        row[\"fee\"] = fee\n    if turnaround is not None:\n        row[\"turnaround_business_days\"] = turnaround\n    if max_value is not None:\n        row[\"max_declared_or_insured_value\"] = max_value\n    return row\n\n\ndef _parse_bgs_services(currency: str, text: str, source: str) -> list[dict]:\n    \"\"\"Parse Beckett's current tier cards, including both Base price variants.\"\"\"\n    tier_names = (\"Base\", \"Standard\", \"Express\", \"Priority\")\n    markers: list[tuple[int, int, str, int]] = []\n    for name in tier_names:\n        pattern = re.compile(rf\"(?i)\\b{re.escape(name)}\\b\\s+(\\d{{1,3}})\\+?\\s+business\\s+days?\")\n        match = pattern.search(text)\n        if not match:\n            # Fail closed: a partial layout must not be accepted as a current BGS table.\n            return []\n        markers.append((match.start(), match.end(), name, int(match.group(1))))\n    markers.sort()\n    segments: dict[str, tuple[str, int]] = {}\n    for index, (start, _end, name, days) in enumerate(markers):\n        stop = markers[index + 1][0] if index + 1 < len(markers) else min(len(text), start + 900)\n        segments[name] = (text[start:stop], days)\n\n    rows: list[dict] = []\n    base, base_days = segments[\"Base\"]\n    base_prices = [float(value.replace(\",\", \"\")) for value in\n                   re.findall(r\"\\$\\s*([0-9][0-9,]*(?:\\.[0-9]{1,2})?)\\s+per\\s+card\", base, re.I)]\n    if len(base_prices) != 2:\n        return []\n    first_price = re.search(r\"\\$\\s*[0-9][0-9,]*(?:\\.[0-9]{1,2})?\\s+per\\s+card\", base, re.I)\n    second_price = list(re.finditer(r\"\\$\\s*[0-9][0-9,]*(?:\\.[0-9]{1,2})?\\s+per\\s+card\", base, re.I))[1]\n    without_window = base[first_price.start():second_price.start()] if first_price else base[:second_price.start()]\n    with_window = base[second_price.start():]\n    rows.append(_service_row(\n        \"Base\", \"Base / Without Subgrades\", currency, source,\n        fee=base_prices[0], turnaround=base_days, availability=_availability(without_window),\n    ))\n    rows.append(_service_row(\n        \"Base + Subgrades\", \"Base / Subgrades\", currency, source,\n        fee=base_prices[1], turnaround=base_days, availability=_availability(with_window),\n    ))\n\n    for name in (\"Standard\", \"Express\", \"Priority\"):\n        segment, days = segments[name]\n        prices = [float(value.replace(\",\", \"\")) for value in\n                  re.findall(r\"\\$\\s*([0-9][0-9,]*(?:\\.[0-9]{1,2})?)\\s+per\\s+card\", segment, re.I)]\n        if len(prices) != 1:\n            return []\n        rows.append(_service_row(\n            name, name, currency, source, fee=prices[0], turnaround=days,\n            availability=_availability(segment),\n        ))\n    return rows\n\n\ndef _parse_alias_services(company: str, market: str, currency: str, text: str, source: str) -> list[dict]:\n    rows: list[dict] = []\n    alias_map = SERVICE_ALIASES.get((company, market), {})\n    peer_aliases = tuple(dict.fromkeys(alias for aliases in alias_map.values() for alias in aliases))\n    for canonical, aliases in alias_map.items():\n        best: tuple[str, str] | None = None\n        for alias in sorted(aliases, key=len, reverse=True):\n            if (company, market) == (\"TAG\", \"US\"):\n                win = _tag_service_window(text, alias)\n            elif company == \"PSA\":\n                win = _psa_service_window(text, alias, peer_aliases)\n            else:\n                win = _window(text, alias)\n            if win:\n                best = (alias, win)\n                break\n        if not best:\n            continue\n        alias, win = best\n        fee = _price(win, currency)\n        availability = _availability(win)\n        if (company, market) == (\"TAG\", \"US\") and fee is not None and availability == \"unknown\":\n            if re.search(r\"(?i)\\bquick\\s+buy\\b\", win):\n                availability = \"open\"\n        turnaround = _turnaround(win)\n        max_value = _max_value(win, currency)\n        if fee is None and turnaround is None and max_value is None and availability != \"paused\":\n            continue\n        rows.append(_service_row(\n            canonical, alias, currency, source, fee=fee, turnaround=turnaround,\n            max_value=max_value, availability=availability,\n        ))\n    return rows\n\n\ndef parse_services(company: str, market: str, currency: str, text: str, source: str) -> list[dict]:\n    # Beckett's Base tier contains two distinct price variants inside one tier card,\n    # so a generic alias/radius parser cannot represent it safely. Keep it isolated.\n    if (company, market) == (\"BGS\", \"US\"):\n        return _parse_bgs_services(currency, text, source)\n    return _parse_alias_services(company, market, currency, text, source)\n'''
if text.count(old_parse) != 1:
    raise SystemExit('parse_services anchor mismatch')
text = text.replace(old_parse, new_parse, 1)
watch.write_text(text, encoding='utf-8')


test = Path('test_grading_company_watch_v215.py')
t = test.read_text(encoding='utf-8')
footer = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
if t.count(footer) != 1:
    raise SystemExit('test footer anchor mismatch')
addition = r'''

    def test_bgs_current_layout_parses_base_variants_and_tier_local_availability(self):
        source = "https://www.beckett.com/grading"
        text = (
            "Base 75+ business days $14.95 per card $3 fee for any 10s where subgrades are added "
            "Sold Out Without Subgrades Notify me $17.95 per card Sold Out Subgrades Notify me "
            "Standard 45 business days $34.95 per card Sold Out Subgrades Notify me "
            "Express 15 business days $79.95 per card Subgrades Submit Now "
            "Priority 5 business days $124.95 per card Subgrades Submit Now"
        )
        rows = watch.parse_services("BGS", "US", "USD", text, source)
        by = {row["name"]: row for row in rows}
        self.assertEqual(set(by), {"Base", "Base + Subgrades", "Standard", "Express", "Priority"})
        self.assertEqual(by["Base"]["fee"], 14.95)
        self.assertEqual(by["Base + Subgrades"]["fee"], 17.95)
        self.assertEqual(by["Standard"]["fee"], 34.95)
        self.assertEqual(by["Express"]["fee"], 79.95)
        self.assertEqual(by["Priority"]["fee"], 124.95)
        self.assertEqual(by["Base"]["turnaround_business_days"], 75)
        self.assertEqual(by["Standard"]["turnaround_business_days"], 45)
        self.assertEqual(by["Express"]["turnaround_business_days"], 15)
        self.assertEqual(by["Priority"]["turnaround_business_days"], 5)
        self.assertEqual(by["Base"]["availability"], "paused")
        self.assertEqual(by["Base + Subgrades"]["availability"], "paused")
        self.assertEqual(by["Standard"]["availability"], "paused")
        self.assertEqual(by["Express"]["availability"], "open")
        self.assertEqual(by["Priority"]["availability"], "open")

    def test_bgs_partial_layout_fails_closed_instead_of_publishing_mixed_tiers(self):
        text = "Base 75+ business days $14.95 per card Sold Out Without Subgrades $17.95 per card Sold Out Subgrades"
        self.assertEqual(watch.parse_services("BGS", "US", "USD", text, "https://www.beckett.com/grading"), [])

    def test_psa_overlapping_aliases_do_not_duplicate_longer_tiers(self):
        source = "https://www.psacard.com/services/t"
        text = (
            "Currently Unavailable Value Bulk Max Insured Value: $500 "
            "Currently Unavailable Value Max Insured Value: $500 "
            "Currently Unavailable Value Plus Max Insured Value: $500 "
            "Currently Unavailable Value Max Max Insured Value: $1,000 "
            "Regular $79.99/Card Max Insured Value: $1,500 Estimated Turnaround Time: 70 - 80 Business Days Get Started "
            "Express $149.00/Card Max Insured Value: $2,500 Estimated Turnaround Time: 20 - 30 Business Days Get Started "
            "Super Express $299.00/Card Max Insured Value: $5,000 Estimated Turnaround Time: 10 Business Days Get Started"
        )
        rows = watch.parse_services("PSA", "US", "USD", text, source)
        by = {row["name"]: row for row in rows}
        self.assertEqual(by["Value Bulk"]["max_declared_or_insured_value"], 500.0)
        self.assertEqual(by["Value"]["max_declared_or_insured_value"], 500.0)
        self.assertEqual(by["Value Plus"]["max_declared_or_insured_value"], 500.0)
        self.assertEqual(by["Value Max"]["max_declared_or_insured_value"], 1000.0)
        self.assertEqual(by["Express"]["fee"], 149.0)
        self.assertEqual(by["Super Express"]["fee"], 299.0)
'''
t = t.replace(footer, addition + footer, 1)
test.write_text(t, encoding='utf-8')
