"""Order execution: a paper broker for simulation and a Binance spot broker.

Every order passes through the halal screen first, so a misconfigured agent
cannot trade a non-approved coin. Only spot MARKET orders exist here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .binance_client import BinanceClient, floor_to_step
from .halal import HalalScreen


@dataclass
class Fill:
    symbol: str
    side: str
    qty: float          # coins received (buy) or sold (sell), net of coin fees
    quote: float        # cash spent (buy) or received (sell), net of cash fees
    price: float


@dataclass
class SymbolRules:
    step_size: str = "0.00000001"
    min_qty: float = 0.0
    min_notional: float = 5.0

    @classmethod
    def from_exchange_info(cls, info: dict) -> dict[str, "SymbolRules"]:
        rules = {}
        for s in info.get("symbols", []):
            r = cls()
            for f in s.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    r.step_size, r.min_qty = f["stepSize"], float(f["minQty"])
                elif f["filterType"] in ("NOTIONAL", "MIN_NOTIONAL"):
                    r.min_notional = float(f.get("minNotional", r.min_notional))
            rules[s["symbol"]] = r
        return rules


class Broker:
    def __init__(self, screen: HalalScreen, quote: str, rules: dict[str, SymbolRules] | None = None):
        self.screen = screen
        self.quote = quote
        self.rules = rules or {}

    def rule(self, symbol: str) -> SymbolRules:
        return self.rules.get(symbol, SymbolRules())

    def _check(self, symbol: str) -> None:
        self.screen.assert_allowed(symbol[: -len(self.quote)], self.quote)

    def buy(self, symbol: str, quote_amount: float, price: float) -> Fill | None:
        self._check(symbol)
        if quote_amount < self.rule(symbol).min_notional:
            return None
        return self._buy(symbol, quote_amount, price)

    def sell(self, symbol: str, qty: float, price: float) -> Fill | None:
        self._check(symbol)
        r = self.rule(symbol)
        qty = float(floor_to_step(qty, r.step_size))
        if qty <= 0 or qty < r.min_qty or qty * price < r.min_notional:
            return None
        return self._sell(symbol, qty, price)

    def _buy(self, symbol, quote_amount, price):
        raise NotImplementedError

    def _sell(self, symbol, qty, price):
        raise NotImplementedError


class PaperBroker(Broker):
    """Simulated fills at the latest price with fees and slippage."""

    def __init__(self, screen, quote, rules=None, fee_rate=0.001, slippage=0.0005):
        super().__init__(screen, quote, rules)
        self.fee_rate, self.slippage = fee_rate, slippage

    def _buy(self, symbol, quote_amount, price):
        fill_px = price * (1 + self.slippage)
        qty = float(floor_to_step(quote_amount * (1 - self.fee_rate) / fill_px, self.rule(symbol).step_size))
        return Fill(symbol, "BUY", qty, quote_amount, fill_px)

    def _sell(self, symbol, qty, price):
        fill_px = price * (1 - self.slippage)
        return Fill(symbol, "SELL", qty, qty * fill_px * (1 - self.fee_rate), fill_px)


class BinanceBroker(Broker):
    """Real spot market orders (mainnet or testnet)."""

    def __init__(self, client: BinanceClient, screen, quote, rules=None):
        super().__init__(screen, quote, rules)
        self.client = client

    def _parse(self, symbol: str, side: str, resp: dict) -> Fill:
        base = symbol[: -len(self.quote)]
        qty = float(resp["executedQty"])
        quote_amt = float(resp["cummulativeQuoteQty"])
        for f in resp.get("fills", []):
            fee = float(f.get("commission", 0))
            if f.get("commissionAsset") == base:
                qty -= fee
            elif f.get("commissionAsset") == self.quote:
                quote_amt += fee if side == "BUY" else -fee
        executed = float(resp["executedQty"])
        price = float(resp["cummulativeQuoteQty"]) / executed if executed else 0.0
        return Fill(symbol, side, qty, quote_amt, price)

    def _buy(self, symbol, quote_amount, price):
        resp = self.client.market_order(symbol, "BUY", quote_qty=floor_to_step(quote_amount, "0.01"))
        return self._parse(symbol, "BUY", resp)

    def _sell(self, symbol, qty, price):
        resp = self.client.market_order(symbol, "SELL", quantity=floor_to_step(qty, self.rule(symbol).step_size))
        return self._parse(symbol, "SELL", resp)
