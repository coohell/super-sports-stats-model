"""
Monte Carlo 시뮬레이션 엔진
경기 결과를 N번 시뮬레이션하여 확률 분포 생성
"""
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class SimulationResult:
    """시뮬레이션 결과"""
    home_wins: int
    draws: int
    away_wins: int
    total_runs: int
    
    # 스코어 분포
    score_distribution: Dict[str, int]
    
    # 신뢰구간
    confidence_interval: Tuple[float, float]
    
    def get_probabilities(self) -> Dict[str, float]:
        """시뮬레이션 기반 확률 반환"""
        return {
            'home': self.home_wins / self.total_runs,
            'draw': self.draws / self.total_runs,
            'away': self.away_wins / self.total_runs
        }


class MatchSimulator:
    """경기 시뮬레이터 - Poisson 분포 기반"""
    
    def __init__(self, random_seed: int = 42):
        self.rng = np.random.RandomState(random_seed)
    
    def estimate_team_strength(self, team_stats: Dict) -> Tuple[float, float]:
        """
        팀 공격력/수비력 추정
        
        Args:
            team_stats: {
                'avg_goals_scored': 1.5,
                'avg_goals_conceded': 1.2,
                'avg_shots': 12.5,
                'avg_shots_on_target': 4.3,
                'avg_possession': 55.0,
                'recent_form': [W, D, L, W, W]  # 최근 5경기
            }
        """
        # 기본 득점 기대값
        base_attack = team_stats.get('avg_goals_scored', 1.3)
        
        # 슛 정확도 보정
        shots = team_stats.get('avg_shots', 12)
        shots_on_target = team_stats.get('avg_shots_on_target', 4)
        shot_accuracy = shots_on_target / max(shots, 1)
        
        # 점유율 보정 (50% 기준)
        possession = team_stats.get('avg_possession', 50)
        possession_factor = 0.5 + (possession - 50) / 100
        
        # 최근 폼 보정
        form = team_stats.get('recent_form', [])
        form_score = self._calculate_form_score(form)
        
        # 종합 공격력
        attack_strength = base_attack * (0.8 + shot_accuracy * 0.2) * possession_factor * (0.7 + form_score * 0.3)
        
        # 수비력 (실점 기대값)
        defense_weakness = team_stats.get('avg_goals_conceded', 1.3)
        
        return max(attack_strength, 0.3), max(defense_weakness, 0.3)
    
    def _calculate_form_score(self, form: List[str]) -> float:
        """최근 폼을 점수화 (0.0 ~ 1.0)"""
        if not form:
            return 0.5
        
        weights = [0.1, 0.15, 0.2, 0.25, 0.3]  # 최근 경기에 더 높은 가중치
        score_map = {'W': 1.0, 'D': 0.5, 'L': 0.0}
        
        scores = []
        for i, result in enumerate(form[-5:]):
            weight = weights[min(i, len(weights)-1)]
            score = score_map.get(result, 0.5)
            scores.append(score * weight)
        
        return sum(scores) / sum(weights[:len(scores)]) if scores else 0.5
    
    def simulate_match(self, home_stats: Dict, away_stats: Dict, 
                      n_runs: int = 1000) -> SimulationResult:
        """
        몬테카를로 경기 시뮬레이션
        
        Args:
            home_stats: 홈팀 통계
            away_stats: 원정팀 통계
            n_runs: 시뮬레이션 횟수
        """
        home_attack, home_defense = self.estimate_team_strength(home_stats)
        away_attack, away_defense = self.estimate_team_strength(away_stats)
        
        # 홈 어드밴티지
        home_advantage = 1.15
        
        # 기대 득점 (Poisson 파라미터)
        lambda_home = home_attack * (away_defense / 1.3) * home_advantage
        lambda_away = away_attack * (home_defense / 1.3) * 0.95
        
        # 시뮬레이션 실행
        home_goals = self.rng.poisson(lambda_home, n_runs)
        away_goals = self.rng.poisson(lambda_away, n_runs)
        
        # 결과 집계
        home_wins = np.sum(home_goals > away_goals)
        draws = np.sum(home_goals == away_goals)
        away_wins = np.sum(home_goals < away_goals)
        
        # 스코어 분포
        score_dist = {}
        for hg, ag in zip(home_goals, away_goals):
            key = f"{hg}-{ag}"
            score_dist[key] = score_dist.get(key, 0) + 1
        
        # 상위 10개 스코어
        score_dist = dict(sorted(score_dist.items(), 
                                key=lambda x: x[1], reverse=True)[:10])
        
        # 신뢰구간 (홈팀 승률 기준)
        home_probs = home_goals > away_goals
        ci_low = np.percentile([np.mean(self.rng.choice(home_probs, len(home_probs), replace=True)) 
                                for _ in range(1000)], 2.5)
        ci_high = np.percentile([np.mean(self.rng.choice(home_probs, len(home_probs), replace=True)) 
                                 for _ in range(1000)], 97.5)
        
        return SimulationResult(
            home_wins=int(home_wins),
            draws=int(draws),
            away_wins=int(away_wins),
            total_runs=n_runs,
            score_distribution=score_dist,
            confidence_interval=(ci_low, ci_high)
        )
    
    def simulate_multiple_scenarios(self, home_stats: Dict, away_stats: Dict,
                                   scenarios: List[Dict]) -> List[SimulationResult]:
        """
        다양한 시나리오 시뮬레이션
        
        scenarios 예시:
        [
            {'name': '기본', 'home_stats': {...}, 'away_stats': {...}},
            {'name': '홈팀 핵심 부상', 'home_stats': {...수정...}, 'away_stats': {...}},
            {'name': '원정팀 집중력 저하', 'home_stats': {...}, 'away_stats': {...수정...}},
        ]
        """
        results = []
        for scenario in scenarios:
            result = self.simulate_match(
                scenario.get('home_stats', home_stats),
                scenario.get('away_stats', away_stats),
                n_runs=scenario.get('n_runs', 1000)
            )
            results.append(result)
        
        return results


if __name__ == '__main__':
    # 테스트
    simulator = MatchSimulator()
    
    home = {
        'avg_goals_scored': 1.8,
        'avg_goals_conceded': 0.9,
        'avg_shots': 14.2,
        'avg_shots_on_target': 5.1,
        'avg_possession': 58,
        'recent_form': ['W', 'W', 'D', 'W', 'L']
    }
    
    away = {
        'avg_goals_scored': 1.2,
        'avg_goals_conceded': 1.4,
        'avg_shots': 10.5,
        'avg_shots_on_target': 3.8,
        'avg_possession': 45,
        'recent_form': ['L', 'D', 'L', 'W', 'D']
    }
    
    result = simulator.simulate_match(home, away, n_runs=10000)
    print(f"시뮬레이션 결과 ({result.total_runs}회):")
    print(f"홈승: {result.home_wins} ({result.home_wins/result.total_runs*100:.1f}%)")
    print(f"무승부: {result.draws} ({result.draws/result.total_runs*100:.1f}%)")
    print(f"원정승: {result.away_wins} ({result.away_wins/result.total_runs*100:.1f}%)")
    print(f"\n예상 스코어 Top 5: {dict(list(result.score_distribution.items())[:5])}")
