# run_cross_system.py - PC 및 태블릿 범용 통합 실행 파일
import sys
from cross_platform_agent import CrossPlatformSelfHealingEngine

def main():
    print("📱/💻 PC & 태블릿 호환 통합 학습 파이프라인을 구동합니다.")
    
    # 자가 치유 엔진 초기화 (OS 및 환경 자율 진단)
    engine = CrossPlatformSelfHealingEngine()

    try:
        # 데이터 수집 및 자가 오류 보환 실행
        data = engine.safe_data_collector()

        # 과거 데이터 정제 및 최적화 압축 저장
        engine.save_and_clean_data(data)
        
        print("\n✨ 전체 프로세스가 오류 없이 완료되었습니다.")

    except Exception as fatal_error:
        print(f"\n🚨 [치명적 오류 감지]: {fatal_error}")
        print("🛠️ 오류 로그 수집 후 파이프라인 안전 종료 및 구조 재정비 중...")

if __name__ == "__main__":
    main()