from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from halal_trader import cli
from halal_trader.agent import TradingAgent
from halal_trader.binance_client import floor_to_step, sign
from halal_trader.broker import PaperBroker
from halal_trader.halal import HalalScreen, HalalViolation
from halal_trader.indicators import rsi
from halal_trader.risk import Position, RiskConfig, RiskManager, Sleeve
from halal_trader.strategies import STRATEGIES, MomentumRotation, TrendFollowing
from halal_trader.training import walk_forward

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def prices_frame(n=900, cols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n))) for c in cols}, index=idx)


# -- halal screen ------------------------------------------------------------
@pytest.mark.parametrize("base,quote,reason", [
    ("AAVE", "USDT", "interest"),
    ("BTCUP", "USDT", "leveraged"),
    ("ETHBEAR", "USDT", "leveraged"),
    ("FUN", "USDT", "gambling"),
    ("DOGE", "USDT", "not on approved list"),
    ("BTC", "EUR", "quote"),
    ("USDC", "USDT", "stablecoin"),
])
def test_screen_blocks(base, quote, reason):
    ok, why = HalalScreen().check(base, quote)
    assert not ok and reason in why


def test_prohibited_cannot_be_approved_by_config():
    screen = HalalScreen.from_config({"approved": ["BTC", "AAVE"]})
    assert screen.check("BTC", "USDT")[0]
    assert not screen.check("AAVE", "USDT")[0]


