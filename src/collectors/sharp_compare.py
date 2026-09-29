"""
샤프 북(Pinnacle) 대비 타깃 북(bet365) 배당 비교 → 엣지(EV) 계산

흐름
  1. 어댑터가 각 소스 응답을 공통 Quote 리스트로 정규화
     - TheOddsAPI  : bet365는 `bet365_au`(AU, 유료, AFL/NRL의 h2h/spreads/totals)만 제공
     - API-Football: Bet365(id 8), Pinnacle(id 4) 모두 제공, 축구 BTTS 포함
  2. 같은 (경기, 마켓, 라인)끼리 묶어 Pinnacle 배당에서 마진 제거 → 공정 확률
  3. EV = bet365 배당 × 공정 확률 - 1

사용 (THE_ODDS_API_KEY / API_FOOTBALL_KEY 는 .env 또는 환경변수)
  python src/collectors/sharp_compare.py --source apifootball --league 39 --season 2026 --min-ev 0.02
  python src/collectors/sharp_compare.py --source theodds --sport aussierules_afl
"""
import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Tuple

import requests

THEODDS_BASE = "https://api.the-odds-api.com/v4"
APIFOOTBALL_BASE = "https://v3.football.api-sports.io"

# API-Football 북메이커 ID는 /odds/bookmakers 를 이름으로 조회해서 쓴다.
# 조회 호출 자체가 실패했을 때만 아래 값(실서버 미검증 추정치)으로 대체한다.
APIFOOTBALL_FALLBACK_IDS = {"bet365": 8, "pinnacle": 4}
APIFOOTBALL_BETS = {
    "Match Winner": "h2h",
    "Asian Handicap": "spreads",
    "Goals Over/Under": "totals",
    "Both Teams Score": "btts",
}

MARKETS = ("h2h", "spreads", "totals", "btts")

# TheOddsAPI 의 bet365 는 지역 키(bet365_au, AFL/NRL 한정 유료)로만 제공된다.
# btts 는 경기별 엔드포인트라 경기 수만큼 크레딧이 나가서 TheOddsAPI 기본값에서 뺀다.
THEODDS_KEYS = {"bet365": "bet365_au"}
DEFAULT_MARKETS = {"theodds": ("h2h", "spreads", "totals"), "apifootball": MARKETS}


def _check(resp: requests.Response, name: str) -> None:
    """raise_for_status 는 apiKey 가 든 URL 을 예외 메시지에 넣으므로 직접 만든다"""
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} HTTP {resp.status_code}: {resp.text[:200]}")


@dataclass
class Quote:
    """북메이커 한 곳의 한 선택지 배당"""
    event_id: str
    home_team: str
    away_team: str
    commence_time: str
    bookmaker: str
    market: str            # h2h / spreads / totals / btts
    selection: str         # home / draw / away / over / under / yes / no
    price: float           # 소수 배당
    line: Optional[float] = None  # spreads: 홈 기준 핸디, totals: 기준점


@dataclass
class Edge:
    event_id: str
    home_team: str
    away_team: str
    commence_time: str
    market: str
    line: Optional[float]
    selection: str
    target_price: float
    sharp_price: float
    fair_prob: float
    fair_price: float
    sharp_margin: float
    ev: float              # bet365 배당 기준 기대수익률 (0.03 = +3%)


# ---------------------------------------------------------------------------
# 마진 제거
# ---------------------------------------------------------------------------

def devig(prices: List[float], method: str = "power") -> List[float]:
    """
    배당 목록 → 마진 제거된 공정 확률.
    - proportional: 1/odds 를 합으로 나눔
    - power: p_i = (1/odds_i)^k, 합이 1이 되는 k를 이분법으로 탐색
             (롱샷 쪽 마진을 더 크게 빼서 favourite-longshot bias 반영)
    """
    raw = [1.0 / p for p in prices]
    total = sum(raw)
    if method == "proportional" or total <= 1.0:
        return [r / total for r in raw]
    if method != "power":
        raise ValueError(f"unknown devig method: {method}")

    lo, hi = 1.0, 10.0
    for _ in range(100):
        k = (lo + hi) / 2
        s = sum(r ** k for r in raw)
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    probs = [r ** k for r in raw]
    s = sum(probs)
    return [p / s for p in probs]


# ---------------------------------------------------------------------------
# 비교
# ---------------------------------------------------------------------------

def _outcomes_needed(market: str) -> int:
    return 3 if market == "h2h" else 2


