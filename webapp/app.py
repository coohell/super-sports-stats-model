import streamlit as st
import sys
from pathlib import Path
import random

# DB 연결
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.picks.database import PickDatabase

st.set_page_config(
    page_title="천기누설 - 스포츠 AI 필승예측",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.main-header {
    font-size: 3.5rem; font-weight: 900; text-align: center;
    background: linear-gradient(90deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.3rem;
}
.sub-header { text-align: center; color: #888; font-size: 1.2rem; margin-bottom: 2rem; }
.pick-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 20px; padding: 24px; color: white; text-align: center;
    box-shadow: 0 15px 35px rgba(102,126,234,0.3); margin: 12px 0;
    transition: all 0.3s ease; border: 2px solid transparent;
}
.pick-card:hover { transform: translateY(-8px); border-color: #feca57; }
.kill-badge {
    background: linear-gradient(135deg, #ff4757, #ff6348);
    color: white; padding: 6px 16px; border-radius: 20px;
    font-size: 0.8rem; font-weight: bold; display: inline-block; margin: 4px;
}
.stats-box {
    background: #1e1e2e; border-radius: 16px; padding: 20px;
    border: 1px solid #2d2d44; text-align: center;
}
.stats-number { font-size: 2.5rem; font-weight: 900; color: #feca57; }
.stats-label { font-size: 0.9rem; color: #888; margin-top: 4px; }
.match-row {
    background: #1e1e2e; border-radius: 12px; padding: 16px; margin: 8px 0;
    border: 1px solid #2d2d44; display: flex; align-items: center; justify-content: space-between;
}
.sport-btn {
    background: #2d2d44; color: #888; border: none; padding: 10px 24px;
    border-radius: 25px; margin: 0 6px; cursor: pointer; font-weight: 700;
    transition: all 0.2s;
}
.sport-btn:hover, .sport-btn.active { background: #667eea; color: white; }
.telegram-box {
    background: linear-gradient(135deg, #0088cc, #00a8e8);
    border-radius: 16px; padding: 20px; color: white; text-align: center; margin-top: 30px;
}
/* 다크모드 강제 */
.stApp { background: #0a0a14; color: #e0e0e0; }
</style>
""", unsafe_allow_html=True)

# DB 연결
db = PickDatabase()

# ===== 헤더 =====
st.markdown('<div class="main-header">🔮 천기누설</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI 스포츠 필승예측 | 매일 업데이트되는 슈퍼픽</div>', unsafe_allow_html=True)

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

# ===== 종목 선택 =====
st.subheader("🏆 종목별 오늘의 슈퍼픽")

sport_cols = st.columns(6)
sports = ["전체", "축구", "농구", "야구", "테니스", "배구"]
if "sel_sport" not in st.session_state:
    st.session_state.sel_sport = "전체"

for i, sp in enumerate(sports):
    active = "active" if st.session_state.sel_sport == sp else ""
    if sport_cols[i].button(sp, key=f"sp_{sp}", use_container_width=True):
        st.session_state.sel_sport = sp
        st.rerun()

# ===== 오늘의 픽 3폴더 =====
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")

if st.session_state.sel_sport == "전체":
    picks = db.get_picks_by_date(today)
else:
    picks = db.get_picks_by_date(today, st.session_state.sel_sport)

# DB에 없으면 모의 데이터 표시 (처음 실행 시)
if not picks:
    st.info("📅 오늘의 픽이 아직 생성되지 않았습니다. 매일 오전 10시 자동 업데이트됩니다.")
    
    # 모의 픽 표시
    st.subheader("🎯 예시 픽 (실제 픽은 매일 오전 생성)")
    demo_picks = [
        {"match": "울산 HD vs 포항", "league": "K리그1", "time": "19:00", "pick": "울산 승", "odds": 1.85, "conf": "높음🔥", "ev": 8.5},
        {"match": "맨시티 vs 아스날", "league": "프리미어리그", "time": "21:00", "pick": "맨시티 승", "odds": 1.65, "conf": "매우높음🔥", "ev": 12.3},
        {"match": "레알마드리드 vs 바르셀로나", "league": "라리가", "time": "04:00", "pick": "오버 2.5", "odds": 1.75, "conf": "높음🔥", "ev": 6.8},
    ]
    
    cols = st.columns(3)
    for i, dp in enumerate(demo_picks):
        with cols[i]:
            st.markdown(f"""
            <div class="pick-card">
                <div style="font-size:0.85rem; opacity:0.9;">{dp['league']} · {dp['time']}</div>
                <div style="font-size:1.1rem; font-weight:bold; margin:8px 0;">{dp['match']}</div>
                <div style="font-size:1.5rem; font-weight:900; color:#feca57; margin:12px 0;">{dp['pick']}</div>
                <div style="font-size:1.3rem; font-weight:bold;">@ {dp['odds']}</div>
                <div style="margin-top:12px;">
                    <span class="kill-badge">{dp['conf']}</span>
                </div>
                <div style="font-size:0.8rem; margin-top:8px; opacity:0.9;">EV +{dp['ev']}%</div>
            </div>
            """, unsafe_allow_html=True)
else:
    # 실제 DB 픽 표시
    st.subheader(f"🎯 {st.session_state.sel_sport} 오늘의 필승픽")
    
    # 상위 3개
    top3 = picks[:3]
    cols = st.columns(3)
    for i, pick in enumerate(top3):
        with cols[i]:
            conf_emoji = "🔥" if "매우" in pick.confidence else "✅" if "높음" in pick.confidence else "⚠️"
            st.markdown(f"""
            <div class="pick-card">
                <div style="font-size:0.85rem; opacity:0.9;">{pick.league} · {pick.match_time}</div>
                <div style="font-size:1.1rem; font-weight:bold; margin:8px 0;">{pick.home_team} vs {pick.away_team}</div>
                <div style="font-size:1.5rem; font-weight:900; color:#feca57; margin:12px 0;">{pick.pick_selection}</div>
                <div style="font-size:1.3rem; font-weight:bold;">@ {pick.pick_odds}</div>
                <div style="margin-top:12px;">
                    <span class="kill-badge">{conf_emoji} {pick.confidence}</span>
                </div>
                <div style="font-size:0.8rem; margin-top:8px; opacity:0.9;">EV {pick.ev*100:+.1f}% | 엣지 {pick.edge*100:+.1f}%p</div>
            </div>
            """, unsafe_allow_html=True)
    
    # 전체 픽 목록
    st.divider()
    st.subheader("📋 전체 픽 목록")
    
    for pick in picks:
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 1])
            with col1:
                st.markdown(f"**{pick.home_team} vs {pick.away_team}**  \n{pick.league} · {pick.match_time}")
            with col2:
                st.markdown(f"**{pick.pick_selection}** @ {pick.pick_odds}")
            with col3:
                color = "#4CAF50" if pick.ev > 0 else "#ff4757"
                st.markdown(f"<span style='color:{color}; font-weight:bold;'>EV {pick.ev*100:+.1f}%</span>", unsafe_allow_html=True)
            with col4:
                st.caption(f"신뢰도: {pick.confidence}")
            with col5:
                status_color = {"pending": "🟡", "settled": "🟢", "void": "⚪"}.get(pick.status, "⚪")
                st.markdown(f"{status_color} {pick.status}")
        st.divider()

# ===== 텔레그램 CTA =====
st.markdown("""
<div class="telegram-box">
    <h3>📱 실시간 픽 알림 받기</h3>
    <p>매일 아침 슈퍼픽 3폴더를 텔레그램으로 받아보세요!</p>
    <p style="font-size:0.9rem; opacity:0.9;">@SuperPickKingBot</p>
</div>
""", unsafe_allow_html=True)

# ===== 푸터 =====
st.divider()
st.markdown("""
<div style="text-align: center; color: #555; font-size: 0.8rem; padding: 20px;">
    ⚠️ 본 분석은 통계 모델 기반이며, 결과를 보장하지 않습니다. 스포츠토토는 소액으로 재미삼아 이용하세요.<br>
    🔮 천기누설 AI | Super Pick King v2.0 | 매일 오전 10시 자동 업데이트
</div>
""", unsafe_allow_html=True)
