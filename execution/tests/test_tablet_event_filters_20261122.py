import copy
from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode
from execution.tablet_event_filters_20261122 import filter_view, render
from execution.tablet_menu_shell_v903 import event_news, compose

ROOT=Path(__file__).resolve().parents[2]


class Controls(HTMLParser):
    def __init__(self, page):
        super().__init__();self.forms=[];self.selects={};self.current=None;self.feed(page)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='form':self.forms.append(a)
        if tag=='select':self.current=a.get('name');self.selects[self.current]=[]
        if tag=='option' and self.current and 'selected' in a:self.selects[self.current].append(a.get('value'))
    def handle_endtag(self,tag):
        if tag=='select':self.current=None


class EventFilterTests(unittest.TestCase):
    def data(self):
        def row(name,region,category,game='포켓몬 카드',**kw):
            return dict(name=name,region=region,category=category,game=game,source='',
                        lifecycle='CURRENT',evidence_state='STALE_OFFICIAL',**kw)
        return {'ok':True,'rows':[row('JP movie','JP','movie'),row('KR promo','KR','promo','원피스 카드'),
                                 row('JP series','JP','movie',media_type='streaming_series')]}
    def test_country_filter_selects_only_its_rows(self):
        self.assertEqual([r['name'] for r in filter_view(self.data(),{'event_region':['KR']})['rows']],['KR promo'])
    def test_movie_and_streaming_filter_are_distinct(self):
        for key,name in [('movie','JP movie'),('streaming','JP series')]:
            self.assertEqual([r['name'] for r in filter_view(self.data(),{'event_category':[key]})['rows']],[name])
    def test_game_country_category_and_state_combine(self):
        q={k:[v] for k,v in dict(event_game='포켓몬 카드',event_region='JP',event_category='movie',event_status='CURRENT').items()}
        self.assertEqual(len(filter_view(self.data(),q)['rows']),1)
        q['event_game']=['원피스 카드'];self.assertEqual(filter_view(self.data(),q)['rows'],[])
    def test_search_covers_title_reward_and_conditions(self):
        d=self.data();d['rows'][0]['condition']='온라인 신청';d['rows'][0]['reward']='기념 카드'
        for word in ['movie','신청','기념 카드']:
            self.assertEqual(len(filter_view(d,{'event_query':[word]})['rows']),1)
    def test_reset_discards_filters_and_source_is_unmodified(self):
        d=self.data();before=copy.deepcopy(d);filter_view(d,{'event_region':['KR']})
        self.assertEqual(len(filter_view(d,{})['rows']),3);self.assertEqual(before,d)
    def test_invalid_or_duplicate_parameters_never_expand_to_all(self):
        for raw in [['bad'],['KR','JP'],None,True,{},['x'*161]]:
            r=filter_view(self.data(),{'event_region':raw});self.assertTrue(r['invalid']);self.assertEqual(r['rows'],[])
    def test_empty_match_and_failed_read_have_different_messages(self):
        empty=render(self.data(),{'event_region':['US']},event_news)
        self.assertIn('선택 조건 0건',empty);self.assertNotIn('읽기 보류',empty)
        failed=render({}, {}, event_news);self.assertIn('읽기 보류',failed);self.assertNotIn('선택 조건 0건',failed)
    def test_selected_values_and_reset_are_real_get_forms(self):
        page=render(self.data(),{'event_region':['JP']},event_news);p=Controls(page)
        self.assertEqual(p.selects['event_region'],['JP'])
        self.assertTrue(all(x['method']=='get' and x['action']=='/index.html' for x in p.forms))
        self.assertIn('선택 적용',page);self.assertIn('필터 초기화',page)
        self.assertNotIn('onchange=',page)
    def test_discovery_parameters_do_not_filter_the_official_list(self):
        self.assertEqual(len(filter_view(self.data(),{'game':['unknown'],'region':['KR']})['rows']),3)
    def test_controls_escape_search_and_game_names(self):
        d=self.data();d['rows'][0]['game']='<script>bad</script>'
        page=render(d,{'event_query':['"><img src=x>']},event_news)
        self.assertNotIn('<script>',page);self.assertNotIn('<img',page);self.assertIn('&lt;img',page)
    def test_compose_shows_filters_above_official_list_and_preserves_get_selection(self):
        data={'state':'COMPLETE','count':0,'cards':'','options':'','events':'','event_data':self.data()}
        options=parse_qs(urlencode(dict(pane='events',event_region='KR',event_category='promo')))
        with patch('execution.tablet_menu_shell_v903.gallery',return_value=data),patch('execution.tablet_menu_shell_v903.event_fragment',return_value='DISCOVERY'):
            page=compose(ROOT,options=options)
        self.assertIn('name="event_region"',page);self.assertIn('name="event_category"',page)
        self.assertLess(page.index('name="event_region"'),page.index('<h2>KR promo</h2>'))
        self.assertNotIn('<h2>JP movie</h2>',page)
        self.assertEqual(Controls(page).selects['event_region'],['KR'])
        self.assertIn('DISCOVERY',page)
    def test_unknown_category_and_state_stay_separate(self):
        d=self.data();d['rows'][0]['lifecycle']='TRACKING'
        r=filter_view(d,{'event_status':['TRACKING']});self.assertEqual([x['name'] for x in r['rows']],['JP movie'])
