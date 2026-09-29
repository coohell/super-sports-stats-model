#!/usr/bin/env bash
# 매일 루틴용: 실제 배당으로 최강 조합을 뽑고(또는 스냅샷만 쌓고) CLV 를 계산한다.
#
#   scripts/daily.sh picks     추천 뽑기 + 장부 기록 + CLV 요약 (reports/latest.md)
#   scripts/daily.sh snapshot  배당 스냅샷만 기록 (킥오프 직전 마감 배당 → CLV 계산 근거)
#
# 환경 변수
#   API_FOOTBALL_KEY  필수. 없으면 한 줄 안내를 찍고 코드 3 으로 끝난다 (가짜 추천을 만들지 않는다).
#                     v3.football.api-sports.io 에 닿지 않으면 코드 4
#   SSSM_DATA_DIR     스냅샷·장부 위치. 기본: /mnt/project-files/sssm-data 가 있으면 거기, 아니면 data/
#   SSSM_LEAGUES      API-Football 리그 id (기본 "39 140 78 135 61" = 유럽 5대 리그)
#   SSSM_BANKROLL     자본 (원, 기본 1000000)
set -uo pipefail
cd "$(dirname "$0")/.."

mode="${1:-picks}"
if [ -z "${API_FOOTBALL_KEY:-}" ]; then
  echo "NO_KEY: API_FOOTBALL_KEY 가 없어 실제 배당을 받을 수 없습니다. 오늘 추천은 없습니다."
  exit 3
fi

# 네트워크 정책이 막으면 파이썬 오류 대신 한 줄로 알린다
if ! curl -s -o /dev/null -m 15 "https://v3.football.api-sports.io/status"; then
  echo "NO_NET: v3.football.api-sports.io 에 연결할 수 없습니다 (환경의 네트워크 허용 목록 확인). 오늘 추천은 없습니다."
  exit 4
fi

if [ -z "${SSSM_DATA_DIR:-}" ] && [ -d /mnt/project-files ]; then
  export SSSM_DATA_DIR=/mnt/project-files/sssm-data
fi
[ -n "${SSSM_DATA_DIR:-}" ] && mkdir -p "$SSSM_DATA_DIR"

python -c "import numpy, scipy, pandas, requests" 2>/dev/null || pip install -q -r requirements.txt >/dev/null 2>&1

leagues="${SSSM_LEAGUES:-39 140 78 135 61}"
# shellcheck disable=SC2086
common=(--source apifootball --league $leagues --days 2 --bankroll "${SSSM_BANKROLL:-1000000}")

case "$mode" in
  picks)
    python -m sssm picks "${common[@]}" --record || exit $?
    echo
    echo "== CLV =="
    python -m sssm clv
    ;;
  snapshot)
    python -m sssm picks "${common[@]}" --snapshot-only --out /tmp/sssm-snapshot.json >/dev/null || exit $?
    echo "스냅샷 기록: ${SSSM_DATA_DIR:-data}/snapshots"
    ;;
  *)
    echo "사용법: $0 [picks|snapshot]" >&2
    exit 2
    ;;
esac
