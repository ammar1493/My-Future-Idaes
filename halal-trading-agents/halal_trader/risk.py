"""Per-agent capital sleeves and risk rules.

All three agents share one Binance account, so each one is given a virtual
"sleeve": a fixed USDT allocation plus the coins it bought with it. An agent
can never spend more than its sleeve's cash or sell coins it did not buy, so
the rest of your portfolio is never touched.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class Position:
    qty: float
    entry_price: float


@dataclass
class Sleeve:
    agent: str
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    peak_equity: float = 0.0
    month: str = ""
    month_start_equity: float = 0.0
    day: str = ""
    day_start_equity: float = 0.0
    reserved_usd: float = 0.0          # profits set aside for the subscription
    month_history: list[dict] = field(default_factory=list)
    halted: bool = False
    halt_reason: str = ""
    locked_for_month: bool = False
    cooldowns: dict[str, str] = field(default_factory=dict)   # symbol -> ISO time buys resume

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p.qty * prices.get(s, p.entry_price) for s, p in self.positions.items())

    def weights(self, prices: dict[str, float]) -> dict[str, float]:
        eq = self.equity(prices)
        if eq <= 0:
            return {}
        return {s: p.qty * prices.get(s, p.entry_price) / eq for s, p in self.positions.items()}

    def apply_buy(self, symbol: str, qty: float, cost: float) -> None:
        self.cash -= cost
        old = self.positions.get(symbol)
        if old:
            total = old.qty + qty
            old.entry_price = (old.qty * old.entry_price + cost) / total
            old.qty = total
        else:
            self.positions[symbol] = Position(qty=qty, entry_price=cost / qty)

    def apply_sell(self, symbol: str, qty: float, proceeds: float, close: bool = False) -> None:
        """Record a sale. ``close`` forgets any unsellable dust left after a full exit."""
        pos = self.positions[symbol]
        self.cash += proceeds
        pos.qty -= qty
        if close or pos.qty <= 1e-12:
            del self.positions[symbol]

    # -- persistence -----------------------------------------------------
    def save(self, state_dir: Path) -> None:
        path = state_dir / "sleeves" / f"{self.agent}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)

    @classmethod
    def load(cls, state_dir: Path, agent: str, initial_cash: float) -> "Sleeve":
        path = state_dir / "sleeves" / f"{agent}.json"
        if not path.exists():
            return cls(agent=agent, cash=initial_cash)
        data = json.loads(path.read_text())
        data["positions"] = {s: Position(**p) for s, p in data.get("positions", {}).items()}
        return cls(**data)


@dataclass
class RiskConfig:
    stop_loss: float = 0.08            # exit a coin 8% below its entry price
    max_drawdown: float = 0.25         # halt the agent at -25% from its peak
    daily_loss_limit: float = 0.05     # no new buys after -5% in a day
    max_position_weight: float = 0.5   # never more than 50% of a sleeve in one coin
    lock_profits_on_target: bool = True
    stop_cooldown_hours: float = 24.0  # no re-entry into a coin this long after a stop-loss
    monthly_target_usd: float = 0.0

    @classmethod
    def from_config(cls, cfg: dict, monthly_target_usd: float) -> "RiskConfig":
        known = {k: v for k, v in (cfg or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known, monthly_target_usd=monthly_target_usd)


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def roll_periods(self, sleeve: Sleeve, prices: dict[str, float], now: datetime) -> list[str]:
        events = []
        eq = sleeve.equity(prices)
        month, day = now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")
        if sleeve.month != month:
            if sleeve.month:
                profit = eq - sleeve.month_start_equity
                reserve = min(max(profit, 0.0), self.cfg.monthly_target_usd, max(sleeve.cash, 0.0))
                sleeve.cash -= reserve
                sleeve.reserved_usd += reserve
                sleeve.month_history.append({
                    "month": sleeve.month, "profit_usd": round(profit, 2),
                    "target_usd": self.cfg.monthly_target_usd, "reserved_usd": round(reserve, 2),
                    "target_met": profit >= self.cfg.monthly_target_usd,
                })
                events.append(f"month {sleeve.month} closed: profit ${profit:.2f}, "
                              f"reserved ${reserve:.2f} for subscription")
                eq -= reserve
            sleeve.month, sleeve.month_start_equity = month, eq
            sleeve.locked_for_month = False
        if sleeve.day != day:
            sleeve.day, sleeve.day_start_equity = day, eq
        if sleeve.peak_equity <= 0 or eq > sleeve.peak_equity:
            sleeve.peak_equity = eq
        return events

    def apply(self, target: dict[str, float], sleeve: Sleeve, prices: dict[str, float],
              now: datetime) -> tuple[dict[str, float], list[str]]:
        events = self.roll_periods(sleeve, prices, now)
        eq = sleeve.equity(prices)
        current = sleeve.weights(prices)
        target = {s: max(0.0, min(w, self.cfg.max_position_weight)) for s, w in target.items()}

        if sleeve.halted:
            return {s: 0.0 for s in set(target) | set(current)}, events + [f"halted: {sleeve.halt_reason}"]

        if sleeve.peak_equity > 0 and eq / sleeve.peak_equity - 1 <= -self.cfg.max_drawdown:
            sleeve.halted = True
            sleeve.halt_reason = (f"drawdown {eq / sleeve.peak_equity - 1:.1%} hit limit "
                                  f"-{self.cfg.max_drawdown:.0%}; review and reset manually")
            return {s: 0.0 for s in set(target) | set(current)}, events + [sleeve.halt_reason]

        month_profit = eq - sleeve.month_start_equity
        if (self.cfg.lock_profits_on_target and self.cfg.monthly_target_usd > 0
                and month_profit >= self.cfg.monthly_target_usd):
            if not sleeve.locked_for_month:
                events.append(f"monthly target reached (${month_profit:.2f}); "
                              "moving to cash until next month")
            sleeve.locked_for_month = True
        if sleeve.locked_for_month:
            return {s: 0.0 for s in set(target) | set(current)}, events

        for sym, pos in sleeve.positions.items():
            px = prices.get(sym)
            if px and px <= pos.entry_price * (1 - self.cfg.stop_loss):
                target[sym] = 0.0
                until = now + timedelta(hours=self.cfg.stop_cooldown_hours)
                sleeve.cooldowns[sym] = until.isoformat()
                events.append(f"stop-loss {sym} at {px:.6g} (entry {pos.entry_price:.6g})")

        for sym, until in list(sleeve.cooldowns.items()):
            if now >= datetime.fromisoformat(until):
                del sleeve.cooldowns[sym]
            elif sym not in sleeve.positions:
                target[sym] = 0.0

        if sleeve.day_start_equity > 0 and eq / sleeve.day_start_equity - 1 <= -self.cfg.daily_loss_limit:
            target = {s: min(w, current.get(s, 0.0)) for s, w in target.items()}
            events.append("daily loss limit hit: no new buys today")

        total = sum(target.values())
        if total > 1:
            target = {s: w / total for s, w in target.items()}
        return target, events
