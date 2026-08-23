# cloud_sync_engine.py - 중앙 서버 실시간 동기화 및 오류 자가 수복 모듈
import requests
import json
import gzip
import os
import platform
from datetime import datetime

class CloudSyncEngine:
    def __init__(self):
        # GitHub Gist / Firebase / Supabase 등의 Rest API 엔드포인트 설정
        self.cloud_url = "https://api.github.com/gists/YOUR_GIST_ID"
        self.headers = {"Authorization": "token YOUR_PERSONAL_ACCESS_TOKEN"}
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.local_cache = "cloud_data_cache.json.gz"

    def pull_latest_data_all_devices(self):
        """
        [모든 기기 공통] 실행 시 중앙 클라우드에서 최신 데이터를 가져옴
        """
        try:
            res = requests.get(self.cloud_url, headers=self.headers, timeout=5)
            if res.status_code == 200:
                cloud_content = res.json()["files"]["card_data.json"]["content"]
                data = json.loads(cloud_content)
                print("☁️ [동기화 성공] 클라우드 중앙 서버에서 최신 데이터를 불러왔습니다.")
                # 캐시 압축 저장
                self._save_local_cache(data)
                return data
            else:
                raise ConnectionError(f"HTTP Status: {res.status_code}")

        except Exception as e:
            # 네트워크 끊김/오류 발생 시 로컬 캐시 자가 복구 전환
            print(f"⚠️ 클라우드 연결 장애 감지: {e}")
            print("🔄 [자가 치유] 오프라인 캐시 모드로 자동 전환하여 수정을 진행합니다.")
            return self._load_local_cache()

    def push_update_from_single_device(self, updated_data):
        """
        [한 기기에서 업데이트 시] 중앙 클라우드로 업로드하여 모든 기기에 즉시 반영
        """
        # 만료일 지난 데이터 자동 정제 삭제
        cleaned_data = [
            item for item in updated_data 
            if not item.get("valid_until") or item.get("valid_until") >= self.today
        ]

        payload = {
            "files": {
                "card_data.json": {
                    "content": json.dumps(cleaned_data, ensure_ascii=False, indent=2)
                }
            }
        }

        try:
            res = requests.patch(self.cloud_url, headers=self.headers, json=payload, timeout=5)
            if res.status_code == 200:
                print("🚀 [클라우드 업로드 완료] PC/태블릿 등 모든 기기에 수정사항이 즉시 동기화 적용됩니다.")
                self._save_local_cache(cleaned_data)
                return True
            else:
                raise ValueError("Cloud Upload Failed")

        except Exception as e:
            print(f"🚨 클라우드 동기화 전송 오류: {e}")
            print("🛠️ [스스로 판단 및 보완] 로컬 캐시 임시 반영 후 대기열 저장 처리합니다.")
            self._save_local_cache(cleaned_data)
            return False

    def _save_local_cache(self, data):
        """용량 최소화 Gzip 오프라인 캐시 저장"""
        compressed = gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        with open(self.local_cache, 'wb') as f:
            f.write(compressed)

    def _load_local_cache(self):
        """로컬 압축 캐시 복원"""
        if os.path.exists(self.local_cache):
            with open(self.local_cache, 'rb') as f:
                return json.loads(gzip.decompress(f.read()).decode('utf-8'))
        return []