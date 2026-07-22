import streamlit as st
import sys
from pathlib import Path
import random

# logic.py 임포트
sys.path.insert(0, str(Path(__file__).parent.parent / "telegram_bot"))
from logic import KillPickEngine

# 데이터
from data import get_today_matches, Match

# 페이지 설정
st.set_page_config(
    page_title="천기누설 - 스포츠 AI 필승예측",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS - 유튜브 스포츠 분석 채널 스타일
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif;
}

.main-header {
    font-size: 3rem;
    font-weight: 900;
    text-align: center;
    background: linear-gradient(90deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
}

.sub-header {
    text-align: center;
    color: #888;
    font-size: 1.1rem;
    margin-bottom: 2rem;
}

.pick-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 20px;
    color: white;
    text-align: center;
    box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
    margin: 10px 0;
    transition: transform 0.2s;
}

.pick-card:hover {
    transform: translateY(-5px);
}

.kill-badge {
    background: #ff4757;
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: bold;
}

.confidence-fire { color: #ff6b6b; font-weight: 900; }
.confidence-high { color: #feca57; font-weight: 700; }
.confidence-mid { color: #48dbfb; font-weight: 700; }

.match-card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 16px;
    margin: 8px 0;
    border: 1px solid #2d2d44;
}

.sport-tab {
    padding: 8px 16px;
    border-radius: 20px;
    background: #2d2d44;
    color: #888;
    border: none;
    margin: 0 4px;
    cursor: pointer;
}

.sport-tab.active {
    background: #667eea;
    color: white;
}

.odds-box {
    background: #2d2d44;
    border-radius: 8px;
    padding: 8px 12px;
    text-align: center;
    min-width: 60px;
}

.odds-box.selected {
    background: #667eea;
    color: white;
    font-weight: bold;
}

.telegram-cta {
    background: linear-gradient(135deg, #0088cc, #00a8e8);
    border-radius: 12px;
    padding: 16px;
    color: white;
    text-align: center;
    margin-top: 20px;
}

/* 다크모드 강제 */
.stApp {
    background: #0f0f1a;
    color: #e0e0e0;
}
</style>
""", unsafe_allow_html=True)

# ===== 헤더 =====
st.markdown('<div class="main-header">🔮 천기누설</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI 스포츠 필승예측 시스템 | 오늘의 경기 분석</div>', unsafe_allow_html=True)

# ===== 데이터 로드 =====
engine = KillPickEngine()
all_matches = get_today_matches()

# 필터 탭
col_tabs = st.columns(6)
sport_filters = ["전체", "축구", "농구", "야구", "테니스", "배구"]
if "selected_sport" not in st.session_state:
    st.session_state.selected_sport = "전체"

for i, sport in enumerate(sport_filters):
    active = "active" if st.session_state.selected_sport == sport else ""
    if col_tabs[i].button(sport, key=f"tab_{sport}", use_container_width=True):
        st.session_state.selected_sport = sport
        st.rerun()

filtered_matches = all_matches if st.session_state.selected_sport == "전체" else \
    [m for m in all_matches if m.sport == st.session_state.selected_sport]

# ===== 오늘의 KILL PICK (상단 배너) =====
st.divider()
st.subheader("⚔️ 오늘의 필승픽 TOP 3")

# 상위 3개 픽 계산
top_picks = []
for m in filtered_matches[:10]:
    try:
        if m.sport == "축구":
            pick = engine.find_kill_pick(m.home, m.away, m.home_odds, m.draw_odds, m.away_odds, m.home_xg, m.away_xg)
        else:
            # 축구 외 종목은 draw_odds 없음
            draw = m.draw_odds if m.draw_odds else 3.0
            pick = engine.find_kill_pick(m.home, m.away, m.home_odds, draw, m.away_odds)
        top_picks.append((pick, m))
    except:
        continue

# EV 기준 정렬
top_picks.sort(key=lambda x: x[0].expected_value, reverse=True)

cols = st.columns(3)
for i, (pick, match) in enumerate(top_picks[:3]):
    with cols[i]:
        conf_emoji = "🔥" if "매우" in pick.confidence else "✅" if "높음" in pick.confidence else "⚠️"
        st.markdown(f"""
        <div class="pick-card">
            <div style="font-size:0.8rem; opacity:0.8; margin-bottom:8px;">{match.league} | {match.match_time}</div>
            <div style="font-size:1.1rem; font-weight:bold; margin-bottom:4px;">{pick.match}</div>
            <div style="font-size:1.4rem; font-weight:900; margin:8px 0;">{pick.selection_kr}</div>
            <div style="font-size:1.2rem; color:#feca57; font-weight:bold;">@ {pick.odds}</div>
            <div style="margin-top:8px;">
                <span class="kill-badge">{conf_emoji} {pick.confidence}</span>
            </div>
            <div style="font-size:0.75rem; margin-top:8px; opacity:0.9;">
                EV {pick.expected_value*100:+.1f}% | 엣지 {pick.edge*100:+.1f}%p
            </div>
        </div>
        """, unsafe_allow_html=True)

# ===== 전체 경기 목록 =====
st.divider()
st.subheader(f"📋 오늘의 경기 ({len(filtered_matches)}경기)")

for match in filtered_matches:
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 2, 1.5, 1])
        
        with col1:
            st.markdown(f"""
            <div style="color:#888; font-size:0.8rem;">{match.league} · {match.match_time}</div>
            <div style="font-weight:bold; font-size:1.1rem;">{match.home} vs {match.away}</div>
            """, unsafe_allow_html=True)
            if match.home_form:
                st.caption(f"홈 {match.home_form} | 원정 {match.away_form}")
        
        with col2:
            if match.home_xg:
                st.caption(f"xG: {match.home_xg} - {match.away_xg}")
        
        with col3:
            c1, c2, c3 = st.columns(3)
            c1.markdown(f'<div class="odds-box">홈<br/><b>{match.home_odds}</b></div>', unsafe_allow_html=True)
            if match.sport == "축구":
                c2.markdown(f'<div class="odds-box">무<br/><b>{match.draw_odds}</b></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="odds-box">원정<br/><b>{match.away_odds}</b></div>', unsafe_allow_html=True)
        
        with col4:
            if st.button("🔮 분석", key=f"analyze_{match.home}_{match.away}", use_container_width=True):
                st.session_state.selected_match = match
                st.rerun()
        
        with col5:
            # 빠른 픽
            try:
                if match.sport == "축구":
                    quick = engine.find_kill_pick(match.home, match.away, match.home_odds, match.draw_odds, match.away_odds, match.home_xg, match.away_xg)
                else:
                    draw = match.draw_odds if match.draw_odds else 3.0
                    quick = engine.find_kill_pick(match.home, match.away, match.home_odds, draw, match.away_odds)
                
                color = "#ff6b6b" if quick.expected_value > 0.05 else "#feca57" if quick.expected_value > 0 else "#888"
                st.markdown(f'<div style="color:{color}; font-weight:bold; text-align:center;">{quick.selection_kr}<br/>@ {quick.odds}</div>', unsafe_allow_html=True)
            except:
                pass
        
        st.divider()

# ===== 상세 분석 모달 =====
if "selected_match" in st.session_state and st.session_state.selected_match:
    match = st.session_state.selected_match
    
    st.divider()
    st.header(f"🔮 {match.home} vs {match.away} 상세 분석")
    
    if match.sport == "축구":
        pick = engine.find_kill_pick(match.home, match.away, match.home_odds, match.draw_odds, match.away_odds, match.home_xg, match.away_xg)
    else:
        draw = match.draw_odds if match.draw_odds else 3.0
        pick = engine.find_kill_pick(match.home, match.away, match.home_odds, draw, match.away_odds)
    
    # 결과 카드
    conf_color = "#ff6b6b" if "매우" in pick.confidence else "#feca57" if "높음" in pick.confidence else "#48dbfb"
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e1e2e, #2d2d44); border-radius: 16px; padding: 24px; border: 2px solid {conf_color}; text-align: center;">
        <div style="font-size:1rem; color:#888; margin-bottom:8px;">{match.league} | {match.sport}</div>
        <div style="font-size:2rem; font-weight:900; color: white; margin: 12px 0;">{pick.selection_kr}</div>
        <div style="font-size:1.5rem; color:#feca57; font-weight:bold;">배당률 @ {pick.odds}</div>
        <div style="margin-top:12px; color:{conf_color}; font-size:1.1rem; font-weight:bold;">신뢰도: {pick.confidence}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # 지표
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("모델 확률", f"{pick.model_prob*100:.1f}%")
    m2.metric("암시 확률", f"{pick.implied_prob*100:.1f}%")
    m3.metric("엣지", f"{pick.edge*100:+.1f}%p")
    m4.metric("기대수익 (EV)", f"{pick.expected_value*100:+.1f}%")
    
    # 분석 근거
    st.subheader("📝 분석 근거")
    st.info(pick.reasoning)
    
    # Kelly
    if pick.kelly_fraction > 0:
        st.subheader("💰 자금 관리 (Kelly Criterion)")
        capital = st.number_input("총 자본 (만원)", min_value=1, value=100, step=10)
        bet = capital * 10000 * pick.kelly_fraction
        st.success(f"권장 배팅 금액: **{bet:,.0f}원** (자본의 {pick.kelly_fraction*100:.1f}%)")
    
    # 닫기
    if st.button("❌ 닫기", key="close_detail"):
        del st.session_state.selected_match
        st.rerun()

# ===== 푸터 =====
st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    ⚠️ 본 분석은 통계 모델 기반이며, 결과를 보장하지 않습니다.<br>
    스포츠토토는 소액으로 재미삼아 이용하세요.<br>
    🔮 천기누설 AI | Super Sports Stats Model v1.0
</div>
""", unsafe_allow_html=True)
