# smart_card_pipeline.py - 경량화 및 자가 수정 기반 통합 실행기
from optimized_self_healing import SelfHealingEngine
from card_data_collector import CardDataCollector
from datetime import datetime

def run_optimized_pipeline():
    engine = SelfHealingEngine()
    collector = CardDataCollector()
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 압축된 기존 데이터 로드 (오류 시 자동 복구)
    existing_data = engine.load_compressed_data()

    # 2. 만료 데이터 자가 판단 후 삭제 (용량 절감)
    valid_data = []
    removed_count = 0
    for item in existing_data:
        exp_date = item.get("valid_until") or item.get("release_date")
        # 기한이 지난 과거 데이터 자동 제거
        if exp_date and exp_date < today:
            removed_count += 1
            continue
        valid_data.append(item)

    print(f"📉 만료 데이터 {removed_count}건 정제 완료 (용량 최적화)")

    # 3. 신규 원피스/나루토/포켓몬 카드 정보 자동 탐색 및 병합
    new_cards = collector.fetch_new_card_news()
    existing_keys = {f"{item['category']}_{item['set_name']}" for item in valid_data}

    for card in new_cards:
        key = f"{card['category']}_{card['set_name']}"
        if key not in existing_keys:
            valid_data.append(card)

    # 4. 압축 저장 (용량 최소화 & 오류 수복 반영)
    success = engine.save_compressed_data(valid_data)
    if success:
        print("✅ 최소 용량 압축 저장 및 자가 검증 수치가 업데이트되었습니다.")

if __name__ == "__main__":
    run_optimized_pipeline()