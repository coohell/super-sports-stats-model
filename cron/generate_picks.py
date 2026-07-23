#!/usr/bin/env python3
"""
================================================================
🏆 세계최강 슈퍼픽 자동 생성 (OpenClaw Cron)
================================================================
매일 06:00 실행 → 실제 경기 분석 → 최고 품질의 픽 3개 저장
================================================================
"""

import os
import sys
import json
from datetime import datetime, timedelta

# .env 로드
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print("   → .env 파일 로드 완료")
except ImportError:
    pass

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'picks'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'tracker'))

from world_class_engine import WorldClassEngine
from database import PickDatabase


def fetch_real_matches():
    """
    실제 경기 데이터 수집
    - API 연동 시 실제 데이터 사용
    - 현재는 수동 입력된 경기 + 모의 데이터 혼합
    """
    from data import get_all_matches
    
    # 실제 경기 우선, 모의 데이터 보충
    matches = get_all_matches()
    
    # 오늘 날짜 필터링
    today = datetime.now().strftime("%Y-%m-%d")
    today_matches = [m for m in matches if m.get('date', today) == today]
    
    if not today_matches:
        today_matches = matches  # 오늘 데이터 없으면 전체 사용
    
    return today_matches


def generate_world_class_picks():
    """세계최강 픽 생성 메인 함수"""
    
    print("=" * 70)
    print("🏆 세계최강 SuperPickKing - 자동 픽 생성")
    print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 엔진 초기화
    engine = WorldClassEngine(seed=int(datetime.now().timestamp()))
    
    # 경기 수집
    print("\n🔍 경기 데이터 수집 중...")
    matches = fetch_real_matches()
    print(f"   → {len(matches)}개 경기 수집 완료")
    
    if not matches:
        print("⚠️ 분석할 경기가 없습니다.")
        return
    
    # 픽 생성
    print("\n🧠 AI 분석 중...")
    picks = engine.generate_picks(matches, min_ev=-5.0, top_n=5)
    
    if not picks:
        print("⚠️ 적합한 픽이 없습니다. (EV 기준 미달)")
        return
    
    # 상위 3개만 저장
    top_picks = picks[:3]
    
    # DB 저장
    print("\n💾 데이터베이스 저장 중...")
    db_path = os.environ.get('DB_PATH', '/tmp/superpicks.db')
    db = PickDatabase(db_path)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    combo_id = f"combo_{date_str}"
    
    saved_picks = []
    for i, pick in enumerate(top_picks, 1):
        pick_data = {
            'match_id': pick.match_id,
            'date': date_str,
            'sport': pick.sport,
            'league': pick.league,
            'home_team': pick.home_team,
            'away_team': pick.away_team,
            'match_time': pick.match_time,
            'pick': max(pick.ensemble_prob, key=pick.ensemble_prob.get),
            'odds': getattr(pick, f"{max(pick.ensemble_prob, key=pick.ensemble_prob.get)}_odds"),
            'confidence': pick.quality_score,
            'reason': pick.explanation[:500],
            'model_version': pick.model_version
        }
        
        pick_id = db.add_pick(pick_data)
        saved_picks.append(pick_id)
        print(f"   ✓ 픽 #{i} 저장: {pick.home_team} vs {pick.away_team} (품질: {pick.quality_score:.1f})")
    
    # 조합 저장
    if len(saved_picks) >= 2:
        db.add_combo({
            'combo_id': combo_id,
            'date': date_str,
            'picks': json.dumps(saved_picks),
            'total_odds': 0,  # 나중에 계산
            'status': 'pending'
        })
        print(f"   ✓ 조합 저장: {combo_id}")
    
    # 결과 출력
    print("\n" + "=" * 70)
    print("📊 생성 결과")
    print("=" * 70)
    
    for i, pick in enumerate(top_picks, 1):
        print(f"\n🏆 픽 #{i} | 품질점수: {pick.quality_score:.1f}/100")
        print(pick.explanation)
        print("-" * 70)
    
    # JSON 리포트 저장
    report = {
        'date': date_str,
        'model_version': 'WorldClass-v1.0',
        'total_matches': len(matches),
        'picks_generated': len(top_picks),
        'picks': [engine.to_dict(p) for p in top_picks]
    }
    
    report_path = f'/tmp/superpicks_report_{date_str}.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 리포트 저장: {report_path}")
    print("✅ 완료!")


if __name__ == "__main__":
    generate_world_class_picks()
