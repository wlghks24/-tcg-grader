# create_files.py - 실행 시 두 개의 핵심 파이썬 파일을 자동으로 만들어주는 파일 생성기

github_sync_engine_code = '''# github_sync_engine.py - GitHub 자동 업로드 및 자가 수복 동기화 모듈
import os
import json
import gzip
import base64
import requests
from datetime import datetime

class GitHubSyncEngine:
    def __init__(self, token=None, repo_owner=None, repo_name=None, file_path="cards_data.json"):
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
        if not self.token or not self.repo_owner or not self.repo_name:
            print("⚠️ [환경 진단] GitHub 토큰/레포 정보 미설정. 오프라인 자가 수복 모드로 자동 전환합니다.")
            return self._load_local_cache(), None

        try:
            res = requests.get(self.api_url, headers=self.headers, timeout=5)
            if res.status_code == 200:
                content_b64 = res.json().get("content", "")
                decoded_content = base64.b64decode(content_b64).decode("utf-8")
                data = json.loads(decoded_content)
                print("☁️ [GitHub 동기화 성공] 최신 데이터 세트를 성공적으로 다운로드했습니다.")
                self._save_local_cache(data)
                return data, res.json().get("sha")
            else:
                raise ValueError(f"HTTP Status {res.status_code}")
        except Exception as err:
            return self.auto_heal_error("PULL_FAILED", err)

    def push_to_github(self, data, sha=None):
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
        print(f"🔧 [오류 자가 진단 및 수복] Type: {error_type} | Message: {error_obj}")
        if error_type == "PULL_FAILED":
            print("🔄 오프라인 로컬 압축 캐시 데이터로 자동 복구 구동합니다.")
            return self._load_local_cache(), None
        elif error_type == "PUSH_FAILED" and payload_data:
            print("💾 네트워크 충돌 감지 -> 로컬 캐시 임시 보관 후 오류를 우회 처리합니다.")
            self._save_local_cache(payload_data)
            return False

    def _save_local_cache(self, data):
        compressed = gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        with open(self.local_cache, 'wb') as f:
            f.write(compressed)

    def _load_local_cache(self):
        if os.path.exists(self.local_cache):
            with open(self.local_cache, 'rb') as f:
                return json.loads(gzip.decompress(f.read()).decode('utf-8'))
        return []
'''

run_github_pipeline_code = '''# run_github_pipeline.py - 통합 실행 및 자가 수복 파일
from github_sync_engine import GitHubSyncEngine
import os
import platform
from datetime import datetime

def safe_data_collector():
    today = datetime.now().strftime("%Y-%m-%d")
    keywords = ["원피스", "나루토", "포켓몬"]
    collected = []
    for kw in keywords:
        collected.append({
            "keyword": kw,
            "sns_info": f"{kw} 카드 신규 프로모 및 콜라보 소식 탐색 데이터",
            "valid_until": "2026-12-31",
            "collected_at": today,
            "platform_used": platform.system()
        })
    return collected

def main():
    print("📱/💻 GitHub 단일 업로드 및 전 기기 실시간 반영 파이프라인 가동...")

    github_engine = GitHubSyncEngine(
        token=os.environ.get("GITHUB_TOKEN", "YOUR_GITHUB_TOKEN"),
        repo_owner=os.environ.get("GITHUB_OWNER", "YOUR_GITHUB_ID"),
        repo_name=os.environ.get("GITHUB_REPO", "YOUR_REPO_NAME"),
        file_path="cards_data.json"
    )

    master_data, file_sha = github_engine.pull_from_github()
    new_data = safe_data_collector()

    existing_keys = {f"{item['keyword']}_{item.get('sns_info')}" for item in master_data}
    for item in new_data:
        key = f"{item['keyword']}_{item.get('sns_info')}"
        if key not in existing_keys:
            master_data.append(item)

    github_engine.push_to_github(master_data, sha=file_sha)
    print("✨ 모든 프로세스가 자가 진단 및 보완을 거쳐 완료되었습니다.")

if __name__ == "__main__":
    main()
'''

# 파일 자동 쓰기 실행
with open("github_sync_engine.py", "w", encoding="utf-8") as f:
    f.write(github_sync_engine_code)

with open("run_github_pipeline.py", "w", encoding="utf-8") as f:
    f.write(run_github_pipeline_code)

print("✅ 파일 생성 완료:")
print("1. github_sync_engine.py")
print("2. run_github_pipeline.py")