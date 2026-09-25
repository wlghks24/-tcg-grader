#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def replace_once(path:Path,old:str,new:str)->None:
    text=path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'expected block not found in {path}: {old[:140]!r}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

market=ROOT/'multi_market_price_collector.py'
replace_once(market,
"""            items.append({'source':src['name'],'source_id':sid,'title':r['title'],'url':r['url'],'snippet':r['snippet'],'date':r['date'],
                          **p,'price_kind':kind,'verified_api':False,'score':round(weight,3),
                          'region_scope':region if region in ('KR','JP','US') else 'ALL'})
""",
"""            listing_regions=_explicit_listing_regions(r)
            listing_region=next(iter(listing_regions)) if len(listing_regions)==1 else 'ALL'
            items.append({'source':src['name'],'source_id':sid,'title':r['title'],'url':r['url'],'snippet':r['snippet'],'date':r['date'],
                          **p,'price_kind':kind,'verified_api':False,'score':round(weight,3),
                          # Discovery query scope is not evidence of the listing edition.
                          # Preserve only explicit listing evidence and fail closed otherwise.
                          'region_scope':listing_region})
""")
replace_once(market,
"""    eligible_items=[item for item in items if item.get('summary_eligible') is True]
    variant_state=_variant_summary_state(query,eligible_items)
    if variant_state['ambiguous']:
        comparable=[];basis='인쇄/아트 변형 미지정 · 서로 다른 변형 혼재'
    else:
        comparable,basis=_comparable_summary_items(query,eligible_items)
    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]
    _,query_card_number=_tcgdex_query_parts(query)
    summary={'count':len(prices),'total_count':len([x for x in eligible_items if int(x.get('price_krw',0))>0]),
""",
"""    eligible_items=[item for item in items if item.get('summary_eligible') is True]
    variant_state=_variant_summary_state(query,eligible_items)
    _,query_card_number=_tcgdex_query_parts(query)
    identity_ambiguous=not bool(_normalize_card_number(query_card_number))
    if identity_ambiguous:
        # Name-only searches can span sets, promos, reprints and different releases.
        # Raw observations remain visible, but no aggregate or grade price is fabricated.
        comparable=[];basis='카드번호/세트 식별자 필요 · 이름만으로 시세 요약 보류'
    elif variant_state['ambiguous']:
        comparable=[];basis='인쇄/아트 변형 미지정 · 서로 다른 변형 혼재'
    else:
        comparable,basis=_comparable_summary_items(query,eligible_items)
    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]
    summary={'count':len(prices),'total_count':len([x for x in eligible_items if int(x.get('price_krw',0))>0]),
""")
replace_once(market,
"""             'identity_scope':'exact_card_number' if query_card_number else 'name_only',
             'variant_scope':variant_state['scope'],'variant_ambiguous':variant_state['ambiguous'],
""",
"""             'identity_scope':'exact_card_number' if query_card_number else 'name_only_hold',
             'identity_ambiguous':identity_ambiguous,
             'variant_scope':variant_state['scope'],'variant_ambiguous':variant_state['ambiguous'],
""")
replace_once(market,
"""          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(eligible_items) if not variant_state['ambiguous'] else [],
          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 카드번호·판본·인쇄/아트 변형이 확인된 자료만 중앙값·등급별 시세에 사용합니다. 같은 카드번호에서 Standard·Holo·Reverse Holo·Parallel·Alt Art·Manga 등이 섞이면 자동 중앙값을 보류합니다. 완료거래→API 참고시세→호가 순으로 분리하며, 없는 등급값은 추정하지 않습니다. 403/429는 우회하지 않고 안전 대기합니다.',
""",
"""          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(eligible_items) if query_card_number and not variant_state['ambiguous'] else [],
          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 카드번호·판본·인쇄/아트 변형이 확인된 자료만 중앙값·등급별 시세에 사용합니다. 카드명만 입력한 경우 여러 세트·프로모·재록이 섞일 수 있어 중앙값과 등급별 시세를 보류하고 원자료만 표시합니다. 같은 카드번호에서 Standard·Holo·Reverse Holo·Parallel·Alt Art·Manga 등이 섞여도 자동 중앙값을 보류합니다. 완료거래→API 참고시세→호가 순으로 분리하며, 없는 등급값은 추정하지 않습니다. 검색 요청 판본은 매물의 판본 증거로 재사용하지 않으며 실제 매물 표기만 보존합니다. 403/429는 우회하지 않고 안전 대기합니다.',
""")

