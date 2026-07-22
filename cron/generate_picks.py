#!/usr/bin/env python3
"""
OpenClaw Cron용: 매일 슈퍼픽 생성
실행: python3 cron/generate_picks.py [sport]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

from src.picks.super_king import SuperPickKing
from webapp.data import get_today_matches

def main():
    sport = sys.argv[1] if len(sys.argv) > 1 else "축구"
    
    print(f"🔮 {datetime.now().strftime('%Y-%m-%d %H:%M')} 슈퍼픽 생성 시작")
    
    king = SuperPickKing()
    
    # 오늘 경기 가져오기
    all_matches = get_today_matches()
    sport_matches = [m for m in all_matches if m.sport == sport]
    
    if not sport_matches:
        print(f"⚠️ {sport} 경기 없음")
        return
    
    # dict로 변환
    match_dicts = []
    for m in sport_matches:
        match_dicts.append({
            'home': m.home,
            'away': m.away,
            'home_odds': m.home_odds,
            'draw_odds': m.draw_odds,
            'away_odds': m.away_odds,
            'sport': m.sport,
            'league': m.league,
            'match_time': m.match_time
        })
    
    # 픽 생성
    picks = king.generate_daily_picks(match_dicts, sport)
    
    # 리포트 출력
    report = king.get_pick_report(picks)
    print(report)
    
    # 파일로 저장
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = Path(__file__).parent.parent / "reports" / f"picks_{today}_{sport}.md"
    report_path.write_text(report, encoding='utf-8')
    
    print(f"\n✅ 리포트 저장: {report_path}")

if __name__ == "__main__":
    main()
