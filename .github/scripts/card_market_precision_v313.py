#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# ---- server market collector: exact card number + homogeneous price evidence ----
path = "multi_market_price_collector.py"
src = read(path)

anchor = '''def _json_request(url,headers,allowed_hosts,max_bytes=2_000_000,timeout=15):
    req=Request(url,headers={**headers,'User-Agent':UA,'Accept':'application/json'})
    with safe_urlopen(req,timeout=timeout,allowed_hosts=set(allowed_hosts)) as response:
        raw=response.read(max_bytes+1)
    if len(raw)>max_bytes:raise ValueError('response exceeds safe size limit')
    return json.loads(raw.decode('utf-8','strict'))
'''
insert = anchor + '''\n
def _normalize_card_number(value):
    """Canonicalize a card number without turning substring overlap into identity."""
    text=str(value or '').upper().strip().replace('–','-').replace('—','-')
    text=re.sub(r'\\s+','',text)
    return re.sub(r'[^A-Z0-9/-]','',text)


def _has_explicit_set_prefix(value):
    token=_normalize_card_number(value)
    if not token:return False
    if re.match(r'^[A-Z]{1,6}\\d{0,3}-',token):return True
    # Modern EN codes such as SVI001 or MEW025 carry a set prefix even without '-'.
    return bool(re.match(r'^[A-Z]{2,6}\\d',token))


def _local_card_number(value):
    token=_normalize_card_number(value)
    if not token:return ''
    fraction=re.search(r'([A-Z]?\\d{1,4}/[A-Z]?\\d{1,4})$',token)
    if fraction:return fraction.group(1)
    if '-' in token:
        tail=token.rsplit('-',1)[-1]
        if re.fullmatch(r'[A-Z]?\\d{1,4}',tail):return tail
    simple=re.fullmatch(r'[A-Z]?\\d{1,4}',token)
    return simple.group(0) if simple else token


def _card_number_matches(wanted, actual):
    """Fail closed on explicit set numbers; local-only queries compare exact local IDs."""
    wanted_token=_normalize_card_number(wanted)
    actual_token=_normalize_card_number(actual)
    if not wanted_token or not actual_token:return False
    if wanted_token==actual_token:return True
    if _has_explicit_set_prefix(wanted_token):return False
    return _local_card_number(wanted_token)==_local_card_number(actual_token)
'''
src = replace_once(src, anchor, insert, "card number helper insertion")

src = replace_once(
    src,
    '''        _,wanted_number=_tcgdex_query_parts(query)
        if wanted_number:
            wanted=re.sub(r'[^A-Za-z0-9]','',wanted_number).casefold()
            actual=re.sub(r'[^A-Za-z0-9]','',str(card.get('number') or '')).casefold()
            if wanted and wanted not in actual:continue
''',
    '''        _,wanted_number=_tcgdex_query_parts(query)
        if wanted_number and not _card_number_matches(wanted_number, card.get('number')):
            continue
''',
    "JustTCG exact card number",
)

src = replace_once(
    src,
    '''            if card_number:
                needle=re.sub(r'[^A-Za-z0-9]','',card_number).casefold()
                hay=re.sub(r'[^A-Za-z0-9]','',str(card.get('localId') or '')+' '+card_id).casefold()
                if needle not in hay:continue
''',
    '''            if card_number and not (
                _card_number_matches(card_number, card.get('localId'))
                or _card_number_matches(card_number, card_id)
            ):
                continue
''',
    "TCGdex exact card number",
)

old_grade = '''def _grade_reference(items):
    grouped={label:[] for label in GRADE_ORDER}
    for item in items:
        price=int(item.get('price_krw') or 0)
        if price>0:grouped[_grade_label(item)].append(price)
    return [{'grade':label,'count':len(values),'price_krw':int(statistics.median(values)) if values else 0,
             'min_krw':min(values) if values else 0,'max_krw':max(values) if values else 0}
            for label,values in grouped.items()]
'''
new_grade = '''PRICE_EVIDENCE_PRIORITY=(
    ('completed','완료거래'),
    ('api_reference','API 참고시세'),
    ('asking','판매중/호가'),
)


def _price_evidence_class(item):
    kind=str(item.get('price_kind') or '')
    blob=' '.join(str(item.get(k) or '') for k in ('title','snippet','price_kind')).casefold()
    if kind=='실거래/완료 신호' or any(word in blob for word in SOLD_WORDS):return 'completed'
    if item.get('verified_api') is True and kind not in ('판매중','판매가'):
        return 'api_reference'
    return 'asking'


def _select_price_evidence(items):
    buckets={key:[] for key,_ in PRICE_EVIDENCE_PRIORITY}
    for item in items:
        if int(item.get('price_krw') or 0)>0:
            buckets[_price_evidence_class(item)].append(item)
    for key,label in PRICE_EVIDENCE_PRIORITY:
        if buckets[key]:return buckets[key],label,buckets
    return [],'자료 없음',buckets


def _grade_reference(items):
    grouped={label:[] for label in GRADE_ORDER}
    for item in items:
        if int(item.get('price_krw') or 0)>0:grouped[_grade_label(item)].append(item)
    rows=[]
    for label,grade_items in grouped.items():
        chosen,basis,buckets=_select_price_evidence(grade_items)
        values=[int(item.get('price_krw') or 0) for item in chosen]
        rows.append({
            'grade':label,'count':len(values),'total_count':len(grade_items),'basis':basis,
            'completed_count':len(buckets['completed']),'api_reference_count':len(buckets['api_reference']),
            'asking_count':len(buckets['asking']),
            'price_krw':int(statistics.median(values)) if values else 0,
            'min_krw':min(values) if values else 0,'max_krw':max(values) if values else 0,
        })
    return rows
'''
src = replace_once(src, old_grade, new_grade, "grade evidence separation")