def compare(quotes: Iterable[Quote], target: str = "bet365", sharp: str = "pinnacle",
            method: str = "power", min_ev: Optional[float] = None) -> List[Edge]:
    """
    같은 (경기, 마켓, 라인) 그룹에서 샤프 북의 모든 선택지가 있어야 공정 확률을 계산.
    h2h는 무승부가 없는 종목(AFL/NRL 등)이면 2-way로 처리.
    """
    groups: Dict[Tuple, Dict[str, Dict[str, Quote]]] = defaultdict(lambda: defaultdict(dict))
    for q in quotes:
        if q.bookmaker not in (target, sharp):
            continue
        key = (q.event_id, q.market, q.line)
        groups[key][q.bookmaker][q.selection] = q

    edges: List[Edge] = []
    for (event_id, market, line), books in groups.items():
        sharp_q = books.get(sharp, {})
        target_q = books.get(target, {})
        if not sharp_q or not target_q:
            continue
        needed = _outcomes_needed(market)
        if market == "h2h" and "draw" not in sharp_q and "draw" not in target_q:
            needed = 2
        if len(sharp_q) != needed:
            continue

        selections = sorted(sharp_q)
        sharp_prices = [sharp_q[s].price for s in selections]
        fair = dict(zip(selections, devig(sharp_prices, method)))
        margin = sum(1.0 / p for p in sharp_prices) - 1.0

        for sel, tq in target_q.items():
            if sel not in fair:
                continue
            p = fair[sel]
            ev = tq.price * p - 1.0
            if min_ev is not None and ev < min_ev:
                continue
            edges.append(Edge(
                event_id=event_id,
                home_team=tq.home_team,
                away_team=tq.away_team,
                commence_time=tq.commence_time,
                market=market,
                line=line,
                selection=sel,
                target_price=tq.price,
                sharp_price=sharp_q[sel].price,
                fair_prob=round(p, 4),
                fair_price=round(1.0 / p, 3),
                sharp_margin=round(margin, 4),
                ev=round(ev, 4),
            ))

    return sorted(edges, key=lambda e: e.ev, reverse=True)


# ---------------------------------------------------------------------------
# TheOddsAPI 어댑터
# ---------------------------------------------------------------------------

def _theodds_book(key: str) -> str:
    # bet365_au → bet365 로 통일해서 compare()의 기본 인자와 맞춤
    return "bet365" if key.startswith("bet365") else key


def parse_theodds(events: List[Dict]) -> List[Quote]:
    """/odds 또는 /events/{id}/odds 응답(단일 이벤트면 dict를 리스트로 감싸서) → Quote"""
    quotes: List[Quote] = []
    for ev in events:
        home, away = ev.get("home_team", ""), ev.get("away_team", "")
        base = dict(event_id=ev.get("id", ""), home_team=home, away_team=away,
                    commence_time=ev.get("commence_time", ""))
        for bm in ev.get("bookmakers", []):
            book = _theodds_book(bm.get("key", ""))
            for mk in bm.get("markets", []):
                market = mk.get("key")
                if market not in MARKETS:
                    continue
                for o in mk.get("outcomes", []):
                    name, price, point = o.get("name", ""), o.get("price"), o.get("point")
                    if not price:
                        continue
                    line = None
                    if market in ("h2h",):
                        sel = "home" if name == home else "away" if name == away else "draw"
                    elif market == "spreads":
                        if name == home:
                            sel, line = "home", point
                        elif name == away:
                            sel, line = "away", -point if point is not None else None
                        else:
                            continue
                    elif market == "totals":
                        sel, line = name.lower(), point
                    else:  # btts
                        sel = name.lower()
                    quotes.append(Quote(bookmaker=book, market=market, selection=sel,
                                        price=float(price), line=line, **base))
    return quotes


