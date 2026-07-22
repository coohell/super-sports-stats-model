"""
배팅 전략 엔진
신중 / 적정 / 공격 전략 + 몰빵 방지 + 추천픽
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class BetRecommendation:
    """배팅 추천 결과"""
    strategy: str           # 'conservative', 'balanced', 'aggressive'
    strategy_name: str      # '신중', '적정', '공격'
    
    # 추천 픽
    picks: List[Dict]       # [{'market': '1x2', 'selection': 'home', 'odds': 2.1, 'confidence': 0.65}]
    
    # 분석 요약
    reasoning: str
    total_expected_value: float
    risk_level: str         # 'low', 'medium', 'high'
    
    # 자금 관리
    suggested_stake: float  # 제안 배팅액 (단위: %)
    kelly_fraction: float


class StrategyEngine:
    """전략 엔진"""
    
    STRATEGIES = {
        'conservative': {
            'name': '신중',
            'min_prob': 0.55,
            'max_odds': 2.5,
            'min_ev': 0.02,
            'stake_pct': 0.03,   # 총 자본의 3%
            'description': '확률 높은 것만, 소액 배팅'
        },
        'balanced': {
            'name': '적정',
            'min_prob': 0.42,
            'max_odds': 4.0,
            'min_ev': 0.05,
            'stake_pct': 0.05,   # 총 자본의 5%
            'description': '밸런스 있는 선택, 중간 배팅'
        },
        'aggressive': {
            'name': '공격',
            'min_prob': 0.30,
            'max_odds': 15.0,
            'min_ev': 0.10,
            'stake_pct': 0.08,   # 총 자본의 8%
            'description': '고배당 노림, 고위험 고수익'
        }
    }
    
    def __init__(self, bankroll: float = 100000):
        """
        Args:
            bankroll: 총 배팅 자본 (원)
        """
        self.bankroll = bankroll
    
    def calculate_kelly_criterion(self, probability: float, odds: float,
                                  fraction: float = 0.25) -> float:
        """
        Kelly Criterion 계산 (fractional Kelly)
        
        f* = (bp - q) / b
        b = odds - 1 (순수 배당률)
        p = 승리 확률
        q = 1 - p
        """
        b = odds - 1
        q = 1 - probability
        
        if b <= 0:
            return 0
        
        kelly = (b * probability - q) / b
        kelly = max(0, kelly)  # 음수면 배팅하지 않음
        
        # Fractional Kelly (보수적)
        return kelly * fraction
    
    def evaluate_picks(self, model_probs: Dict[str, float],
                      odds: Dict[str, float],
                      strategy_key: str = 'balanced') -> List[Dict]:
        """
        특정 전략으로 픽 평가
        """
        strategy = self.STRATEGIES[strategy_key]
        picks = []
        
        outcomes = {
            'home': {'prob': model_probs.get('home', 0), 'odds': odds.get('home_win', 0)},
            'draw': {'prob': model_probs.get('draw', 0), 'odds': odds.get('draw', 0)},
            'away': {'prob': model_probs.get('away', 0), 'odds': odds.get('away_win', 0)}
        }
        
        for outcome, data in outcomes.items():
            prob = data['prob']
            odd = data['odds']
            
            if prob < strategy['min_prob'] or odd > strategy['max_odds'] or odd <= 1:
                continue
            
            # Expected Value
            ev = (prob * odd) - 1
            if ev < strategy['min_ev']:
                continue
            
            # Kelly Criterion
            kelly = self.calculate_kelly_criterion(prob, odd)
            stake = self.bankroll * strategy['stake_pct'] * min(kelly * 4, 1)
            
            picks.append({
                'market': '1x2',
                'selection': outcome,
                'odds': odd,
                'probability': prob,
                'expected_value': ev,
                'kelly_fraction': kelly,
                'suggested_stake': round(stake, 0),
                'potential_return': round(stake * odd, 0)
            })
        
        return sorted(picks, key=lambda x: x['expected_value'], reverse=True)
    
    def apply_risk_management(self, all_picks: List[Dict],
                             max_per_match: int = 1) -> List[Dict]:
        """
        몰빵 방지 + 분산 규칙 적용
        """
        if not all_picks:
            return []
        
        # 1. EV 기준 정렬
        sorted_picks = sorted(all_picks, key=lambda x: x['expected_value'], reverse=True)
        
        # 2. 한 경기당 최대 N개
        match_counts = {}
        filtered = []
        
        for pick in sorted_picks:
            match_key = pick.get('match_id', 'unknown')
            match_counts[match_key] = match_counts.get(match_key, 0) + 1
            
            if match_counts[match_key] <= max_per_match:
                filtered.append(pick)
        
        # 3. 총 자본의 20%를 초과하지 않도록 조정
        total_stake = sum(p['suggested_stake'] for p in filtered)
        max_total = self.bankroll * 0.20
        
        if total_stake > max_total:
            ratio = max_total / total_stake
            for pick in filtered:
                pick['suggested_stake'] = round(pick['suggested_stake'] * ratio, 0)
                pick['potential_return'] = round(pick['suggested_stake'] * pick['odds'], 0)
        
        return filtered
    
    def generate_all_strategies(self, model_probs: Dict[str, float],
                               odds: Dict[str, float]) -> Dict[str, BetRecommendation]:
        """
        세 가지 전략 모두 생성
        """
        results = {}
        
        for key, config in self.STRATEGIES.items():
            picks = self.evaluate_picks(model_probs, odds, key)
            picks = self.apply_risk_management(picks)
            
            total_ev = sum(p['expected_value'] for p in picks) / len(picks) if picks else 0
            
            # 리스크 레벨 결정
            if total_ev > 0.1:
                risk = 'high'
            elif total_ev > 0.05:
                risk = 'medium'
            else:
                risk = 'low'
            
            # Kelly
            avg_kelly = np.mean([p['kelly_fraction'] for p in picks]) if picks else 0
            
            # 추천 근거
            if picks:
                top_pick = picks[0]
                reasoning = (
                    f"{top_pick['selection']} 승/배당 {top_pick['odds']} "
                    f"(모델 확률 {top_pick['probability']*100:.1f}%, "
                    f"EV +{top_pick['expected_value']*100:.1f}%)"
                )
            else:
                reasoning = "조건에 맞는 가치 배팅 없음"
            
            results[key] = BetRecommendation(
                strategy=key,
                strategy_name=config['name'],
                picks=picks,
                reasoning=reasoning,
                total_expected_value=total_ev,
                risk_level=risk,
                suggested_stake=sum(p['suggested_stake'] for p in picks),
                kelly_fraction=avg_kelly
            )
        
        return results
    
    def get_best_pick(self, all_strategies: Dict[str, BetRecommendation]) -> Dict:
        """
        모든 전략 중 최고 추천픽 반환
        """
        all_picks = []
        for strat in all_strategies.values():
            for pick in strat.picks:
                pick['strategy'] = strat.strategy_name
                all_picks.append(pick)
        
        if not all_picks:
            return {'message': '추천할 픽이 없습니다. 조건을 완화하거나 다른 경기를 확인하세요.'}
        
        # EV + 확률 종합 점수
        for pick in all_picks:
            pick['score'] = pick['expected_value'] * pick['probability']
        
        best = max(all_picks, key=lambda x: x['score'])
        
        return {
            'best_pick': best,
            'total_picks_considered': len(all_picks),
            'recommendation': f"[{best['strategy']}] {best['selection']} @ {best['odds']}"
        }


if __name__ == '__main__':
    engine = StrategyEngine(bankroll=100000)
    
    model_probs = {'home': 0.55, 'draw': 0.25, 'away': 0.20}
    odds = {'home_win': 1.85, 'draw': 3.5, 'away_win': 4.2}
    
    results = engine.generate_all_strategies(model_probs, odds)
    
    for key, rec in results.items():
        print(f"\n=== {rec.strategy_name} 전략 ===")
        print(f"픽 수: {len(rec.picks)}")
        print(f"평균 EV: {rec.total_expected_value:.3f}")
        print(f"리스크: {rec.risk_level}")
        for p in rec.picks:
            print(f"  → {p['selection']} @ {p['odds']} (EV: {p['expected_value']:+.2f}, 배팅: {p['suggested_stake']:,.0f}원)")
    
    best = engine.get_best_pick(results)
    print(f"\n🏆 최고 추천: {best.get('recommendation', '없음')}")
