"""GET filters for the stored official-event list, separate from discovery."""
import html
from execution.tablet_event_labels_20261122 import CATEGORIES, LIFECYCLE

FIELDS = [('region','국가·지역'),('game','게임'),('category','행사 종류'),('status','진행 상태')]
REGIONS = {'KR':'한국','JP':'일본','US':'미국','CN':'중국','CN-S':'중국 간체',
           'CN-T':'대만 번체','TW':'대만','HK':'홍콩','ASIA':'아시아','GLOBAL':'글로벌'}


def kind(row):
    if row.get('media_type') == 'streaming_series':
        return 'streaming'
    value = row.get('category')
    return 'collaboration' if value == 'collab' else value


def filter_view(events, options):
    rows = events.get('rows') if isinstance(events,dict) and events.get('ok') is True else None
    available = isinstance(rows,list) and len(rows)<=600 and all(isinstance(r,dict) for r in rows)
    rows = rows if available else []
    choices = {key:sorted({value for r in rows if isinstance(value := (
        kind(r) if key=='category' else r.get('lifecycle' if key=='status' else key)),str) and value})
        for key,_ in FIELDS}
    # Regions are selectable even when a country has no stored rows; zero-match
    # is distinct from a failed source read.
    choices['region'] = sorted(set(choices['region']) | set(REGIONS))
    selected, invalid = {}, False
    for key in [key for key,_ in FIELDS]+['query']:
        raw = options.get('event_'+key, [''])
        valid = isinstance(raw,list) and len(raw)==1 and isinstance(raw[0],str) and len(raw[0])<=160
        value = raw[0].strip() if valid else ''
        if not valid or (key!='query' and value and value not in choices[key]):invalid=True
        selected[key] = value
    matched = []
    if available and not invalid:
        for row in rows:
            if any(selected[key] and selected[key] != (
                kind(row) if key=='category' else row.get('lifecycle' if key=='status' else key))
                for key,_ in FIELDS):continue
            query=selected['query'].casefold()
            if query and query not in ' '.join(str(row.get(k) or '') for k in ('name','reward','condition','date_label')).casefold():continue
            matched.append(row)
    return dict(available=available,invalid=invalid,rows=matched,choices=choices,selected=selected,total=len(rows))


def render(events, options, render_news):
    state=filter_view(events,options)
    e=lambda value:html.escape(str(value),quote=True)
    controls=[]
    for key,label in FIELDS:
        labels=REGIONS if key=='region' else LIFECYCLE if key=='status' else {
            **CATEGORIES,'anniversary':'기념 행사','streaming':'스트리밍·시리즈'} if key=='category' else {}
        choices=['<option value="">전체</option>']
        for value in state['choices'][key]:
            selected=' selected' if state['selected'][key]==value else ''
            choices.append('<option value="'+e(value)+'"'+selected+'>'+e(labels.get(value,value))+'</option>')
        controls.append('<label>'+label+'<select name="event_'+key+'" id="tcg-event-'+key+'">'+''.join(choices)+'</select></label>')
    form='<form method="get" action="/index.html" class="tcg903-filters" aria-label="영화·행사 목록 필터"><input type="hidden" name="pane" value="events">'+''.join(controls)+'<label>검색어<input type="search" name="event_query" value="'+e(state['selected']['query'])+'" placeholder="행사명·특전·참여 조건"></label><button type="submit">선택 적용</button></form>'
    form+='<form method="get" action="/index.html"><input type="hidden" name="pane" value="events"><button type="submit">필터 초기화</button></form>'
    if not state['available']:return form+'<p role="alert">행사 자료 읽기 보류 · 확인된 0건이 아닙니다.</p>'
    if state['invalid']:return form+'<p role="alert">필터 값이 올바르지 않습니다. 필터를 초기화해 다시 선택하세요.</p>'
    count='<p role="status">선택 조건 '+str(len(state['rows']))+'건 / 저장된 전체 '+str(state['total'])+'건</p>'
    if not state['rows']:return form+count+'<p>선택 조건에 맞는 저장 자료가 없습니다. 다른 국가·종류를 선택하거나 필터를 초기화하세요.</p>'
    return form+count+render_news({'ok':True,'rows':state['rows']})
