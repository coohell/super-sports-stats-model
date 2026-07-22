import streamlit as st
import sys
from pathlib import Path

# logic.py 임포트를 위해 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "telegram_bot"))
from logic import KillPickEngine

# 페이지 설정
st.set_page_config(
    page_title="슈퍼 스포츠 통계 모델",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# CSS 스타일
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .kill-pick-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
    .confidence-high { color: #00c853; font-weight: bold; }
    .confidence-medium { color: #ffab00; font-weight: bold; }
    .confidence-low { color: #ff1744; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 헤더
st.markdown('<div class="main-header">⚽ 슈퍼 스포츠 통계 모델</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AI 기반 필살승부 분석 시스템</div>', unsafe_allow_html=True)

st.divider()

# 엔진 초기화
@st.cache_resource
def get_engine():
    return KillPickEngine()

engine = get_engine()

# 입력 섹션
st.subheader("📋 경기 정보 입력")

col1, col2 = st.columns(2)

with col1:
    home_team = st.text_input("홈팀", placeholder="예: 한국")
    home_odds = st.number_input("홈승 배당률", min_value=1.01, value=2.10, step=0.05)

with col2:
    away_team = st.text_input("원정팀", placeholder="예: 체코")
    away_odds = st.number_input("원정승 배당률", min_value=1.01, value=3.60, step=0.05)

draw_odds = st.number_input("무승부 배당률", min_value=1.01, value=3.30, step=0.05)

# 옵션
with st.expander("⚙️ 고급 설정"):
    col3, col4 = st.columns(2)
    with col3:
        home_xg = st.number_input("홈팀 기대득점 (xG)", min_value=0.0, value=0.0, step=0.1,
                                   help="0이면 배당률 역산")
    with col4:
        away_xg = st.number_input("원정팀 기대득점 (xG)", min_value=0.0, value=0.0, step=0.1,
                                   help="0이면 배당률 역산")

st.divider()

# 분석 버튼
if st.button("🔥 필살승부 분석 시작", type="primary", use_container_width=True):
    if not home_team or not away_team:
        st.error("⚠️ 팀명을 입력해주세요!")
    else:
        with st.spinner("Monte Carlo 5000회 시뮬레이션 실행 중..."):
            # xG가 0이면 None으로 전달 (배당률 역산)
            hxg = home_xg if home_xg > 0 else None
            axg = away_xg if away_xg > 0 else None
            
            pick = engine.find_kill_pick(
                home_team, away_team,
                float(home_odds), float(draw_odds), float(away_odds),
                hxg, axg
            )
        
        st.divider()
        
        # 결과 표시
        st.subheader("⚔️ 필살승부 결과")
        
        # 메인 추천 박스
        conf_color = "confidence-high" if "높음" in pick.confidence else \
                     "confidence-medium" if "보통" in pick.confidence else "confidence-low"
        
        st.markdown(f"""
        <div class="kill-pick-box">
            <h2>🎯 {pick.match}</h2>
            <h1>{pick.selection_kr}</h1>
            <h2>@ {pick.odds}</h2>
            <p class="{conf_color}">신뢰도: {pick.confidence}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 지표 카드
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        
        with col_m1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("모델 확률", f"{pick.model_prob*100:.1f}%")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col_m2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("배당 암시확률", f"{pick.implied_prob*100:.1f}%")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col_m3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            delta_color = "inverse" if pick.edge < 0 else "normal"
            st.metric("엣지 (Edge)", f"{pick.edge*100:+.1f}%p", delta_color=delta_color)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col_m4:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            ev_color = "inverse" if pick.expected_value < 0 else "normal"
            st.metric("기대수익률 (EV)", f"{pick.expected_value*100:+.1f}%", delta_color=ev_color)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.divider()
        
        # 분석 근거
        st.subheader("📝 분석 근거")
        st.info(pick.reasoning)
        
        # Kelly Criterion
        st.subheader("💰 자금 관리 (Kelly Criterion)")
        
        if pick.kelly_fraction > 0:
            col_k1, col_k2 = st.columns(2)
            with col_k1:
                capital = st.number_input("총 자본 (만원)", min_value=1, value=100, step=10)
            with col_k2:
                kelly_percent = pick.kelly_fraction * 100
                st.metric("권장 배팅 비율", f"{kelly_percent:.1f}%")
            
            bet_amount = capital * 10000 * pick.kelly_fraction
            st.success(f"💡 권장 배팅 금액: **{bet_amount:,.0f}원** (자본의 {kelly_percent:.1f}%)")
        else:
            st.warning("⚠️ Kelly Criterion 기준 배팅 금액이 0입니다. (EV가 음수이거나 엣지가 없음)")
        
        # 전략 비교
        st.divider()
        st.subheader("🎯 3가지 전략 비교")
        
        strategies = engine.generate_all_strategies(
            home_team, away_team,
            float(home_odds), float(draw_odds), float(away_odds),
            hxg, axg
        )
        
        strat_cols = st.columns(3)
        strat_data = [
            ("conservative", "🛡️ 신중", "#4CAF50"),
            ("balanced", "⚖️ 적정", "#2196F3"),
            ("aggressive", "⚔️ 공격", "#FF9800")
        ]
        
        for i, (key, name, color) in enumerate(strat_data):
            with strat_cols[i]:
                st.markdown(f"""
                <div style="padding:1rem; border-radius:0.5rem; background:{color}15; border:2px solid {color};">
                    <h4 style="color:{color}; margin:0;">{name}</h4>
                </div>
                """, unsafe_allow_html=True)
                
                strat = strategies[key]
                if strat['picks']:
                    for p in strat['picks'][:1]:
                        st.write(f"**{p['selection']}** @ {p['odds']}")
                        st.caption(f"확률 {p['prob']*100:.0f}% | EV {p['ev']*100:+.1f}%")
                else:
                    st.caption("조건 미충족")

# 푸터
st.divider()
st.caption("""
⚠️ **면책 조항**: 본 분석은 통계 모델 기반이며, 스포츠 결과를 보장하지 않습니다. 
스포츠토토는 소액으로 재미삼아 이용하세요. | Super Sports Stats Model v1.0
""")
