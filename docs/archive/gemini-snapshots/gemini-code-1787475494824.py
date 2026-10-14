# update_market_prices.py - 다중 크롤링 및 자가 보정 파이프라인
import json
import requests
from auto_repair_engine import SelfOptimizingEngine

def run_market_data_collection():
    engine = SelfOptimizingEngine()
    # 학습된 최적 가중치값 자동 로드
    weights = engine.learning_data.get("weights", {"crawl_timeout": 5})
    
    logs = {"errors": []}
    market_data = []

    # 1. 다중 소스 수집 시도
    try:
        # 가중치에 따른 타임아웃 값 가변 적용
        res = requests.get("https://api.tcgplayer.com/...", timeout=weights["crawl_timeout"])
        if res.status_code == 200:
            market_data.extend(res.json().get("results", []))
    except Exception as e:
        logs["errors"].append({"type": "TIMEOUT", "message": str(e)})

    # 2. 결과 저장 후 자동 데이터 자가 교정 및 학습 반영
    with open("market_prices.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    # 3. 오류 로그 기반 최적화 스토어 업데이트
    engine.analyze_and_optimize(logs)
    engine.auto_fix_data_anomaly("market_prices.json")

if __name__ == "__main__":
    run_market_data_collection()