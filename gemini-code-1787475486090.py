# auto_card_pipeline.py - 신규 카드 자동 업로드 및 자가 학습 모듈
import json
import os
from card_data_collector import CardDataCollector
from auto_repair_engine import SelfOptimizingEngine

NEW_CARDS_STORE = "new_cards_database.json"

class AutoCardUploader:
    def __init__(self):
        self.collector = CardDataCollector()
        self.engine = SelfOptimizingEngine()

    def run_auto_investigation_and_upload(self):
        print("[1/3] 원피스 / 나루토 / 포켓몬 카드 신규 자료 자동 수집 중...")
        new_data = self.collector.fetch_new_card_news()

        print("[2/3] 기존 데이터베이스 교차 검증 및 중복 체크...")
        existing_data = []
        if os.path.exists(NEW_CARDS_STORE):
            with open(NEW_CARDS_STORE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)

        # 중복 제거 및 신규 항목 필터링
        existing_ids = {f"{item['category']}_{item['set_name']}" for item in existing_data}
        added_count = 0

        for item in new_data:
            item_id = f"{item['category']}_{item['set_name']}"
            if item_id not in existing_ids:
                existing_data.append(item)
                added_count += 1

        # 수집 데이터 파일 저장
        with open(NEW_CARDS_STORE, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

        print(f"[3/3] 신규 {added_count}개 항목 자동 업로드 완료. 자가 치유 및 최적화 실행...")
        
        # 데이터 결측치 및 오류 자가 수정을 위한 엔진 호출
        self.engine.auto_fix_data_anomaly(NEW_CARDS_STORE)
        print("✅ 원피스·나루토·포켓몬 신규 카드 자동 조사 및 업로드가 정상적으로 처리되었습니다.")

if __name__ == "__main__":
    uploader = AutoCardUploader()
    uploader.run_auto_investigation_and_upload()