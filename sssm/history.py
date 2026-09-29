"""과거 경기 CSV 로더.

두 형식을 읽는다.
1. 이 저장소 형식: date, home, away, hg, ag
2. football-data.co.uk 형식: Date, HomeTeam, AwayTeam, FTHG, FTAG 와 배당 컬럼
   (B365H/D/A, B365CH/CD/CA, PSH/D/A, PSCH/D/A, B365>2.5, B365C>2.5, P>2.5, PC>2.5 ...)
   https://www.football-data.co.uk/englandm.php 에서 시즌별 CSV 를 받을 수 있다.

football-data.co.uk 가 막힌 환경에서는 `download_mirror()` 가 같은 데이터를 정리해 둔
GitHub 미러(AnishKhetani/premier-league-data, EPL 만)에서 받아 football-data 형식으로
바꿔 저장한다. 원 데이터의 권리는 football-data.co.uk 에 있으므로 저장소에는 넣지 않는다
(data/history/*.csv 는 .gitignore).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

import pandas as pd
import requests

from .config import ROOT
from .sources import check

DEFAULT_RESULTS = ROOT / "data" / "epl_results_2015_2025.csv"
HISTORY_DIR = ROOT / "data" / "history"
MIRROR_URL = "https://raw.githubusercontent.com/AnishKhetani/premier-league-data/main/data/processed"

def _odds_columns() -> dict:
    """football-data 배당 컬럼 -> (북, 마켓, 결과). 시가/마감을 다른 "북"으로 본다."""
    cols = {}
    for prefix, book in (("B365", "bet365"), ("B365C", "bet365_close"), ("PS", "pinnacle"), ("PSC", "pinnacle_close"),
                         ("Avg", "avg"), ("AvgC", "avg_close"), ("Max", "max"), ("MaxC", "max_close")):
        for suf, o in (("H", "home"), ("D", "draw"), ("A", "away")):
            cols[f"{prefix}{suf}"] = (book, "1X2", o)
    for prefix, book in (("B365", "bet365"), ("B365C", "bet365_close"), ("P", "pinnacle"), ("PC", "pinnacle_close"),
                         ("Avg", "avg"), ("AvgC", "avg_close"), ("Max", "max"), ("MaxC", "max_close")):
        cols[f"{prefix}>2.5"] = (book, "OU:2.5", "over")
        cols[f"{prefix}<2.5"] = (book, "OU:2.5", "under")
    # 아시안 핸디캡: 라인은 AHh(시가)/AHCh(마감) 컬럼, 마켓 이름은 row_to_fixture 에서 채운다
    for prefix, book in (("B365AH", "bet365"), ("B365CAH", "bet365_close"), ("PAH", "pinnacle"),
                         ("PCAH", "pinnacle_close")):
        cols[f"{prefix}H"] = (book, "AH", "home")
        cols[f"{prefix}A"] = (book, "AH", "away")
    return cols


ODDS_COLUMNS = _odds_columns()
AH_LINE_COLUMNS = {"bet365": "AHh", "pinnacle": "AHh", "bet365_close": "AHCh", "pinnacle_close": "AHCh"}


def _parse_dates(s: pd.Series) -> pd.Series:
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    if iso.notna().all():
        return iso
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def load(paths: Union[str, Path, Iterable[Union[str, Path]]] = DEFAULT_RESULTS) -> pd.DataFrame:
    """CSV 들을 읽어 date, home, away, hg, ag (+ 있으면 배당 컬럼) 로 합친다."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    frames = []
    for p in paths:
        df = pd.read_csv(p, encoding_errors="replace")
        df = df.rename(columns={"Date": "date", "HomeTeam": "home", "AwayTeam": "away", "FTHG": "hg", "FTAG": "ag"})
        df = df.dropna(subset=["home", "away"])
        df["date"] = _parse_dates(df["date"].astype(str))
        if "AHh" not in df.columns and "BbAHh" in df.columns:
            df["AHh"] = df["BbAHh"]
        extra = [c for c in ("AHh", "AHCh", "Div", "Season") if c in df.columns]
        keep = ["date", "home", "away", "hg", "ag"] + [c for c in ODDS_COLUMNS if c in df.columns] + extra
        frames.append(df[keep])
    out = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    return out


def has_odds(df: pd.DataFrame) -> bool:
    return {"B365H", "PSH"}.issubset(df.columns)


