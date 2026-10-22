#!/usr/bin/env python3
"""Read-only static navigation contracts; not a browser or device success claim."""
from __future__ import annotations
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re

class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.targets=[];self.buttons=0;self.categories=0;self.shortcuts=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);classes=set(a.get('class','').split())
        if a.get('id'):self.ids.append(a['id'])
        if tag=='button':self.buttons+=1
        if 'feature-category' in classes:self.categories+=1
        if 'feature-shortcut' in classes:self.shortcuts+=1
        href=a.get('href','')
        if tag=='a' and href.startswith('#') and href!='#':self.targets.append(('anchor',href[1:]))
        for name in ('data-feature-open-panel','data-tablet-target','data-tablet-click','data-update-target','data-home-target','aria-controls'):
            if a.get(name):
                for value in a[name].split():self.targets.append((name,value))

def audit_html(source):
    p=NavigationParser();p.feed(source)
    counts=Counter(p.ids);ids=set(counts)
    duplicate=sorted(name for name,count in counts.items() if count>1)
    invalid=sorted({value for _,value in p.targets if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,80}',value)})
    missing=sorted({value for _,value in p.targets if value not in ids})
    return {'ok':not duplicate and not invalid and not missing,'scope':'STATIC_NAVIGATION_CONTRACT_ONLY',
            'physical_tablet_verified':False,'browser_render_verified':False,
            'categories':p.categories,'primary_shortcuts':p.shortcuts,'buttons_inventory':p.buttons,
            'declared_target_references':len(p.targets),'duplicate_ids':duplicate,'invalid_targets':invalid,
            'missing_targets':missing,'all_button_actions_executed':False}

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,default=Path(__file__).resolve().parents[1]/'index.html')
    args=parser.parse_args()
    if args.html.is_symlink() or args.html.stat().st_size>2_000_000:raise ValueError('unsafe/oversized HTML input')
    result=audit_html(args.html.read_text(encoding='utf-8'))
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 2

if __name__=='__main__':raise SystemExit(main())
