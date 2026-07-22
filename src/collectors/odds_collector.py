"""
배당률 수집기 - 여러 소스에서 배당률 데이터 수집
"""
import requests
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class OddsData:
    """배당률 데이터 클래스"""
    match_id: str
    home_team: str
    away_team: str
    match_time: str
    
    # 1X2 (승무패)
    home_win: Optional[float] = None
    draw: Optional[float] = None
    away_win: Optional[float] = None
    
    # 아시안 핸디캡
    asian_handicap: Optional[Dict] = None  # {'line': -0.5, 'home': 1.95, 'away': 1.85}
    
    # 언더오버
    over_under: Optional[Dict] = None  # {'line': 2.5, 'over': 1.90, 'under': 1.90}
    
    # 언제 수집했는지
    collected_at: str = ""
    source: str = ""


class OddsCollector:
    """배당률 수집기"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_odds_from_api_football(self, fixture_id: int) -> Optional[OddsData]:
        """
        API-Football에서 배당률 가져오기
        (무료 티어: 하루 100 requests)
        """
        if not self.api_key:
            return None
            
        url = f"https://v3.football.api-sports.io/odds?fixture={fixture_id}"
        headers = {
            'x-rapidapi-key': self.api_key,
            'x-rapidapi-host': 'v3.football.api-sports.io'
        }
        
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            data = resp.json()
            
            if data.get('results', 0) == 0:
                return None
            
            odds_info = data['response'][0]
            fixture = odds_info.get('fixture', {})
            
            odds_data = OddsData(
                match_id=str(fixture_id),
                home_team="",
                away_team="",
                match_time=fixture.get('date', ''),
                collected_at=datetime.now().isoformat(),
                source="api-football"
            )
            
            # bookmaker별 배당률 파싱
            for bookmaker in odds_info.get('bookmakers', []):
                for bet in bookmaker.get('bets', []):
                    bet_name = bet.get('name', '')
                    values = bet.get('values', [])
                    
                    if bet_name == 'Match Winner' and not odds_data.home_win:
                        for val in values:
                            if val['value'] == 'Home':
                                odds_data.home_win = float(val['odd'])
                            elif val['value'] == 'Draw':
                                odds_data.draw = float(val['odd'])
                            elif val['value'] == 'Away':
                                odds_data.away_win = float(val['odd'])
                    
                    elif bet_name == 'Asian Handicap':
                        ah_values = {}
                        for val in values:
                            ah_values[val['value']] = float(val['odd'])
                        odds_data.asian_handicap = ah_values
                    
                    elif bet_name == 'Goals Over/Under':
                        ou_values = {}
                        for val in values:
                            ou_values[val['value']] = float(val['odd'])
                        odds_data.over_under = ou_values
            
            return odds_data
            
        except Exception as e:
            print(f"[배당률 수집 오류] {e}")
            return None
    
    def calculate_implied_probabilities(self, odds: OddsData) -> Dict[str, float]:
        """
        배당률 → 무배당 확률 (implied probability) 계산
        """
        probs = {}
        
        if odds.home_win and odds.draw and odds.away_win:
            # 무배당 확률 (vig 제거 전)
            raw_home = 1 / odds.home_win
            raw_draw = 1 / odds.draw
            raw_away = 1 / odds.away_win
            
            # Vig (수수료) 제거 - proportional method
            total = raw_home + raw_draw + raw_away
            
            probs['home'] = round(raw_home / total, 4)
            probs['draw'] = round(raw_draw / total, 4)
            probs['away'] = round(raw_away / total, 4)
        
        return probs
    
    def find_value_bets(self, model_probs: Dict[str, float], 
                       odds: OddsData,
                       threshold: float = 0.05) -> List[Dict]:
        """
        가치 배팅 찾기: 모델 확률 > 배당률 암시확률 + threshold
        """
        value_bets = []
        implied = self.calculate_implied_probabilities(odds)
        
        outcomes = {
            'home': {'odds': odds.home_win, 'prob_key': 'home'},
            'draw': {'odds': odds.draw, 'prob_key': 'draw'},
            'away': {'odds': odds.away_win, 'prob_key': 'away'},
        }
        
        for outcome, info in outcomes.items():
            if info['odds'] and info['prob_key'] in model_probs:
                model_p = model_probs[info['prob_key']]
                implied_p = implied.get(info['prob_key'], 0)
                
                edge = model_p - implied_p
                
                if edge > threshold:
                    expected_value = (model_p * info['odds']) - 1
                    value_bets.append({
                        'outcome': outcome,
                        'odds': info['odds'],
                        'model_probability': model_p,
                        'implied_probability': implied_p,
                        'edge': edge,
                        'expected_value': expected_value
                    })
        
        return sorted(value_bets, key=lambda x: x['edge'], reverse=True)
    
    def compare_odds(self, odds_list: List[OddsData]) -> Dict:
        """
        여러 북메이커 배당률 비교해서 최고 배당률 찾기
        """
        if not odds_list:
            return {}
        
        best = {
            'home_win': {'odds': 0, 'source': ''},
            'draw': {'odds': 0, 'source': ''},
            'away_win': {'odds': 0, 'source': ''},
        }
        
        for o in odds_list:
            if o.home_win and o.home_win > best['home_win']['odds']:
                best['home_win'] = {'odds': o.home_win, 'source': o.source}
            if o.draw and o.draw > best['draw']['odds']:
                best['draw'] = {'odds': o.draw, 'source': o.source}
            if o.away_win and o.away_win > best['away_win']['odds']:
                best['away_win'] = {'odds': o.away_win, 'source': o.source}
        
        return best


class KoreanTotoOdds:
    """한국 스포츠토토(배트맨) 배당률 파싱"""
    
    @staticmethod
    def parse_toto_odds(html_content: str) -> Dict:
        """
        배트맨 웹사이트에서 배당률 파싱
        (스크래핑이 필요한 경우)
        """
        # 배트맨은 웹사이트 구조가 복잡하고 자주 바뀜
        # 여기서는 구조만 잡아둠
        return {
            'note': '배트맨은 수동 확인 권장. 자동화는 정책상 어려움.',
            'url': 'https://www.sportstoto.co.kr/'
        }


if __name__ == '__main__':
    collector = OddsCollector()
    # 테스트용 예시
    test_odds = OddsData(
        match_id="test",
        home_team="Team A",
        away_team="Team B",
        match_time="2024-01-01",
        home_win=2.1,
        draw=3.4,
        away_win=3.5
    )
    
    implied = collector.calculate_implied_probabilities(test_odds)
    print(f"무배당 확률: {implied}")
