#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'expected block not found in {path}: {old[:120]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


market = ROOT / 'multi_market_price_collector.py'
replace_once(
    market,
    """            items.append({'source':src['name'],'source_id':sid,'title':r['title'],'url':r['url'],'snippet':r['snippet'],'date':r['date'],\n                          **p,'price_kind':kind,'verified_api':False,'score':round(weight,3),\n                          'region_scope':region if region in ('KR','JP','US') else 'ALL'})\n""",
    """            listing_regions=_explicit_listing_regions(r)\n            listing_region=next(iter(listing_regions)) if len(listing_regions)==1 else 'ALL'\n            items.append({'source':src['name'],'source_id':sid,'title':r['title'],'url':r['url'],'snippet':r['snippet'],'date':r['date'],\n                          **p,'price_kind':kind,'verified_api':False,'score':round(weight,3),\n                          # RSS discovery is not edition proof. Preserve only explicit\n                          # listing evidence; never stamp the requested region onto a row.\n                          'region_scope':listing_region})\n""",
)
replace_once(
    market,
    """    eligible_items=[item for item in items if item.get('summary_eligible') is True]\n    variant_state=_variant_summary_state(query,eligible_items)\n    if variant_state['ambiguous']:\n        comparable=[];basis='인쇄/아트 변형 미지정 · 서로 다른 변형 혼재'\n    else:\n        comparable,basis=_comparable_summary_items(query,eligible_items)\n    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]\n    _,query_card_number=_tcgdex_query_parts(query)\n    summary={'count':len(prices),'total_count':len([x for x in eligible_items if int(x.get('price_krw',0))>0]),\n""",
    """    eligible_items=[item for item in items if item.get('summary_eligible') is True]\n    variant_state=_variant_summary_state(query,eligible_items)\n    _,query_card_number=_tcgdex_query_parts(query)\n    identity_ambiguous=not bool(_normalize_card_number(query_card_number))\n    if identity_ambiguous:\n        # A name-only query can span many sets, promos, reprints and printings.\n        # Keep raw evidence visible, but never manufacture one headline/grade price.\n        comparable=[];basis='카드번호/세트 식별자 필요 · 이름만으로 시세 요약 보류'\n    elif variant_state['ambiguous']:\n        comparable=[];basis='인쇄/아트 변형 미지정 · 서로 다른 변형 혼재'\n    else:\n        comparable,basis=_comparable_summary_items(query,eligible_items)\n    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]\n    summary={'count':len(prices),'total_count':len([x for x in eligible_items if int(x.get('price_krw',0))>0]),\n""",
)
replace_once(
    market,
    """             'identity_scope':'exact_card_number' if query_card_number else 'name_only',\n             'variant_scope':variant_state['scope'],'variant_ambiguous':variant_state['ambiguous'],\n""",
    """             'identity_scope':'exact_card_number' if query_card_number else 'name_only_hold',\n             'identity_ambiguous':identity_ambiguous,\n             'variant_scope':variant_state['scope'],'variant_ambiguous':variant_state['ambiguous'],\n""",
)
replace_once(
    market,
    """          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(eligible_items) if not variant_state['ambiguous'] else [],\n          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 카드번호·판본·인쇄/아트 변형이 확인된 자료만 중앙값·등급별 시세에 사용합니다. 같은 카드번호에서 Standard·Holo·Reverse Holo·Parallel·Alt Art·Manga 등이 섞이면 자동 중앙값을 보류합니다. 완료거래→API 참고시세→호가 순으로 분리하며, 없는 등급값은 추정하지 않습니다. 403/429는 우회하지 않고 안전 대기합니다.',\n""",
    """          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(eligible_items) if query_card_number and not variant_state['ambiguous'] else [],\n          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 카드번호·판본·인쇄/아트 변형이 확인된 자료만 중앙값·등급별 시세에 사용합니다. 카드명만 입력한 경우 여러 세트·프로모·재록이 섞일 수 있어 중앙값과 등급별 시세를 보류하고 원자료만 표시합니다. 같은 카드번호에서 Standard·Holo·Reverse Holo·Parallel·Alt Art·Manga 등이 섞여도 자동 중앙값을 보류합니다. 완료거래→API 참고시세→호가 순으로 분리하며, 없는 등급값은 추정하지 않습니다. RSS 검색의 요청 판본은 증거로 재사용하지 않으며 실제 매물의 판본 표기만 보존합니다. 403/429는 우회하지 않고 안전 대기합니다.',\n""",
)

