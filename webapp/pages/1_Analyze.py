import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "telegram_bot"))
from logic import KillPickEngine

st.set_page_config(page_title="상세 분석", page_icon="📊", layout="wide")

st.title("📊 상세 경기 분석")
st.caption("다중 경기 비교 분석")

engine = KillPickEngine()

st.info("""
이 페이지에서는 여러 경기를 한 번에 입력하여 비교 분석할 수 있습니다.
각 줄에 `홈팀,원정팀,홈배당,무배당,원정배당` 형식으로 입력하세요.
""")

input_text = st.text_area(
    "경기 목록 입력",
    height=200,
    placeholder="""한국,체코,2.10,3.30,3.60
맨시티,아스날,1.85,3.50,4.20
리버풀,첼시,2.05,3.40,3.80"""
)

if st.button("🔍 전체 분석", type="primary"):
    lines = [l.strip() for l in input_text.strip().split('\n') if l.strip()]
    
    if not lines:
        st.error("경기 데이터를 입력해주세요!")
    else:
        results = []
        progress = st.progress(0)
        
        for i, line in enumerate(lines):
            try:
                parts = line.split(',')
                if len(parts) == 5:
                    pick = engine.find_kill_pick(
                        parts[0], parts[1],
                        float(parts[2]), float(parts[3]), float(parts[4])
                    )
                    results.append({
                        'match': pick.match,
                        'pick': pick.selection_kr,
                        'odds': pick.odds,
                        'model_prob': pick.model_prob,
                        'implied_prob': pick.implied_prob,
                        'edge': pick.edge,
                        'ev': pick.expected_value,
                        'confidence': pick.confidence,
                        'kelly': pick.kelly_fraction
                    })
            except Exception as e:
                st.error(f"라인 {i+1} 오류: {e}")
            
            progress.progress((i + 1) / len(lines))
        
        if results:
            st.divider()
            st.subheader(f"📈 분석 결과 ({len(results)}경기)")
            
            # 데이터프레임으로 표시
            import pandas as pd
            df = pd.DataFrame(results)
            
            # 컬럼명 한글화
            df.columns = ['경기', '추천', '배당률', '모델확률', '암시확률', '엣지', 'EV', '신뢰도', 'Kelly']
            
            # 엣지 기준 정렬
            df = df.sort_values('엣지', ascending=False)
            
            st.dataframe(
                df.style.background_gradient(subset=['엣지', 'EV'], cmap='RdYlGn'),
                use_container_width=True
            )
            
            # 필살승부 TOP 3
            st.subheader("🏆 필살승부 TOP 3")
            top3 = df.head(3)
            
            for idx, row in top3.iterrows():
                emoji = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉"
                st.success(f"""
                {emoji} **{row['경기']}** → **{row['추천']}** @ {row['배당률']}  
                엣지: {row['엣지']*100:+.1f}%p | EV: {row['EV']*100:+.1f}% | {row['신뢰도']}
                """)
