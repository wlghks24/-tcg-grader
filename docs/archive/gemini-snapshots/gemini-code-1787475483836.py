# auto_update_all.py 업데이트 구문
import subprocess

def execute_full_auto_system():
    # 1. 신규 원피스/나루토/포켓몬 카드 정보 자동 탐색 및 업로드
    subprocess.run(["python", "auto_card_pipeline.py"])

    # 2. 크롤링 및 수집 실행
    subprocess.run(["python", "update_market_prices.py"])

    # 3. 데이터 통합 자가 검증 및 엔진 최적화
    subprocess.run(["python", "verify_all.py"])

if __name__ == "__main__":
    execute_full_auto_system()