def test_resolve_universe_uses_exchange_listing():
    info = {"symbols": [
        {"symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
        {"symbol": "ETHUSDT", "status": "BREAK", "isSpotTradingAllowed": True},
    ]}
    allowed, rejected = HalalScreen().resolve_universe(["BTC", "ETH", "SOL", "AAVE"], "USDT", info)
    assert allowed == ["BTC"]
    assert set(rejected) == {"ETH", "SOL", "AAVE"}


def test_broker_refuses_non_halal_symbol():
    broker = PaperBroker(HalalScreen(), "USDT")
    with pytest.raises(HalalViolation):
        broker.buy("AAVEUSDT", 100, 50.0)


# -- primitives ----------------------------------------------------------------
def test_binance_signature_matches_docs_example():
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
    params = {"symbol": "LTCBTC", "side": "BUY", "type": "LIMIT", "timeInForce": "GTC",
              "quantity": 1, "price": 0.1, "recvWindow": 5000, "timestamp": 1499827319559}
    assert sign(secret, params) == "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"


def test_floor_to_step():
    assert floor_to_step(0.123456789, "0.00010000") == "0.1234"
    assert floor_to_step(12.9, "1.00000000") == "12"
    assert floor_to_step(5.0, "0.01") == "5.00"


def test_rsi_bounded():
    r = rsi(prices_frame()["BTCUSDT"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()


# -- strategies ------------------------------------------------------------------
@pytest.mark.parametrize("name", list(STRATEGIES))
def test_strategies_long_only_and_no_lookahead(name):
    closes = prices_frame()
    strat = STRATEGIES[name]()
    w = strat.target_weights(closes)
    assert (w >= 0).all().all() and (w.sum(axis=1) <= 1 + 1e-9).all()

    cut = 600
    future_changed = closes.copy()
    future_changed.iloc[cut:] *= 3.0
    w2 = strat.target_weights(future_changed)
    pd.testing.assert_frame_equal(w.iloc[:cut], w2.iloc[:cut])


def test_grid_respects_constraints():
    assert all(p["fast"] < p["slow"] <= p["trend"] for p in TrendFollowing.grid())


def test_walk_forward_rejects_losing_strategy():
    idx = pd.date_range("2023-01-01", periods=2000, freq="4h", tz="UTC")
    falling = pd.DataFrame({"BTCUSDT": np.linspace(100, 20, 2000), "ETHUSDT": np.linspace(50, 10, 2000)},
                           index=idx)
    res = walk_forward("t", "momentum_rotation", falling, "4h", 400, 20)
    assert not res.approved


# -- risk ----------------------------------------------------------------------
def rm(**kw):
    return RiskManager(RiskConfig(monthly_target_usd=kw.pop("target", 20), **kw))


def test_drawdown_halts_and_liquidates():
    s = Sleeve("a", cash=0, positions={"BTCUSDT": Position(1.0, 100.0)})
    risk = rm()
    risk.apply({"BTCUSDT": 0.5}, s, {"BTCUSDT": 100.0}, NOW)
    target, _ = risk.apply({"BTCUSDT": 0.5}, s, {"BTCUSDT": 70.0}, NOW)
    assert s.halted and target["BTCUSDT"] == 0


def test_monthly_target_locks_profit_then_reserves_on_rollover():
    s = Sleeve("a", cash=400)
    risk = rm(target=20)
    risk.apply({}, s, {}, NOW)
    s.cash = 425  # made $25 this month
    target, events = risk.apply({"BTCUSDT": 0.5}, s, {}, NOW)
    assert target["BTCUSDT"] == 0 and s.locked_for_month
    risk.apply({"BTCUSDT": 0.5}, s, {}, NOW + timedelta(days=20))
    assert s.reserved_usd == 20 and s.cash == 405 and not s.locked_for_month
    assert s.month_history[-1]["target_met"]


def test_stop_loss_and_cooldown():
    s = Sleeve("a", cash=0, positions={"BTCUSDT": Position(1.0, 100.0)})
    risk = rm(max_drawdown=0.9)
    target, _ = risk.apply({"BTCUSDT": 0.5}, s, {"BTCUSDT": 90.0}, NOW)
    assert target["BTCUSDT"] == 0 and "BTCUSDT" in s.cooldowns
    del s.positions["BTCUSDT"]
    s.cash = 90
    target, _ = risk.apply({"BTCUSDT": 0.5}, s, {"BTCUSDT": 95.0}, NOW + timedelta(hours=2))
    assert target["BTCUSDT"] == 0
    target, _ = risk.apply({"BTCUSDT": 0.5}, s, {"BTCUSDT": 95.0}, NOW + timedelta(hours=30))
    assert target["BTCUSDT"] == 0.5


def test_position_weight_cap():
    s = Sleeve("a", cash=1000)
    target, _ = rm(max_position_weight=0.4).apply({"BTCUSDT": 1.0}, s, {"BTCUSDT": 1.0}, NOW)
    assert target["BTCUSDT"] == 0.4


# -- agent ---------------------------------------------------------------------
class AlwaysIn(MomentumRotation):
    def target_weights(self, closes):
        return pd.DataFrame(0.5, index=closes.index, columns=closes.columns)


def test_agent_never_spends_more_than_sleeve():
    closes = prices_frame(cols=("BTCUSDT", "ETHUSDT"))
    prices = closes.iloc[-1].to_dict()
    sleeve = Sleeve("a", cash=300)
    ag = TradingAgent("a", AlwaysIn(), ["BTCUSDT", "ETHUSDT"], PaperBroker(HalalScreen(), "USDT"),
                      rm(max_position_weight=1.0, target=0), sleeve)
    fills, _ = ag.step(closes, prices, NOW)
    assert len(fills) == 2 and sleeve.cash >= 0
    assert sleeve.equity(prices) <= 300
    fills, _ = ag.step(closes, prices, NOW)  # already at target: no churn
    assert fills == []


# -- end to end: paper mode against a fake Binance --------------------------------
class FakeClient:
    def __init__(self, closes):
        self.closes = closes

    def exchange_info(self):
        return {"symbols": [{"symbol": s, "status": "TRADING", "isSpotTradingAllowed": True,
                             "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001"},
                                         {"filterType": "NOTIONAL", "minNotional": "5"}]}
                            for s in self.closes.columns]}

    def closed_closes(self, symbol, interval, limit=500):
        return self.closes[symbol].iloc[-limit:]

    def prices(self, symbols):
        return {s: float(self.closes[s].iloc[-1]) for s in symbols}


def test_paper_run_end_to_end(tmp_path, monkeypatch):
    cfg = cli.load_config("config.example.yaml")
    cfg["state_dir"] = str(tmp_path)
    closes = prices_frame(n=1500, cols=tuple(
        sorted({b + "USDT" for a in cfg["agents"].values() for b in a["universe"]})))
    fake = FakeClient(closes)
    for name, a in cfg["agents"].items():
        res = walk_forward(name, a["strategy"], closes[[b + "USDT" for b in a["universe"]]],
                           "4h", a["capital_usd"], a["monthly_target_usd"])
        res.approved = True  # force through the gate to exercise the trading path
        res.save(tmp_path / "params" / f"{name}.json")
    monkeypatch.setattr(cli, "make_client", lambda cfg, signed: fake)
    agents = cli.build_agents(cfg, fake, fake.exchange_info(), force=False)
    assert len(agents) == 3
    cli.run_once(cfg, fake, agents)
    for name in cfg["agents"]:
        loaded = Sleeve.load(tmp_path, name, 0)
        assert loaded.cash >= 0 and loaded.month == datetime.now(timezone.utc).strftime("%Y-%m")
