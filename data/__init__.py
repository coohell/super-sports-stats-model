"""
SuperPickKing 데이터 모듈
- 경기 데이터 수집 (API 연동 + 모의 데이터)
- get_all_matches(): 모든 경기 반환
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict

# 환경 변수
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")

def get_mock_matches() -> List[Dict]:
    """테스트용 모의 경기 데이터"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    matches = [
        # KBO
        {"match_id": "kbo_001", "date": today, "sport": "야구", "league": "KBO", "match_time": "18:30",
         "home_team": "LG", "away_team": "NC", "home_odds": 1.65, "draw_odds": 0, "away_odds": 2.25,
         "home_xg": 4.5, "away_xg": 3.8, "home_strength": 0.65, "away_strength": 0.45},
        {"match_id": "kbo_002", "date": today, "sport": "야구", "league": "KBO", "match_time": "18:30",
         "home_team": "롯데", "away_team": "SSG", "home_odds": 2.10, "draw_odds": 0, "away_odds": 1.75,
         "home_xg": 3.2, "away_xg": 4.1, "home_strength": 0.40, "away_strength": 0.60},
        {"match_id": "kbo_003", "date": today, "sport": "야구", "league": "KBO", "match_time": "18:30",
         "home_team": "삼성", "away_team": "KT", "home_odds": 1.80, "draw_odds": 0, "away_odds": 2.00,
         "home_xg": 4.0, "away_xg": 3.5, "home_strength": 0.55, "away_strength": 0.50},
        {"match_id": "kbo_004", "date": today, "sport": "야구", "league": "KBO", "match_time": "18:30",
         "home_team": "기아", "away_team": "한화", "home_odds": 1.55, "draw_odds": 0, "away_odds": 2.40,
         "home_xg": 5.2, "away_xg": 3.0, "home_strength": 0.75, "away_strength": 0.35},
        {"match_id": "kbo_005", "date": today, "sport": "야구", "league": "KBO", "match_time": "18:30",
         "home_team": "키움", "away_team": "두산", "home_odds": 1.90, "draw_odds": 0, "away_odds": 1.90,
         "home_xg": 3.8, "away_xg": 3.8, "home_strength": 0.50, "away_strength": 0.50},
        
        # 축구
        {"match_id": "soc_001", "date": today, "sport": "축구", "league": "K리그1", "match_time": "19:00",
         "home_team": "울산 HD", "away_team": "포항", "home_odds": 1.85, "draw_odds": 3.40, "away_odds": 4.20,
         "home_xg": 1.5, "away_xg": 1.2, "home_strength": 0.55, "away_strength": 0.45},
        {"match_id": "soc_002", "date": today, "sport": "축구", "league": "프리미어리그", "match_time": "21:00",
         "home_team": "맨시티", "away_team": "아스날", "home_odds": 1.65, "draw_odds": 3.80, "away_odds": 5.20,
         "home_xg": 1.8, "away_xg": 1.0, "home_strength": 0.65, "away_strength": 0.40},
        {"match_id": "soc_003", "date": today, "sport": "축구", "league": "라리가", "match_time": "04:00",
         "home_team": "레알마드리드", "away_team": "바르셀로나", "home_odds": 2.10, "draw_odds": 3.50, "away_odds": 3.40,
         "home_xg": 1.6, "away_xg": 1.5, "home_strength": 0.60, "away_strength": 0.55},
        
        # 농구
        {"match_id": "bask_001", "date": today, "sport": "농구", "league": "KBL", "match_time": "19:00",
         "home_team": "창원LG", "away_team": "서울SK", "home_odds": 1.80, "draw_odds": 0, "away_odds": 1.95,
         "home_xg": 82.0, "away_xg": 78.0, "home_strength": 0.52, "away_strength": 0.48},
        {"match_id": "bask_002", "date": today, "sport": "농구", "league": "NBA", "match_time": "08:30",
         "home_team": "셀틱스", "away_team": "매버릭스", "home_odds": 1.65, "draw_odds": 0, "away_odds": 2.25,
         "home_xg": 115.0, "away_xg": 108.0, "home_strength": 0.60, "away_strength": 0.45},
    ]
    
    return matches

def get_all_matches() -> List[Dict]:
    """모든 경기 데이터 반환 (API 연동 준비 + 모의 데이터 폴백)"""
    # TODO: API 연동 시 실제 데이터 우선 사용
    # if API_FOOTBALL_KEY or THE_ODDS_API_KEY:
    #     return fetch_api_matches()
    
    return get_mock_matches()

def get_matches_by_sport(sport: str) -> List[Dict]:
    """종목별 경기 필터링"""
    all_matches = get_all_matches()
    return [m for m in all_matches if m["sport"] == sport]

def get_matches_by_date(date: str = None) -> List[Dict]:
    """날짜별 경기 필터링"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    all_matches = get_all_matches()
    return [m for m in all_matches if m.get("date", date) == date]
