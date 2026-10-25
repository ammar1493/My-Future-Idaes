"""The three agents' trading strategies.

Each strategy maps a DataFrame of close prices (one column per halal coin) to
target portfolio weights in [0, 1] per coin, with each row summing to <= 1.
Weights are long-only by construction: no shorting, no leverage.
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from .indicators import bollinger, ema, rsi, sma


class Strategy(ABC):
    name: str = ""
    default_params: dict = {}
    param_grid: dict[str, list] = {}

    def __init__(self, **params):
        self.params = {**self.default_params, **params}

    @classmethod
    def grid(cls) -> list[dict]:
        keys = list(cls.param_grid)
        combos = (dict(zip(keys, vals)) for vals in itertools.product(*cls.param_grid.values()))
        return [c for c in combos if cls.valid(c)]

    @staticmethod
    def valid(params: dict) -> bool:
        return True

    @property
    @abstractmethod
    def warmup(self) -> int:
        """Bars of history needed before the first meaningful signal."""

    @abstractmethod
    def target_weights(self, closes: pd.DataFrame) -> pd.DataFrame:
        ...


class TrendFollowing(Strategy):
    """Agent 1: ride established uptrends, step aside in downtrends."""

    name = "trend_following"
    default_params = {"fast": 20, "slow": 50, "trend": 200}
    param_grid = {"fast": [10, 20, 30], "slow": [50, 100], "trend": [100, 200]}

    @staticmethod
    def valid(p):
        return p["fast"] < p["slow"] <= p["trend"]

    @property
    def warmup(self):
        return self.params["trend"]

    def target_weights(self, closes):
        p = self.params
        signal = (ema(closes, p["fast"]) > ema(closes, p["slow"])) & (closes > sma(closes, p["trend"]))
        return signal.astype(float) / closes.shape[1]


class MeanReversion(Strategy):
    """Agent 2: buy sharp dips inside an uptrend, sell on the bounce."""

    name = "mean_reversion"
    default_params = {"rsi_period": 14, "entry_rsi": 30, "exit_rsi": 55,
                      "bb_period": 20, "bb_k": 2.0, "trend": 200}
    param_grid = {"entry_rsi": [25, 30, 35], "exit_rsi": [50, 60],
                  "bb_k": [1.5, 2.0], "trend": [0, 200]}

    @property
    def warmup(self):
        return max(self.params["bb_period"], self.params["rsi_period"], self.params["trend"]) + 1

    def target_weights(self, closes):
        p = self.params
        r = rsi(closes, p["rsi_period"]).to_numpy()
        mid, _, lower = bollinger(closes, p["bb_period"], p["bb_k"])
        c = closes.to_numpy()
        mid, lower = mid.to_numpy(), lower.to_numpy()
        if p["trend"]:
            uptrend = (closes > sma(closes, p["trend"])).to_numpy()
        else:
            uptrend = np.ones_like(c, dtype=bool)

        pos = np.zeros_like(c, dtype=float)
        for j in range(c.shape[1]):
            holding = False
            for i in range(c.shape[0]):
                if not holding:
                    if r[i, j] < p["entry_rsi"] and c[i, j] < lower[i, j] and uptrend[i, j]:
                        holding = True
                elif c[i, j] > mid[i, j] or r[i, j] > p["exit_rsi"]:
                    holding = False
                pos[i, j] = holding
        return pd.DataFrame(pos / c.shape[1], index=closes.index, columns=closes.columns)


class MomentumRotation(Strategy):
    """Agent 3: periodically rotate into the strongest halal coins, else hold cash."""

    name = "momentum_rotation"
    default_params = {"lookback": 42, "top_k": 2, "rebalance": 6}
    param_grid = {"lookback": [21, 42, 84], "top_k": [1, 2, 3], "rebalance": [6, 18]}

    @property
    def warmup(self):
        return self.params["lookback"] + 1

    def target_weights(self, closes):
        p = self.params
        mom = closes / closes.shift(p["lookback"]) - 1
        k = min(p["top_k"], closes.shape[1])
        weights = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
        for i in range(self.warmup, len(closes), p["rebalance"]):
            row = mom.iloc[i].dropna()
            picks = row[row > 0].nlargest(k).index
            w = pd.Series(0.0, index=closes.columns)
            w[picks] = 1.0 / k
            weights.iloc[i] = w
        return weights.ffill().fillna(0.0)


STRATEGIES: dict[str, type[Strategy]] = {
    cls.name: cls for cls in (TrendFollowing, MeanReversion, MomentumRotation)
}
