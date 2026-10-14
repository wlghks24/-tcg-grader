# main_sync_runner.py - 중앙 동기화 및 실시간 적용 메인
from cloud_sync_engine import CloudSyncEngine
from cross_platform_agent import CrossPlatformSelfHealingEngine

def main():
    sync = CloudSyncEngine()
    engine = CrossPlatformSelfHealingEngine()

    print("🔄 [1/3] 중앙 서버에서 전 기기 공통 최신 데이터 동기화 가져오기...")
    master_data = sync.pull_latest_data_all_devices()

    print("🔎 [2/3] 신규 조사 자료(원피스/나루토/포켓몬) 병합 및 자가 치유 실행...")
    new_collected = engine.safe_data_collector()

    # 데이터 통합
    existing_keys = {f"{item['keyword']}_{item.get('sns_info')}" for item in master_data}
    for item in new_collected:
        key = f"{item['keyword']}_{item.get('sns_info')}"
        if key not in existing_keys:
            master_data.append(item)

    print("☁️ [3/3] 중앙 클라우드 단일 업로드 실행 (모든 PC/태블릿 일괄 업데이트)...")
    sync.push_update_from_single_device(master_data)

    print("\n✨ 전 기기 실시간 일괄 적용 및 자가 수복 완료!")

if __name__ == "__main__":
    main()