class TheOddsClient:
    """
    featured 마켓(h2h/spreads/totals)은 /sports/{sport}/odds 한 번에,
    btts 같은 additional 마켓은 /events/{id}/odds 로 경기별 호출.
    비용 = 마켓 수 × 지역 수(bookmakers 10개당 1지역) per call.
    """

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.api_key = api_key or os.getenv("THE_ODDS_API_KEY", "")
        self.session = session or requests.Session()
        self.remaining: Optional[str] = None

    def _get(self, path: str, **params) -> object:
        if not self.api_key:
            raise RuntimeError("THE_ODDS_API_KEY 가 설정되지 않았습니다")
        params.update(apiKey=self.api_key, oddsFormat="decimal")
        resp = self.session.get(f"{THEODDS_BASE}{path}", params=params, timeout=15)
        self.remaining = resp.headers.get("x-requests-remaining", self.remaining)
        _check(resp, "TheOddsAPI")
        return resp.json()

    def fetch(self, sport: str, bookmakers: str = "bet365_au,pinnacle",
              markets: Iterable[str] = DEFAULT_MARKETS["theodds"]) -> List[Quote]:
        markets = list(markets)
        featured = [m for m in markets if m != "btts"]
        events = []
        if featured:
            events = self._get(f"/sports/{sport}/odds", bookmakers=bookmakers,
                               markets=",".join(featured))
        quotes = parse_theodds(events)
        if "btts" in markets:
            ids = [e["id"] for e in events] or [e["id"] for e in self._get(f"/sports/{sport}/events")]
            for eid in ids:
                ev = self._get(f"/sports/{sport}/events/{eid}/odds", bookmakers=bookmakers,
                               markets="btts")
                quotes.extend(parse_theodds([ev]))
        return quotes


# ---------------------------------------------------------------------------
# API-Football 어댑터
# ---------------------------------------------------------------------------

def _parse_af_value(market: str, value: str) -> Tuple[Optional[str], Optional[float]]:
    v = str(value).strip()
    if market == "h2h":
        return {"Home": "home", "Draw": "draw", "Away": "away"}.get(v), None
    if market == "btts":
        return {"Yes": "yes", "No": "no"}.get(v), None
    parts = v.split()
    if len(parts) != 2:
        return None, None
    side, num = parts
    try:
        point = float(num)
    except ValueError:
        return None, None
    if market == "totals":
        return side.lower(), point
    # spreads: 홈 기준 라인으로 통일
    if side == "Home":
        return "home", point
    if side == "Away":
        return "away", -point
    return None, None


def parse_apifootball(responses: List[Dict]) -> List[Quote]:
    """/odds 응답의 response 배열 → Quote (팀명은 fixtures 조회 없이는 비어 있음)"""
    quotes: List[Quote] = []
    for item in responses:
        fx = item.get("fixture", {})
        base = dict(event_id=str(fx.get("id", "")), home_team=item.get("home_team", ""),
                    away_team=item.get("away_team", ""), commence_time=fx.get("date", ""))
        for bm in item.get("bookmakers", []):
            book = str(bm.get("name", "")).strip().lower()
            for bet in bm.get("bets", []):
                market = APIFOOTBALL_BETS.get(bet.get("name"))
                if not market:
                    continue
                for val in bet.get("values", []):
                    sel, line = _parse_af_value(market, val.get("value"))
                    if not sel:
                        continue
                    quotes.append(Quote(bookmaker=book, market=market, selection=sel,
                                        price=float(val["odd"]), line=line, **base))
    return quotes