identity=ROOT/'card_identity_recognition.js'
replace_once(identity,
""" const byYear=generationByYear(year,input?.region);
 if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'low',evidence_count:1,context_evidence_count:0,basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대/시리즈는 보조 추정입니다.'};
""",
""" const byYear=generationByYear(year,input?.region);
 if(byYear)return {status:'context_only',game:'pokemon',generation:null,generation_hint:byYear.generation,generation_label:'세대 확인 필요',series:byYear.series,era:byYear.era,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'context',evidence_count:0,context_evidence_count:1,basis:[`©/제작연도 ${year}`],note:'©연도만으로는 재록·재판·지역 출시차를 배제할 수 없어 세대 번호를 확정하지 않습니다. 시대 힌트만 제공합니다.'};
""")
replace_once(identity,
""" if(info.status==='context_only'){if(badge)badge.textContent='?';if(title)title.textContent=`세대 확인 필요 · 레귤레이션 ${info.regulation_mark||''}`.trim();if(meta)meta.textContent='레귤레이션은 사용 가능 시기 표기이며 세대 번호 근거로 사용하지 않습니다. 확장팩/세트 코드 또는 ©연도를 확인해 주세요.';return info}
""",
""" if(info.status==='context_only'){const regulationOnly=Boolean(info.regulation_mark);if(badge)badge.textContent='?';if(title)title.textContent=regulationOnly?`세대 확인 필요 · 레귤레이션 ${info.regulation_mark}`:`세대 확인 필요 · ${info.series||'연도 문맥'}`;if(meta)meta.textContent=regulationOnly?'레귤레이션은 사용 가능 시기 표기이며 세대 번호 근거로 사용하지 않습니다. 확장팩/세트 코드를 확인해 주세요.':`©${info.year||'?'} 단독 근거는 재록·재판·지역 출시차 때문에 세대 번호로 확정하지 않습니다${info.generation_hint?` · 시대 힌트 ${info.generation_hint}세대`:''}.`;return info}
""")
replace_once(identity,"window.TCGPokemonGeneration=Object.freeze({version:'v320'","window.TCGPokemonGeneration=Object.freeze({version:'v325'")

verify=ROOT/'verify_pokemon_generation_runtime.js'
replace_once(verify,
"""r=api.infer({game:'pokemon',ocr_text:'©2026 Pokémon',region:'US'});
eq(r.generation,null,'2026 year-only evidence must not invent generation');eq(r.confidence_level,'low','2026 year-only confidence');

r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});
eq(r.generation,8,'year fallback generation');eq(r.confidence_level,'low','year fallback confidence');
""",
"""r=api.infer({game:'pokemon',ocr_text:'©2026 Pokémon',region:'US'});
eq(r.generation,null,'2026 year-only evidence must not invent generation');eq(r.generation_hint,null,'2026 transition era must not invent generation hint');eq(r.status,'context_only','2026 year-only context status');eq(r.confidence_level,'context','2026 year-only confidence');

r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});
eq(r.generation,null,'year-only evidence must not invent generation');eq(r.generation_hint,8,'year-only era hint');eq(r.status,'context_only','year-only context status');eq(r.confidence_level,'context','year-only context confidence');
""")
replace_once(verify,"eq(api.version,'v320','generation runtime version');\nconsole.log('Pokémon generation runtime v320: PASS');","eq(api.version,'v325','generation runtime version');\nconsole.log('Pokémon generation runtime v325: PASS');")

runtime=ROOT/'verify_current_runtime.py'
replace_once(runtime,
'"test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_card_promo_precision_v322.py","test_card_variant_market_precision_v323.py","test_card_collector_edition_alias_v324.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),',
'"test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_card_promo_precision_v322.py","test_card_variant_market_precision_v323.py","test_card_collector_edition_alias_v324.py","test_card_market_generation_precision_v325.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),')
replace_once(runtime,'engine":"current-main-v323-variant-edition-price-precision"','engine":"current-main-v325-market-generation-failclosed"')

