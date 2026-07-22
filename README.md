# 🏆 Super Sports Stats Model

> AI 기반 스포츠 경기 분석 & 예측 시스템  
> 뉴스 수집 + 통계 분석 + Monte Carlo 시뮬레이션 + LLM 인사이트

---

## 🎬 영상 기반 업그레이드

유튜브에서 본 **"AI 스포츠 토토 예측"** 영상을 바탕으로, 더 발전된 모듈로 재구성한 프로젝트입니다.

### 기존 vs 개선

| 기능 | 영상 버전 | 이 프로젝트 |
|------|----------|------------|
| 뉴스 수집 | 수동 클로드 검색 | **자동 다국어 뉴스 크롤링** |
| 배당률 | 단일 소스 | **다중 북메이커 비교 + 가치 배팅 탐지** |
| 예측 방식 | 단일 추론 | **Monte Carlo 1000회 시뮬레이션** |
| 전략 | 3가지 고정 | **Kelly Criterion + 자동 자금 관리** |
| 분석 | 텍스트 기반 | **LLM 기반 인사이트 리포트** |
| 몰빵 방지 | 수동 | **자동 분산 + 한 경기당 픽 제한** |

---

## 🏗️ 아키텍처

```
super-sports-stats-model/
├── src/
│   ├── collectors/          # 데이터 수집
│   │   ├── news_scraper.py       # 네이버/구글 뉴스
│   │   └── odds_collector.py     # 배당률 수집 + 가치 배팅
│   ├── engine/              # 분석 엔진
│   │   ├── simulator.py          # Monte Carlo (Poisson 기반)
│   │   └── strategy.py           # 신중/적정/공격 + Kelly
│   ├── llm/                 # AI 분석
│   │   └── match_analyzer.py     # Claude/GPT 경기 분석
│   └── main.py              # 메인 파이프라인
├── config/
│   └── settings.yaml        # 설정 파일
├── data/                    # SQLite DB + 결과
├── notebooks/               # 탐색적 분석
└── requirements.txt
```

---

## 🚀 설치

```bash
git clone <repo>
cd super-sports-stats-model
pip install -r requirements.txt

# LLM 사용시 API 키 설정
echo "ANTHROPIC_API_KEY=your_key" > .env
# 또는
echo "OPENAI_API_KEY=your_key" > .env
```

---

## 📊 사용법

### 기본 분석

```bash
python src/main.py --home "Korea" --away "Mexico" --league "World Cup"
```

### 옵션

```bash
python src/main.py \
  --home "Manchester City" \
  --away "Arsenal" \
  --league "Premier League" \
  --bankroll 500000 \
  --api-key "your_api_football_key"
```

---

## 🧠 핵심 모듈 설명

### 1. Monte Carlo 시뮬레이터 (`engine/simulator.py`)

- **Poisson 분포** 기반 득점 시뮬레이션
- 홈 어드밴티지, 폼, 점유율 반영
- 1000회+ 반복으로 확률 분포 생성
- 신뢰구간 계산

### 2. 전략 엔진 (`engine/strategy.py`)

| 전략 | 특징 | 배팅 비중 |
|------|------|----------|
| **신중** | 확률 55%+, 배당 2.5 이하 | 총자본 3% |
| **적정** | 확률 42%+, 배당 4.0 이하 | 총자본 5% |
| **공격** | 확률 30%+, 배당 15 이하 | 총자본 8% |

- **Kelly Criterion** 적용 (fractional 0.25)
- **몰빵 방지**: 한 경기당 최대 1픽, 총 자본 20% 초과 시 자동 조정

### 3. 배당률 분석 (`collectors/odds_collector.py`)

- 다중 북메이커 배당률 비교
- **Implied Probability** → Vig 제거
- **Value Bet** 탐지 (모델 확률 > 배당률 암시확률 + 5%)

### 4. LLM 인사이트 (`llm/match_analyzer.py`)

- 뉴스 + 통계 + 시뮬레이션 결과 종합
- Claude 3 Sonnet 또는 GPT-4o 활용
- 핵심 요약 / 강약점 / 결정적 변수 / 최종 예측

---

## 📈 예측 파이프라인

```
[경기 입력]
     ↓
[뉴스 수집] ──→ [LLM 요약]
     ↓
[통계 로드] ──→ [특성 엔지니어링]
     ↓
[Monte Carlo] ──→ [확률 분포]
     ↓
[배당률 비교] ──→ [Value Bet 탐지]
     ↓
[전략 엔진] ──→ [신중/적정/공격 픽 생성]
     ↓
[리스크 관리] ──→ [몰빵 방지 + Kelly 조정]
     ↓
[최종 리포트] ──→ [JSON 저장 + 콘솔 출력]
```

---

## ⚠️ 중요 안내

이 프로젝트는 **데이터 분석 및 예측 연구 목적**입니다.

- ❌ 자동 배팅/자동 거래 기능 **없음**
- ❌ 배팅 사이트 API 연동 **없음**
- ✅ 데이터 분석 / 확률 모델링 / 리서치 도구

스포츠토토는 과도한 이용은 건강에 해롭습니다. 소액으로 재미삼아 이용하세요.

---

## 🛠️ 확장 계획

- [ ] API-Football 연동 (실시간 데이터)
- [ ] Flashscore 스크래퍼 통합
- [ ] Streamlit 웹 대시보드
- [ ] 텔레그램/디스코드 알림 봇
- [ ] 과거 결과 백테스팅 프레임워크

---

## 📄 라이선스

MIT License


---

## 🌐 웹사이트

Streamlit 기반 웹사이트 포함.

| 페이지 | 기능 |
|--------|------|
| **🏠 홈** | 한 경기 입력 → 필살승부 + Kelly 비율 + 3전략 |
| **📊 상세 분석** | 여러 경기 CSV 입력 → 전체 비교 + TOP 3 |
| **📄 보고서** | PDF 다운로드 + 요약 수치 |

```bash
cd webapp
pip install -r requirements.txt
streamlit run app.py
```

## 🚀 배포 (Oracle Cloud / Ubuntu)

```bash
# 서버에서 한 줄 실행
curl -sSL https://raw.githubusercontent.com/coohell/super-sports-stats-model/main/deploy.sh | bash
```

자동으로 설치:
- Python 가상환경
- Streamlit (포트 80)
- systemd 서비스 (재부팅 자동 실행)
- Nginx 리버스 프록시

업데이트:
```bash
cd ~/super-sports-stats-model
git pull origin main
sudo systemctl restart super-sports-stats
```

## 🤖 텔레그램 봇

```bash
export TELEGRAM_BOT_TOKEN='your_token'
python3 telegram_bot/bot.py
```

**명령어:**
- `/killpick 홈팀 원정팀 홈배당 무배당 원정배당` — 필살승부
- `/analyze` — 상세 분석
- `/strategies` — 3가지 전략

---

GitHub: https://github.com/coohell/super-sports-stats-model
