"""Shariah screening for tradable symbols.

Rules applied (following common scholarly positions on crypto trading):

* Spot only: no margin, futures, options or leveraged tokens (riba / gharar / maysir).
* No assets whose core purpose is interest-based lending or borrowing.
* No gambling, betting or lottery tokens.
* Only coins on an explicit approved list are traded. Everything else is rejected.
* Stablecoins are used only as the quote currency (cash), never "earned" on.

The approved list is a starting point, not a fatwa. Verify each coin with a
scholar or screening service you trust (e.g. Islamicly, Sharlife, Shariyah
Review Bureau) and edit ``halal.approved`` in config.yaml accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_APPROVED = (
    "BTC", "ETH", "SOL", "ADA", "DOT", "LINK", "AVAX",
    "ATOM", "NEAR", "ALGO", "XLM", "LTC",
)

DEFAULT_QUOTE_ASSETS = ("USDT", "USDC", "FDUSD")

# Assets rejected even if a user adds them to the approved list by mistake.
PROHIBITED = {
    # interest-based lending / borrowing protocols
    "AAVE": "interest-based lending protocol",
    "COMP": "interest-based lending protocol",
    "MKR": "interest-bearing collateralised debt",
    "XVS": "interest-based lending protocol",
    "JST": "interest-based lending protocol",
    "ALPACA": "leveraged yield farming",
    "BNX": "leveraged yield farming",
    # gambling / betting
    "FUN": "gambling",
    "WIN": "gambling",
    "CHIPS": "gambling",
    "ROLL": "gambling",
}

LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


class HalalViolation(Exception):
    """Raised when something tries to trade a symbol that failed screening."""


@dataclass
class HalalScreen:
    approved: set[str] = field(default_factory=lambda: set(DEFAULT_APPROVED))
    quote_assets: set[str] = field(default_factory=lambda: set(DEFAULT_QUOTE_ASSETS))
    extra_blocked: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: dict | None) -> "HalalScreen":
        cfg = cfg or {}
        return cls(
            approved={a.upper() for a in cfg.get("approved", DEFAULT_APPROVED)},
            quote_assets={a.upper() for a in cfg.get("quote_assets", DEFAULT_QUOTE_ASSETS)},
            extra_blocked={k.upper(): v for k, v in (cfg.get("blocked") or {}).items()},
        )

    def check_asset(self, base: str) -> tuple[bool, str]:
        base = base.upper()
        blocked = {**PROHIBITED, **self.extra_blocked}
        if base in blocked:
            return False, blocked[base]
        if any(base.endswith(s) and len(base) > len(s) for s in LEVERAGED_SUFFIXES):
            return False, "leveraged token"
        if base in self.quote_assets:
            return False, "stablecoin (cash only, not traded)"
        if base not in self.approved:
            return False, "not on approved list"
        return True, "approved"

    def check(self, base: str, quote: str, symbol_info: dict | None = None) -> tuple[bool, str]:
        if quote.upper() not in self.quote_assets:
            return False, f"quote {quote} is not an approved cash asset"
        ok, reason = self.check_asset(base)
        if not ok:
            return ok, reason
        if symbol_info is not None:
            if symbol_info.get("status") != "TRADING":
                return False, "not currently trading"
            if not symbol_info.get("isSpotTradingAllowed", False):
                return False, "spot trading not allowed"
        return True, "approved"

    def assert_allowed(self, base: str, quote: str) -> None:
        ok, reason = self.check(base, quote)
        if not ok:
            raise HalalViolation(f"{base}{quote} blocked: {reason}")

    def resolve_universe(
        self, bases: list[str], quote: str, exchange_info: dict | None = None
    ) -> tuple[list[str], dict[str, str]]:
        """Return (allowed bases, {rejected base: reason})."""
        info = {}
        if exchange_info:
            info = {s["symbol"]: s for s in exchange_info.get("symbols", [])}
        allowed, rejected = [], {}
        for base in bases:
            base = base.upper()
            sym_info = None
            if exchange_info is not None:
                sym_info = info.get(base + quote)
                if sym_info is None:
                    rejected[base] = f"{base}{quote} not listed on Binance"
                    continue
            ok, reason = self.check(base, quote, sym_info)
            if ok:
                allowed.append(base)
            else:
                rejected[base] = reason
        return allowed, rejected
