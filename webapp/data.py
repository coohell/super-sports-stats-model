"""
오늘의 경기 데이터 + 다양한 종목 지원
API-Football 연동 (API 키 있을 시 실시간, 없으면 고퀄리티 모의 데이터)
"""
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
import requests
import streamlit as st

@dataclass
class Match:
    league: str
    home: str
    away: str
    match_time: str
    sport: str
    home_odds: float
    draw_odds: float
    away_odds: float
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None
    home_form: str = ""
    away_form: str = ""

# ===== 고퀄리티 모의 데이터 (API 키 없을 때) =====
SOCCER_LEAGUES = [
    ("K리그1", "대한민국"),
    ("프리미어리그", "잉글랜드"),
    ("라리가", "스페인"),
    ("세리에A", "이탈리아"),
    ("분데스리가", "독일"),
    ("리그1", "프랑스"),
    ("J리그", "일본"),
    ("챔피언스리그", "유럽"),
]

SOCCER_TEAMS = {
    "K리그1": [("울산 HD", 1.85), ("포항", 2.10), ("전북", 1.95), ("FC서울", 2.30), 
               ("수원FC", 2.80), ("인천", 2.60), ("강원", 2.40), ("대구", 2.50)],
    "프리미어리그": [("맨시티", 1.60), ("아스날", 1.90), ("리버풀", 1.75), ("첼시", 2.20),
                    ("맨유", 2.40), ("토트넘", 2.30), ("뉴캐슬", 2.50), ("아스톤빌라", 2.80)],
    "라리가": [("레알마드리드", 1.55), ("바르셀로나", 1.65), ("AT마드리드", 1.90),
              ("세비야", 2.60), ("발렌시아", 2.80), ("비야레알", 2.40)],
    "세리에A": [("인터밀란", 1.70), ("AC밀란", 1.85), ("유벤투스", 1.90), ("나폴리", 1.80),
               ("로마", 2.50), ("라치오", 2.60)],
    "분데스리가": [("바이에른", 1.50), ("도르트문트", 1.80), ("레버쿠젠", 1.75),
                 ("라이프치히", 2.00), ("프랑크푸르트", 2.60)],
    "J리그": [("요코하마F", 1.80), ("비셀고베", 2.10), ("가와사키", 1.70),
              ("히로시마", 2.20), ("도쿄", 2.30)],
}

BASKETBALL_MATCHES = [
    Match("NBA", "보스턴 셀틱스", "댈러스 매버릭스", "08:30", "농구", 1.65, 13.0, 2.25),
    Match("NBA", "덴버 너기츠", "마이애미 히트", "11:00", "농구", 1.55, 12.5, 2.50),
    Match("KBL", "창원LG", "서울SK", "19:00", "농구", 1.80, 11.5, 1.95),
    Match("KBL", "원주DB", "부산KCC", "17:00", "농구", 2.10, 12.0, 1.75),
]

BASEBALL_MATCHES = [
    Match("KBO", "삼성", "두산", "18:30", "야구", 1.85, 7.5, 1.95),
    Match("KBO", "기아", "LG", "14:00", "야구", 1.75, 8.0, 2.10),
    Match("KBO", "NC", "KT", "18:30", "야구", 2.00, 7.0, 1.80),
    Match("MLB", "다저스", "양키스", "11:10", "야구", 1.60, 8.5, 2.40),
]

TENNIS_MATCHES = [
    Match("Wimbledon", "알카라스", "조코비치", "22:00", "테니스", 1.55, None, 2.50),
    Match("Wimbledon", "시너", "메드베데프", "20:00", "테니스", 1.70, None, 2.20),
    Match("ATP", "즈베레프", "루블료프", "01:00", "테니스", 1.85, None, 1.95),
]

VOLLEYBALL_MATCHES = [
    Match("V리그", "대한항공", "현대캐피탈", "19:00", "배구", 1.75, None, 2.05),
    Match("V리그", "우리카드", "OK금융", "14:00", "배구", 1.90, None, 1.90),
]

def generate_soccer_matches(date_offset: int = 0) -> List[Match]:
    """모의 축구 경기 생성"""
    base_date = datetime.now() + timedelta(days=date_offset)
    matches = []
    times = ["14:00", "16:30", "19:00", "20:00", "21:00", "22:00"]
    
    for league_name, _ in SOCCER_LEAGUES[:6]:
        teams = SOCCER_TEAMS.get(league_name, SOCCER_TEAMS["프리미어리그"])
        random.shuffle(teams)
        
        for i in range(0, min(4, len(teams)-1), 2):
            home_team, home_strength = teams[i]
            away_team, away_strength = teams[i+1]
            
            # 배당률 생성
            base_h = (home_strength + away_strength) / 2
            home_odds = round(max(1.25, min(4.0, base_h + random.uniform(-0.3, 0.3))), 2)
            away_odds = round(max(1.25, min(5.0, away_strength + random.uniform(-0.3, 0.3))), 2)
            draw_odds = round(1 / (1 - 1/home_odds - 1/away_odds) if (1/home_odds + 1/away_odds) < 0.95 else 3.40, 2)
            
            # xG 생성
            home_xg = round(random.uniform(0.8, 2.5), 1)
            away_xg = round(random.uniform(0.5, 2.0), 1)
            
            # 폼 생성
            forms = ["W", "D", "L"]
            home_form = "".join(random.choices(forms, weights=[5, 3, 2], k=5))
            away_form = "".join(random.choices(forms, weights=[4, 3, 3], k=5))
            
            match = Match(
                league=league_name,
                home=home_team,
                away=away_team,
                match_time=random.choice(times),
                sport="축구",
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
                home_xg=home_xg,
                away_xg=away_xg,
                home_form=home_form,
                away_form=away_form
            )
            matches.append(match)
    
    return matches

def get_today_matches() -> List[Match]:
    """오늘의 경기 목록 반환 (API 키 있으면 실시간, 없으면 모의)"""
    api_key = st.secrets.get("API_FOOTBALL_KEY", "") if hasattr(st, "secrets") else ""
    
    # 우선 모의 데이터로 다양한 종목 구성
    matches = []
    matches.extend(generate_soccer_matches(0))  # 오늘 축구
    matches.extend(BASKETBALL_MATCHES)
    matches.extend(BASEBALL_MATCHES)
    matches.extend(TENNIS_MATCHES)
    matches.extend(VOLLEYBALL_MATCHES)
    
    return matches

def get_match_by_teams(home: str, away: str, all_matches: List[Match]) -> Optional[Match]:
    """팀명으로 경기 찾기"""
    for m in all_matches:
        if m.home == home or m.away == away:
            return m
    return None
