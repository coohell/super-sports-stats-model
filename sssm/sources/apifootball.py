"""API-Football (v3.football.api-sports.io) 어댑터.

bet365 와 Pinnacle 배당을 모두 주고 BTTS 도 있어 축구의 기본 소스다.
- 북메이커 id: bet365 = 8, Pinnacle = 4
- 베팅 id: Match Winner = 1, Goals Over/Under = 5, Both Teams Score = 8
무료 플랜은 하루 100회 요청이고 조회 가능한 시즌이 제한된다.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd
import requests

from ..config import env
from ..markets import Fixture

log = logging.getLogger(__name__)

BASE = "https://v3.football.api-sports.io"
BOOKMAKERS = {"bet365": 8, "pinnacle": 4}
LEAGUES = {"EPL": 39, "LaLiga": 140, "SerieA": 135, "Bundesliga": 78, "Ligue1": 61, "K League 1": 292}


class APIFootball:
    def __init__(self, key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.key = key or env("API_FOOTBALL_KEY")
        if not self.key:
            raise RuntimeError("API_FOOTBALL_KEY 가 없습니다 (.env 확인)")
        self.http = session or requests.Session()

    def _get(self, path: str, **params) -> List[dict]:
        out, page = [], 1
        while True:
            if page > 1:
                params["page"] = page
            r = self.http.get(f"{BASE}/{path}", headers={"x-apisports-key": self.key}, params=params, timeout=20)
            r.raise_for_status()
            body = r.json()
            errors = body.get("errors")
            if errors:
                raise RuntimeError(f"API-Football 오류: {errors}")
            out.extend(body.get("response", []))
            paging = body.get("paging") or {}
            if paging.get("current", 1) >= paging.get("total", 1):
                return out
            page += 1

    # ---- 경기 결과 (모델 학습용) ----
    def results(self, league: int, season: int) -> pd.DataFrame:
        rows = []
        for g in self._get("fixtures", league=league, season=season, status="FT"):
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
        for g in self._get("fixtures", league=league, season=season, **{"from": date_from, "to": date_to}):
            if g["fixture"]["status"]["short"] not in ("NS", "TBD"):
                continue
            fid = g["fixture"]["id"]
            fixtures[fid] = Fixture(
                fixture_id=str(fid), kickoff=g["fixture"]["date"], league=g["league"]["name"],
                home=g["teams"]["home"]["name"], away=g["teams"]["away"]["name"],
            )
        if not fixtures:
            return []
        for book, bid in BOOKMAKERS.items():
            for item in self._get("odds", league=league, season=season, bookmaker=bid):
                fid = item["fixture"]["id"]
                if fid in fixtures:
                    fixtures[fid].odds[book] = parse_bets(item)
        return list(fixtures.values())


def parse_bets(item: dict) -> Dict[str, Dict[str, float]]:
    """odds 응답 항목 하나를 {market: {outcome: odds}} 로 바꾼다."""
    out: Dict[str, Dict[str, float]] = {}
    for bm in item.get("bookmakers", []):
        for bet in bm.get("bets", []):
            vals = {str(v["value"]): float(v["odd"]) for v in bet.get("values", [])}
            if bet["id"] == 1:
                m = {"home": vals.get("Home"), "draw": vals.get("Draw"), "away": vals.get("Away")}
                out["1X2"] = m
            elif bet["id"] == 5 and "Over 2.5" in vals and "Under 2.5" in vals:
                out["OU2.5"] = {"over": vals["Over 2.5"], "under": vals["Under 2.5"]}
            elif bet["id"] == 8:
                out["BTTS"] = {"yes": vals.get("Yes"), "no": vals.get("No")}
    return {k: v for k, v in out.items() if all(x for x in v.values())}
