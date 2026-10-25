"""Vectorised backtester with fees and slippage."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .strategies import Strategy

BARS_PER_YEAR = {"15m": 4 * 24 * 365, "1h": 24 * 365, "4h": 6 * 365, "1d": 365}


def net_returns(strategy: Strategy, closes: pd.DataFrame, fee_rate: float = 0.001,
                slippage: float = 0.0005) -> tuple[pd.Series, pd.DataFrame]:
    """Per-bar portfolio returns after costs.

    Weights decided at the close of bar t earn the return from t to t+1, so
    there is no look-ahead. Trading cost is charged on every change in weight.
    """
    w = strategy.target_weights(closes).reindex(closes.index).fillna(0.0)
    asset_rets = closes.pct_change().fillna(0.0)
    gross = (w.shift(1).fillna(0.0) * asset_rets).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1)
    turnover.iloc[0] = w.iloc[0].abs().sum()
    return gross - turnover * (fee_rate + slippage), w


def count_entries(weights: pd.DataFrame) -> int:
    held = weights > 0
    return int((held & ~held.shift(1, fill_value=False)).to_numpy().sum())


def metrics(rets: pd.Series, interval: str, weights: pd.DataFrame | None = None) -> dict:
    rets = rets.dropna()
    bpy = BARS_PER_YEAR[interval]
    if rets.empty:
        return {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "monthly_mean": 0.0, "positive_months": 0.0, "trades": 0, "bars": 0}
    equity = (1 + rets).cumprod()
    std = rets.std()
    sharpe = float(rets.mean() / std * np.sqrt(bpy)) if std > 0 else 0.0
    drawdown = equity / equity.cummax() - 1
    monthly = equity.resample("ME").last().pct_change()
    first_month = equity.resample("ME").last().iloc[0] - 1
    monthly.iloc[0] = first_month
    out = {
        "total_return": float(equity.iloc[-1] - 1),
        "annual_return": float(equity.iloc[-1] ** (bpy / len(rets)) - 1),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "monthly_mean": float(monthly.mean()),
        "positive_months": float((monthly > 0).mean()),
        "bars": int(len(rets)),
    }
    if weights is not None:
        w = weights.loc[rets.index]
        out["trades"] = count_entries(w)
        out["exposure"] = float(w.sum(axis=1).mean())
    return out


def buy_and_hold(closes: pd.DataFrame) -> pd.Series:
    return closes.pct_change().fillna(0.0).mean(axis=1)
