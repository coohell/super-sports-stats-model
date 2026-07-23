# 🏆 SuperPickKing — 프로젝트 완전 정리 문서
> 작성일: 2026-07-23 | 마지막 커밋: `62b2f36`

---

## 1. 프로젝트 개요

**목표:** 실시간 스포츠 배당률 기반 AI 픽 생성 시스템

**핵심 기능:**
- TheOddsAPI + API-Football 실시간 데이터 연동
- Poisson + Monte Carlo + 배당역산 앙상블 엔진
- Aliyun(Qwen) / OpenAI LLM 심층 분석
- 매일 10:00 / 22:00 자동 픽 생성 (OpenClaw Cron)
- Streamlit 웹 대시보드
- SQLite 기반 픽/결과 추적 DB

---

## 2. 디렉토리 구조

```
super-sports-stats-model/
├── .env                          # 서버용 환경변수 (Git에 커밋됨 ❌ 보안 주의)
├── .env.example                  # 템플릿
├── .streamlit/
│   └── secrets.toml              # Streamlit Cloud용 Secrets 템플릿
├── cron/
│   ├── generate_picks.py         # 메인: 매일 픽 생성
│   └── track_results.py          # 결과 추적
├── data/
│   └── __init__.py               # 데이터 수집: TheOddsAPI + API-Football + 모의데이터
├── src/
│   ├── engine/                   # (사용 안 함 — world_class_engine.py로 대체)
│   ├── llm/                      # (사용 안 함 — super_king.py에 통합)
│   ├── main.py                   # (사용 안 함 — cron이 직접 부름)
│   ├── picks/
│   │   ├── database.py           # SQLite DB 모델 + PickDatabase 클래스
│   │   ├── super_king.py         # SuperPickKing 클래스 (LLM + 데이터 수집)
│   │   └── world_class_engine.py # WorldClassEngine (Poisson/MC/배당역산)
│   ├── tracker/
│   │   └── result_tracker.py     # 결과 추적 (mock 데이터 사용 중)
│   └── utils/                    # (비어있음)
├── telegram_bot/
│   ├── bot.py                    # 텔레그램 봇 (미완성)
│   └── logic.py                  # KillPickEngine (Poisson/Kelly)
├── webapp/
│   ├── app.py                    # Streamlit 메인 (CSS + UI + DB 연동)
│   └── pages/                    # (비어있음)
├── config/
│   └── settings.yaml             # (사용 안 함)
├── db/                           # SQLite 파일 저장소
├── reports/                      # 생성된 리포트
├── requirements.txt              # 서버용 의존성
├── packages.txt                  # Streamlit Cloud용 시스템 패키지 (fonts-noto-cjk)
└── deploy.sh                     # Oracle Cloud 배포 스크립트
```

---

## 3. 데이터 흐름

```
[TheOddsAPI] ──┐
               ├──→ [data/__init__.py] ──→ [WorldClassEngine] ──→ [PickDatabase]
[API-Football]─┘                                      ↑
                                                      │
                                               [Streamlit app.py]
```

**문제:** `cron/generate_picks.py`와 `webapp/app.py`가 다른 방식으로 데이터를 불러옴
- Cron: `data/__init__.py` → 실시간 API
- Streamlit: `app.py` 안에서 직접 `get_all_matches()` 호출 → 동일 경로 사용

---

## 4. 설정 방법

### 4.1 서버 (OpenClaw Cron 용)

```bash
cd super-sports-stats-model
cp .env.example .env
# .env 편집해서 실제 키 입력
```

