# 🔮 슈퍼픽킹 운영 가이드

## 개요
- 매일 오전 10시: 당일 경기 분석 → 3픽 생성 → DB 저장
- 매일 자정: 경기 결과 추적 → DB 업데이트
- 24시간 구동 (OpenClaw cron)

---

## 1. 실제 데이터 API 설정 (필수)

### API-Football (무료: 100 req/day)
```bash
# .env 파일에 추가
API_FOOTBALL_KEY=your_key_here
```
- https://www.api-football.com/ 가입
- 무료 티어: 100 requests/day
- 유료: $19/month (무제한)

### TheOddsAPI (배당률)
```bash
THE_ODDS_API_KEY=your_key_here
```
- https://the-odds-api.com/
- 무료: 500 requests/month

---

## 2. OpenClaw Cron 설정

### 매일 픽 생성 (오전 10시)
```bash
openclaw cron add \
  --name "daily-picks" \
  --schedule "0 10 * * *" \
  --command "cd ~/super-sports-stats-model && python3 cron/generate_picks.py 축구"
```

### 결과 추적 (자정)
```bash
openclaw cron add \
  --name "track-results" \
  --schedule "0 0 * * *" \
  --command "cd ~/super-sports-stats-model && python3 cron/track_results.py"
```

### 상태 확인
```bash
openclaw cron list
```

---

## 3. 수동 픽 생성

```bash
cd ~/super-sports-stats-model
python3 cron/generate_picks.py 축구
python3 cron/generate_picks.py 농구
python3 cron/generate_picks.py 야구
```

---

## 4. 결과 확인

```bash
# DB 직접 확인
sqlite3 db/superpicks.db "SELECT * FROM picks WHERE date = date('now');"

# 리포트 생성
python3 -c "
from src.picks.database import PickDatabase
db = PickDatabase()
stats = db.get_stats(days=7)
print(f'7일 승률: {stats[\"win_rate\"]:.1f}%')
"
```

---

## 5. Streamlit Cloud 설정

### secrets.toml
```toml
# .streamlit/secrets.toml
API_FOOTBALL_KEY = "your_key"
THE_ODDS_API_KEY = "your_key"
```

### 배포
```bash
# GitHub push 후
# https://share.streamlit.io 에서 Deploy
```

---

## 6. 디렉토리 구조

```
super-sports-stats-model/
├── cron/                    # 자동화 스크립트
│   ├── generate_picks.py   # 매일 픽 생성
│   └── track_results.py    # 결과 추적
├── src/
│   ├── picks/              # 픽 생성 엔진
│   │   ├── database.py     # SQLite DB
│   │   └── super_king.py   # 슈퍼픽킹 엔진
│   └── tracker/            # 결과 추적
│       └── result_tracker.py
├── db/                     # 데이터베이스 파일
│   └── superpicks.db
├── webapp/                 # Streamlit 웹사이트
│   ├── app.py             # 메인 페이지
│   └── pages/
└── reports/               # 생성된 리포트
```

---

## 7. 주의사항

- API 호출량 제한 준수 (무료 티어)
- 배당률은 실시간 변동되므로 픽 생성 시점 기준
- 결과 추적은 API 제공 여부에 따라 지연 가능
- DB는 SQLite로 로컬 파일 기반 (백업 권장)

---

## 8. 업그레이드 로드맵

- [ ] API-Football 유료 전환 (무제한 데이터)
- [ ] 실시간 배당률 스트리밍 (WebSocket)
- [ ] 머신러닝 모델 추가 (LightGBM)
- [ ] 텔레그램 봇 연동 (실시간 알림)
- [ ] 다중 사용자 지원 (PostgreSQL)