def row_to_fixture(row, books: Optional[dict] = None, fixture_id: Optional[str] = None):
    """과거 데이터 한 줄을 Fixture 로. books 는 {데이터의 북 이름: Fixture 에 쓸 이름}.

    예: 마감 시점을 흉내 내려면 {"bet365_close": "bet365", "pinnacle_close": "pinnacle"}.
    """
    from .markets import Fixture, make

    books = books or {"bet365": "bet365", "pinnacle": "pinnacle"}
    fx = Fixture(fixture_id or f"{row['date']:%Y%m%d}-{row['home']}-{row['away']}", f"{row['date']:%Y-%m-%d}",
                 str(row.get("Div", "")), row["home"], row["away"])
    for col, (book, market, outcome) in ODDS_COLUMNS.items():
        if book not in books or col not in row.index:
            continue
        v = row[col]
        if pd.isna(v) or v <= 1.0:
            continue
        if market == "AH":
            line_col = AH_LINE_COLUMNS[book]
            line = row.get(line_col)
            if line is None or pd.isna(line):
                continue
            market = make("AH", float(line))
        fx.odds.setdefault(books[book], {}).setdefault(market, {})[outcome] = float(v)
    return fx


FOOTBALL_DATA_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def download(league: str = "E0", seasons: Iterable[str] = ("2122", "2223", "2324", "2425"),
             out: Path = HISTORY_DIR, session: Optional[requests.Session] = None) -> List[Path]:
    """football-data.co.uk 에서 시즌별 결과+배당 CSV 를 받는다.

    league: E0=EPL, E1=챔피언십, SP1=라리가, D1=분데스, I1=세리에A, F1=리그1
    seasons: "2425" = 2024/25 시즌. 사내 프록시 등에서 사이트가 막혀 있으면 로컬 PC 에서 실행하거나 CSV 를 직접 넣는다.
    """
    http = session or requests.Session()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for season in seasons:
        r = http.get(FOOTBALL_DATA_URL.format(season=season, league=league), timeout=30)
        check(r, "football-data.co.uk")
        path = out / f"{league}_{season}.csv"
        path.write_bytes(r.content)
        paths.append(path)
    return paths


# 미러 컬럼 -> football-data 컬럼
_MIRROR_COLUMNS = {
    "bet365_1x2_home": "B365H", "bet365_1x2_draw": "B365D", "bet365_1x2_away": "B365A",
    "bet365_1x2_home_close": "B365CH", "bet365_1x2_draw_close": "B365CD", "bet365_1x2_away_close": "B365CA",
    "pinnacle_1x2_home": "PSH", "pinnacle_1x2_draw": "PSD", "pinnacle_1x2_away": "PSA",
    "pinnacle_1x2_home_close": "PSCH", "pinnacle_1x2_draw_close": "PSCD", "pinnacle_1x2_away_close": "PSCA",
    "bet365_over25": "B365>2.5", "bet365_under25": "B365<2.5",
    "bet365_over25_close": "B365C>2.5", "bet365_under25_close": "B365C<2.5",
    "pinnacle_over25": "P>2.5", "pinnacle_under25": "P<2.5",
    "pinnacle_over25_close": "PC>2.5", "pinnacle_under25_close": "PC<2.5",
}


def from_mirror(results: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    """미러의 results / results_with_odds 표를 football-data 형식 한 표로 합친다."""
    res = results.rename(columns={"home_team": "HomeTeam", "away_team": "AwayTeam", "fthg": "FTHG", "ftag": "FTAG",
                                  "date": "Date", "season_code": "Season"})
    res = res[["match_id", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]
    od = odds[["match_id"] + [c for c in _MIRROR_COLUMNS if c in odds.columns]].rename(columns=_MIRROR_COLUMNS)
    out = res.merge(od, on="match_id", how="left").drop(columns="match_id")
    out["Season"] = out["Season"].astype(str).str.zfill(4)
    return out


def download_mirror(seasons: Iterable[str], out: Path = HISTORY_DIR, session: Optional[requests.Session] = None,
                    base_url: str = MIRROR_URL) -> List[Path]:
    """GitHub 미러에서 EPL 결과+배당을 받아 out/E0_<시즌>.csv (football-data 형식) 로 저장한다."""
    import io

    http = session or requests.Session()

    def get(name: str) -> pd.DataFrame:
        r = http.get(f"{base_url}/{name}", timeout=60)
        check(r, "GitHub 미러")
        return pd.read_csv(io.StringIO(r.text), low_memory=False)

    df = from_mirror(get("results.csv"), get("results_with_odds.csv"))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for season in seasons:
        g = df[df["Season"] == season]
        if g.empty:
            raise ValueError(f"미러에 {season} 시즌이 없습니다")
        path = out / f"E0_{season}.csv"
        g.drop(columns="Season").to_csv(path, index=False)
        paths.append(path)
    return paths


def history_files(out: Path = HISTORY_DIR) -> List[Path]:
    return sorted(Path(out).glob("*.csv"))  # E0_2425.csv, E1_2425.csv ... 여러 리그를 함께 쓴다
