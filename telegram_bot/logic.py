"""
필살승부 로직 - 최고의 픽 하나만 추천
가장 확실한 승부를 골라내는 알고리즘
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class KillPick:
    """필살 픽 결과"""
    match: str
    selection: str           # 'home', 'draw', 'away'
    selection_kr: str        # '홈승', '무승부', '원정승'
    odds: float
    model_prob: float        # 우리 모델의 예측 확률
    implied_prob: float      # 배당률이 암시하는 확률
    edge: float              # 모델 - 암시확률
    expected_value: float    # 기대수익률
    kelly_fraction: float    # Kelly Criterion 비율
    confidence: str          # '매우 높음', '높음', '보통', '낮음'
    reasoning: str           # 추천 근거


class KillPickEngine:
    """
    필살승부 엔진
    - Poisson 기반 득점 예측
    - 배당률 비교로 Value Bet 탐지
    - Kelly Criterion 최적화
    - 가장 확실한 1개 픽만 반환
    """
    
    def __init__(self, random_seed: int = 42):
        self.rng = np.random.RandomState(random_seed)
    
    def estimate_poisson_probs(self, home_xg: float, away_xg: float,
                               n_simulations: int = 5000) -> Dict[str, float]:
        """
        Poisson 분포 기반 승무패 확률 계산
        
        Args:
            home_xg: 홈팀 기대 득점 (expected goals)
            away_xg: 원정팀 기대 득점
        """
        home_goals = self.rng.poisson(home_xg, n_simulations)
        away_goals = self.rng.poisson(away_xg, n_simulations)
        
        home_wins = np.sum(home_goals > away_goals)
        draws = np.sum(home_goals == away_goals)
        away_wins = np.sum(home_goals < away_goals)
        
        return {
            'home': home_wins / n_simulations,
            'draw': draws / n_simulations,
            'away': away_wins / n_simulations
        }
    
    def calculate_implied_probs(self, home_odds: float, draw_odds: float,
                                away_odds: float) -> Dict[str, float]:
        """
        배당률 → 무배당 확률 (vig 제거)
        2-way market (야구/농구/테니스): draw_odds = 0 or None
        """
        raw_home = 1 / home_odds
        raw_away = 1 / away_odds
        
        # 3-way market (축구 등)
        if draw_odds and draw_odds > 0:
            raw_draw = 1 / draw_odds
            total = raw_home + raw_draw + raw_away
            return {
                'home': raw_home / total,
                'draw': raw_draw / total,
                'away': raw_away / total
            }
        
        # 2-way market (야구/농구/테니스 등)
        total = raw_home + raw_away
        return {
            'home': raw_home / total,
            'draw': 0.0,
            'away': raw_away / total
        }
    
    def calculate_kelly(self, prob: float, odds: float,
                       fraction: float = 0.25) -> float:
        """
        Fractional Kelly Criterion
        f* = (bp - q) / b
        """
        b = odds - 1
        q = 1 - prob
        
        if b <= 0:
            return 0
        
        kelly = (b * prob - q) / b
        return max(0, kelly * fraction)
    
    def find_kill_pick(self, home_team: str, away_team: str,
                      home_odds: float, draw_odds: float, away_odds: float,
                      home_xg: Optional[float] = None,
                      away_xg: Optional[float] = None) -> KillPick:
        """
        필살승부 - 최고의 픽 하나만 반환
        
        Args:
            home_team: 홈팀 이름
            away_team: 원정팀 이름
            home_odds, draw_odds, away_odds: 배당률
            home_xg, away_xg: 기대 득점 (None이면 배당률 역산)
        """
        # 1. 모델 확률 계산
        if home_xg is None or away_xg is None:
            # 배당률 역산 (bookmaker 기준) + 보정
            implied = self.calculate_implied_probs(home_odds, draw_odds, away_odds)
            # Bookmaker는 보통 실제 확률보다 2~5% 낮게 설정하므로 보정
            home_xg = implied['home'] * 2.8
            away_xg = implied['away'] * 2.5
        
        model_probs = self.estimate_poisson_probs(home_xg, away_xg)
        
        # 2. 배당률 암시확률
        implied_probs = self.calculate_implied_probs(home_odds, draw_odds, away_odds)
        
        # 3. 각 결과별 분석
        outcomes = {
            'home': {'odds': home_odds, 'name_kr': '홈승', 'xg': home_xg},
            'away': {'odds': away_odds, 'name_kr': '원정승', 'xg': away_xg}
        }
        
        # 3-way market only if draw_odds exists and > 0
        if draw_odds and draw_odds > 0:
            outcomes['draw'] = {'odds': draw_odds, 'name_kr': '무승부', 'xg': 0}
        
        picks = []
        for key, info in outcomes.items():
            model_p = model_probs[key]
            implied_p = implied_probs[key]
            edge = model_p - implied_p
            ev = (model_p * info['odds']) - 1
            kelly = self.calculate_kelly(model_p, info['odds'])
            
            # 신뢰도 판정
            if edge > 0.08 and ev > 0.15:
                confidence = '매우 높음 🔥'
            elif edge > 0.05 and ev > 0.08:
                confidence = '높음 ✅'
            elif edge > 0.02 and ev > 0.03:
                confidence = '보통 ⚠️'
            else:
                confidence = '낮음 ❌'
            
            picks.append({
                'selection': key,
                'selection_kr': info['name_kr'],
                'odds': info['odds'],
                'model_prob': model_p,
                'implied_prob': implied_p,
                'edge': edge,
                'ev': ev,
                'kelly': kelly,
                'confidence': confidence
            })
        
        # 4. 최고 픽 선정 (EV 기준, edge가 양수인 것 중)
        valid_picks = [p for p in picks if p['edge'] > 0]
        
        if valid_picks:
            best = max(valid_picks, key=lambda x: x['ev'])
        else:
            # 양수 edge 없으면 그냥 확률 가장 높은 것
            best = max(picks, key=lambda x: x['model_prob'])
        
        # 5. 근거 생성
        if best['edge'] > 0:
            reasoning = (
                f"모델 예측 확률({best['model_prob']*100:.1f}%)이 "
                f"배당률 암시확률({best['implied_prob']*100:.1f}%)보다 "
                f"{best['edge']*100:.1f}%p 높습니다. "
                f"기대수익률 +{best['ev']*100:.1f}%."
            )
        else:
            reasoning = (
                f"모든 결과가 공정 배당률 이하로 예측됩니다. "
                f"가장 확률 높은 결과는 {best['selection_kr']}({best['model_prob']*100:.1f}%)이나 "
                f"가치 배팅 기회는 없습니다."
            )
        
        return KillPick(
            match=f"{home_team} vs {away_team}",
            selection=best['selection'],
            selection_kr=best['selection_kr'],
            odds=best['odds'],
            model_prob=best['model_prob'],
            implied_prob=best['implied_prob'],
            edge=best['edge'],
            expected_value=best['ev'],
            kelly_fraction=best['kelly'],
            confidence=best['confidence'],
            reasoning=reasoning
        )
    
    def generate_all_strategies(self, home_team: str, away_team: str,
                               home_odds: float, draw_odds: float, away_odds: float,
                               home_xg: Optional[float] = None,
                               away_xg: Optional[float] = None) -> Dict[str, dict]:
        """
        세 가지 전략 모두 생성
        """
        if home_xg is None or away_xg is None:
            implied = self.calculate_implied_probs(home_odds, draw_odds, away_odds)
            home_xg = implied['home'] * 2.8
            away_xg = implied['away'] * 2.5
        
        model_probs = self.estimate_poisson_probs(home_xg, away_xg)
        implied_probs = self.calculate_implied_probs(home_odds, draw_odds, away_odds)
        
        strategies = {
            'conservative': {'name': '신중 🛡️', 'min_prob': 0.55, 'min_edge': 0.05},
            'balanced': {'name': '적정 ⚖️', 'min_prob': 0.45, 'min_edge': 0.03},
            'aggressive': {'name': '공격 ⚔️', 'min_prob': 0.35, 'min_edge': 0.01}
        }
        
        results = {}
        for key, config in strategies.items():
            picks = []
            for outcome, name_kr in [('home', '홈승'), ('draw', '무승부'), ('away', '원정승')]:
                odds = {'home': home_odds, 'draw': draw_odds, 'away': away_odds}[outcome]
                mp = model_probs[outcome]
                ip = implied_probs[outcome]
                edge = mp - ip
                ev = (mp * odds) - 1
                
                if mp >= config['min_prob'] and edge >= config['min_edge']:
                    picks.append({
                        'selection': name_kr,
                        'odds': odds,
                        'prob': mp,
                        'edge': edge,
                        'ev': ev
                    })
            
            picks.sort(key=lambda x: x['ev'], reverse=True)
            results[key] = {
                'name': config['name'],
                'picks': picks[:2],  # 상위 2개만
                'recommendation': picks[0]['selection'] if picks else '조건 미충족'
            }
        
        return results


if __name__ == '__main__':
    engine = KillPickEngine()
    
    # 테스트: 한국 vs 체코
    pick = engine.find_kill_pick(
        "Korea", "Czech",
        home_odds=2.10, draw_odds=3.30, away_odds=3.60
    )
    
    print(f"🏆 필살승부: {pick.match}")
    print(f"추천: {pick.selection_kr} @ {pick.odds}")
    print(f"확률: 모델 {pick.model_prob*100:.1f}% vs 배당 {pick.implied_prob*100:.1f}%")
    print(f"엣지: +{pick.edge*100:.1f}%p | EV: {pick.expected_value:+.1f}")
    print(f"Kelly: {pick.kelly_fraction:.2f}")
    print(f"신뢰도: {pick.confidence}")
    print(f"근거: {pick.reasoning}")
