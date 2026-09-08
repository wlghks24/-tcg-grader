"""Feature -> one entry -> bounded impact -> targeted tests. Never scans a repo."""
import argparse
import json
from pathlib import Path


def route(feature):
    data=json.loads(Path(__file__).with_name('CODE_MAP.json').read_text())
    key=data['aliases'].get(feature,feature)
    if key not in data['features']:
        return {'status':'UNKNOWN_FEATURE','available':list(data['features'])}
    return dict(status='ROUTED',feature=key,**data['features'][key])


def route_file(filename):
    """Reverse-route one changed file to bounded impacted features and tests."""
    name=Path(filename).name
    data=json.loads(Path(__file__).with_name('CODE_MAP.json').read_text())
    matched=[];tests=[]
    for key,item in data['features'].items():
        if name==item['entry_file'] or name in item['impact']:
            matched.append(key)
            tests.extend(item['tests'])
    return {'status':'ROUTED_FILE' if matched else 'UNKNOWN_FILE','file':name,
            'features':matched,'targeted_tests':list(dict.fromkeys(tests))}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('query');parser.add_argument('--file',action='store_true')
    args=parser.parse_args()
    print(json.dumps(route_file(args.query) if args.file else route(args.query),ensure_ascii=False,indent=2))
