#!/usr/bin/env python3
from pathlib import Path

PATH = Path("verified_code_repair_rules.py")
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"missing patch anchor: {old[:100]!r}")
    text = text.replace(old, new, 1)


replace_once(
    "import verified_neural_self_refine as neural_refine\n",
    "import verified_neural_self_refine as neural_refine\nimport verified_public_search_url_repair_v217 as public_search_repair\n",
)

replace_once(
    'TABLET_COLLECTION_HEALTH_RULE_ID = "tablet-runtime-require-collection-health-v1"\n',
    'TABLET_COLLECTION_HEALTH_RULE_ID = "tablet-runtime-require-collection-health-v1"\n'
    'PUBLIC_SEARCH_URL_RULE_ID = public_search_repair.RULE_ID\n',
)

replace_once(
    "    TABLET_COLLECTION_HEALTH_RULE_ID,\n)\nRULE_PATHS = {\n",
    "    TABLET_COLLECTION_HEALTH_RULE_ID,\n    PUBLIC_SEARCH_URL_RULE_ID,\n)\nRULE_PATHS = {\n",
)

replace_once(
    "    TABLET_COLLECTION_HEALTH_RULE_ID: frozenset({TABLET_RUNTIME_VERIFY_PATH}),\n}\n",
    "    TABLET_COLLECTION_HEALTH_RULE_ID: frozenset({TABLET_RUNTIME_VERIFY_PATH}),\n"
    "    PUBLIC_SEARCH_URL_RULE_ID: public_search_repair.RULE_PATHS,\n}\n",
)

replace_once(
    "    if relative in CORE_WORKFLOWS:\n",
    "    public_search_issue = public_search_repair.detect(relative, text)\n"
    "    if public_search_issue:\n"
    "        issues.append(public_search_issue)\n\n"
    "    if relative in CORE_WORKFLOWS:\n",
)

replace_once(
    "    if stage == \"TABLET_COLLECTION_HEALTH_NOT_ENFORCED\" and path == TABLET_RUNTIME_VERIFY_PATH:\n"
    "        return TABLET_COLLECTION_HEALTH_RULE_ID\n"
    "    return None\n",
    "    if stage == \"TABLET_COLLECTION_HEALTH_NOT_ENFORCED\" and path == TABLET_RUNTIME_VERIFY_PATH:\n"
    "        return TABLET_COLLECTION_HEALTH_RULE_ID\n"
    "    if stage == public_search_repair.STAGE and path in public_search_repair.RULE_PATHS:\n"
    "        return PUBLIC_SEARCH_URL_RULE_ID\n"
    "    return None\n",
)

replace_once(
    "    elif rule_id == TABLET_COLLECTION_HEALTH_RULE_ID:\n"
    "        payload = {\n"
    "            \"rule_id\": rule_id,\n"
    "            \"paths\": sorted(RULE_PATHS[rule_id]),\n"
    "            \"before\": STALE_TABLET_HEALTH,\n"
    "            \"after\": CURRENT_TABLET_HEALTH,\n"
    "        }\n"
    "    else:\n",
    "    elif rule_id == TABLET_COLLECTION_HEALTH_RULE_ID:\n"
    "        payload = {\n"
    "            \"rule_id\": rule_id,\n"
    "            \"paths\": sorted(RULE_PATHS[rule_id]),\n"
    "            \"before\": STALE_TABLET_HEALTH,\n"
    "            \"after\": CURRENT_TABLET_HEALTH,\n"
    "        }\n"
    "    elif rule_id == PUBLIC_SEARCH_URL_RULE_ID:\n"
    "        payload = public_search_repair.fingerprint_payload()\n"
    "    else:\n",
)

replace_once(
    "    if rule_id == TABLET_COLLECTION_HEALTH_RULE_ID:\n"
    "        return _transform_tablet_collection_health(relative, text)\n"
    "    return text\n",
    "    if rule_id == TABLET_COLLECTION_HEALTH_RULE_ID:\n"
    "        return _transform_tablet_collection_health(relative, text)\n"
    "    if rule_id == PUBLIC_SEARCH_URL_RULE_ID:\n"
    "        return public_search_repair.transform(relative, text)\n"
    "    return text\n",
)

PATH.write_text(text, encoding="utf-8")
print("public-search URL auto-repair v217 integrated")
