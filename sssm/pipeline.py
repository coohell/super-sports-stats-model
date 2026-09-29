"""전체 파이프라인: 경기·배당 수집 → 팀 전력 모델 → 공정 확률 → +EV 선택지 → 최강 조합."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd

from . import history
from .config import ROOT
from .markets import Fixture, Selection
from .model import DixonColes
from .parlay import Parlay, best_parlays
from .pricing import PricingConfig, ValueFilter, price_all, value_bets
from .teams import norm

log = logging.getLogger(__name__)

SAMPLE_FIXTURES = ROOT / "data" / "sample_fixtures.json"


@dataclass
class Settings:
    pricing: PricingConfig = field(default_factory=PricingConfig)
    value: ValueFilter = field(default_factory=ValueFilter)
    max_legs: int = 3
    top: int = 10
    kelly_fraction: float = 0.25


@dataclass
class Report:
    generated_at: str
    source: str
    fixtures: List[Fixture]
    selections: List[Selection]
    value: List[Selection]
    parlays: List[Parlay]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def sel(s: Selection) -> dict:
            return {
                "fixture_id": s.fixture_id, "kickoff": s.kickoff, "league": s.league, "match": s.match,
                "market": s.market, "pick": s.label, "odds": s.odds, "fair_prob": round(s.fair_prob, 4),
                "sharp_prob": None if s.sharp_prob is None else round(s.sharp_prob, 4),
                "model_prob": None if s.model_prob is None else round(s.model_prob, 4),
                "ev": round(s.ev, 4), "source": s.source,
            }

        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "n_fixtures": len(self.fixtures),
            "notes": self.notes,
            "value": [sel(s) for s in self.value],
            "parlays": [p.to_dict() for p in self.parlays],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def fit_model(results: pd.DataFrame) -> Optional[DixonColes]:
    results = results.assign(home=results["home"].map(norm), away=results["away"].map(norm))
    try:
        return DixonColes().fit(results)
    except ValueError as e:
        log.warning("모델 학습 생략: %s", e)
        return None


def analyze(fixtures: List[Fixture], model: Optional[DixonColes], source: str,
            settings: Optional[Settings] = None, notes: Optional[List[str]] = None) -> Report:
    settings = settings or Settings()
    for fx in fixtures:
        fx.home, fx.away = norm(fx.home), norm(fx.away)
    sels = price_all(fixtures, model, settings.pricing)
    value = value_bets(sels, settings.value)
    parlays = best_parlays(value, max_legs=settings.max_legs, top=settings.top, kelly_fraction=settings.kelly_fraction)
    notes = list(notes or [])
    no_b365 = sum(1 for fx in fixtures if "bet365" not in fx.odds)
    if no_b365:
        notes.append(f"bet365 배당이 없는 경기 {no_b365}개는 제외했습니다.")
    no_sharp = sum(1 for fx in fixtures if "pinnacle" not in fx.odds)
    if no_sharp:
        notes.append(f"Pinnacle 배당이 없는 경기 {no_sharp}개는 모델만으로 평가했습니다 (EV 문턱 {settings.value.model_only_min_ev:.0%}).")
    return Report(datetime.now(timezone.utc).isoformat(timespec="seconds"), source, fixtures, sels, value, parlays, notes)


# ---- 소스별 진입점 ----

def load_fixtures_json(path: Path) -> List[Fixture]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Fixture(**{k: v for k, v in f.items() if k in Fixture.__dataclass_fields__}) for f in raw["fixtures"]]


def run_file(path: Path = SAMPLE_FIXTURES, results_csv: Optional[Path] = None, settings: Optional[Settings] = None) -> Report:
    fixtures = load_fixtures_json(path)
    model = fit_model(history.load(results_csv or history.DEFAULT_RESULTS))
    notes = ["예시 배당입니다. 실제 배당이 아닙니다."] if Path(path) == SAMPLE_FIXTURES else []
    return analyze(fixtures, model, f"file:{Path(path).name}", settings, notes)


def run_apifootball(league: int, season: int, days: int = 3, settings: Optional[Settings] = None) -> Report:
    from .sources.apifootball import APIFootball

    api = APIFootball()
    today = datetime.now(timezone.utc).date()
    fixtures = api.upcoming(league, season, today.isoformat(), (today + timedelta(days=days)).isoformat())
    results = pd.concat([api.results(league, season - 1), api.results(league, season)], ignore_index=True)
    model = fit_model(results)
    return analyze(fixtures, model, f"api-football:{league}/{season}", settings)


def run_theoddsapi(sport: str, settings: Optional[Settings] = None, markets: tuple = ("h2h", "spreads", "totals")) -> Report:
    from .sources.theoddsapi import TheOddsAPI

    api = TheOddsAPI()
    fixtures = api.upcoming(sport, markets=markets)
    notes = ["TheOddsAPI 는 팀 전력 모델 없이 Pinnacle 대비 가격만 비교합니다."]
    if api.remaining is not None:
        notes.append(f"TheOddsAPI 남은 요청 수: {api.remaining}")
    return analyze(fixtures, None, f"theoddsapi:{sport}", settings, notes)