tablet_test=ROOT/'test_card_tablet_runtime_v300.py'
replace_once(tablet_test,'"version:\'v320\'",','"version:\'v325\'",')
replace_once(tablet_test,
'            "test_card_identity_market_precision_v309.py",\n            "test_multi_market_price_collector.py",',
'            "test_card_identity_market_precision_v309.py",\n            "test_card_market_generation_precision_v325.py",\n            "test_multi_market_price_collector.py",')

ambiguity_test=ROOT/'test_card_identity_ambiguity_v320.py'
replace_once(ambiguity_test,'self.assertIn("Pokémon generation runtime v320: PASS", proc.stdout)','self.assertIn("Pokémon generation runtime v325: PASS", proc.stdout)')

new_test=ROOT/'test_card_market_generation_precision_v325.py'
new_test.write_text(r'''#!/usr/bin/env python3
import subprocess
import unittest
from unittest import mock
import multi_market_price_collector as m

class CardMarketGenerationPrecisionV325Tests(unittest.TestCase):
    def _search(self,query,region,rss,api_rows=None):
        with mock.patch.object(m,'_ebay_api',return_value=api_rows or []), mock.patch.object(m,'_justtcg_api',return_value=([],'not_configured')), mock.patch.object(m,'_tcgdex_api',return_value=([],'ok')), mock.patch.object(m,'_rss',return_value=rss), mock.patch.object(m,'_fx',return_value={'USD':1000,'JPY':10,'EUR':1500,'KRW':1}), mock.patch.object(m,'_learning',return_value={}), mock.patch.object(m,'_save_learning'), mock.patch.object(m,'_save_cache'), mock.patch.object(m,'_cached',return_value=None):
            return m.search_multi_market(query,region=region,game='pokemon',force=True)

    def test_name_only_query_never_builds_headline_or_grade_price(self):
        rows=[{'source':'eBay','source_id':'ebay','title':'Pikachu English card sold','snippet':'','url':'https://www.ebay.com/itm/1','price_krw':10000,'price_native':10,'currency':'USD','price_kind':'실거래/완료 신호','verified_api':True,'date':'','score':1}]
        result=self._search('Pikachu','US',[],rows)
        self.assertEqual('name_only_hold',result['summary']['identity_scope'])
        self.assertTrue(result['summary']['identity_ambiguous'])
        self.assertEqual(0,result['summary']['median_krw'])
        self.assertEqual([],result['grade_reference'])
        self.assertGreaterEqual(len(result['items']),1)

    def test_requested_region_is_not_self_attested_on_rss_result(self):
        result=self._search('Pikachu PAL185/193','US',[{'title':'Pikachu PAL185/193 $10','url':'https://www.ebay.com/itm/1','snippet':'current price $10','date':''}])
        matched=[row for row in result['items'] if row.get('source_id')=='ebay']
        self.assertTrue(matched)
        self.assertEqual('ALL',matched[0]['region_scope'])

    def test_explicit_rss_edition_is_preserved(self):
        result=self._search('Pikachu PAL185/193','US',[{'title':'Pikachu PAL185/193 English version $10','url':'https://www.ebay.com/itm/1','snippet':'sold $10','date':''}])
        matched=[row for row in result['items'] if row.get('source_id')=='ebay']
        self.assertTrue(matched)
        self.assertEqual('US',matched[0]['region_scope'])

    def test_generation_runtime_fail_closes_year_only_evidence(self):
        proc=subprocess.run(['node','verify_pokemon_generation_runtime.js'],capture_output=True,text=True,encoding='utf-8',errors='replace',check=False)
        self.assertEqual(0,proc.returncode,proc.stderr or proc.stdout)
        self.assertIn('v325: PASS',proc.stdout)

if __name__=='__main__':
    unittest.main(verbosity=2)
''',encoding='utf-8')
print('v325 card market/generation precision patch applied')