# market_prices.py - 촬영 후 카드 정보로 실시간 구매처 및 가격 조회
import requests

def fetch_card_market_info(card_name, card_number=""):
    results = []
    
    # 1. PriceCharting / TCGPlayer API 또는 크롤러 수집
    search_query = f"{card_name} {card_number}".strip()
    
    # 2. 국내 네이버 쇼핑 / TCG 전문몰 검색 API 예시
    naver_url = f"https://openapi.naver.com/v1/search/shop.json?query={search_query}&display=5"
    headers = {"X-Naver-Client-Id": "YOUR_ID", "X-Naver-Client-Secret": "YOUR_SECRET"}
    
    try:
        res = requests.get(naver_url, headers=headers, timeout=5)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                results.append({
                    "store": item['mallName'],
                    "price": int(item['lprice']),
                    "link": item['link'],
                    "title": item['title'].replace("<b>", "").replace("</b>", "")
                })
    except Exception as e:
        print(f"시세 조회 오류: {e}")
        
    return results