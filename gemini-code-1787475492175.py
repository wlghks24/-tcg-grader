# auto_update_all.py
import subprocess
from auto_repair_engine import SelfOptimizingEngine

def execute_one_click_auto_pipeline():
    print("[1/3] 수집 및 자가 보정 모듈 동작 중...")
    subprocess.run(["python", "update_market_prices.py"])
    subprocess.run(["python", "update_promo_events.py"])
    subprocess.run(["python", "update_purchase_sources.py"])

    print("[2/3] 검증 시스템 전체 스캔 및 자가 검증 중...")
    subprocess.run(["python", "verify_all.py"])

    print("[3/3] 최적화 파라미터 적용 및 오류 자동 수정 중...")
    engine = SelfOptimizingEngine()
    engine.auto_fix_data_anomaly("purchase_sources.json")
    engine.auto_fix_data_anomaly("promo_events.json")

    print("✅ 자가 피드백 학습 및 통합 업데이트가 정상 완료되었습니다.")

if __name__ == "__main__":
    execute_one_click_auto_pipeline()