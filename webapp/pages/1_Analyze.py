import streamlit as st
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "telegram_bot"))
from logic import KillPickEngine

from data import get_today_matches

st.set_page_config(page_title="일괄 분석", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp { background: #0f0f1a; color: #e0e0e0; }
</style>
""", unsafe_allow_html=True)

st.title("📊 일괄 필살승부 분석")
st.caption("여러 경기를 한 번에 비교 분석")

engine = KillPickEngine()

# 텍스트 영역
input_text = st.text_area(
    "경기 목록 (CSV 형식)",
    height=150,
    placeholder="""홈팀,원정팀,홈배당,무배당,원정배당
한국,체코,2.10,3.30,3.60
맨시티,아스날,1.85,3.50,4.20"""
)

# 또는 오늘 경기 자동 로드
if st.button("📅 오늘 경기 전체 분석", type="primary", use_container_width=True):
    matches = get_today_matches()
    input_text = "\n".join([f"{m.home},{m.away},{m.home_odds},{m.draw_odds or 3.0},{m.away_odds}" for m in matches[:20]])
    st.text_area("자동 로드된 경기", input_text, height=150, disabled=True)

if st.button("🔍 분석 실행", type="secondary", use_container_width=True) and input_text.strip():
    lines = [l.strip() for l in input_text.strip().split('\n') if l.strip() and not l.startswith('홈')]
    
    results = []
    progress = st.progress(0)
    
    for i, line in enumerate(lines):
        try:
            parts = line.split(',')
            if len(parts) >= 4:
                home, away = parts[0], parts[1]
                ho, do, ao = float(parts[2]), float(parts[3]), float(parts[4]) if len(parts) > 4 else 3.0
                pick = engine.find_kill_pick(home, away, ho, do, ao)
                results.append({
                    '경기': pick.match,
                    '추천': pick.selection_kr,
                    '배당률': pick.odds,
                    '모델확률': f"{pick.model_prob*100:.1f}%",
                    '엣지': f"{pick.edge*100:+.1f}%p",
                    'EV': f"{pick.expected_value*100:+.1f}%",
                    '신뢰도': pick.confidence,
                })
        except Exception as e:
            pass
        progress.progress((i + 1) / len(lines))
    
    if results:
        df = pd.DataFrame(results)
        # 엣지 기준 정렬을 위해 숫자 변환
        df['엣지_숫자'] = df['엣지'].str.replace('%p', '').str.replace('+', '').astype(float)
        df = df.sort_values('엣리_숫자', ascending=False).drop('엣지_숫자', axis=1)
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # TOP 3
        st.subheader("🏆 필살승부 TOP 3")
        for idx, row in df.head(3).iterrows():
            emoji = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉"
            st.success(f"{emoji} **{row['경기']}** → **{row['추천']}** @ {row['배당률']} | {row['신뢰도']}")
    else:
        st.error("분석할 수 있는 경기가 없습니다.")
