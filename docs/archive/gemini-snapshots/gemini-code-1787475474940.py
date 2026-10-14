# optimized_self_healing.py - 경량화 저장 및 오류 자가 수복 엔진
import json
import gzip
import os
import traceback
from datetime import datetime

class SelfHealingEngine:
    def __init__(self, data_file="cards_data.json.gz", backup_file="cards_data_backup.json.gz"):
        self.data_file = data_file
        self.backup_file = backup_file

    def save_compressed_data(self, data):
        """
        [용량 최소화] Gzip 압축을 적용하여 메모리 및 저장 용량 최소화
        """
        try:
            # 기존 데이터 백업
            if os.path.exists(self.data_file):
                os.replace(self.data_file, self.backup_file)

            json_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            with gzip.open(self.data_file, 'wb') as f:
                f.write(json_bytes)
            return True
        except Exception as e:
            self.auto_heal_error("SAVE_FAILED", e, data)
            return False

    def load_compressed_data(self):
        """
        [자가 진단] 손상된 파일 로드 시 자동 손상 감지 및 백업 자동 복구
        """
        if not os.path.exists(self.data_file):
            return []

        try:
            with gzip.open(self.data_file, 'rb') as f:
                return json.loads(f.read().decode('utf-8'))
        except Exception as e:
            print("⚠️ 데이터 파일 손상 감지! 자가 복구(Self-Healing) 동작 중...")
            return self.auto_heal_error("LOAD_FAILED", e)

    def auto_heal_error(self, error_type, error_obj, payload=None):
        """
        [스스로 판단 및 수정] 오류 유형 분류 후 자율적 보완 실행
        """
        err_msg = str(error_obj)
        print(f"🔧 [오류 판단] Type: {error_type} | Cause: {err_msg}")

        # 1. 파일 깨짐/파싱 에러 -> 백업 파일로 자가 복원
        if error_type == "LOAD_FAILED":
            if os.path.exists(self.backup_file):
                print("🔄 백업 데이터를 로드하여 구동을 정상 복구합니다.")
                with gzip.open(self.backup_file, 'rb') as f:
                    recovered_data = json.loads(f.read().decode('utf-8'))
                # 깨진 파일 덮어쓰기
                self.save_compressed_data(recovered_data)
                return recovered_data
            return []

        # 2. 용량 부족 또는 필드 결측 에러 -> 비어있는 필드 삭제 및 정제 보완
        elif error_type == "SAVE_FAILED" and payload:
            print("🧹 데이터 불량 구조 자가 정제 후 다시 저장을 시도합니다.")
            cleaned_payload = [item for item in payload if isinstance(item, dict) and item.get("set_name")]
            with gzip.open(self.data_file, 'wb') as f:
                f.write(json.dumps(cleaned_payload, separators=(',', ':')).encode('utf-8'))
            return cleaned_payload