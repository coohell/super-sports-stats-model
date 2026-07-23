"""
SuperPickKing 데이터 모듈
- 경기 데이터 수집 (API 연동 + 모의 데이터)
- get_all_matches(): 모든 경기 반환
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict
import requests

# 환경 변수
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")


def fetch_theodds_api(sport: str = "soccer", region: str = "eu") -> List[Dict]:
    """TheOddsAPI에서 실시간 배당 수집"""
    if not THE_ODDS_API_KEY:
        return []
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        'apiKey': THE_ODDS_API_KEY,
        'regions': region,
        'markets': 'h2h',
        'oddsFormat': 'decimal'
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        matches = []
        today = datetime.now().strftime("%Y-%m-%d")
        
        for game in data[:10]:
            match_time = game.get('commence_time', '')
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            
            # 배당률 추출
            odds = game.get('bookmakers', [{}])[0].get('markets', [{}])[0].get('outcomes', [])
            home_odds = draw_odds = away_odds = 0
            
            for o in odds:
                name = o.get('name', '')
                price = o.get('price', 0)
                if name == home:
                    home_odds = price
                elif name == away:
                    away_odds = price
                elif name in ['Draw', '무승부']:
                    draw_odds = price
            
            if home_odds > 0 and away_odds > 0:
                matches.append({
                    'match_id': f"odds_{game.get('id', '')}",
                    'date': today,
                    'sport': '축구' if sport == 'soccer' else sport,
                    'league': game.get('sport_title', ''),
                    'match_time': match_time,
                    'home_team': home,
                    'away_team': away,
                    'home_odds': home_odds,
                    'draw_odds': draw_odds or 0,
                    'away_odds': away_odds,
                    'home_xg': 1.5,
                    'away_xg': 1.2,
                    'home_strength': 0.5,
                    'away_strength': 0.5
                })
        
        return matches
    except Exception as e:
        print(f"⚠️ TheOddsAPI 오류: {e}")
        return []


def get_mock_matches() -> List[Dict]:
    """테스트용 모의 경기 데이터 (API 실패 시 폴백)"""""
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
    """모든 경기 데이터 반환 (API 우선, 실패 시 모의 데이터)"""
    # 실제 API 데이터 우선 시도
    real_matches = fetch_theodds_api("soccer", "eu")
    
    if real_matches:
        print(f"   → TheOddsAPI 실시간 데이터 {len(real_matches)}개 로드")
        return real_matches
    
    print("   → API 실패, 모의 데이터 사용")
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
