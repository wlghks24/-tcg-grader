# auto_repair_engine.py - 자가 진단, 학습값 최적화 및 자동 오류 치유 엔진
import json
import os
import datetime

LEARNING_STORE_PATH = "learning_store.json"
REPAIR_MEMORY_PATH = "auto_repair_memory.json"

class SelfOptimizingEngine:
    def __init__(self):
        self.learning_data = self._load_json(LEARNING_STORE_PATH)
        self.repair_memory = self._load_json(REPAIR_MEMORY_PATH)

    def _load_json(self, path):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def analyze_and_optimize(self, execution_logs):
        """
        수집/분석 중 발생한 오류 로그 분석 후 피드백 및 파라미터 최적화
        """
        errors = execution_logs.get("errors", [])
        weights = self.learning_data.get("weights", {
            "centering_threshold": 0.85,
            "crawl_timeout": 5,
            "retry_count": 3
        })

        # 오류 유형에 따른 자동 피드백 학습 조정
        for err in errors:
            err_type = err.get("type")
            if err_type == "TIMEOUT":
                # 네트워크 지연 오류 발생 시 타임아웃 및 가중치 수치 자동 보정
                weights["crawl_timeout"] = min(weights["crawl_timeout"] + 2, 15)
                weights["retry_count"] += 1
            elif err_type == "CENTERING_FAILED":
                # 이미지 감지 실패 시 임계값(Threshold) 수치 자율 하향 조정
                weights["centering_threshold"] = max(weights["centering_threshold"] - 0.05, 0.60)

        # 학습 결과 저장
        self.learning_data["weights"] = weights
        self.learning_data["last_optimization"] = str(datetime.datetime.now())
        self._save_json(LEARNING_STORE_PATH, self.learning_data)
        
        return weights

    def auto_fix_data_anomaly(self, json_file_path):
        """
        JSON 수집 데이터 내 누락/오류 항목 자동 교정 및 최적화 반영
        """
        if not os.path.exists(json_file_path):
            return

        data = self._load_json(json_file_path)
        fixed_count = 0

        if isinstance(data, dict) and "sources" in data:
            for item in data["sources"]:
                # 링크 유효성 체크 및 빈 필드 자동 채움(Self-Repair)
                if not item.get("url") or item.get("url") == "":
                    item["url"] = "https://tcgplayer.com"
                    fixed_count += 1
                if "price" in item and (item["price"] is None or item["price"] <= 0):
                    item["price"] = self.learning_data.get("avg_fallback_price", 1000)
                    fixed_count += 1

        if fixed_count > 0:
            self._save_json(json_file_path, data)
            self.repair_memory[json_file_path] = {
                "fixed_items": fixed_count,
                "timestamp": str(datetime.datetime.now())
            }
            self._save_json(REPAIR_MEMORY_PATH, self.repair_memory)