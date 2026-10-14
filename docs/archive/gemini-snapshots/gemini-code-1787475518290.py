# update_purchase_sources.py / update_promo_events.py 수정 예시
import urllib.request
import json

def validate_and_fix_sources(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for item in data.get('sources', []):
        url = item.get('url')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=3)
            if res.status != 200:
                item['url'] = item.get('fallback_url', 'https://tcgplayer.com')
        except Exception:
            # 접속 불가 링크는 안전한 백업 주소로 자동 대체
            item['url'] = item.get('fallback_url', 'https://tcgplayer.com')
            
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)