old_compare = '''    wanted=_query_grade_label(query)
    valid=[x for x in items if int(x.get('price_krw') or 0)>0]
    if wanted:
        chosen=[x for x in valid if _grade_label(x)==wanted]
        return chosen, wanted
    raw=[x for x in valid if _grade_label(x)=='미감정']
    return raw, '미감정'
'''
new_compare = '''    wanted=_query_grade_label(query)
    valid=[x for x in items if int(x.get('price_krw') or 0)>0]
    same_grade=[x for x in valid if _grade_label(x)==wanted] if wanted else [x for x in valid if _grade_label(x)=='미감정']
    chosen,evidence_basis,_=_select_price_evidence(same_grade)
    grade_basis=wanted or '미감정'
    return chosen, f'{grade_basis} · {evidence_basis}'
'''
src = replace_once(src, old_compare, new_compare, "summary evidence separation")
write(path, src)

# ---- UI: expose the evidence basis instead of presenting mixed prices as one median ----
path = "multi_market_prices.js"
src = read(path)
src = replace_once(
    src,
    "globalThis[GLOBAL_KEY]={loaded:true,version:181};",
    "globalThis[GLOBAL_KEY]={loaded:true,version:313};",
    "multi-market UI version",
)
src = replace_once(
    src,
    "<small>확인된 공개가격의 중앙값이며, 자료가 없는 등급은 추정하지 않습니다.</small>",
    "<small>완료거래를 우선하고, 없으면 API 참고시세·판매중/호가를 서로 섞지 않고 표시합니다.</small>",
    "grade evidence UI help",
)
src = replace_once(
    src,
    "<small>${row.count?`${Number(row.count)}건 확인`:'공개가격 없음'}</small>",
    "<small>${row.count?`${Number(row.count)}건 · ${esc(row.basis||'공개가격')}`:'공개가격 없음'}</small>",
    "grade evidence UI basis",
)
write(path, src)

# ---- tests: reproduce false substring match and mixed evidence median ----
path = "test_multi_market_price_collector.py"
src = read(path)
src = replace_once(
    src,
    "import unittest\nimport multi_market_price_collector as m\n",
    "import unittest\nfrom unittest import mock\nimport multi_market_price_collector as m\n",
    "test mock import",
)
insert_tests = '''    def test_card_number_matching_is_exact_not_substring(self):
        self.assertFalse(m._card_number_matches('001','1001'))
        self.assertTrue(m._card_number_matches('001','SV1-001'))
        self.assertTrue(m._card_number_matches('OP13-007','OP13-007'))
        self.assertFalse(m._card_number_matches('OP13-007','OP14-007'))
        self.assertFalse(m._card_number_matches('SVI001','SVI1001'))

    def test_justtcg_rejects_substring_card_number_collision(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        payload={'data':[{'name':'Pikachu','number':'1001','variants':[{'price':10.0,'condition':'NM','printing':'Normal'}]}]}
        with mock.patch.dict(m.os.environ,{'JUSTTCG_API_KEY':'token'}), mock.patch.object(m,'_json_request',return_value=payload):
            rows,status=m._justtcg_api('Pikachu 001','pokemon',fx,'US')
        self.assertEqual(status,'ok')
        self.assertEqual(rows,[])

    def test_tcgdex_rejects_substring_card_number_collision(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        def fake_json(url,*args,**kwargs):
            if '/cards?' in url:return [{'id':'sv01-1001'}]
            return {'name':'Pikachu','localId':'1001','pricing':{'tcgplayer':{'updated':'2026-09-25','normal':{'marketPrice':10.0}}}}
        with mock.patch.object(m,'_json_request',side_effect=fake_json):
            rows,status=m._tcgdex_api('Pikachu 001','pokemon',fx,'US')
        self.assertEqual(status,'ok')
        self.assertEqual(rows,[])

    def test_grade_reference_prefers_completed_sales_without_mixing_asking_prices(self):
        items=[
            {'title':'Pikachu PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':100000,'verified_api':False},
            {'title':'Pikachu PSA 10','price_kind':'API 현재가','price_krw':200000,'verified_api':True},
            {'title':'Pikachu PSA 10','price_kind':'판매중','price_krw':500000,'verified_api':True},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 10')
        self.assertEqual(row['price_krw'],100000)
        self.assertEqual(row['basis'],'완료거래')
        self.assertEqual(row['completed_count'],1)
        self.assertEqual(row['api_reference_count'],1)
        self.assertEqual(row['asking_count'],1)
        self.assertEqual(row['total_count'],3)
        chosen,basis=m._comparable_summary_items('Pikachu PSA 10',items)
        self.assertEqual([x['price_krw'] for x in chosen],[100000])
        self.assertEqual(basis,'PSA 10 · 완료거래')

    def test_grade_reference_uses_api_reference_before_asking_when_no_completed_sale(self):
        items=[
            {'title':'Pikachu PSA 9','price_kind':'API 현재가','price_krw':180000,'verified_api':True},
            {'title':'Pikachu PSA 9','price_kind':'판매중','price_krw':400000,'verified_api':True},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 9')
        self.assertEqual(row['price_krw'],180000)
        self.assertEqual(row['basis'],'API 참고시세')
        self.assertEqual(row['count'],1)

'''
src = replace_once(src, "\nif __name__=='__main__':\n", "\n"+insert_tests+"if __name__=='__main__':\n", "market precision tests")
write(path, src)

print('card market precision v313 patch prepared')
