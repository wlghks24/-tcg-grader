from pathlib import Path

p = Path('grading_company_watch.py')
text = p.read_text(encoding='utf-8')
if 'TAG_PRODUCT_SOURCES = {' in text:
    raise SystemExit('TAG fallback already present; refusing duplicate insertion')
text = text.replace(
    'import json\nimport re\nimport urllib.request\n',
    'import json\nimport math\nimport re\nimport urllib.request\n',
    1,
)
marker = 'SERVICE_ALIASES = {\n'
if marker not in text:
    raise SystemExit('SERVICE_ALIASES anchor missing')
block = r'''# Official product pages provide machine-readable offers when the pricing
# overview renders its service table as an image. Require the whole tier set.
TAG_PRODUCT_SOURCES = {
    "Basic": "https://taggrading.com/products/grading-regular-new",
    "Standard": "https://taggrading.com/products/grading-standard",
    "Express": "https://taggrading.com/products/grading-express",
    "Priority": "https://taggrading.com/collections/grading-services-official/products/grading-priority",
    "Walkthrough": "https://taggrading.com/products/grading-walkthrough",
}


def parse_tag_product_offers(raw: str, name: str, source: str) -> dict:
    """Read only the named official product's offers, never review/add-on prices."""
    if source != TAG_PRODUCT_SOURCES.get(name) or not _source_host_allowed(source):
        raise ValueError("unapproved TAG product source")
    products = []
    for script_block in re.findall(r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", raw, re.I | re.S):
        try:
            value = json.loads(script_block)
        except (TypeError, ValueError):
            continue
        nodes = value if isinstance(value, list) else [value]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "Product":
                products.append(node)
    expected = "GRADING | " + name.upper()
    matches = [product for product in products if str(product.get("name", "")).strip().upper() == expected]
    if not matches:
        blocks = re.findall(r"<script\b(?=[^>]*\bid=[\"']tpo-store-data[\"'])[^>]*>(.*?)</script>", raw, re.I | re.S)
        if len(blocks) == 1:
            try:
                data = json.loads(blocks[0])
                product = data["product"]
                if (product["title"].strip().upper() == expected
                        and product["handle"] == urlsplit(source).path.rsplit("/", 1)[-1]
                        and data["shop"]["money_with_currency_format"].strip().endswith(" USD")):
                    offers = []
                    for variant in product["variants"]:
                        if type(variant["price"]) is not int or type(variant["available"]) is not bool:
                            raise ValueError("invalid TAG variant")
                        offers.append({
                            "@type": "Offer", "url": source, "priceCurrency": "USD",
                            "price": variant["price"] / 100,
                            "availability": "https://schema.org/" + ("InStock" if variant["available"] else "OutOfStock"),
                        })
                    matches = [{"name": product["title"], "url": source, "offers": offers}]
            except (KeyError, TypeError, ValueError, AttributeError):
                pass
    if len(matches) != 1:
        raise ValueError("TAG product identity missing or ambiguous")
    product = matches[0]
    slug = urlsplit(source).path.rsplit("/products/", 1)[-1]

    def same_product(url):
        return (
            isinstance(url, str)
            and _source_host_allowed(url)
            and urlsplit(url).hostname == "taggrading.com"
            and urlsplit(url).path.rsplit("/products/", 1)[-1] == slug
        )

    if not same_product(product.get("url")):
        raise ValueError("TAG product URL mismatch")
    offers = product.get("offers")
    offers = [offers] if isinstance(offers, dict) else offers
    if not isinstance(offers, list) or not offers or len(offers) > 100:
        raise ValueError("TAG product offers missing")
    prices, states = [], []
    availability = {"InStock": "open", "OutOfStock": "paused", "SoldOut": "paused"}
    for offer in offers:
        if (
            not isinstance(offer, dict)
            or offer.get("@type") != "Offer"
            or offer.get("priceCurrency") != "USD"
            or not same_product(offer.get("url"))
        ):
            raise ValueError("TAG offer provenance or currency mismatch")
        value = offer.get("price")
        if isinstance(value, bool):
            raise ValueError("invalid TAG offer price")
        price = float(value)
        if not math.isfinite(price) or not 5 <= price <= 50_000:
            raise ValueError("invalid TAG offer price")
        state = str(offer.get("availability", ""))
        if state not in {
            prefix + key
            for prefix in ("https://schema.org/", "http://schema.org/")
            for key in availability
        }:
            raise ValueError("unknown TAG offer availability")
        prices.append(price)
        states.append(availability[state.rsplit("/", 1)[-1]])
    eligible = [price for price, state in zip(prices, states) if state == "open"] or prices
    return {
        "name": name,
        "observed_label": product["name"],
        "currency": "USD",
        "fee": min(eligible),
        "fee_basis": "lowest_available_variant_or_listed_if_paused",
        "availability": "open" if "open" in states else "paused",
        "source": source,
        "verified_official_source": True,
        "parser_version": PARSER_VERSION,
        "evidence_format": "official_product_structured_offers",
    }


def fetch_tag_product_services(fetcher) -> list[dict]:
    rows = []
    for name, url in TAG_PRODUCT_SOURCES.items():
        if not _source_host_allowed(url) or urlsplit(url).hostname != "taggrading.com":
            raise ValueError("unapproved TAG product source")
        rows.append(parse_tag_product_offers(fetcher(url), name, url))
    return rows


'''
text = text.replace(marker, block + marker, 1)
old = '''                services = parse_services(company, spec["market"], spec["currency"], text, spec["url"]) if "pricing" in spec["kind"] else []
                if "pricing" in spec["kind"] and not services:
'''
new = '''                services = parse_services(company, spec["market"], spec["currency"], text, spec["url"]) if "pricing" in spec["kind"] else []
                if company == "TAG" and "pricing" in spec["kind"] and not services:
                    try:
                        services = fetch_tag_product_services(fetcher)
                    except Exception as exc:
                        raise ValueError("pricing parser yielded zero verified services; TAG official fallback failed: " + diagnostic_exception(exc)) from exc
                if "pricing" in spec["kind"] and not services:
'''
if old not in text:
    raise SystemExit('collect services anchor missing')
text = text.replace(old, new, 1)
if 'PARSER_VERSION = 3' in text:
    raise SystemExit('global parser version unexpectedly changed')
p.write_text(text, encoding='utf-8')
