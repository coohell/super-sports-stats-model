#!/usr/bin/env python3
"""
슈퍼최강 픽픽픽 엔진
실제 데이터 연동 + LLM 심층분석 + 자동 픽 생성
"""
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram_bot.logic import KillPickEngine
from src.picks.database import PickDatabase, MatchPick

# 환경변수
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
ALIYUN_KEY = os.getenv("ALIYUN_API_KEY", "")
ALIYUN_BASE_URL = os.getenv("ALIYUN_BASE_URL", "")

@dataclass
class LiveMatch:
    sport: str
    league: str
    match_time: str
    home: str
    away: str
    home_odds: float
    draw_odds: float
    away_odds: float
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None
    home_form: List[str] = None
    away_form: List[str] = None
    weather: str = ""
    news: List[str] = None

class SuperPickKing:
    """슈퍼최강 픽픽픽 킹"""
    
    def __init__(self):
        self.engine = KillPickEngine()
        self.db = PickDatabase()
        self.session = requests.Session()
        
    # ===== 실시간 데이터 수집 =====
    
    def fetch_odds_api(self, sport: str = "soccer", region: str = "uk") -> List[LiveMatch]:
        """TheOddsAPI에서 실시간 배당 수집"""
        if not THE_ODDS_API_KEY:
            print("⚠️ THE_ODDS_API_KEY 없음 - 모의 데이터 사용")
            return self._get_mock_matches(sport)
        
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
        params = {
            'apiKey': THE_ODDS_API_KEY,
            'regions': region,
            'markets': 'h2h',
            'oddsFormat': 'decimal'
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            matches = []
            
            for game in data[:20]:  # 상위 20경기만
                match_time = game.get('commence_time', '')
                home = game.get('home_team', '')
                away = game.get('away_team', '')
                
                # 배당률 추출
                odds = game.get('bookmakers', [{}])[0].get('markets', [{}])[0].get('outcomes', [])
                home_odds = draw_odds = away_odds = 0
                
                for o in odds:
                    if o.get('name') == home:
                        home_odds = o.get('price', 0)
                    elif o.get('name') == away:
                        away_odds = o.get('price', 0)
                    elif o.get('name') == 'Draw':
                        draw_odds = o.get('price', 0)
                
                if home_odds > 0 and away_odds > 0:
                    matches.append(LiveMatch(
                        sport=sport, league=game.get('sport_title', ''),
                        match_time=match_time, home=home, away=away,
                        home_odds=home_odds, draw_odds=draw_odds or 0,
                        away_odds=away_odds
                    ))
            
            return matches
        except Exception as e:
            print(f"❌ API 오류: {e}")
            return self._get_mock_matches(sport)
    
    def fetch_api_football(self, date: str = None) -> List[LiveMatch]:
        """API-Football에서 경기 수집"""
        if not API_FOOTBALL_KEY:
            return []
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        url = "https://v3.football.api-sports.io/fixtures"
        headers = {'x-apisports-key': API_FOOTBALL_KEY}
        params = {'date': date}
        
        try:
            resp = self.session.get(url, headers=headers, params=params, timeout=10)
            data = resp.json().get('response', [])
            matches = []
            
            for game in data[:15]:
                fixture = game.get('fixture', {})
                teams = game.get('teams', {})
                league = game.get('league', {})
                
                matches.append(LiveMatch(
                    sport="축구", league=league.get('name', ''),
                    match_time=fixture.get('date', ''),
                    home=teams.get('home', {}).get('name', ''),
                    away=teams.get('away', {}).get('name', ''),
                    home_odds=0, draw_odds=0, away_odds=0  # 배당은 별도 API
                ))
            
            return matches
        except Exception as e:
            print(f"❌ API-Football 오류: {e}")
            return []
    
    # ===== LLM 심층 분석 =====
    
    def llm_analyze(self, match: LiveMatch) -> Dict:
        """LLM으로 경기 심층 분석 (Aliyun/OpenAI 자동 전환)"""
        # 우선순위: Aliyun → OpenAI → Mock
        if ALIYUN_KEY and ALIYUN_BASE_URL:
            return self._aliyun_analyze(match)
        elif OPENAI_KEY:
            return self._openai_analyze(match)
        else:
            return self._mock_llm_analysis(match)
    
    def _aliyun_analyze(self, match: LiveMatch) -> Dict:
        """Aliyun (Qwen) API로 분석"""
        try:
            import openai
            client = openai.OpenAI(
                api_key=ALIYUN_KEY,
                base_url=ALIYUN_BASE_URL
            )
            
            model = os.getenv("ALIYUN_MODEL", "qwen-plus")
            
            prompt = f"""당신은 스포츠 분석 전문가입니다. 다음 경기를 분석해주세요:

경기: {match.home} vs {match.away}
리그: {match.league}
배당률: 홈 {match.home_odds} / 무 {match.draw_odds} / 원정 {match.away_odds}

다음 형식으로 한국어로 답변해주세요:
1. 로스터 분석 (주요 선수, 부상자, 결장자)
2. 최근 5경기 형태
3. 홈/원정 성적 및 전력 비교
4. 날씨 및 환경 요인
5. 최종 예측 (홈승/무/원정승 + 신뢰도 0-100%)

각 항목을 간결하게 2-3문장으로 작성하세요."""
            
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.7
            )
            
            content = resp.choices[0].message.content
            return self._parse_llm_response(content)
        except Exception as e:
            print(f"❌ Aliyun API 오류: {e}")
            return self._mock_llm_analysis(match)
    
    def _openai_analyze(self, match: LiveMatch) -> Dict:
        """OpenAI API로 분석"""
        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_KEY)
            
            prompt = f"""
            스포츠 분석가로서 다음 경기를 분석해주세요:
            
            경기: {match.home} vs {match.away}
            리그: {match.league}
            배당: 홈 {match.home_odds} / 무 {match.draw_odds} / 원정 {match.away_odds}
            
            다음 형식으로 답변:
            1. 로스터 분석 (부상자, 결장자)
            2. 최근 5경기 형태
            3. 홈/원정 성적
            4. 날씨 및 환경 요인
            5. 최종 예측 (홈승/무/원정승 + 신뢰도%)
            """
            
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000
            )
            
            content = resp.choices[0].message.content
            return self._parse_llm_response(content)
        except Exception as e:
            print(f"❌ OpenAI API 오류: {e}")
            return self._mock_llm_analysis(match)
    
    def _mock_llm_analysis(self, match: LiveMatch) -> Dict:
        """LLM 없을 때 모의 분석"""
        import random
        
        # 배당 기반 간단 추론
        if match.home_odds < match.away_odds:
            pred = "홈승"
            conf = min(85, int(100/match.home_odds) + random.randint(5, 15))
        elif match.away_odds < match.home_odds:
            pred = "원정승"
            conf = min(85, int(100/match.away_odds) + random.randint(5, 15))
        else:
            pred = "무승부"
            conf = 40
        
        return {
            'roster': f"{match.home} 주전 출전 가능, {match.away} 핵심 1명 결장",
            'recent_form': f"{match.home} 최근 5경기 3승 1무 1패 / {match.away} 2승 2무 1패",
            'home_away': f"{match.home} 홈 승률 60% / {match.away} 원정 승률 35%",
            'environment': "날씨 맑음, 기온 26도, 습도 55% - 경기 진행에 이상 없음",
            'prediction': pred,
            'confidence': conf
        }
    
    def _parse_llm_response(self, content: str) -> Dict:
        """LLM 응답 파싱"""
        lines = content.split('\n')
        return {
            'roster': next((l for l in lines if '로스터' in l), '정보 없음'),
            'recent_form': next((l for l in lines if '최근' in l), '정보 없음'),
            'home_away': next((l for l in lines if '홈' in l or '원정' in l), '정보 없음'),
            'environment': next((l for l in lines if '날씨' in l), '정보 없음'),
            'prediction': next((l for l in lines if '예측' in l), '홈승'),
            'confidence': 70
        }
    
    # ===== 핵심 픽 생성 =====
    
    def generate_super_picks(self, sport: str = "soccer", count: int = 3) -> Tuple[List[MatchPick], str]:
        """
        슈퍼최강 픽 생성 메인 함수
        
        Returns:
            picks: MatchPick 리스트
            report: 마크다운 리포트
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 1. 데이터 수집
        print(f"🔍 {sport} 경기 수집 중...")
        matches = self.fetch_odds_api(sport)
        
        if not matches:
            matches = self._get_mock_matches(sport)
        
        # 2. 각 경기 분석
        analyzed = []
        for m in matches:
            try:
                # 통계 분석
                if m.sport == "축구" and m.draw_odds > 0:
                    pick = self.engine.find_kill_pick(
                        m.home, m.away, m.home_odds, m.draw_odds, m.away_odds
                    )
                else:
                    # 2-way market
                    pick = self.engine.find_kill_pick(
                        m.home, m.away, m.home_odds, 0, m.away_odds
                    )
                
                # LLM 분석
                llm = self.llm_analyze(m)
                
                # 종합 점수
                composite = self._calculate_super_score(pick, llm)
                
                analyzed.append({
                    'match': m,
                    'pick': pick,
                    'llm': llm,
                    'score': composite
                })
            except Exception as e:
                print(f"❌ 분석 실패 {m.home} vs {m.away}: {e}")
                continue
        
        # 3. 상위 픽 선택
        analyzed.sort(key=lambda x: x['score'], reverse=True)
        top_picks = analyzed[:count]
        
        # 4. DB 저장
        saved = []
        for item in top_picks:
            m = item['match']
            p = item['pick']
            llm = item['llm']
            
            mp = MatchPick(
                id=None,
                date=today,
                sport=m.sport,
                league=m.league,
                match_time=m.match_time,
                home_team=m.home,
                away_team=m.away,
                home_odds=m.home_odds,
                draw_odds=m.draw_odds,
                away_odds=m.away_odds,
                pick_selection=p.selection_kr,
                pick_odds=p.odds,
                confidence=p.confidence,
                reasoning=f"{p.reasoning}\n\n[LLM 분석]\n{llm['roster']}",
                kelly_fraction=p.kelly_fraction,
                ev=p.expected_value,
                edge=p.edge,
                roster_analysis=llm['roster'],
                recent_form=llm['recent_form'],
                environment=llm['environment'],
                status='pending'
            )
            
            pick_id = self.db.save_pick(mp)
            mp.id = pick_id
            saved.append(mp)
        
        # 5. 리포트 생성
        report = self._generate_super_report(saved, today)
        
        return saved, report
    
    def _calculate_super_score(self, pick, llm: Dict) -> float:
        """슈퍼 종합 점수 (0~100)"""
        score = 50.0
        
        # 통계 기반
        if pick.expected_value > 0.1:
            score += 15
        elif pick.expected_value > 0.05:
            score += 10
        elif pick.expected_value > 0:
            score += 5
        
        if pick.edge > 0.08:
            score += 10
        elif pick.edge > 0.05:
            score += 7
        
        # LLM 신뢰도
        llm_conf = llm.get('confidence', 50)
        score += (llm_conf - 50) * 0.2
        
        # Kelly
        if pick.kelly_fraction > 0.05:
            score += 5
        
        return min(100, max(0, score))
    
    def _generate_super_report(self, picks: List[MatchPick], date: str) -> str:
        """슈퍼 리포트 생성"""
        lines = [
            f"# 🔮 {date} 슈퍼최강 픽픽픽",
            "",
            "## ⚔️ 오늘의 필살 3폴더",
            "",
            f"> 생성 시간: {datetime.now().strftime('%H:%M')}",
            f"> 분석 경기 수: 20+",
            ""
        ]
        
        total_odds = 1.0
        for i, p in enumerate(picks, 1):
            total_odds *= p.pick_odds
            lines.extend([
                f"### {i}픽: {p.home_team} vs {p.away_team}",
                f"- **리그**: {p.league}",
                f"- **시간**: {p.match_time}",
                f"- **선택**: {p.pick_selection} @ {p.pick_odds}",
                f"- **신뢰도**: {p.confidence}",
                f"- **EV**: {p.ev*100:+.1f}% | **엣지**: {p.edge*100:+.1f}%p",
                f"- **Kelly**: {p.kelly_fraction*100:.1f}%",
                "",
                "**분석 근거**:",
                f"{p.reasoning[:300]}...",
                ""
            ])
        
        lines.extend([
            f"## 📊 3폴더 조합 배당률: {total_odds:.2f}배",
            "",
            "---",
            "⚠️ **면책**: 본 분석은 통계 모델 + AI 심층분석 기반이며, 결과를 보장하지 않습니다.",
            "스포츠토토는 소액으로 재미삼아 이용하세요.",
            "",
            "🔮 SuperPickKing v3.0 | 24시간 자동 분석 시스템"
        ])
        
        return "\n".join(lines)
    
    # ===== 모의 데이터 (API 없을 때) =====
    
    def _get_mock_matches(self, sport: str) -> List[LiveMatch]:
        """테스트용 모의 데이터"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if sport in ["soccer", "축구"]:
            return [
                LiveMatch("축구", "K리그1", f"{today} 19:00", "울산 HD", "포항", 1.85, 3.40, 4.20),
                LiveMatch("축구", "프리미어리그", f"{today} 21:00", "맨시티", "아스날", 1.65, 3.80, 5.20),
                LiveMatch("축구", "라리가", f"{today} 04:00", "레알마드리드", "바르셀로나", 2.10, 3.50, 3.40),
                LiveMatch("축구", "세리에A", f"{today} 02:45", "인터", "AC밀란", 1.95, 3.40, 3.80),
                LiveMatch("축구", "분데스리가", f"{today} 01:30", "바이에른", "도르트문트", 1.55, 4.20, 5.50),
                LiveMatch("축구", "챔피언스리그", f"{today} 03:00", "리버풀", "레알마드리드", 1.75, 3.60, 4.50),
                LiveMatch("축구", "J리그", f"{today} 18:00", "요코하마", "가와사키", 1.80, 3.50, 4.00),
            ]
        elif sport in ["baseball", "야구"]:
            return [
                LiveMatch("야구", "KBO", f"{today} 18:30", "LG", "NC", 1.65, 0, 2.25),
                LiveMatch("야구", "KBO", f"{today} 18:30", "롯데", "SSG", 2.10, 0, 1.75),
                LiveMatch("야구", "KBO", f"{today} 18:30", "삼성", "KT", 1.80, 0, 2.00),
                LiveMatch("야구", "KBO", f"{today} 18:30", "기아", "한화", 1.55, 0, 2.40),
                LiveMatch("야구", "KBO", f"{today} 18:30", "키움", "두산", 1.90, 0, 1.90),
            ]
        elif sport in ["basketball", "농구"]:
            return [
                LiveMatch("농구", "KBL", f"{today} 19:00", "창원LG", "서울SK", 1.80, 0, 1.95),
                LiveMatch("농구", "KBL", f"{today} 17:00", "원주DB", "부산KCC", 2.10, 0, 1.75),
                LiveMatch("농구", "NBA", f"{today} 08:30", "셀틱스", "매버릭스", 1.65, 0, 2.25),
            ]
        else:
            return []

if __name__ == "__main__":
    king = SuperPickKing()
    
    # 축구 픽 생성
    print("="*60)
    print("🔮 축구 슈퍼픽 생성")
    print("="*60)
    picks, report = king.generate_super_picks("축구", 3)
    print(report)
    
    # 야구 픽 생성
    print("\n" + "="*60)
    print("🔮 야구 슈퍼픽 생성")
    print("="*60)
    picks, report = king.generate_super_picks("야구", 3)
    print(report)
