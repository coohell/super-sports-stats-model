"""API-Football (v3.football.api-sports.io) 어댑터.

bet365 와 Pinnacle 배당을 모두 주고 BTTS 도 있어 축구의 기본 소스다.
- 북메이커 id 는 /odds/bookmakers 를 이름으로 조회해서 쓴다. 조회 호출 자체가 실패할 때만
  기본값(bet365=8, pinnacle=4, 실서버 미검증)으로 대체한다.
- 베팅 id: Match Winner = 1, Goals Over/Under = 5, Both Teams Score = 8
- 아시안 핸디캡(id 4)은 라인 표기 규칙을 실서버로 확인하지 못해 지원하지 않는다.
무료 플랜은 하루 100회 요청이고 조회 가능한 시즌이 제한된다.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

from .. import markets as mkt
from ..config import env
from ..markets import Fixture
from . import check

log = logging.getLogger(__name__)

BASE = "https://v3.football.api-sports.io"
FALLBACK_BOOKMAKER_IDS = {"bet365": 8, "pinnacle": 4}
LEAGUES = {"EPL": 39, "LaLiga": 140, "SerieA": 135, "Bundesliga": 78, "Ligue1": 61, "K League 1": 292}


class APIFootball:
    def __init__(self, key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.key = key or env("API_FOOTBALL_KEY")
        if not self.key:
            raise RuntimeError("API_FOOTBALL_KEY 가 없습니다 (.env 확인)")
        self.http = session or requests.Session()

    def _get(self, path: str, **params) -> dict:
        r = self.http.get(f"{BASE}/{path}", headers={"x-apisports-key": self.key}, params=params, timeout=20)
        check(r, "API-Football")
        body = r.json()
        if body.get("errors"):  # 200 이어도 쿼터/파라미터 오류는 errors 에 담겨 온다
            raise RuntimeError(f"API-Football 오류: {body['errors']}")
        return body

    def _paged(self, path: str, **params) -> List[dict]:
        out, page = [], 1
        while True:
            body = self._get(path, **({**params, "page": page} if page > 1 else params))
            out.extend(body.get("response", []))
            paging = body.get("paging") or {}
            if page >= paging.get("total", 1):
                return out
            page += 1

    def bookmaker_ids(self, names: Iterable[str]) -> Dict[str, int]:
        """북메이커 이름(bet365, pinnacle) -> API-Football id."""
        wanted = [n.lower() for n in names]
        cache = getattr(self, "_bookmaker_cache", None)
        if cache is not None and all(n in cache for n in wanted):  # 여러 리그를 돌 때 조회 한 번으로 (무료 요청 한도)
            return {n: cache[n] for n in wanted}
        found: Dict[str, int] = {}
        lookup_ok = False
        try:
            for b in self._get("odds/bookmakers").get("response", []):
                name = str(b.get("name", "")).strip().lower()
                if name in wanted:
                    found[name] = int(b["id"])
            lookup_ok = True
        except (RuntimeError, requests.RequestException) as e:
            log.warning("북메이커 id 조회 실패, 기본값으로 대체: %s", e)
        for n in wanted:
            if n in found:
                continue
            if lookup_ok or n not in FALLBACK_BOOKMAKER_IDS:
                raise RuntimeError(f"API-Football 에서 북메이커 '{n}' 를 찾지 못했습니다")
            found[n] = FALLBACK_BOOKMAKER_IDS[n]
        self._bookmaker_cache = {**(cache or {}), **found}
        return found

    # ---- 경기 결과 (모델 학습용) ----
    def results(self, league: int, season: int) -> pd.DataFrame:
        rows = []
        for g in self._paged("fixtures", league=league, season=season, status="FT"):
            rows.append({
                "date": g["fixture"]["date"][:10],
                "home": g["teams"]["home"]["name"],
                "away": g["teams"]["away"]["name"],
                "hg": g["goals"]["home"],
                "ag": g["goals"]["away"],
            })
        return pd.DataFrame(rows, columns=["date", "home", "away", "hg", "ag"])

    # ---- 예정 경기 + 배당 ----
    def upcoming(self, league: int, season: int, date_from: str, date_to: str) -> List[Fixture]:
        fixtures: Dict[int, Fixture] = {}
        for g in self._paged("fixtures", league=league, season=season, **{"from": date_from, "to": date_to}):
            if g["fixture"]["status"]["short"] not in ("NS", "TBD"):
                continue
            fid = g["fixture"]["id"]
            fixtures[fid] = Fixture(
                fixture_id=str(fid), kickoff=g["fixture"]["date"], league=g["league"]["name"],
                home=g["teams"]["home"]["name"], away=g["teams"]["away"]["name"],
            )
        if not fixtures:
            return []
        for book, bid in self.bookmaker_ids(["bet365", "pinnacle"]).items():
            for item in self._paged("odds", league=league, season=season, bookmaker=bid):
                fx = fixtures.get(item["fixture"]["id"])
                if fx is not None:
                    fx.odds.setdefault(book, {}).update(parse_bets(item))
        return list(fixtures.values())


def parse_bets(item: dict) -> Dict[str, Dict[str, float]]:
    """odds 응답 항목 하나를 {market: {outcome: odds}} 로 바꾼다."""
    out: Dict[str, Dict[str, float]] = {}
    for bm in item.get("bookmakers", []):
        for bet in bm.get("bets", []):
            vals = {str(v["value"]).strip(): float(v["odd"]) for v in bet.get("values", [])}
            if bet["id"] == 1:
                out["1X2"] = {"home": vals.get("Home"), "draw": vals.get("Draw"), "away": vals.get("Away")}
            elif bet["id"] == 5:
                for name in vals:
                    side, _, num = name.partition(" ")
                    if side != "Over":
                        continue
                    try:
                        line = float(num)
                    except ValueError:
                        continue
                    under = vals.get(f"Under {num}")
                    market = mkt.make("OU", line)
                    if under and mkt.is_supported(market):
                        out[market] = {"over": vals[name], "under": under}
            elif bet["id"] == 8:
                out["BTTS"] = {"yes": vals.get("Yes"), "no": vals.get("No")}
    return {k: v for k, v in out.items() if all(x for x in v.values())}
