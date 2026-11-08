"""Preserve all existing static sections/details, including advanced/id-less panels."""
import html
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import quote

ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,80}$')


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__(); self.items=[];self.stack=[];self.heading=None;self.ids=set();self.controls=0
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if attrs.get('id'):self.ids.add(attrs['id'])
        if tag in ('button','input','select','textarea'):self.controls+=1
        if tag in ('section','details'):
            item={'tag':tag,'id':attrs.get('id'),'label':attrs.get('aria-label',''),'opening':self.get_starttag_text(),'ordinal':len(self.items)+1,'marked':'data-tcg-migration-target' in attrs}
            self.items.append(item);self.stack.append(item)
        title = tag in ('h1','h2','h3','h4','summary') or (tag=='div' and any('title' in c or c=='muted' for c in attrs.get('class','').split()))
        if title and self.stack and not self.stack[-1]['label'] and self.heading is None:
            self.heading=(tag,self.stack[-1],[])
    def handle_data(self,data):
        if self.heading:self.heading[2].append(data)
    def handle_endtag(self,tag):
        if self.heading and tag==self.heading[0]:
            self.heading[1]['label']=' '.join(''.join(self.heading[2]).split())[:240];self.heading=None
        if tag in ('section','details') and self.stack and self.stack[-1]['tag']==tag:
            child=self.stack.pop()
            if self.stack and not self.stack[-1]['label'] and child['label']:self.stack[-1]['label']=child['label']


def inventory(document):
    parser=Inventory();parser.feed(document)
    for item in parser.items:
        if not item['id']:
            target='migrationSection'+str(item['ordinal'])
            while target in parser.ids:target+='x'
            parser.ids.add(target);item['id']=target;item['assigned']=True
        if not ID.fullmatch(item['id']):raise ValueError('invalid legacy target ID')
        item['label']=item['label'] or '기존 상세 기능 '+str(item['ordinal'])
    targets=[i['id'] for i in parser.items]
    if len(targets)!=len(set(targets)):raise ValueError('duplicate legacy section target')
    return {'items':parser.items,'controls':parser.controls}


def annotate(document):
    """Add anchors to anonymous original panels; don't replace/remove their contents."""
    report=inventory(document)
    for item in report['items']:
        if item.get('marked'):continue
        opening=item['opening']
        replacement=opening[:-1]+(' id="'+item['id']+'"' if item.get('assigned') else '')+' data-tcg-migration-target="true">'
        document=document.replace(opening,replacement,1)
    return document


def read_source(repo):
    p=Path(repo)/'index.html'
    if p.is_symlink() or not p.is_file() or p.stat().st_size>3_000_000:raise ValueError('legacy index unavailable')
    return p.read_text(encoding='utf-8')


def render_directory(repo):
    report=inventory(read_source(repo));esc=html.escape
    links=''.join('<li><a href="/index.html?target='+quote(i['id'],safe='')+'">'+esc(i['label'])+'</a><small>'+esc(i['id'])+'</small></li>' for i in report['items'])
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>기존 전체 기능</title><style>body{font:17px/1.6 system-ui;background:#f3f7f6;color:#172c35;max-width:1100px;padding:24px;margin:auto}a{color:#087f69}input{font:inherit;padding:14px;border:1px solid #ccdcd5;border-radius:12px;width:100%}ul{padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}li{list-style:none;padding:18px;background:white;border:1px solid #dde6e1;border-radius:16px}li a{display:block;min-height:44px}small{color:#60757d;overflow-wrap:anywhere}li[hidden]{display:none}</style><a href="/tablet-unified">통합 카드·BOX로 돌아가기</a><h1>기존 전체 기능</h1><p>상세 화면 '''+str(len(report['items']))+'개 · 원래 입력·버튼 '+str(report['controls'])+'''개 보존 대상. 각 화면 안의 기존 동작을 그대로 사용합니다. 측정 결과 화면은 관련 작업 완료 후 표시됩니다.</p><label>기능 찾기<input id="search" type="search" placeholder="등급·시세·행사·업데이트·학습"></label><ul>'''+links+'''</ul><script>document.getElementById('search').addEventListener('input',e=>{const query=e.target.value.trim().toLowerCase();document.querySelectorAll('li').forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(query));});</script></html>'''
