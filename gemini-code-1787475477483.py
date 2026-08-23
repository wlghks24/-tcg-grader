# auto_card_pipeline.py - 만료 데이터 삭제 및 신규 데이터 자동 반영
import json
import os
from card_data_collector import CardDataCollector
from auto_repair_engine import SelfOptimizingEngine
from data_cleaner_engine import DataCleanerEngine

NEW_CARDS_STORE = "new_cards_database.json"
PROMO_EVENTS_STORE = "promo_events.json"

class AutoCardUploader:
    def __init__(self):
        self.collector = CardDataCollector()
        self.engine = SelfOptimizingEngine()
        self.cleaner = DataCleanerEngine()

    def run_auto_investigation_and_upload(self):
        print("[1/4] 기한이 지난 과거 데이터 자동 확인 및 삭제 중...")
        self.cleaner.purge_and_update_events(PROMO_EVENTS_STORE)
        self.cleaner.purge_and_update_events(NEW_CARDS_STORE)

        print("[2/4] 원피스 / 나루토 / 포켓몬 카드 최신 정보 자동 수집 중...")
        new_data = self.collector.fetch_new_card_news()

        print("[3/4] 중복 방지 검증 및 신규 최신 자료 대체 중...")
        existing_data = []
        if os.path.exists(NEW_CARDS_STORE):
            with open(NEW_CARDS_STORE, "r", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []

        existing_ids = {f"{item['category']}_{item['set_name']}" for item in existing_data}
        added_count = 0

        for item in new_data:
            item_id = f"{item['category']}_{item['set_name']}"
            if item_id not in existing_ids:
                existing_data.append(item)
                added_count += 1

        with open(NEW_CARDS_STORE, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

        print(f"[4/4] 신규 {added_count}개 최신 항목 보완 완료. 학습 최적화 적용...")
        self.engine.auto_fix_data_anomaly(NEW_CARDS_STORE)
        print("✅ 과거 데이터 정제 및 최신 자료 자동 교체 프로세스가 완료되었습니다.")

if __name__ == "__main__":
    uploader = AutoCardUploader()
    uploader.run_auto_investigation_and_upload()