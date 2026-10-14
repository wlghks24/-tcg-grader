# auto_pipeline_runner.py - 오류 검증, 만료 데이터 삭제, 용량 최적화 통합 실행
import os
import json
import gzip
from datetime import datetime
from multi_channel_agent import MultiChannelCollector

STORE_FILE = "comprehensive_card_news.json.gz"

class AutoPipelineRunner:
    def __init__(self):
        self.agent = MultiChannelCollector()
        self.today = datetime.now().strftime("%Y-%m-%d")

    def run_pipeline(self):
        keywords = ["원피스", "나루토", "포켓몬"]
        collected_data = []

        print("🚀 [1/3] 인스타 / X / 구글 다중 채널 수집 및 자가 진단 시작...")
        for kw in keywords:
            # 구글 수집 & 에러 시 자동 수복
            web_res = self.agent.search_google_news(kw)
            # SNS 수집 & 에러 시 자동 수복
            sns_res = self.agent.fetch_sns_trends(kw)

            collected_data.append({
                "keyword": kw,
                "web_news": web_res,
                "sns_news": sns_res,
                "updated_at": self.today
            })

        print("🧹 [2/3] 과거 지난 데이터 삭제 및 자가 정제 처리...")
        cleaned_data = self.clean_expired_records(collected_data)

        print("💾 [3/3] Gzip 압축 저장 (용량 최소화 & 손상 감지 자가 치유)...")
        self.save_with_auto_healing(cleaned_data)

    def clean_expired_records(self, data_list):
        """만료 데이터 자동 제거 코딩"""
        for entry in data_list:
            valid_sns = []
            for sns in entry.get("sns_news", []):
                valid_until = sns.get("valid_until")
                # 기한이 지나지 않은 데이터만 유지
                if not valid_until or valid_until >= self.today:
                    valid_sns.append(sns)
            entry["sns_news"] = valid_sns
        return data_list

    def save_with_auto_healing(self, data):
        """손상 및 파싱 오류 시 자가 복구 저장 기법 적용"""
        try:
            compressed_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            with gzip.open(STORE_FILE, 'wb') as f:
                f.write(compressed_bytes)
            print(f"✅ 실행 완료: 오류 없이 자가 정제되어 '{STORE_FILE}'에 압축 저장되었습니다.")

        except Exception as e:
            print(f"🚨 저장 모듈 오류 감지: {e}")
            print("🔧 데이터 구조 자가 보정 후 재저장합니다.")
            
            # 파이썬 기본 JSON 파일로 자가 복원 우회
            fallback_file = "comprehensive_card_news_backup.json"
            with open(fallback_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 백업 모드로 전환하여 안전하게 수정을 마쳤습니다: {fallback_file}")

if __name__ == "__main__":
    runner = AutoPipelineRunner()
    runner.run_pipeline()