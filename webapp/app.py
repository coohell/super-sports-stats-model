import streamlit as st
import sys
from pathlib import Path
import random
import os

# 경로 설정
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'picks'))

from src.picks.database import PickDatabase
from src.picks.world_class_engine import WorldClassEngine

st.set_page_config(
    page_title="🏆 천기누설 - 세계최강 AI 필승예측",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ===== CSS 스타일 =====
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

.main-header {
    font-size: 4rem; font-weight: 900; text-align: center;
    background: linear-gradient(90deg, #FFD700, #FF6B6B, #4ECDC4, #FFE66D);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.3rem;
    text-shadow: 0 0 30px rgba(255,215,0,0.3);
}
.sub-header { 
    text-align: center; color: #888; font-size: 1.2rem; 
    margin-bottom: 2rem; font-weight: 400;
}
.version-badge {
    display: inline-block; background: linear-gradient(135deg, #667eea, #764ba2);
    color: white; padding: 4px 12px; border-radius: 12px;
    font-size: 0.75rem; font-weight: bold; margin-left: 8px;
}

/* 세계최강 픽 카드 */
.world-class-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 20px; padding: 24px; color: white; text-align: center;
    box-shadow: 0 10px 40px rgba(102,126,234,0.2); margin: 12px 0;
    transition: all 0.3s ease; border: 2px solid transparent;
    position: relative; overflow: hidden;
}
.world-class-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, #FFD700, #FF6B6B, #4ECDC4);
}
.world-class-card:hover { 
    transform: translateY(-8px); border-color: #FFD700; 
    box-shadow: 0 20px 60px rgba(255,215,0,0.2);
}
.quality-score {
    font-size: 2.5rem; font-weight: 900; color: #FFD700;
    text-shadow: 0 0 20px rgba(255,215,0,0.3);
}
.quality-label { font-size: 0.8rem; color: #aaa; margin-top: -5px; }

/* EV 배지 */
.ev-badge {
    display: inline-block; padding: 4px 12px; border-radius: 12px;
    font-size: 0.85rem; font-weight: bold; margin: 4px;
}
.ev-positive { background: rgba(76,175,80,0.2); color: #4CAF50; border: 1px solid #4CAF50; }
.ev-negative { background: rgba(255,71,87,0.2); color: #ff4757; border: 1px solid #ff4757; }
.ev-neutral { background: rgba(254,202,87,0.2); color: #feca57; border: 1px solid #feca57; }

/* 아비트라지 배지 */
.arb-badge {
    background: linear-gradient(135deg, #ff4757, #ff6348);
    color: white; padding: 4px 12px; border-radius: 12px;
    font-size: 0.8rem; font-weight: bold; animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

/* Kelly */
.kelly-text { font-size: 0.8rem; color: #aaa; }

/* 통계 박스 */
.stats-box {
    background: linear-gradient(135deg, #1e1e2e, #2d2d44); 
    border-radius: 16px; padding: 20px;
    border: 1px solid #333; text-align: center;
}
.stats-number { font-size: 2.5rem; font-weight: 900; color: #FFD700; }
.stats-label { font-size: 0.9rem; color: #888; margin-top: 4px; }

/* 모델 정보 */
.model-info {
    background: rgba(255,255,255,0.05); border-radius: 10px;
    padding: 12px; margin-top: 12px; font-size: 0.75rem;
    text-align: left; color: #aaa;
}
.model-info strong { color: #FFD700; }

/* 다크모드 */
.stApp { background: #0a0a14; color: #e0e0e0; }
</style>
""", unsafe_allow_html=True)

# ===== DB 연결 =====
db_path = os.environ.get('DB_PATH', '/tmp/superpicks.db')
os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '/tmp', exist_ok=True)
db = PickDatabase(db_path)

# ===== 헤더 =====
st.markdown('<div class="main-header">🏆 천기누설</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">세계최강 AI 스포츠 필승예측 <span class="version-badge">WorldClass-v1.0</span></div>', unsafe_allow_html=True)

# ===== 통계 배너 =====
stats = db.get_stats(days=30)
cols = st.columns(5)
with cols[0]:
    st.markdown(f'<div class="stats-box"><div class="stats-number">{stats["total"]}</div><div class="stats-label">총 픽</div></div>', unsafe_allow_html=True)
with cols[1]:
    st.markdown(f'<div class="stats-box"><div class="stats-number" style="color:#4CAF50">{stats["wins"]}</div><div class="stats-label">적중</div></div>', unsafe_allow_html=True)
with cols[2]:
    st.markdown(f'<div class="stats-box"><div class="stats-number" style="color:#ff4757">{stats["losses"]}</div><div class="stats-label">미적중</div></div>', unsafe_allow_html=True)
with cols[3]:
    st.markdown(f'<div class="stats-box"><div class="stats-number" style="color:#feca57">{stats["win_rate"]:.1f}%</div><div class="stats-label">승률</div></div>', unsafe_allow_html=True)
with cols[4]:
    profit_color = "#4CAF50" if stats["total_profit"] >= 0 else "#ff4757"
    st.markdown(f'<div class="stats-box"><div class="stats-number" style="color:{profit_color}">{stats["total_profit"]:+.0f}</div><div class="stats-label">수익(만원)</div></div>', unsafe_allow_html=True)

st.divider()

# ===== 세계최강 픽 생성 버튼 =====
from datetime import datetime
from data import get_all_matches

today = datetime.now().strftime("%Y-%m-%d")

col1, col2 = st.columns([1, 3])
with col1:
    if st.button("🚀 세계최강 픽 생성", type="primary", use_container_width=True):
        with st.spinner("🏆 세계최강 엔진 분석 중..."):
            engine = WorldClassEngine(seed=int(datetime.now().timestamp()))
            matches = get_all_matches()
            today_matches = [m for m in matches if m.get('date', today) == today]
            if not today_matches:
                today_matches = matches
            
            picks = engine.generate_picks(today_matches, min_ev=-10.0, top_n=3)
            
            # DB 저장
            saved = []
            for pick in picks:
                pick_data = {
                    'match_id': pick.match_id,
                    'date': today,
                    'sport': pick.sport,
                    'league': pick.league,
                    'home_team': pick.home_team,
                    'away_team': pick.away_team,
                    'match_time': pick.match_time,
                    'pick': max(pick.ensemble_prob, key=pick.ensemble_prob.get),
                    'odds': getattr(pick, f"{max(pick.ensemble_prob, key=pick.ensemble_prob.get)}_odds"),
                    'confidence': f"{pick.quality_score:.0f}",
                    'reason': pick.explanation[:500],
                    'model_version': pick.model_version
                }
                db.add_pick(pick_data)
                saved.append(pick)
            
            st.success(f"✅ {len(saved)}개 세계최강 픽 생성 완료!")
            st.rerun()

with col2:
    st.caption("🧠 Poisson(40%) + Monte Carlo(35%) + 배당역산(25%) 앙상블 | EV 필터링 | Fractional Kelly | 아비트라지 탐지")

# ===== 오늘의 세계최강 픽 =====
st.subheader("🏆 오늘의 세계최강 픽")

picks = db.get_picks_by_date(today)

if not picks:
    st.info("📅 오늘의 픽이 아직 생성되지 않았습니다. '세계최강 픽 생성' 버튼을 눌러주세요.")
    
    # 예시 카드
    st.subheader("🎯 예시 (세계최강 엔진 출력 형태)")
    
    # 예시용 WorldClassPick
    engine = WorldClassEngine(seed=42)
    demo_match = {
        'match_id': 'demo1', 'home_team': 'LG', 'away_team': 'NC',
        'home_odds': 1.45, 'draw_odds': 0, 'away_odds': 3.20,
        'home_xg': 5.2, 'away_xg': 3.0,
        'home_strength': 0.75, 'away_strength': 0.35,
        'sport': '야구', 'league': 'KBO', 'match_time': '18:30'
    }
    demo_pick = engine.analyze_match(demo_match)
    
    if demo_pick:
        cols = st.columns(3)
        with cols[0]:
            st.markdown(f"""
            <div class="world-class-card">
                <div style="font-size:0.8rem; color:#FFD700; font-weight:bold;">🏆 세계최강 #{1}</div>
                <div style="font-size:0.85rem; opacity:0.9; margin-top:8px;">{demo_pick.league} · {demo_pick.match_time}</div>
                <div style="font-size:1.1rem; font-weight:bold; margin:8px 0;">{demo_pick.home_team} vs {demo_pick.away_team}</div>
                <div class="quality-score">{demo_pick.quality_score:.0f}</div>
                <div class="quality-label">품질 점수 / 100</div>
                <div style="font-size:1.4rem; font-weight:900; color:#4ECDC4; margin:12px 0;">
                    {max(demo_pick.ensemble_prob, key=demo_pick.ensemble_prob.get).upper()} @ {getattr(demo_pick, f"{max(demo_pick.ensemble_prob, key=demo_pick.ensemble_prob.get)}_odds")}
                </div>
                <span class="ev-badge {'ev-positive' if demo_pick.ev_percent > 0 else 'ev-negative'}">
                    EV {demo_pick.ev_percent:+.1f}%
                </span>
                <div class="kelly-text" style="margin-top:8px;">
                    Half-Kelly: {demo_pick.half_kelly:.1%} | 엔진: {demo_pick.model_version}
                </div>
                {'<div style="margin-top:8px;"><span class="arb-badge">🎯 아비트라지 +' + str(demo_pick.arbitrage_profit) + '%</span></div>' if demo_pick.is_arbitrage else ''}
                <div class="model-info">
                    <strong>🔮 모델 예측 확률:</strong><br>
                    홈승: {demo_pick.ensemble_prob['home']:.1%} | 
                    무: {demo_pick.ensemble_prob['draw']:.1%} | 
                    원정승: {demo_pick.ensemble_prob['away']:.1%}<br>
                    <strong>📊 앙상블 구성:</strong><br>
                    Poisson(40%) + Monte Carlo(35%) + 배당역산(25%)
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    # 실제 DB 픽 표시 - 세계최강 카드
    top3 = picks[:3]
    cols = st.columns(min(3, len(top3)))
    
    for i, pick in enumerate(top3):
        with cols[i]:
            try:
                quality = float(pick.confidence) if pick.confidence else 0
            except:
                quality = 0
            
            ev_color = "ev-positive" if pick.ev > 0 else "ev-negative" if pick.ev < 0 else "ev-neutral"
            
            st.markdown(f"""
            <div class="world-class-card">
                <div style="font-size:0.8rem; color:#FFD700; font-weight:bold;">🏆 세계최강 #{i+1}</div>
                <div style="font-size:0.85rem; opacity:0.9; margin-top:8px;">{pick.league} · {pick.match_time}</div>
                <div style="font-size:1.1rem; font-weight:bold; margin:8px 0;">{pick.home_team} vs {pick.away_team}</div>
                <div class="quality-score">{quality:.0f}</div>
                <div class="quality-label">품질 점수 / 100</div>
                <div style="font-size:1.4rem; font-weight:900; color:#4ECDC4; margin:12px 0;">
                    {pick.pick_selection.upper()} @ {pick.pick_odds}
                </div>
                <span class="ev-badge {ev_color}">
                    EV {pick.ev*100:+.1f}%
                </span>
                <div class="kelly-text" style="margin-top:8px;">
                    {pick.model_version}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ===== 기술 설명 =====
with st.expander("🔬 세계최강 엔진 기술 상세"):
    st.markdown("""
    ### 🏆 WorldClassEngine v1.0 기술 스택
    
    **GitHub 9개 오픈소스 분석 결과 통합:**
    
    | 기술 | 출처 | 역할 |
    |------|------|------|
    | **Poisson 분포** | sports-betting, pena.lt/y | 득점 기반 확률 |
    | **Monte Carlo** | AlphaPy, NBA-ML | 시뮬레이션 확률 |
    | **배당 역산** | pretrehr | 시장 암시확률 |
    | **앙상블** | AlphaPy, georgedouzas | 가중 평균 |
    | **EV 필터링** | georgedouzas | 가치 배팅 선별 |
    | **Kelly Criterion** | NBA-ML, AlphaPy | 자금 관리 |
    | **아비트라지** | pretrehr | 무리스크 기회 |
    | **SHAP 설명** | nickklos10 | 모델 해석 |
    | **LLM 분석** | llSourcell | 뉴스/감정 |
    
    ### 📊 앙상블 가중치
    - Poisson (40%): 축구/야구 표준 득점 모델
    - Monte Carlo (35%): 팀 강도 + 홈 어드밴티지 시뮬레이션
    - 배당 역산 (25%): 시장의 집단 지성
    
    ### 💰 품질 점수 산출
    - EV 기여 (40%): 기대 수익률
    - 최고 확률 (30%): 모델 신뢰도
    - 모델 일치도 (30%): 3모델 예측 일치율
    
    ### ⚠️ 주의사항
    본 분석은 통계 모델 기반이며, 결과를 보장하지 않습니다. 스포츠토토는 소액으로 재미삼아 이용하세요.
    """)

# ===== 푸터 =====
st.divider()
st.markdown("""
<div style="text-align: center; color: #555; font-size: 0.8rem; padding: 20px;">
    ⚠️ 본 분석은 통계 모델 기반이며, 결과를 보장하지 않습니다.<br>
    🏆 천기누설 AI | Super Pick King <strong>WorldClass-v1.0</strong> | 세계최강 엔진
</div>
""", unsafe_allow_html=True)