class ApiFootballClient:
    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY", "")
        self.session = session or requests.Session()

    def _get(self, path: str, **params) -> Dict:
        if not self.api_key:
            raise RuntimeError("API_FOOTBALL_KEY 가 설정되지 않았습니다")
        resp = self.session.get(f"{APIFOOTBALL_BASE}{path}", params=params,
                                headers={"x-apisports-key": self.api_key}, timeout=15)
        _check(resp, "API-Football")
        return resp.json()

    def bookmaker_ids(self, names: Iterable[str]) -> Dict[str, int]:
        """북메이커 이름(bet365, pinnacle) → API-Football ID. 조회 호출이 실패할 때만 기본값 사용"""
        if not self.api_key:  # 키가 없는 건 조회 실패가 아니라 설정 오류
            raise RuntimeError("API_FOOTBALL_KEY 가 설정되지 않았습니다")
        wanted = [n.lower() for n in names]
        found: Dict[str, int] = {}
        lookup_ok = False
        try:
            for b in self._get("/odds/bookmakers").get("response", []):
                name = str(b.get("name", "")).strip().lower()
                if name in wanted:
                    found[name] = int(b["id"])
            lookup_ok = True
        except (RuntimeError, requests.RequestException) as e:
            print(f"[경고] 북메이커 ID 조회 실패, 기본값으로 대체: {e}", file=sys.stderr)
        for n in wanted:
            if n in found:
                continue
            if lookup_ok or n not in APIFOOTBALL_FALLBACK_IDS:
                raise RuntimeError(f"API-Football 에서 북메이커 '{n}' 를 찾지 못했습니다")
            found[n] = APIFOOTBALL_FALLBACK_IDS[n]
        return found

    def fetch(self, league: int, season: int, date: Optional[str] = None,
              books: Iterable[str] = ("bet365", "pinnacle")) -> List[Quote]:
        """북메이커별로 호출(bookmaker 파라미터는 하나만 받음), 페이지 끝까지"""
        items: Dict[int, Dict] = {}
        for book_id in self.bookmaker_ids(books).values():
            page = 1
            while True:
                params = dict(league=league, season=season, bookmaker=book_id, page=page)
                if date:
                    params["date"] = date
                data = self._get("/odds", **params)
                for it in data.get("response", []):
                    fid = it["fixture"]["id"]
                    merged = items.setdefault(fid, {"fixture": it["fixture"], "bookmakers": []})
                    merged["bookmakers"].extend(it.get("bookmakers", []))
                paging = data.get("paging", {})
                if page >= paging.get("total", 1):
                    break
                page += 1
        self._attach_teams(items)
        return parse_apifootball(list(items.values()))

    def _attach_teams(self, items: Dict[int, Dict]) -> None:
        ids = list(items)
        for i in range(0, len(ids), 20):  # fixtures?ids= 는 최대 20개
            chunk = ids[i:i + 20]
            data = self._get("/fixtures", ids="-".join(map(str, chunk)))
            for fx in data.get("response", []):
                it = items.get(fx["fixture"]["id"])
                if it:
                    it["home_team"] = fx["teams"]["home"]["name"]
                    it["away_team"] = fx["teams"]["away"]["name"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_edges(edges: List[Edge], limit: int, target: str = "bet365", sharp: str = "pinnacle") -> None:
    if not edges:
        print("비교 가능한 배당이 없습니다 (두 북 모두 같은 라인을 제공해야 함)")
        return
    print(f"{'EV':>7}  {target[:6]:>6}  {'fair':>6}  {sharp[:6]:>6}  market      sel    match")
    for e in edges[:limit]:
        mk = e.market if e.line is None else f"{e.market} {e.line:+g}"
        print(f"{e.ev:+7.2%}  {e.target_price:6.2f}  {e.fair_price:6.2f}  {e.sharp_price:6.2f}  "
              f"{mk:<11} {e.selection:<6} {e.home_team} vs {e.away_team}")


def main(argv: Optional[List[str]] = None) -> List[Edge]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description="bet365 vs Pinnacle 엣지 계산")
    ap.add_argument("--source", choices=["theodds", "apifootball"], default="apifootball")
    ap.add_argument("--sport", default="aussierules_afl", help="TheOddsAPI sport key")
    ap.add_argument("--target", default="bet365", help="엣지를 찾을 북")
    ap.add_argument("--sharp", default="pinnacle", help="기준이 되는 샤프 북")
    ap.add_argument("--markets", help="쉼표 구분 (h2h,spreads,totals,btts). 기본: theodds는 btts 제외, "
                                      "apifootball은 전체. theodds의 btts는 경기당 크레딧을 쓴다")
    ap.add_argument("--league", type=int, default=39, help="API-Football league id (39=EPL)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--date", help="API-Football YYYY-MM-DD")
    ap.add_argument("--method", choices=["power", "proportional"], default="power")
    ap.add_argument("--min-ev", type=float, default=None, help="예: 0.02 = +2%% 이상만")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args(argv)

    markets = args.markets.split(",") if args.markets else list(DEFAULT_MARKETS[args.source])
    unknown = set(markets) - set(MARKETS)
    if unknown:
        ap.error(f"알 수 없는 마켓: {', '.join(sorted(unknown))} (가능: {', '.join(MARKETS)})")

    try:
        if args.source == "theodds":
            books = ",".join(THEODDS_KEYS.get(b, b) for b in (args.target, args.sharp))
            client = TheOddsClient()
            quotes = client.fetch(args.sport, books, markets)
            print(f"[TheOddsAPI] 남은 요청: {client.remaining}")
        else:
            quotes = ApiFootballClient().fetch(args.league, args.season, args.date,
                                               (args.target, args.sharp))
    except (RuntimeError, requests.RequestException) as e:
        sys.exit(f"오류: {e}")
    quotes = [q for q in quotes if q.market in markets]

    edges = compare(quotes, target=args.target, sharp=args.sharp,
                    method=args.method, min_ev=args.min_ev)
    _print_edges(edges, args.limit, args.target, args.sharp)
    return edges


if __name__ == "__main__":
    main()
