"""전체 흐름: 경기·배당 → 스코어 격자 가격 → +엣지 선택지 → 최강 조합 포트폴리오 → 리포트."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from . import history, tracking
from .config import ROOT
from .markets import Fixture
from .model import DixonColes
from .portfolio import Portfolio, PortfolioConfig, optimize
from .pricing import FixturePricing, PricingConfig, Selection, ValueFilter, price_all, value_bets
from .teams import norm

log = logging.getLogger(__name__)

SAMPLE_FIXTURES = ROOT / "data" / "sample_fixtures.json"


@dataclass
class Settings:
    pricing: PricingConfig = field(default_factory=PricingConfig)
    value: ValueFilter = field(default_factory=ValueFilter)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    bankroll: float = 1_000_000
    use_model: bool = False  # 자체 모델 학습 여부 (model_weight > 0 이거나 샤프 가격이 없을 때 의미)
    record: bool = False  # 스냅샷과 추천 배팅을 data/ 에 기록


@dataclass
class Report:
    generated_at: str
    source: str
    fixtures: List[Fixture]
    pricings: Dict[str, FixturePricing]
    selections: List[Selection]
    value: List[Selection]
    portfolio: Portfolio
    settings: Settings
    notes: List[str] = field(default_factory=list)
    moves: Dict[tuple, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        def sel(s: Selection) -> dict:
            d = s.to_dict()
            mv = self.moves.get((s.fixture_id, s.market, s.outcome))
            if mv:
                d["move"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in mv.items()}
            return d

        p = self.settings.pricing
        return {
            "generated_at": self.generated_at, "source": self.source, "n_fixtures": len(self.fixtures),
            "n_priced": len(self.pricings), "n_selections": len(self.selections),
            "settings": {"shrink": p.shrink, "model_weight": p.model_weight, "min_edge": self.settings.value.min_edge,
                         "kelly_fraction": self.settings.portfolio.kelly_fraction,
                         "max_legs": self.settings.portfolio.max_legs, "bankroll": self.settings.bankroll},
            "notes": self.notes,
            "portfolio": self.portfolio.to_dict(self.settings.bankroll),
            "value": [sel(s) for s in self.value],
            "top_candidates": [b.to_dict() for b in self.portfolio.candidates[:20]],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def to_markdown(self) -> str:
        bank = self.settings.bankroll
        pf = self.portfolio
        lines = [f"# 오늘의 최강 조합 ({self.generated_at[:16].replace('T', ' ')} UTC)", "",
                 f"소스 `{self.source}` · 경기 {len(self.fixtures)} · 가격 매긴 선택지 {len(self.selections)} · "
                 f"+엣지 {len(self.value)}", ""]
        for n in self.notes:
            lines.append(f"> {n}")
        if self.notes:
            lines.append("")
        if not pf.bets:
            lines += ["**오늘은 걸 만한 배팅이 없습니다.** bet365 가 샤프 공정 가격보다 후한 곳이 없거나, "
                      "보정(shrink) 후 엣지가 문턱보다 작습니다. 걸지 않는 것도 전략입니다.", ""]
        else:
            lines += [f"## 배팅 {len(pf.bets)}건, 총 {bank * pf.total_stake:,.0f}원 (자본의 {pf.total_stake:.2%})", "",
                      f"보수적 확률 기준 기대 수익 {bank * pf.exp_return:+,.0f}원, 손실 날 확률 {pf.p_loss:.0%}, "
                      f"하위 5% 결과 {bank * pf.q05:+,.0f}원", "",
                      "| # | 종류 | 선택 | 배당 | 적중 확률 | EV | 보정 엣지 | 금액 |",
                      "|---|---|---|---|---|---|---|---|"]
            for i, b in enumerate(pf.bets, 1):
                picks = "<br>".join(f"{s.match} · **{s.label}** @{s.odds:.2f}" for s in b.legs)
                bonus = f" (+부스트 {b.bonus:.0%})" if b.bonus else ""
                lines.append(f"| {i} | {b.kind}{bonus} | {picks} | {b.odds:.2f} | {b.win_prob:.1%} | {b.ev:+.1%} | "
                             f"{b.edge:+.1%} | {bank * b.stake:,.0f}원 |")
            lines.append("")
        if self.value:
            lines += ["## +엣지 선택지", "", "| 경기 | 선택 | bet365 | 공정 배당 | 공정 확률 | EV | 보정 엣지 | 근거 | 움직임 |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for s in self.value[:25]:
                mv = self.moves.get((s.fixture_id, s.market, s.outcome))
                mvs = "" if not mv else (f"샤프 {mv['fair_move']:+.1%}p" + (" · bet365 지연" if mv["stale"] else ""))
                lines.append(f"| {s.match} | {s.label} | {s.odds:.2f} | {s.fair_odds:.2f} | {s.fair_prob:.1%} | "
                             f"{s.ev:+.1%} | {s.edge:+.1%} | {s.source} | {mvs} |")
            lines.append("")
        lines += ["---", "EV 는 샤프(Pinnacle) 공정 확률 기준, 보정 엣지는 과거에 샤프-bet365 차이가 마감까지 살아남은 "
                  f"비율(shrink {self.settings.pricing.shrink:.2f})만 믿은 값입니다. 금액은 보정 엣지로 푼 "
                  f"{self.settings.portfolio.kelly_fraction:g} 켈리입니다. 근거 derived 는 샤프 북이 직접 내지 않은 마켓을 "
                  "스코어 격자로 끌어낸 가격입니다."]
        return "\n".join(lines)


def fit_model(results: pd.DataFrame) -> Optional[DixonColes]:
    results = results.assign(home=results["home"].map(norm), away=results["away"].map(norm))
    try:
        return DixonColes().fit(results)
    except (ValueError, RuntimeError) as e:
        log.warning("모델 학습 생략: %s", e)
        return None


def analyze(fixtures: List[Fixture], model: Optional[DixonColes], source: str,
            settings: Optional[Settings] = None, notes: Optional[List[str]] = None) -> Report:
    settings = settings or Settings()
    for fx in fixtures:
        fx.home, fx.away = norm(fx.home), norm(fx.away)
    fps, sels = price_all(fixtures, model, settings.pricing)
    pricings = {fp.fixture_id: fp for fp in fps}
    value = value_bets(sels, settings.value)
    pf = optimize(value, pricings, settings.portfolio)

    notes = list(notes or [])
    soft, sharps = settings.pricing.soft_book, settings.pricing.sharp_books
    no_soft = sum(1 for fx in fixtures if soft not in fx.odds)
    if no_soft:
        notes.append(f"{soft} 배당이 없는 경기 {no_soft}개는 제외했습니다.")
    no_sharp = [fx for fx in fixtures if soft in fx.odds and not any(b in fx.odds for b in sharps)]
    if no_sharp:
        how = "자체 모델로만 (보수적으로) 평가했습니다" if model is not None else "근거가 없어 제외했습니다"
        notes.append(f"샤프 북 배당이 없는 경기 {len(no_sharp)}개는 {how}.")

    moves: Dict[tuple, dict] = {}
    if settings.record:
        moves = tracking.movements(fixtures, tracking.load_snapshots(), settings.pricing)
        tracking.record_snapshot(fixtures)
        if pf.bets:
            tracking.log_bets(pf.bets, settings.bankroll)
        stale = sum(1 for v in moves.values() if v["stale"])
        if stale:
            notes.append(f"직전 스냅샷 이후 Pinnacle 은 움직였는데 bet365 는 그대로인 선택지 {stale}개 (움직임 열 참고).")
    return Report(datetime.now(timezone.utc).isoformat(timespec="seconds"), source, fixtures, pricings, sels, value,
                  pf, settings, notes, moves)


# ---- 소스별 진입점 ----

def load_fixtures_json(path: Path) -> List[Fixture]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Fixture(**{k: v for k, v in f.items() if k in Fixture.__dataclass_fields__}) for f in raw["fixtures"]]


def _model_if_needed(settings: Settings, results_loader) -> Optional[DixonColes]:
    if not settings.use_model and settings.pricing.model_weight <= 0:
        return None
    return fit_model(results_loader())


def run_file(path: Path = SAMPLE_FIXTURES, results_csv: Optional[Path] = None, settings: Optional[Settings] = None) -> Report:
    settings = settings or Settings()
    fixtures = load_fixtures_json(path)
    model = _model_if_needed(settings, lambda: history.load(results_csv or history.DEFAULT_RESULTS))
    notes = ["예시 배당입니다. 실제 배당이 아닙니다."] if Path(path) == SAMPLE_FIXTURES else []
    return analyze(fixtures, model, f"file:{Path(path).name}", settings, notes)


def run_apifootball(league: int, season: int, days: int = 3, settings: Optional[Settings] = None) -> Report:
    from .sources.apifootball import APIFootball

    settings = settings or Settings()
    api = APIFootball()
    today = datetime.now(timezone.utc).date()
    fixtures = api.upcoming(league, season, today.isoformat(), (today + timedelta(days=days)).isoformat())
    model = _model_if_needed(settings, lambda: pd.concat([api.results(league, season - 1), api.results(league, season)],
                                                         ignore_index=True))
    return analyze(fixtures, model, f"api-football:{league}/{season}", settings)


def run_theoddsapi(sport: str, settings: Optional[Settings] = None, markets: tuple = ("h2h", "spreads", "totals")) -> Report:
    from .sources.theoddsapi import TheOddsAPI

    api = TheOddsAPI()
    fixtures = api.upcoming(sport, markets=markets)
    notes = []
    if api.remaining is not None:
        notes.append(f"TheOddsAPI 남은 요청 수: {api.remaining}")
    return analyze(fixtures, None, f"theoddsapi:{sport}", settings, notes)
