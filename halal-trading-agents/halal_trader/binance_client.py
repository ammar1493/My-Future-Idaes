"""Minimal Binance spot REST client (no margin / futures endpoints on purpose)."""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import ROUND_DOWN, Decimal
from urllib.parse import urlencode

import pandas as pd
import requests

MAINNET = "https://api.binance.com"
TESTNET = "https://testnet.binance.vision"

INTERVAL_MS = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


class BinanceError(Exception):
    pass


def sign(secret: str, params: dict) -> str:
    query = urlencode(params)
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def floor_to_step(value: float, step: str | float) -> str:
    """Floor ``value`` to a Binance step size and return it as a plain string."""
    step_d = Decimal(str(step)).normalize()
    if step_d <= 0:
        return format(Decimal(str(value)), "f")
    floored = (Decimal(str(value)) / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d
    return format(floored.quantize(step_d) if step_d < 1 else floored, "f")


class BinanceClient:
    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = False,
                 timeout: float = 15.0, session: requests.Session | None = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = TESTNET if testnet else MAINNET
        self.timeout = timeout
        self.session = session or requests.Session()

    # -- transport -------------------------------------------------------
    def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        headers = {}
        if signed:
            if not (self.api_key and self.api_secret):
                raise BinanceError("API key/secret required for signed endpoint " + path)
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            params["signature"] = sign(self.api_secret, params)
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        resp = self.session.request(method, self.base_url + path, params=params,
                                    headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise BinanceError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # -- public ----------------------------------------------------------
    def exchange_info(self) -> dict:
        return self._request("GET", "/api/v3/exchangeInfo")

    def prices(self, symbols: list[str]) -> dict[str, float]:
        data = self._request("GET", "/api/v3/ticker/price")
        wanted = set(symbols)
        return {d["symbol"]: float(d["price"]) for d in data if d["symbol"] in wanted}

    def klines(self, symbol: str, interval: str, limit: int = 500,
               start_ms: int | None = None, end_ms: int | None = None) -> list:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._request("GET", "/api/v3/klines", params)

    def closed_closes(self, symbol: str, interval: str, limit: int = 500) -> pd.Series:
        """Close prices of fully closed candles only (drops the live candle)."""
        rows = self.klines(symbol, interval, limit=limit)
        now_ms = int(time.time() * 1000)
        rows = [r for r in rows if int(r[6]) < now_ms]
        return _rows_to_series(rows, symbol)

    def history(self, symbol: str, interval: str, days: int) -> pd.Series:
        step = INTERVAL_MS[interval]
        end = int(time.time() * 1000)
        start = end - days * 24 * 60 * 60_000
        rows: list = []
        while start < end:
            batch = self.klines(symbol, interval, limit=1000, start_ms=start)
            if not batch:
                break
            rows.extend(batch)
            start = int(batch[-1][0]) + step
            if len(batch) < 1000:
                break
        rows = [r for r in rows if int(r[6]) < end]
        return _rows_to_series(rows, symbol)

    # -- signed (spot only) ---------------------------------------------
    def account(self) -> dict:
        return self._request("GET", "/api/v3/account", signed=True)

    def api_restrictions(self) -> dict:
        return self._request("GET", "/sapi/v1/account/apiRestrictions", signed=True)

    def market_order(self, symbol: str, side: str, quantity: str | None = None,
                     quote_qty: str | None = None) -> dict:
        params = {"symbol": symbol, "side": side, "type": "MARKET", "newOrderRespType": "FULL"}
        if quantity is not None:
            params["quantity"] = quantity
        elif quote_qty is not None:
            params["quoteOrderQty"] = quote_qty
        else:
            raise ValueError("quantity or quote_qty required")
        return self._request("POST", "/api/v3/order", params, signed=True)


def _rows_to_series(rows: list, symbol: str) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float, name=symbol)
    idx = pd.to_datetime([int(r[6]) + 1 for r in rows], unit="ms", utc=True)
    s = pd.Series([float(r[4]) for r in rows], index=idx, name=symbol)
    return s[~s.index.duplicated(keep="last")]
