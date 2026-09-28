#!/usr/bin/env python3
from pathlib import Path

SOURCE = Path("update_market_prices.py")
TEST = Path("test_update_market_prices_packmagik_v353.py")

text = SOURCE.read_text(encoding="utf-8")

helper_anchor = '''def kream_label_prices(text:str,label_pattern:str,low:int,high:int,limit:int=12)->list[int]:
    """Read public KREAM transaction rows without mistaking release/shipping prices."""
    values=[int(value.replace(',','')) for value in re.findall(label_pattern+r'\\s*([0-9,]+)원',text,re.I)]
    return [value for value in values if low<=value<=high][:max(1,min(int(limit),30))]
'''
helper = helper_anchor + '''

def packmagik_market_value(text:str)->str|None:
    """Extract only Pack Magik raw Market/Market Value USD, never graded values."""
    match=re.search(r'(?:Market(?:\\s+Value)?|시장가)\\s*\\$([0-9]+(?:\\.[0-9]+)?)',text,re.I)
    return match.group(1) if match else None
'''
if "def packmagik_market_value(" not in text:
    if helper_anchor not in text:
        raise SystemExit("kream_label_prices anchor not found; fail closed")
    text = text.replace(helper_anchor, helper, 1)

old = '''    try:
        url='https://www.packmagik.com/cards/op-op14-op14-009-p1';text=html_to_text(fetch(url))
        m=re.search(r'(?:Market|시장가)\\s*\\$([0-9]+(?:\\.[0-9]+)?)',text,re.I)
        if m:set_price(db,'KR|창해의 칠걸|HIT','$'+m.group(1),'OP14-009 패러렐 국제판 참고시세','Pack Magik 국제시장','한국판 실거래 아님 · 국제판 시장가 참고',url)
        else: errors.append('Pack Magik OP14-009: 가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('Pack Magik OP14-009: '+diagnostic_exception(e))
'''
new = '''    try:
        url='https://www.packmagik.com/cards/1767522330718x781330136463076700';text=html_to_text(fetch(url))
        value=packmagik_market_value(text)
        if value:
            key='JP|창해의 칠걸 일본판 OP14-009|HIT'
            set_price(db,key,'$'+value,'OP14-009 얼터너티브 아트 일본판 참고시세','Pack Magik 일본판 국제시장','일본판 공개 Market Value · 한국판 시세로 결합 금지',url)
            db['entries'][key].update({'game':'ONE PIECE','card_name':'Trafalgar Law [Alternate Art]','card_number':'OP14-009','product_name':"Azure Sea's Seven [Japanese]",'language':'JP','variant':'alternate_art'})
        else: errors.append('Pack Magik OP14-009 JP: 가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('Pack Magik OP14-009 JP: '+diagnostic_exception(e))
'''
if old not in text:
    raise SystemExit("legacy Pack Magik block not found; fail closed")
text = text.replace(old, new, 1)
SOURCE.write_text(text, encoding="utf-8")

TEST.write_text('''import unittest
from pathlib import Path

import update_market_prices as market


class PackMagikMarketParserV353Tests(unittest.TestCase):
    def test_market_value_label(self):
        self.assertEqual(market.packmagik_market_value("Market Value $11.49"), "11.49")

    def test_legacy_market_label(self):
        self.assertEqual(market.packmagik_market_value("Market $17.15"), "17.15")

    def test_does_not_capture_graded_price_without_market_label(self):
        self.assertIsNone(market.packmagik_market_value("PSA 10 $63.20"))

    def test_source_is_japanese_scoped_and_old_kr_merge_is_removed(self):
        source = Path("update_market_prices.py").read_text(encoding="utf-8")
        self.assertIn("https://www.packmagik.com/cards/1767522330718x781330136463076700", source)
        self.assertIn("JP|창해의 칠걸 일본판 OP14-009|HIT", source)
        self.assertIn("'card_number':'OP14-009'", source)
        self.assertIn("'language':'JP'", source)
        self.assertIn("'variant':'alternate_art'", source)
        self.assertNotIn("https://www.packmagik.com/cards/op-op14-op14-009-p1", source)
        self.assertNotIn("set_price(db,'KR|창해의 칠걸|HIT'", source)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")
