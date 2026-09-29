"""TheOddsAPI 어댑터.

주의: TheOddsAPI 의 bet365 는 호주 지역 키 `bet365_au` 뿐이고 유료 플랜 전용이며
AFL/NRL 의 h2h·spreads·totals 만 있다. 축구 bet365 는 API-Football 을 쓴다.
Pinnacle 은 `pinnacle` (eu 지역) 키로 제공된다.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import requests

from ..config import env
from ..markets import Fixture

BASE = "https://api.the-odds-api.com/v4"
BOOK_KEYS = {"bet365_au": "bet365", "bet365": "bet365", "pinnacle": "pinnacle"}


class TheOddsAPI:
    def __init__(self, key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.key = key or env("THE_ODDS_API_KEY")
        if not self.key:
            raise RuntimeError("THE_ODDS_API_KEY 가 없습니다 (.env 확인)")
        self.http = session or requests.Session()

    def upcoming(self, sport: str, bookmakers: str = "bet365_au,pinnacle") -> List[Fixture]:
        r = self.http.get(
            f"{BASE}/sports/{sport}/odds",
            params={"apiKey": self.key, "bookmakers": bookmakers, "markets": "h2h,totals", "oddsFormat": "decimal"},
            timeout=20,
        )
        r.raise_for_status()
        return [parse_event(e) for e in r.json()]


def parse_event(e: dict) -> Fixture:
    fx = Fixture(fixture_id=e["id"], kickoff=e["commence_time"], league=e.get("sport_title", ""),
                 home=e["home_team"], away=e["away_team"])
    for bm in e.get("bookmakers", []):
        book = BOOK_KEYS.get(bm["key"])
        if not book:
            continue
        mk: Dict[str, Dict[str, float]] = {}
        for m in bm.get("markets", []):
            if m["key"] == "h2h":
                o = {}
                for oc in m["outcomes"]:
                    if oc["name"] == e["home_team"]:
                        o["home"] = oc["price"]
                    elif oc["name"] == e["away_team"]:
                        o["away"] = oc["price"]
                    elif oc["name"].lower() == "draw":
                        o["draw"] = oc["price"]
                if "draw" in o:
                    mk["1X2"] = o
                else:
                    mk["H2H"] = o  # 무승부 없는 종목(AFL/NRL 등)
            elif m["key"] == "totals":
                o = {oc["name"].lower(): oc["price"] for oc in m["outcomes"] if oc.get("point") == 2.5}
                if set(o) == {"over", "under"}:
                    mk["OU2.5"] = o
        fx.odds[book] = mk
    return fx
