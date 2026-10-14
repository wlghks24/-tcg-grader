# data_cleaner_engine.py - 만료 데이터 자동 정리 및 최신화 파이프라인
import json
import os
from datetime import datetime

class DataCleanerEngine:
    def __init__(self):
        # 기준 날짜 설정
        self.today = datetime.now().strftime("%Y-%m-%d")

    def purge_and_update_events(self, file_path):
        """
        날짜가 지난 프로모션 및 이벤트 데이터 자동 정제
        """
        if not os.path.exists(file_path):
            return

        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return

        updated_items = []
        removed_count = 0

        # 데이터 리스트 순회 검사
        items = data if isinstance(data, list) else data.get("events", [])
        for item in items:
            end_date = item.get("end_date") or item.get("valid_until")
            
            # 만료 날짜가 존재하고, 오늘 날짜보다 과거인 경우 삭제 대상 처리
            if end_date and end_date < self.today:
                removed_count += 1
                continue
            
            updated_items.append(item)

        # 정제된 데이터 재저장
        output_data = updated_items if isinstance(data, list) else {**data, "events": updated_items}
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"🧹 [{file_path}] 만료된 과거 자료 {removed_count}건 삭제 및 정제 완료.")
        return removed_count