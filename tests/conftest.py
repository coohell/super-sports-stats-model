import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def synthetic_league():
    """알려진 전력으로 만든 가상 리그 3시즌."""
    rng = np.random.RandomState(0)
    teams = [f"T{i}" for i in range(10)]
    attack = np.linspace(0.4, -0.4, 10)
    defence = np.linspace(-0.3, 0.3, 10)
    rows, day = [], pd.Timestamp("2022-08-01")
    for season in range(3):
        for rnd in range(18):
            order = rng.permutation(10)
            for k in range(5):
                h, a = order[2 * k], order[2 * k + 1]
                lam = np.exp(attack[h] + defence[a] + 0.25)
                mu = np.exp(attack[a] + defence[h])
                rows.append({"date": day, "home": teams[h], "away": teams[a],
                             "hg": rng.poisson(lam), "ag": rng.poisson(mu)})
            day += pd.Timedelta(days=7)
    return pd.DataFrame(rows)
