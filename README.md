# Super Sports Stats Model

bet365 에서 걸 수 있는 선택지 중 **실제로 가치가 있는 것만 골라, 단식과 멀티를 섞은 "최강 조합"을 자금 성장률 기준으로 짜 주는 도구**입니다.

```bash
pip install -r requirements-dev.txt
python -m sssm picks                        # 예시 배당으로 오늘의 최강 조합
python -m sssm picks --source apifootball --league 39 --season 2025 --record   # 실제 배당 (API_FOOTBALL_KEY)
streamlit run webapp/app.py                 # 대시보드
```

## 한눈에

```
bet365 배당 ─────────────────────────────────────────────┐
Pinnacle 배당 ─ 마진 제거 ─ 스코어 확률 격자 P[홈골, 원정골] ─┤
                                (모든 마켓, 같은 경기 상관)   │
과거 Pinnacle 시가→마감 ─ shrink (차이 중 믿을 비율) ───────┤
                                                          ▼
                선택지마다 EV(공정) · 보정 엣지(shrink 반영)
                                                          ▼
          단식 + 서로 다른 경기 멀티 후보 → 기대 로그 자산 최대화
                 (분수 켈리, 배팅·하루 상한, Acca Boost 옵션)
                                                          ▼
               오늘의 배팅 목록: 배당, 적중 확률, EV, 엣지, 금액
```

### 1. 공정 확률은 시장에서 온다

과거 검증에서 자체 팀 전력 모델(Dixon-Coles)은 bet365 시가보다도 부정확했고, Pinnacle 에 섞으면 로그 손실이 나빠지거나 그대로였습니다(아래 표). 그래서 공정 확률의 근거는 Pinnacle 입니다.

Pinnacle 의 여러 마켓(승무패, 오버/언더, 핸디캡) 배당에서 마진을 빼고, 그 확률들에 가장 잘 맞는 **스코어 확률 격자**를 만듭니다(`sssm/grid.py`). Dixon-Coles 분포를 맞춘 뒤 IPF 로 시장 확률에 정확히 일치시킵니다. 그러면

- Pinnacle 이 내지 않은 마켓(BTTS, 팀 득점, 다른 핸디캡 라인, 정확한 스코어)도 같은 격자에서 일관된 공정 확률이 나오고 (`derived`, 모형 오차 몫으로 엣지 1%p 를 더 요구),
- 같은 경기 선택지들의 상관(예: 홈승 + 오버 2.5 는 독립일 때보다 1.2배 자주 같이 맞음)이 자동으로 반영되며,
- 아시안 쿼터/정수 라인의 반승·반패·적특도 정확히 정산됩니다 (`sssm/markets.py`).

### 2. 차이를 전부 믿지 않는다 (shrink)

Pinnacle 과 bet365 가 다를 때, 그 차이가 경기 직전(Pinnacle 마감)까지 얼마나 살아남는지를 과거 데이터로 잽니다(`sssm/calibrate.py`). 실제로 걸게 되는 쪽만 보면 **EPL 2012-26 에서 0.76, 챔피언십 2013-20 에서 0.74** 였습니다. 배팅 크기는 이 비율만큼만 믿은 "보정 엣지"로 정합니다. 기본값 0.75, `python -m sssm calibrate` 로 다시 잴 수 있습니다.

### 3. 최강 조합 = 포트폴리오

같은 날 +엣지 선택지가 여러 개면, 켈리 이론상 가장 빠르게 자금을 불리는 방법은 단식과 그 선택지들로 만든 멀티를 **적절한 비율로 함께** 거는 것입니다. 멀티 하나에 몰면 적중 확률이 곱으로 줄고, 단식만 걸면 엣지의 복리 효과를 놓칩니다. 그래서 후보(단식 + 2~N폴 멀티)를 만들고 스코어 격자에서 뽑은 시나리오로 `E[log(1 + Σ f_j (G_j − 1))]` 를 최대화하는 비율을 한 번에 풉니다(`sssm/portfolio.py`). 기본은 1/4 켈리, 배팅 하나 3%, 하루 15%, 최대 8건입니다.

bet365 일반 멀티는 같은 경기 두 폴을 허용하지 않으므로 멀티 후보는 경기당 한 폴입니다. 같은 경기 조합(Bet Builder) 가격은 `python -m sssm sgp` 나 대시보드 계산기로 따로 평가합니다.

### 4. 실전 기록 (CLV)

`picks --record` 는 배당 스냅샷을 `data/snapshots/` 에, 추천 배팅을 `data/ledger.jsonl` 에 쌓습니다. 직전 스냅샷보다 Pinnacle 은 움직였는데 bet365 는 그대로인 선택지(남은 엣지의 주 원천)를 표시하고, `python -m sssm clv` 는 추천 배팅마다 킥오프 직전 Pinnacle 공정 확률 기준 CLV 를 계산합니다. 경기 전 몇 시간 간격으로 `picks --record` 를 돌리면 됩니다(cron 등).

