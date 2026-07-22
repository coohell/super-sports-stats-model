#!/usr/bin/env python3
"""
OpenClaw Cron용: 경기 결과 추적
실행: python3 cron/track_results.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.tracker.result_tracker import ResultTracker

def main():
    print(f"📊 {datetime.now().strftime('%Y-%m-%d %H:%M')} 결과 추적 시작")
    
    tracker = ResultTracker()
    tracker.check_live_results()
    
    # 어제 리포트
    report = tracker.generate_daily_report()
    print(report)
    
    print("✅ 결과 추적 완료")

if __name__ == "__main__":
    main()
