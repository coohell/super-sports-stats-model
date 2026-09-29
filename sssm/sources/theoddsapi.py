"""TheOddsAPI 어댑터.

주의: TheOddsAPI 의 bet365 는 호주 지역 키 `bet365_au` 뿐이고 유료 플랜 전용이며
AFL/NRL 의 h2h·spreads·totals 만 있다. 축구 bet365 는 API-Football 을 쓴다.
Pinnacle 은 `pinnacle` (eu 지역) 키로 제공된다.

- h2h/spreads/totals 는 /sports/{sport}/odds 한 번에 받는다.
- btts 는 경기별 엔드포인트라 경기 수만큼 크레딧이 나가서 기본에서 뺀다.
- 남은 크레딧은 응답 헤더 x-requests-remaining 으로 `remaining` 에 남는다.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import requests

from .. import markets as mkt
from ..config import env
from ..markets import Fixture
from . import check

BASE = "https://api.the-odds-api.com/v4"
BOOK_KEYS = {"bet365_au": "bet365", "bet365": "bet365", "pinnacle": "pinnacle"}
DEFAULT_MARKETS = ("h2h", "spreads", "totals")
ALL_MARKETS = DEFAULT_MARKETS + ("btts",)


class TheOddsAPI:
    def __init__(self, key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.key = key or env("THE_ODDS_API_KEY")
        if not self.key:
            raise RuntimeError("THE_ODDS_API_KEY 가 없습니다 (.env 확인)")
        self.http = session or requests.Session()
        self.remaining: Optional[str] = None

    def _get(self, path: str, **params):
        r = self.http.get(f"{BASE}{path}", params={**params, "apiKey": self.key, "oddsFormat": "decimal"}, timeout=20)
        self.remaining = r.headers.get("x-requests-remaining", self.remaining)
        check(r, "TheOddsAPI")
        return r.json()

    def upcoming(self, sport: str, bookmakers: str = "bet365_au,pinnacle",
                 markets: Iterable[str] = DEFAULT_MARKETS) -> List[Fixture]:
        markets = list(markets)
        unknown = set(markets) - set(ALL_MARKETS)
        if unknown:
            raise ValueError(f"알 수 없는 마켓: {sorted(unknown)} (가능: {ALL_MARKETS})")
        featured = [m for m in markets if m != "btts"]
        events = self._get(f"/sports/{sport}/odds", bookmakers=bookmakers, markets=",".join(featured)) if featured else []
        fixtures = {e["id"]: parse_event(e) for e in events}
        if "btts" in markets:
            ids = list(fixtures) or [e["id"] for e in self._get(f"/sports/{sport}/events")]
            for eid in ids:
                ev = self._get(f"/sports/{sport}/events/{eid}/odds", bookmakers=bookmakers, markets="btts")
                extra = parse_event(ev)
                base = fixtures.setdefault(eid, extra)
                for book, mk in extra.odds.items():
                    base.odds.setdefault(book, {}).update(mk)
        return list(fixtures.values())


def parse_event(e: dict) -> Fixture:
    home, away = e["home_team"], e["away_team"]
    sport_key = str(e.get("sport_key", ""))
    # 축구가 아니면(AFL/NRL 등) 스코어 격자를 쓸 수 없어 승패(H2H)만 가격을 매긴다
    sport = "football" if sport_key.startswith("soccer") else (sport_key or "other")
    fx = Fixture(fixture_id=e["id"], kickoff=e["commence_time"], league=e.get("sport_title", ""), home=home, away=away,
                 sport=sport)
    for bm in e.get("bookmakers", []):
        book = BOOK_KEYS.get(bm["key"])
        if not book:
            continue
        out: Dict[str, Dict[str, float]] = {}
        for m in bm.get("markets", []):
            outs = [o for o in m.get("outcomes", []) if o.get("price")]
            if m["key"] == "h2h":
                o = {}
                for oc in outs:
                    if oc["name"] == home:
                        o["home"] = oc["price"]
                    elif oc["name"] == away:
                        o["away"] = oc["price"]
                    elif oc["name"].lower() == "draw":
                        o["draw"] = oc["price"]
                out["1X2" if "draw" in o else "H2H"] = o
            elif m["key"] == "totals":
                by_line: Dict[float, Dict[str, float]] = {}
                for oc in outs:
                    if oc.get("point") is not None:
                        by_line.setdefault(float(oc["point"]), {})[oc["name"].lower()] = oc["price"]
                for line, o in by_line.items():
                    out[mkt.make("OU", line)] = o
            elif m["key"] == "spreads":
                # 라인은 홈 기준으로 통일한다. 원정 쪽 point 는 홈 point 의 부호 반대여야 한다.
                by_line = {}
                for oc in outs:
                    if oc.get("point") is None:
                        continue
                    if oc["name"] == home:
                        by_line.setdefault(float(oc["point"]), {})["home"] = oc["price"]
                    elif oc["name"] == away:
                        by_line.setdefault(-float(oc["point"]), {})["away"] = oc["price"]
                for line, o in by_line.items():
                    out[mkt.make("AH", line)] = o
            elif m["key"] == "btts":
                out["BTTS"] = {oc["name"].lower(): oc["price"] for oc in outs}
        fx.odds[book] = {k: v for k, v in out.items() if mkt.is_supported(k) and set(v) == set(mkt.outcomes(k))}
    return fx
