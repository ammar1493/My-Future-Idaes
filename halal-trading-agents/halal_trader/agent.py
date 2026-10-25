"""A trading agent = strategy + risk manager + sleeve + broker."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .broker import Broker, Fill
from .risk import RiskManager, Sleeve
from .strategies import Strategy

log = logging.getLogger("halal_trader")


class TradingAgent:
    def __init__(self, name: str, strategy: Strategy, symbols: list[str], broker: Broker,
                 risk: RiskManager, sleeve: Sleeve, rebalance_threshold: float = 0.05,
                 min_trade_usd: float = 10.0):
        self.name = name
        self.strategy = strategy
        self.symbols = symbols
        self.broker = broker
        self.risk = risk
        self.sleeve = sleeve
        self.rebalance_threshold = rebalance_threshold
        self.min_trade_usd = min_trade_usd

    def step(self, closes: pd.DataFrame, prices: dict[str, float],
             now: datetime | None = None) -> tuple[list[Fill], list[str]]:
        now = now or datetime.now(timezone.utc)
        closes = closes[self.symbols].dropna(how="any")
        if len(closes) < self.strategy.warmup:
            return [], [f"waiting for history ({len(closes)}/{self.strategy.warmup} bars)"]

        raw = self.strategy.target_weights(closes).iloc[-1].to_dict()
        target, events = self.risk.apply(raw, self.sleeve, prices, now)
        equity = self.sleeve.equity(prices)
        current = self.sleeve.weights(prices)
        fills: list[Fill] = []

        # sells first so their cash can fund buys
        for sym in sorted(set(current) | set(target)):
            cur_w, tgt_w = current.get(sym, 0.0), target.get(sym, 0.0)
            pos = self.sleeve.positions.get(sym)
            if pos is None or tgt_w >= cur_w:
                continue
            full_exit = tgt_w == 0.0
            if not full_exit and cur_w - tgt_w < self.rebalance_threshold:
                continue
            qty = pos.qty if full_exit else (cur_w - tgt_w) * equity / prices[sym]
            fill = self.broker.sell(sym, min(qty, pos.qty), prices[sym])
            if fill:
                self.sleeve.apply_sell(sym, fill.qty, fill.quote, close=full_exit)
                fills.append(fill)
            elif full_exit and pos.qty * prices[sym] < self.broker.rule(sym).min_notional:
                # below Binance's minimum order size: unsellable dust, stop tracking it
                del self.sleeve.positions[sym]
                events.append(f"dropped {sym} dust ({pos.qty:.8g}) below exchange minimum")

        for sym, tgt_w in sorted(target.items()):
            cur_w = current.get(sym, 0.0)
            if tgt_w <= cur_w or (cur_w > 0 and tgt_w - cur_w < self.rebalance_threshold):
                continue
            amount = min((tgt_w - cur_w) * equity, self.sleeve.cash * 0.999)
            if amount < self.min_trade_usd:
                continue
            fill = self.broker.buy(sym, amount, prices[sym])
            if fill and fill.qty > 0:
                self.sleeve.apply_buy(sym, fill.qty, fill.quote)
                fills.append(fill)

        for f in fills:
            events.append(f"{f.side} {f.qty:.8g} {f.symbol} @ {f.price:.6g} (${f.quote:.2f})")
        return fills, events