identity_js = ROOT / 'card_identity_recognition.js'
replace_once(
    identity_js,
    """ const byYear=generationByYear(year,input?.region);\n if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'low',evidence_count:1,context_evidence_count:0,basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대/시리즈는 보조 추정입니다.'};\n""",
    """ const byYear=generationByYear(year,input?.region);\n if(byYear)return {status:'context_only',game:'pokemon',generation:null,generation_hint:byYear.generation,generation_label:'세대 확인 필요',series:byYear.series,era:byYear.era,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'context',evidence_count:0,context_evidence_count:1,basis:[`©/제작연도 ${year}`],note:'©연도만으로는 재록·재판·지역 출시차를 배제할 수 없어 세대 번호를 확정하지 않습니다. 시대 힌트만 제공합니다.'};\n""",
)
replace_once(
    identity_js,
    """ if(info.status==='context_only'){if(badge)badge.textContent='?';if(title)title.textContent=`세대 확인 필요 · 레귤레이션 ${info.regulation_mark||''}`.trim();if(meta)meta.textContent='레귤레이션은 사용 가능 시기 표기이며 세대 번호 근거로 사용하지 않습니다. 확장팩/세트 코드 또는 ©연도를 확인해 주세요.';return info}\n""",
    """ if(info.status==='context_only'){const regulationOnly=Boolean(info.regulation_mark);if(badge)badge.textContent='?';if(title)title.textContent=regulationOnly?`세대 확인 필요 · 레귤레이션 ${info.regulation_mark}`:`세대 확인 필요 · ${info.series||'연도 문맥'}`;if(meta)meta.textContent=regulationOnly?'레귤레이션은 사용 가능 시기 표기이며 세대 번호 근거로 사용하지 않습니다. 확장팩/세트 코드를 확인해 주세요.':`©${info.year||'?'} 단독 근거는 재록·재판·지역 출시차 때문에 세대 번호로 확정하지 않습니다${info.generation_hint?` · 시대 힌트 ${info.generation_hint}세대`:''}.`;return info}\n""",
)
replace_once(identity_js, "window.TCGPokemonGeneration=Object.freeze({version:'v320'", "window.TCGPokemonGeneration=Object.freeze({version:'v324'")

verify_js = ROOT / 'verify_pokemon_generation_runtime.js'
replace_once(
    verify_js,
    """r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});\neq(r.generation,8,'year fallback generation');eq(r.confidence_level,'low','year fallback confidence');\n""",
    """r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});\neq(r.generation,null,'year-only evidence must not invent generation');eq(r.generation_hint,8,'year-only era hint');eq(r.status,'context_only','year-only context status');eq(r.confidence_level,'context','year-only context confidence');\n""",
)
replace_once(verify_js, "eq(api.version,'v320','generation runtime version');", "eq(api.version,'v324','generation runtime version');")

verify_py = ROOT / 'verify_current_runtime.py'
replace_once(
    verify_py,
    '"test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_card_promo_precision_v322.py","test_card_variant_market_precision_v323.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),',
    '"test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_card_promo_precision_v322.py","test_card_variant_market_precision_v323.py","test_card_market_generation_precision_v324.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),',
)
replace_once(verify_py, 'engine":"current-main-v323-variant-edition-price-precision"', 'engine":"current-main-v324-market-generation-failclosed"')

