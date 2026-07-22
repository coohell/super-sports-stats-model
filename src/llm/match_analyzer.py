"""
LLM 기반 경기 분석기
뉴스 + 통계 데이터를 LLM에게 넘겨 인사이트 생성
"""
import os
from typing import Dict, List, Optional


class MatchAnalyzer:
    """LLM을 활용한 경기 분석"""
    
    def __init__(self, provider: str = "anthropic"):
        self.provider = provider
        self.api_key = os.getenv("ANTHROPIC_API_KEY") if provider == "anthropic" else os.getenv("OPENAI_API_KEY")
        self.model = "claude-3-sonnet-20240229" if provider == "anthropic" else "gpt-4o"
    
    def build_prompt(self, home_team: str, away_team: str,
                    news: Dict, stats: Dict, odds: Dict,
                    simulation: Dict) -> str:
        """
        LLM에 보낼 프롬프트 구성
        """
        # 뉴스 요약
        kr_news = news.get('korean', [])
        en_news = news.get('english', [])
        
        news_summary = ""
        if kr_news:
            news_summary += "\n[한국어 뉴스]\n"
            for i, n in enumerate(kr_news[:5], 1):
                news_summary += f"{i}. {n['title']}\n"
        
        if en_news:
            news_summary += "\n[영어 뉴스]\n"
            for i, n in enumerate(en_news[:5], 1):
                news_summary += f"{i}. {n['title']}\n"
        
        # 통계
        stats_text = f"""
[팀 통계]
홈팀 ({home_team}):
- 평균 득점: {stats.get('home', {}).get('avg_goals_scored', 'N/A')}
- 평균 실점: {stats.get('home', {}).get('avg_goals_conceded', 'N/A')}
- 최근 폼: {stats.get('home', {}).get('recent_form', [])}
- 점유율: {stats.get('home', {}).get('avg_possession', 'N/A')}%

원정팀 ({away_team}):
- 평균 득점: {stats.get('away', {}).get('avg_goals_scored', 'N/A')}
- 평균 실점: {stats.get('away', {}).get('avg_goals_conceded', 'N/A')}
- 최근 폼: {stats.get('away', {}).get('recent_form', [])}
- 점유율: {stats.get('away', {}).get('avg_possession', 'N/A')}%
"""
        
        # 배당률
        odds_text = f"""
[배당률]
홈승: {odds.get('home_win', 'N/A')}
무승부: {odds.get('draw', 'N/A')}
원정승: {odds.get('away_win', 'N/A')}
"""
        
        # 시뮬레이션
        sim_text = f"""
[Monte Carlo 시뮬레이션 (1000회)]
홈승 확률: {simulation.get('home_prob', 0)*100:.1f}%
무승부 확률: {simulation.get('draw_prob', 0)*100:.1f}%
원정승 확률: {simulation.get('away_prob', 0)*100:.1f}%
예상 스코어 TOP3: {dict(list(simulation.get('top_scores', {}).items())[:3])}
"""
        
        prompt = f"""당신은 스포츠 데이터 분석 전문가입니다. 다음 정보를 바탕으로 경기를 분석해주세요.

{stats_text}
{odds_text}
{sim_text}
{news_summary}

다음 형식으로 분석을 작성해주세요:

1. 핵심 요약 (3줄 이내)
2. 홈팀 강점/약점
3. 원정팀 강점/약점
4. 결정적 변수 (이 경기를 가를 핵심 포인트)
5. 최종 예측 (홈승/무/원정승 중 선택 + 신뢰도 %)
6. 주의사항 (놓치기 쉬운 리스크)

분석은 사실 기반으로, 과장 없이 작성해주세요."""
        
        return prompt
    
    def analyze(self, prompt: str) -> str:
        """
        LLM API 호출
        (API 키 없으면 더미 응답 반환)
        """
        if not self.api_key:
            return "[LLM API 키가 설정되지 않음. ANTHROPIC_API_KEY 또는 OPENAI_API_KEY를 .env에 설정하세요.]"
        
        try:
            if self.provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=self.api_key)
                
                response = client.messages.create(
                    model=self.model,
                    max_tokens=1500,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
                
            else:
                import openai
                client = openai.OpenAI(api_key=self.api_key)
                
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1500
                )
                return response.choices[0].message.content
                
        except Exception as e:
            return f"[LLM 분석 오류: {e}]"
    
    def analyze_match(self, home_team: str, away_team: str,
                     news: Dict, stats: Dict, odds: Dict,
                     simulation: Dict) -> str:
        """
        전체 분석 파이프라인
        """
        prompt = self.build_prompt(home_team, away_team, news, stats, odds, simulation)
        return self.analyze(prompt)


if __name__ == '__main__':
    analyzer = MatchAnalyzer()
    
    test_news = {
        'korean': [{'title': '한국, 주전 부상 속 출전'}],
        'english': [{'title': 'Korea faces injury crisis before match'}]
    }
    
    test_stats = {
        'home': {'avg_goals_scored': 1.5, 'avg_goals_conceded': 1.0, 'recent_form': ['W', 'W', 'D']},
        'away': {'avg_goals_scored': 1.2, 'avg_goals_conceded': 1.3, 'recent_form': ['L', 'D', 'W']}
    }
    
    test_odds = {'home_win': 1.95, 'draw': 3.4, 'away_win': 3.8}
    test_sim = {'home_prob': 0.52, 'draw_prob': 0.28, 'away_prob': 0.20, 'top_scores': {'1-0': 150, '2-1': 120}}
    
    result = analyzer.analyze_match("Korea", "Czech", test_news, test_stats, test_odds, test_sim)
    print(result)