**현재 `.env` 내용:**
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
API_FOOTBALL_KEY=d4333d5b0800c4fa1a549a37883c5abc
THE_ODDS_API_KEY=d1f1a17879ebcfadc5c28534ce5ae276
DB_PATH=/tmp/superpicks.db
ALIYUN_API_KEY=sk-ws-***
ALIYUN_BASE_URL=https://ws-bsw4a9yr62tiw1sn.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
ALIYUN_MODEL=qwen-plus
```

### 4.2 Streamlit Cloud

Settings → Secrets:
```toml
API_FOOTBALL_KEY = "d4333d5b0800c4fa1a549a37883c5abc"
THE_ODDS_API_KEY = "d1f1a17879ebcfadc5c28534ce5ae276"
DB_PATH = "/tmp/superpicks.db"
```

---

## 5. Cron 작업 현황

| 이름 | 스케줄 | 상태 |
|---|---|---|
| `daily-picks-10am` | 매일 10:00 | ✅ 등록 완료 |
| `daily-picks-10pm` | 매일 22:00 | ✅ 등록 완료 |

**OpenClaw Cron 확인:**
```bash
openclaw cron list
openclaw cron run daily-picks-10am    # 수동 테스트
```

---

## 6. 알려진 버그 및 기술 부채

### 🔴 치명적 문제

1. **`.env`에 실제 API 키가 하드코딩됨**
   - Aliyun 키가 `.env`에 평문 저장됨 + GitHub에 푸시됨
   - 해결: `git rm --cached .env` + `.gitignore`에 `.env` 추가 + 키 재발급

2. **Streamlit `model_version` AttributeError**
   - DB의 `picks` 테이블에 `model_version` 컬럼 없음
   - 임시 해결: `getattr(pick, 'model_version', 'WorldClass-v1.0')`로 fallback
   - 근본 해결: DB 스키마에 `model_version` 컬럼 추가 필요

3. **`webapp/data.py` 충돌**
   - `webapp/data.py`가 루트 `data/` 패키지를 가로막았었음
   - 해결: 삭제 완료 (`3344753`)

### 🟡 구조적 문제

4. **엔진 중복**
   - `src/picks/super_king.py`, `src/picks/world_class_engine.py`, `telegram_bot/logic.py`가 서로 다른 엔진
   - 실제로는 `cron/generate_picks.py`가 `WorldClassEngine`만 사용
   - `super_king.py`의 `SuperPickKing` 클래스는 사용 안 됨

5. **DB 스키마 불일치**
   - Cron용 DB(`PickDatabase`)와 Streamlit용 DB(`database.py`)가 동일 파일이지만
   - `add_pick()`이 dict를 받는 래퍼로 처리되어서 타입 불안정
   - `daily_combos` 테이블은 pick_id가 3개 고정인데 2개만 있을 때 에러

6. **경로 설정 난잡함**
   - `sys.path.insert()` 남발
   - `cron/generate_picks.py`, `webapp/app.py` 각자 경로 설정
   - Python 패키지 구조가 제대로 안 잡힘

7. **결과 추적이 Mock**
   - `tracker/result_tracker.py`가 실제 API로 결과 확인 안 하고 랜덤 Mock 사용

### 🟢 개선 필요

8. **에러 처리 부족**
   - API 실패 시 자동 폴백은 되지만 로깅이 콘솔 print 뿐
   - Streamlit에서 예외 발생하면 전체 앱 죽음

9. **설정 이중 관리**
   - `.env` (서버) + `.streamlit/secrets.toml` (Streamlit) + `os.environ` 직접 접근
   - 통합 설정 클래스 필요

---

## 7. Git 커밋 히스토리

```
62b2f36 fix: Streamlit DB picks missing model_version fallback
3344753 fix: remove stale webapp/data.py, add Streamlit secrets template
6da08f4 feat: API-Football + TheOddsAPI dual integration
fbbcbc0 feat: real-time TheOddsAPI integration, Aliyun LLM ready
4bfc27e feat: Aliyun(Qwen) OpenAI-compatible API support
ae70f0b fix: data module, db methods, cron paths, min_ev filter
ffa7003 feat: WorldClassEngine v1.0 - 세계최강 픽봇
cd75e77 docs: SuperPickKing 기술 분석 보고서
498e563 feat: SuperPickKing v3.0 - API integration, LLM analysis
```

---

## 8. 재구축을 위한 권장사항

만약 처음부터 다시 짠다면:

1. **단일 엔진 클래스**
   - `WorldClassEngine` 하나로 통일
   - `super_king.py`, `logic.py`는 삭제

2. **DB 스키마 단순화**
   - `picks` 테이블만 사용 (combos 제거)
   - `model_version` 컬럼 추가
   - SQLAlchemy ORM 사용 고려

3. **설정 통합**
   - `pydantic-settings`로 `.env` / `secrets.toml` 통합 관리

4. **패키지 구조**
   - `sys.path.insert` 제거
   - `pyproject.toml` + `src/` layout 사용

5. **테스트**
   - pytest + API mock (`responses` 라이브러리)

6. **로깅**
   - `logging` 모듈 사용, print 제거

---

*이 문서는 현재 코드베이스의 진실된 상태를 기록함.*
