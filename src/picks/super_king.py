#!/usr/bin/env python3
"""
슈퍼픽킹 - 매일 자동 픽 생성 시스템
OpenClaw Cron용
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict

from telegram_bot.logic import KillPickEngine
from src.picks.database import PickDatabase, MatchPick

# LLM 분석 (선택적)
try:
    import openai
    OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
except:
    OPENAI_KEY = ""

class SuperPickKing:
    """슈퍼 최강 픽픽픽 시스템"""
    
    def __init__(self):
        self.engine = KillPickEngine()
        self.db = PickDatabase()
    
    def analyze_match_deep(self, match_data: dict) -> dict:
        """심층 분석: 배당 + 로스터 + 환경"""
        home = match_data['home']
        away = match_data['away']
        ho = match_data['home_odds']
        do = match_data.get('draw_odds', 3.0)
        ao = match_data['away_odds']
        sport = match_data.get('sport', '축구')
        league = match_data.get('league', '')
        
        # 1. 기본 통계 분석
        pick = self.engine.find_kill_pick(home, away, ho, do, ao)
        
        # 2. 로스터 분석 (모의 - 실제로는 API에서 가져와야 함)
        roster_analysis = self._analyze_roster(home, away, sport)
        
        # 3. 최근 형태 분석
        recent_form = self._analyze_recent_form(home, away, sport)
        
        # 4. 환경 요인
        environment = self._analyze_environment(match_data)
        
        # 5. 종합 점수
        composite_score = self._calculate_composite_score(pick, roster_analysis, recent_form, environment)
        
        return {
            'pick': pick,
            'roster_analysis': roster_analysis,
            'recent_form': recent_form,
            'environment': environment,
            'composite_score': composite_score,
            'match_data': match_data
        }
    
    def _analyze_roster(self, home: str, away: str, sport: str) -> str:
        """로스터 분석 (실제로는 API 연동 필요)"""
        # 모의 분석 - 실제 구현 시 API-Football 등 연동
        analyses = {
            '축구': f"""
            {home}: 주요 선수 출전 가능 (부상자 1명)
            {away}: 핵심 미드필더 결장, 수비 라인 재정비 중
            홈팀 벤치 뎁스 우세, 원정팀 주전 2명 부상
            """,
            '농구': f"""
            {home}: 시즌 평균 105.3득점, 최근 5경기 4승
            {away}: 원정 경기 약세, 주요 가드 부상 의심
            """,
            '야구': f"""
            {home}: 선발투수 ERA 3.45, 최근 등판 QS 2회
            {away}: 타선 뜨거움 (최근 5경기 타율 .312)
            불펜 피로도: 홈팀 우세
            """,
        }
        return analyses.get(sport, f"{home} vs {away} 로스터 분석 데이터 수집 중...")
    
    def _analyze_recent_form(self, home: str, away: str, sport: str) -> str:
        """최근 형태 분석"""
        # 모의 데이터
        forms = [
            f"{home}: 최근 5경기 3승 1무 1패 (홈 3연승)",
            f"{away}: 최근 5경기 2승 1무 2패 (원정 1승 2패)",
            f"맞대결: 최근 3회전 {home} 2승 1패",
            f"{home} 홈 성적: 시즌 홈 승률 65%",
            f"{away} 원정 성적: 시즌 원정 승률 38%"
        ]
        return "\n".join(forms)
    
    def _analyze_environment(self, match_data: dict) -> str:
        """환경 요인 분석"""
        factors = []
        
        # 날씨 (축구/야구)
        if match_data.get('sport') in ['축구', '야구']:
            factors.append("🌤️ 날씨: 맑음, 기온 24°C, 습도 60% - 경기 진행에 이상 없음")
        
        # 홈 어드밴티지
        factors.append(f"🏟️ 홈 어드밴티지: {match_data['home']} 홈 경기장")
        
        # 일정
        factors.append("📅 일정: 홈팀 3일 휴식, 원정팀 2일 휴식 - 홈팀 체력 우세")
        
        # 동기부여
        factors.append("🔥 동기부여: 홈팀 상위권 진출 중요 경기, 원정팀 중위권 유지")
        
        return "\n".join(factors)
    
    def _calculate_composite_score(self, pick, roster: str, form: str, env: str) -> float:
        """종합 점수 계산 (0~100)"""
        score = 50.0
        
        # EV 기반
        if pick.expected_value > 0.1:
            score += 20
        elif pick.expected_value > 0.05:
            score += 10
        elif pick.expected_value > 0:
            score += 5
        else:
            score -= 10
        
        # 엣지 기반
        if pick.edge > 0.1:
            score += 15
        elif pick.edge > 0.05:
            score += 10
        elif pick.edge > 0:
            score += 5
        
        # 신뢰도
        if "매우 높음" in pick.confidence:
            score += 15
        elif "높음" in pick.confidence:
            score += 10
        elif "보통" in pick.confidence:
            score += 5
        
        # Kelly
        if pick.kelly_fraction > 0.05:
            score += 5
        
        return min(100, max(0, score))
    
    def generate_daily_picks(self, matches: List[dict], sport: str = "축구") -> List[MatchPick]:
        """당일 최고의 픽 3개 생성"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 모든 경기 심층 분석
        analyzed = []
        for match in matches:
            try:
                result = self.analyze_match_deep(match)
                analyzed.append(result)
            except Exception as e:
                print(f"분석 실패 {match}: {e}")
                continue
        
        # 종합 점수 기준 정렬
        analyzed.sort(key=lambda x: x['composite_score'], reverse=True)
        
        # 상위 3개 선택
        top3 = analyzed[:3]
        saved_picks = []
        
        for item in top3:
            pick = item['pick']
            match = item['match_data']
            
            mp = MatchPick(
                id=None,
                date=today,
                sport=sport,
                league=match.get('league', ''),
                match_time=match.get('match_time', ''),
                home_team=match['home'],
                away_team=match['away'],
                home_odds=match['home_odds'],
                draw_odds=match.get('draw_odds', 3.0),
                away_odds=match['away_odds'],
                pick_selection=pick.selection_kr,
                pick_odds=pick.odds,
                confidence=pick.confidence,
                reasoning=pick.reasoning,
                kelly_fraction=pick.kelly_fraction,
                ev=pick.expected_value,
                edge=pick.edge,
                roster_analysis=item['roster_analysis'],
                recent_form=item['recent_form'],
                environment=item['environment'],
                status='pending'
            )
            
            pick_id = self.db.save_pick(mp)
            mp.id = pick_id
            saved_picks.append(mp)
        
        # 3픽 조합 저장
        if len(saved_picks) == 3:
            combo_odds = saved_picks[0].pick_odds * saved_picks[1].pick_odds * saved_picks[2].pick_odds
            avg_conf = sum([1 if '높음' in p.confidence else 0.5 for p in saved_picks]) / 3
            conf_str = "높음" if avg_conf > 0.7 else "보통"
            
            self.db.save_daily_combo(
                today, sport,
                [saved_picks[0].id, saved_picks[1].id, saved_picks[2].id],
                combo_odds, conf_str
            )
        
        return saved_picks
    
    def get_pick_report(self, picks: List[MatchPick]) -> str:
        """픽 리포트 생성"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        lines = [
            f"# 🔮 {today} 슈퍼픽킹 리포트",
            "",
            "## ⚔️ 오늘의 필승 3폴더",
            ""
        ]
        
        total_odds = 1.0
        for i, pick in enumerate(picks, 1):
            total_odds *= pick.pick_odds
            lines.extend([
                f"### {i}픽: {pick.home_team} vs {pick.away_team}",
                f"- **선택**: {pick.pick_selection} @ {pick.pick_odds}",
                f"- **신뢰도**: {pick.confidence}",
                f"- **EV**: {pick.ev*100:+.1f}% | **엣지**: {pick.edge*100:+.1f}%p",
                f"- **분석**: {pick.reasoning[:100]}...",
                ""
            ])
        
        lines.extend([
            f"## 📊 조합 배당률: {total_odds:.2f}배",
            "",
            "⚠️ **주의**: 본 분석은 통계적 예측이며, 결과를 보장하지 않습니다.",
            "스포츠토토는 소액으로 재미삼아 이용하세요."
        ])
        
        return "\n".join(lines)

if __name__ == "__main__":
    # 테스트 실행
    king = SuperPickKing()
    
    # 모의 데이터로 테스트
    test_matches = [
        {"home": "울산", "away": "포항", "home_odds": 1.85, "draw_odds": 3.40, "away_odds": 4.20, "sport": "축구", "league": "K리그1", "match_time": "19:00"},
        {"home": "맨시티", "away": "아스날", "home_odds": 1.65, "draw_odds": 3.80, "away_odds": 5.20, "sport": "축구", "league": "프리미어리그", "match_time": "21:00"},
        {"home": "레알마드리드", "away": "바르셀로나", "home_odds": 2.10, "draw_odds": 3.50, "away_odds": 3.40, "sport": "축구", "league": "라리가", "match_time": "04:00"},
    ]
    
    picks = king.generate_daily_picks(test_matches, "축구")
    print(king.get_pick_report(picks))
