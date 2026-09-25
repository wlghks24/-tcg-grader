#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


old_source = r'''GRADER_QUERY_RE=re.compile(r'\b(?:PSA|BGS|CGC|TAG|BRG)\s*(?:10|[1-9])(?:\.5)?(?:\s*BLACK\s*LABEL)?\b',re.I)


def _query_card_number_match(query):
    text=str(query or '')
    for match in CARD_NUMBER_QUERY_RE.finditer(text):
        token=match.group(0).strip()
        prefix=text[max(0,match.start()-16):match.start()]
        if GRADER_QUERY_RE.fullmatch(token) or re.search(r'(?:PSA|BGS|CGC|TAG|BRG)\s*$',prefix,re.I):continue
        compact=_normalize_card_number(token)
        if compact.isdigit() and len(compact)==4 and 1996<=int(compact)<=2099:continue
        return match
    return None
'''
new_source = r'''GRADER_QUERY_RE=re.compile(
    r'\b(?:PSA|BGS|CGC|TAG|BRG)\s*[:#-]?\s*(?:10|[1-9])(?:\s*\.\s*(?:0|5))?(?:\s*BLACK\s*LABEL)?\b',
    re.I,
)


def _iter_card_number_matches(text):
    """Yield card-number tokens while excluding grader scores and copyright years.

    Decimal grading labels such as BGS 9.5 or PSA 10.0 contain standalone digit
    fragments that also satisfy the generic card-number regex.  Excluding the
    complete grader span prevents the decimal tail from becoming a fake card ID
    in both query parsing and listing identity checks.
    """
    text=str(text or '')
    grade_spans=[(match.start(),match.end()) for match in GRADER_QUERY_RE.finditer(text)]
    for match in CARD_NUMBER_QUERY_RE.finditer(text):
        if any(match.start()<end and match.end()>start for start,end in grade_spans):
            continue
        token=match.group(0).strip()
        prefix=text[max(0,match.start()-16):match.start()]
        if re.search(r'(?:PSA|BGS|CGC|TAG|BRG)\s*[:#-]?\s*$',prefix,re.I):
            continue
        compact=_normalize_card_number(token)
        if compact.isdigit() and len(compact)==4 and 1996<=int(compact)<=2099:
            continue
        yield match


def _query_card_number_match(query):
    return next(_iter_card_number_matches(query),None)
'''
replace_once("multi_market_price_collector.py", old_source, new_source)

old_blob = r'''def _identity_blob_numbers(value):
    text=str(value or '').upper().replace('–','-').replace('—','-')
    found=[]
    for match in CARD_NUMBER_QUERY_RE.finditer(text):
        token=_normalize_card_number(match.group(0))
        if token and token not in found:found.append(token)
    return found[:32]
'''
new_blob = r'''def _identity_blob_numbers(value):
    text=str(value or '').upper().replace('–','-').replace('—','-')
    found=[]
    for match in _iter_card_number_matches(text):
        token=_normalize_card_number(match.group(0))
        if token and token not in found:found.append(token)
    return found[:32]
'''
replace_once("multi_market_price_collector.py", old_blob, new_blob)

old_test = r'''    def test_grade_number_is_not_mistaken_for_card_number(self):
        name,number=m._tcgdex_query_parts('Pikachu PSA 10 English')
        self.assertEqual(number,'')
        self.assertEqual(name,'Pikachu')
        name,number=m._tcgdex_query_parts('Pikachu 025 PSA 10 English')
        self.assertEqual(m._normalize_card_number(number),'025')
        self.assertEqual(name,'Pikachu')
'''
new_test = r'''    def test_grade_number_is_not_mistaken_for_card_number(self):
        for label in ('PSA 10','PSA 10.0','BGS 9.5','CGC 9.5','TAG 9.5','BRG 9.5','BGS:9.5'):
            with self.subTest(label=label):
                name,number=m._tcgdex_query_parts(f'Pikachu {label} English')
                self.assertEqual(number,'')
                self.assertEqual(name,'Pikachu')
        name,number=m._tcgdex_query_parts('Pikachu 025 BGS 9.5 English')
        self.assertEqual(m._normalize_card_number(number),'025')
        self.assertEqual(name,'Pikachu')
        name,number=m._tcgdex_query_parts('Pikachu PAL185/193 CGC 9.5 English')
        self.assertEqual(m._normalize_card_number(number),'PAL185/193')
        self.assertEqual(name,'Pikachu')

    def test_decimal_grade_fragments_never_become_listing_card_numbers(self):
        self.assertEqual(m._identity_blob_numbers('Pikachu BGS 9.5 sold'),[])
        self.assertEqual(m._identity_blob_numbers('Pikachu PSA 10.0 sold'),[])
        self.assertIn('005',m._identity_blob_numbers('Pikachu 005 BGS 9.5 sold'))
        listing={'title':'Pikachu BGS 9.5 sold','snippet':'Pikachu','price_krw':95000}
        eligible,basis=m._item_identity_eligibility('Pikachu 005',listing)
        self.assertFalse(eligible)
        self.assertEqual(basis,'card_number_mismatch')
'''
replace_once("test_multi_market_price_collector.py", old_test, new_test)

print("v316 decimal grade/card-number precision patch prepared")
