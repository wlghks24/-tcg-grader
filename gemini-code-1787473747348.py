# run_github_pipeline.py - 통합 실행 및 자가 수복 파일
from github_sync_engine import GitHubSyncEngine
from cross_platform_agent import CrossPlatformSelfHealingEngine

def main():
    print("📱/💻 GitHub 단일 업로드 및 전 기기 실시간 반영 파이프라인 가동...")

    # 1. GitHub 엔진 및 크로스 플랫폼 agent 초기화
    github_engine = GitHubSyncEngine(
        token="YOUR_GITHUB_TOKEN",       # 사용자의 GitHub Personal Access Token 입력
        repo_owner="YOUR_GITHUB_ID",     # GitHub 계정 ID
        repo_name="YOUR_REPO_NAME",      # 레포지토리 이름
        file_path="cards_data.json"
    )
    platform_agent = CrossPlatformSelfHealingEngine()

    # 2. GitHub 최신 데이터 가져오기 (실패 시 로컬 캐시 자가 복구)
    master_data, file_sha = github_engine.pull_from_github()

    # 3. 새로운 카드 소식 조사 및 수집 에러 자가 보완
    new_data = platform_agent.safe_data_collector()

    # 4. 데이터 병합 및 중복 제거
    existing_keys = {f"{item['keyword']}_{item.get('sns_info')}" for item in master_data}
    for item in new_data:
        key = f"{item['keyword']}_{item.get('sns_info')}"
        if key not in existing_keys:
            master_data.append(item)

    # 5. GitHub 단일 업로드 (오류 시 자가 치유 전환 및 전 기기 동기화 완료)
    github_engine.push_to_github(master_data, sha=file_sha)
    print("\n✨ 모든 프로세스가 자가 진단 및 보완을 거쳐 완료되었습니다.")

if __name__ == "__main__":
    main()