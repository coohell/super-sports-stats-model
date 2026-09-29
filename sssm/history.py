"""과거 경기 CSV 로더.

두 형식을 읽는다.
1. 이 저장소 형식: date, home, away, hg, ag
2. football-data.co.uk 형식: Date, HomeTeam, AwayTeam, FTHG, FTAG 와 배당 컬럼
   (B365H/D/A, PSH/D/A, PSCH/D/A, B365>2.5, B365<2.5, P>2.5, P<2.5, PC>2.5, PC<2.5)
   https://www.football-data.co.uk/englandm.php 에서 시즌별 CSV 를 받을 수 있다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

import pandas as pd
import requests

from .config import ROOT
from .sources import check

DEFAULT_RESULTS = ROOT / "data" / "epl_results_2015_2025.csv"

ODDS_COLUMNS = {
    "B365H": ("bet365", "1X2", "home"), "B365D": ("bet365", "1X2", "draw"), "B365A": ("bet365", "1X2", "away"),
    "PSH": ("pinnacle", "1X2", "home"), "PSD": ("pinnacle", "1X2", "draw"), "PSA": ("pinnacle", "1X2", "away"),
    "PSCH": ("pinnacle_close", "1X2", "home"), "PSCD": ("pinnacle_close", "1X2", "draw"),
    "PSCA": ("pinnacle_close", "1X2", "away"),
    "B365>2.5": ("bet365", "OU:2.5", "over"), "B365<2.5": ("bet365", "OU:2.5", "under"),
    "P>2.5": ("pinnacle", "OU:2.5", "over"), "P<2.5": ("pinnacle", "OU:2.5", "under"),
    "PC>2.5": ("pinnacle_close", "OU:2.5", "over"), "PC<2.5": ("pinnacle_close", "OU:2.5", "under"),
}


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
        keep = ["date", "home", "away", "hg", "ag"] + [c for c in ODDS_COLUMNS if c in df.columns]
        frames.append(df[keep])
    out = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    return out


def has_odds(df: pd.DataFrame) -> bool:
    return {"B365H", "PSH"}.issubset(df.columns)


FOOTBALL_DATA_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def download(league: str = "E0", seasons: Iterable[str] = ("2122", "2223", "2324", "2425"),
             out: Path = ROOT / "data" / "history", session: Optional[requests.Session] = None) -> List[Path]:
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