new_test = ROOT / 'test_card_market_generation_precision_v324.py'
new_test.write_text(r'''#!/usr/bin/env python3
import subprocess
import unittest
from unittest import mock
import multi_market_price_collector as m


class CardMarketGenerationPrecisionV324Tests(unittest.TestCase):
    def test_name_only_query_never_builds_headline_or_grade_price(self):
        rows=[{
            'source':'eBay','source_id':'ebay','title':'Pikachu English card sold','snippet':'',
            'url':'https://www.ebay.com/itm/1','price_krw':10000,'price_native':10,'currency':'USD',
            'price_kind':'실거래/완료 신호','verified_api':True,'date':'','score':1,
        }]
        with mock.patch.object(m,'_ebay_api',return_value=rows), mock.patch.object(m,'_justtcg_api',return_value=([],'not_configured')), mock.patch.object(m,'_tcgdex_api',return_value=([],'ok')), mock.patch.object(m,'_rss',return_value=[]), mock.patch.object(m,'_fx',return_value={'USD':1000,'JPY':10,'EUR':1500,'KRW':1}), mock.patch.object(m,'_learning',return_value={}), mock.patch.object(m,'_save_learning'), mock.patch.object(m,'_save_cache'), mock.patch.object(m,'_cached',return_value=None):
            result=m.search_multi_market('Pikachu',region='US',game='pokemon',force=True)
        self.assertEqual('name_only_hold',result['summary']['identity_scope'])
        self.assertTrue(result['summary']['identity_ambiguous'])
        self.assertEqual(0,result['summary']['median_krw'])
        self.assertEqual([],result['grade_reference'])
        self.assertGreaterEqual(len(result['items']),1)

    def test_requested_region_is_not_self_attested_on_rss_result(self):
        rss=[{'title':'Pikachu PAL185/193 $10','url':'https://www.ebay.com/itm/1','snippet':'current price $10','date':''}]
        with mock.patch.object(m,'_ebay_api',return_value=[]), mock.patch.object(m,'_justtcg_api',return_value=([],'not_configured')), mock.patch.object(m,'_tcgdex_api',return_value=([],'ok')), mock.patch.object(m,'_rss',return_value=rss), mock.patch.object(m,'_fx',return_value={'USD':1000,'JPY':10,'EUR':1500,'KRW':1}), mock.patch.object(m,'_learning',return_value={}), mock.patch.object(m,'_save_learning'), mock.patch.object(m,'_save_cache'), mock.patch.object(m,'_cached',return_value=None):
            result=m.search_multi_market('Pikachu PAL185/193',region='US',game='pokemon',force=True)
        matched=[row for row in result['items'] if row.get('source_id')=='ebay']
        self.assertTrue(matched)
        self.assertEqual('ALL',matched[0]['region_scope'])

    def test_explicit_rss_edition_is_preserved(self):
        rss=[{'title':'Pikachu PAL185/193 English version $10','url':'https://www.ebay.com/itm/1','snippet':'sold $10','date':''}]
        with mock.patch.object(m,'_ebay_api',return_value=[]), mock.patch.object(m,'_justtcg_api',return_value=([],'not_configured')), mock.patch.object(m,'_tcgdex_api',return_value=([],'ok')), mock.patch.object(m,'_rss',return_value=rss), mock.patch.object(m,'_fx',return_value={'USD':1000,'JPY':10,'EUR':1500,'KRW':1}), mock.patch.object(m,'_learning',return_value={}), mock.patch.object(m,'_save_learning'), mock.patch.object(m,'_save_cache'), mock.patch.object(m,'_cached',return_value=None):
            result=m.search_multi_market('Pikachu PAL185/193',region='US',game='pokemon',force=True)
        matched=[row for row in result['items'] if row.get('source_id')=='ebay']
        self.assertTrue(matched)
        self.assertEqual('US',matched[0]['region_scope'])

    def test_year_only_generation_is_context_not_identity(self):
        proc=subprocess.run(['node','verify_pokemon_generation_runtime.js'],capture_output=True,text=True,encoding='utf-8',errors='replace',check=False)
        self.assertEqual(0,proc.returncode,proc.stderr or proc.stdout)
        self.assertIn('v320', proc.stdout) if False else None
        self.assertIn('PASS',proc.stdout)


if __name__=='__main__':
    unittest.main(verbosity=2)
''',encoding='utf-8')

print('v324 card market/generation precision patch applied')
