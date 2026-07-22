#!/usr/bin/env python3
"""
Super Sports Stats Model - 메인 파이프라인
경기 분석 → 시뮬레이션 → 전략 생성 → LLM 인사이트

사용법:
    python src/main.py --home "Korea" --away "Mexico" --league "World Cup"
"""
import argparse
import json
import sys
from pathlib import Path

# 경로 설정
sys.path.insert(0, str(Path(__file__).parent))

from collectors.news_scraper import NewsScraper
from collectors.odds_collector import OddsCollector
from engine.simulator import MatchSimulator
from engine.strategy import StrategyEngine
from llm.match_analyzer import MatchAnalyzer


def load_sample_stats():
    """
    데모용 샘플 데이터
    실제 사용시 API나 DB에서 로드
    """
    return {
        'home': {
            'avg_goals_scored': 1.6,
            'avg_goals_conceded': 1.1,
            'avg_shots': 13.5,
            'avg_shots_on_target': 4.8,
            'avg_possession': 54,
            'recent_form': ['W', 'D', 'W', 'L', 'W']
        },
        'away': {
            'avg_goals_scored': 1.3,
            'avg_goals_conceded': 1.4,
            'avg_shots': 11.2,
            'avg_shots_on_target': 3.9,
            'avg_possession': 47,
            'recent_form': ['D', 'L', 'W', 'D', 'L']
        }
    }


def run_analysis(home_team: str, away_team: str, league: str = "",
                bankroll: float = 100000, api_key: str = ""):
    """
    전체 분석 파이프라인 실행
    """
    print(f"\n{'='*60}")
    print(f"🏟️  {home_team} vs {away_team}")
    if league:
        print(f"📌 {league}")
    print(f"{'='*60}\n")
    
    # 1. 뉴스 수집
    print("📰 [1/5] 뉴스 수집 중...")
    news_scraper = NewsScraper()
    news = news_scraper.collect_match_news(home_team, away_team, league, max_per_source=5)
    print(f"   한국어: {len(news['korean'])}개 | 영어: {len(news['english'])}개")
    
    # 2. 배당률 수집 (샘플)
    print("\n📊 [2/5] 배당률 분석 중...")
    odds_collector = OddsCollector(api_key=api_key)
    
    # 데모용 배당률
    sample_odds = {
        'home_win': 2.10,
        'draw': 3.30,
        'away_win': 3.60
    }
    implied = odds_collector.calculate_implied_probabilities(
        type('obj', (object,), {
            'home_win': sample_odds['home_win'],
            'draw': sample_odds['draw'],
            'away_win': sample_odds['away_win']
        })()
    )
    print(f"   배당률: 홈 {sample_odds['home_win']} / 무 {sample_odds['draw']} / 원정 {sample_odds['away_win']}")
    print(f"   암시확률: 홈 {implied['home']*100:.1f}% / 무 {implied['draw']*100:.1f}% / 원정 {implied['away']*100:.1f}%")
    
    # 3. Monte Carlo 시뮬레이션
    print(f"\n🎲 [3/5] Monte Carlo 시뮬레이션 (1000회)...")
    stats = load_sample_stats()
    simulator = MatchSimulator()
    sim_result = simulator.simulate_match(stats['home'], stats['away'], n_runs=1000)
    
    probs = sim_result.get_probabilities()
    print(f"   홈승: {probs['home']*100:.1f}%")
    print(f"   무승부: {probs['draw']*100:.1f}%")
    print(f"   원정승: {probs['away']*100:.1f}%")
    print(f"   예상 스코어 Top3: {dict(list(sim_result.score_distribution.items())[:3])}")
    
    # 4. 전략 엔진
    print(f"\n🎯 [4/5] 전략 분석 중...")
    strategy_engine = StrategyEngine(bankroll=bankroll)
    
    strategies = strategy_engine.generate_all_strategies(probs, sample_odds)
    
    for key, rec in strategies.items():
        print(f"\n   [{rec.strategy_name}] 픽 {len(rec.picks)}개")
        for p in rec.picks[:2]:  # 상위 2개만
            print(f"     → {p['selection'].upper()} @ {p['odds']} "
                  f"(확률 {p['probability']*100:.0f}%, EV {p['expected_value']:+.1f}, "
                  f"배팅 {p['suggested_stake']:,.0f}원)")
    
    best = strategy_engine.get_best_pick(strategies)
    if 'best_pick' in best:
        print(f"\n   🏆 최고 추천: {best['recommendation']}")
    
    # 5. LLM 인사이트
    print(f"\n🧠 [5/5] AI 인사이트 생성 중...")
    analyzer = MatchAnalyzer()
    
    sim_data = {
        'home_prob': probs['home'],
        'draw_prob': probs['draw'],
        'away_prob': probs['away'],
        'top_scores': sim_result.score_distribution
    }
    
    insight = analyzer.analyze_match(home_team, away_team, news, stats, sample_odds, sim_data)
    print(f"\n{insight}")
    
    # 결과 저장
    result = {
        'match': f"{home_team} vs {away_team}",
        'league': league,
        'probabilities': probs,
        'odds': sample_odds,
        'strategies': {
            k: {
                'name': v.strategy_name,
                'picks_count': len(v.picks),
                'risk': v.risk_level,
                'reasoning': v.reasoning
            } for k, v in strategies.items()
        },
        'best_pick': best,
        'simulation': {
            'top_scores': sim_result.score_distribution,
            'confidence_interval': sim_result.confidence_interval
        }
    }
    
    # JSON 저장
    output_path = Path(f"data/prediction_{home_team}_vs_{away_team}.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 결과 저장: {output_path}")
    print(f"{'='*60}\n")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Super Sports Stats Model')
    parser.add_argument('--home', required=True, help='홈팀 이름')
    parser.add_argument('--away', required=True, help='원정팀 이름')
    parser.add_argument('--league', default='', help='리그 이름 (선택)')
    parser.add_argument('--bankroll', type=float, default=100000, help='총 자본 (원)')
    parser.add_argument('--api-key', default='', help='API-Football API 키')
    
    args = parser.parse_args()
    
    run_analysis(
        home_team=args.home,
        away_team=args.away,
        league=args.league,
        bankroll=args.bankroll,
        api_key=args.api_key
    )


if __name__ == '__main__':
    main()
