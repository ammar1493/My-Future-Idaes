"""Causal technical indicators (each value uses only data up to that bar)."""

from __future__ import annotations

import pandas as pd


def ema(s: pd.Series | pd.DataFrame, span: int):
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def sma(s: pd.Series | pd.DataFrame, n: int):
    return s.rolling(n, min_periods=n).mean()


def rsi(s: pd.Series | pd.DataFrame, n: int = 14):
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def bollinger(s: pd.Series | pd.DataFrame, n: int = 20, k: float = 2.0):
    mid = sma(s, n)
    std = s.rolling(n, min_periods=n).std()
    return mid, mid + k * std, mid - k * std
