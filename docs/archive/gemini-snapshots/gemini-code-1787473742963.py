# github_sync_engine.py - GitHub 자동 업로드 및 자가 수복 동기화 파일
import os
import json
import gzip
import base64
import requests
from datetime import datetime

class GitHubSyncEngine:
    def __init__(self, token=None, repo_owner=None, repo_name=None, file_path="cards_data.json"):
        # GitHub 인증 정보 설정 (환경 변수 또는 기본값)
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo_owner = repo_owner or os.environ.get("GITHUB_OWNER", "")
        self.repo_name = repo_name or os.environ.get("GITHUB_REPO", "")
        self.file_path = file_path
        
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{self.file_path}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.local_cache = "github_cards_cache.json.gz"

    def pull_from_github(self):
        """[모든 기기 공통] GitHub에서 최신 파일을 다운로드하여 적용"""
        if not self.token or not self.repo_owner or not self.repo_name:
            print("⚠️ [환경 진단] GitHub 토큰/레포 정보 미설정. 로컬 백업 모드로 자동 전환합니다.")
            return self._load_local_cache()

        try:
            res = requests.get(self.api_url, headers=self.headers, timeout=5)
            if res.status_code == 200:
                content_b64 = res.json().get("content", "")
                decoded_content = base64.b64decode(content_b64).decode("utf-8")
                data = json.loads(decoded_content)
                
                print("☁️ [GitHub 동기화 성공] 최신 데이터 세트를 다운로드했습니다.")
                self._save_local_cache(data)
                return data, res.json().get("sha")
            else:
                raise ValueError(f"HTTP Status {res.status_code}")

        except Exception as err:
            return self.auto_heal_error("PULL_FAILED", err)

    def push_to_github(self, data, sha=None):
        """[한 기기에서 실행] 최신 가공 데이터를 GitHub에 자동 커밋/업로드"""
        # 만료 일자가 지난 과거 데이터 자동 정제
        cleaned_data = [
            item for item in data 
            if not item.get("valid_until") or item.get("valid_until") >= self.today
        ]

        if not self.token or not self.repo_owner or not self.repo_name:
            print("⚠️ GitHub 인증 값이 없어 로컬 캐시 저정으로 우회 보완합니다.")
            self._save_local_cache(cleaned_data)
            return False

        try:
            json_str = json.dumps(cleaned_data, ensure_ascii=False, indent=2)
            encoded_content = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

            payload = {
                "message": f"Auto-update card data: {self.today}",
                "content": encoded_content
            }
            if sha:
                payload["sha"] = sha

            res = requests.put(self.api_url, headers=self.headers, json=payload, timeout=5)
            if res.status_code in [200, 201]:
                print("🚀 [GitHub 업로드 완료] 모든 PC 및 태블릿 기기에 실시간 반영되었습니다.")
                self._save_local_cache(cleaned_data)
                return True
            else:
                raise ValueError(f"Upload Status Code: {res.status_code}")

        except Exception as err:
            self.auto_heal_error("PUSH_FAILED", err, payload_data=cleaned_data)
            return False

    def auto_heal_error(self, error_type, error_obj, payload_data=None):
        """실행 중 오류 발생 시 스스로 판단하여 예외를 수복하는 자가 치유 함수"""
        print(f"🔧 [오류 자가 진단 및 수복] Type: {error_type} | Message: {error_obj}")
        
        if error_type == "PULL_FAILED":
            print("🔄 오프라인 로컬 압축 캐시 데이터로 자동 복구 구동합니다.")
            return self._load_local_cache(), None

        elif error_type == "PUSH_FAILED" and payload_data:
            print("💾 네트워크 충돌 감지 -> 로컬 캐시 임시 보관 후 오류를 우회 처리합니다.")
            self._save_local_cache(payload_data)
            return False

    def _save_local_cache(self, data):
        """용량 절감을 위한 Gzip 로컬 캐시 저장을 보장"""
        compressed = gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        with open(self.local_cache, 'wb') as f:
            f.write(compressed)

    def _load_local_cache(self):
        if os.path.exists(self.local_cache):
            with open(self.local_cache, 'rb') as f:
                return json.loads(gzip.decompress(f.read()).decode('utf-8'))
        return []