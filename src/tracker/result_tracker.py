#!/usr/bin/env python3
"""
경기 결과 추적 및 DB 업데이트
경기 종료 후 결과 수집 → 픽 결과 업데이트
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from typing import List, Optional
import requests

from src.picks.database import PickDatabase

class ResultTracker:
    """경기 결과 추적기"""
    
    def __init__(self):
        self.db = PickDatabase()
    
    def fetch_match_result(self, home: str, away: str, date: str, sport: str = "축구") -> Optional[dict]:
        """
        경기 결과 조회
        실제 구현 시 API-Football, ESPN API 등 연동
        """
        # 모의 결과 (테스트용)
        # 실제로는 API 호출 필요
        return None
    
    def check_live_results(self):
        """진행 중인 경기 결과 확인"""
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # 어제/오늘 경기 중 미정산 픽 조회
        picks = self.db.get_picks_by_date(yesterday) + self.db.get_picks_by_date(today)
        pending = [p for p in picks if p.status == 'pending']
        
        for pick in pending:
            # TODO: 실제 API로 결과 조회
            # result = self.fetch_match_result(pick.home_team, pick.away_team, pick.date, pick.sport)
            
            # 모의 결과 (테스트용)
            import random
            result = random.choice(['win', 'loss', 'push'])
            score = "2:1" if result == 'win' else "0:2" if result == 'loss' else "1:1"
            profit = (pick.pick_odds - 1) * 10000 if result == 'win' else -10000 if result == 'loss' else 0
            
            self.db.update_result(pick.id, result, score, profit)
            print(f"✅ {pick.home_team} vs {pick.away_team}: {result} ({score})")
    
    def generate_daily_report(self, date: str = None) -> str:
        """일일 결과 리포트"""
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        picks = self.db.get_picks_by_date(date)
        settled = [p for p in picks if p.status == 'settled']
        
        if not settled:
            return f"{date} 정산된 픽이 없습니다."
        
        wins = sum(1 for p in settled if p.result == 'win')
        losses = sum(1 for p in settled if p.result == 'loss')
        pushes = sum(1 for p in settled if p.result == 'push')
        total_profit = sum(p.profit for p in settled)
        
        report = f"""
# 📊 {date} 슈퍼픽킹 결과 리포트

## 성적
- ✅ 승: {wins}회
- ❌ 패: {losses}회  
- ➖ 무: {pushes}회
- 💰 총 수익: {total_profit:+,}원
- 📈 승률: {wins/(wins+losses)*100:.1f}% (무 제외)

## 상세
"""
        for p in settled:
            emoji = "✅" if p.result == 'win' else "❌" if p.result == 'loss' else "➖"
            report += f"- {emoji} {p.home_team} vs {p.away_team}: {p.pick_selection} @ {p.pick_odds} → {p.actual_score}\n"
        
        return report

if __name__ == "__main__":
    tracker = ResultTracker()
    tracker.check_live_results()
    print(tracker.generate_daily_report())