## 검증 결과

자세한 표와 해석은 [reports/engine_backtest.md](reports/engine_backtest.md).

- 엔진 전체(가격 → 보정 → 포트폴리오)를 날짜 순서대로, 그날 이전 정보만으로 돌렸습니다. shrink 도 그 시점 이전 데이터로만 다시 추정합니다.
- **Pinnacle 마감 대비 CLV 는 양수**였습니다. 이기는 배터의 가장 믿을 만한 선행 지표입니다.
- **ROI 는 판단할 수 없습니다.** 시즌당 수 건~수십 건이라 95% 구간이 ±40%p 안팎입니다. 가상 시장 테스트에서 진짜 엣지가 +8% 여도 60건 정도로는 ROI 가 마이너스로 나올 수 있음을 확인했습니다(`tests/test_backtest_pipeline.py`).
- 과거 데이터는 경기당 한두 번의 배당 스냅샷뿐이라 실전보다 기회가 훨씬 적게 잡힙니다. 실전 엣지는 bet365 가 Pinnacle 움직임을 늦게 따라가는 순간에 있고, 그건 `--record` 로 스냅샷을 촘촘히 쌓아야 보입니다.

과거 배당은 `python -m sssm fetch-history` (football-data.co.uk) 또는 `--source mirror` (막힌 환경에서 EPL 미러)로 `data/history/` 에 받습니다. 원 데이터 권리 때문에 저장소에는 넣지 않습니다.

```bash
python -m sssm fetch-history --source mirror --seasons 1920 2021 2122 2223 2324 2425
python -m sssm calibrate                       # shrink 추정
python -m sssm backtest --start 2021-08-01     # 엔진 전체 walk-forward (open: 시가로 걸고 마감으로 CLV)
python -m sssm backtest --phase close          # 마감 직전 가격으로 걸기
python -m sssm model-eval --csv data/history/*.csv --start 2021-08-01   # 자체 모델이 가중치를 버는지
```

## 명령

| 명령 | 하는 일 |
|---|---|
| `picks` | 오늘의 최강 조합. `--source demo/file/apifootball/theodds`, `--bankroll`, `--shrink`, `--min-edge`, `--kelly`, `--max-legs`, `--acca-boost`, `--record`. `reports/latest.json` 과 `.md` 저장 |
| `backtest` | 과거 배당으로 엔진 전체 검증 (ROI 구간, 로그 성장, MDD, CLV). `--bets-out` 으로 배팅 내역 저장 |
| `calibrate` | shrink 추정 |
| `model-eval` | 자체 팀 전력 모델의 로그 손실과 Pinnacle 에 섞을 최적 가중치 |
| `sgp` | 같은 경기 조합 공정 확률과 상관 배수, 제시 배당의 EV. 예: `--fixture demo-1 --legs 1X2=home OU:2.5=over --odds 3.1` |
| `clv` | 기록한 추천 배팅의 CLV |
| `ratings` | 팀 전력 순위 |
| `fetch-history` | 과거 결과+배당 CSV 받기 |

## 데이터 소스

- **API-Football** (`API_FOOTBALL_KEY`): 축구 bet365 와 Pinnacle 배당을 모두 줍니다(무료 100회/일). 기본 소스입니다.
- **TheOddsAPI** (`THE_ODDS_API_KEY`): bet365 는 호주 지역 유료 플랜의 AFL/NRL 만 있습니다. 축구가 아닌 종목은 승패(H2H)만 가격을 매깁니다.
- `.env.example` 을 `.env` 로 복사해 키를 넣습니다. 키는 커밋하지 마세요.

## 구조

```
sssm/
  markets.py     마켓 키, 스코어별 정산(W/R 격자), Fixture
  odds.py        마진 제거(power/shin/proportional), EV, 켈리
  grid.py        배당 → 스코어 확률 격자 (Dixon-Coles + IPF), 로그 풀링
  pricing.py     공정/보수적 격자, bet365 선택지별 EV·엣지, 가치 필터
  calibrate.py   shrink 추정
  portfolio.py   단식+멀티 후보, 시나리오, 켈리 포트폴리오, Bet Builder 확률
  backtest.py    엔진 전체 walk-forward, 블록 부트스트랩, CLV
  tracking.py    배당 스냅샷, bet365 지연 감지, 추천 기록과 CLV
  model/         Dixon-Coles 팀 전력 모델과 검증 (기본 가중치 0)
  sources/       API-Football, TheOddsAPI 어댑터
  pipeline.py    전체 연결, 리포트(JSON/Markdown)
webapp/app.py    Streamlit 대시보드
```

## 주의

분석 연구용 도구입니다. 자동 배팅 기능은 없고 수익을 보장하지 않습니다. bet365 는 이기는 계정의 한도를 줄이는 것으로 알려져 있어, 엣지가 있어도 오래 걸 수 있다는 보장이 없습니다. 감당할 수 있는 금액으로만 쓰세요.
