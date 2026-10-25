"""Command line entry point: python -m halal_trader <command>."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .agent import TradingAgent
from .binance_client import INTERVAL_MS, BinanceClient
from .broker import BinanceBroker, PaperBroker, SymbolRules
from .halal import HalalScreen
from .risk import RiskConfig, RiskManager, Sleeve
from .strategies import STRATEGIES
from .training import load_params, walk_forward

log = logging.getLogger("halal_trader")


# -- setup -------------------------------------------------------------------
def load_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg.get("mode") not in ("paper", "testnet", "live"):
        raise SystemExit("config mode must be paper, testnet or live")
    for name, a in cfg["agents"].items():
        if a["strategy"] not in STRATEGIES:
            raise SystemExit(f"agent {name}: unknown strategy {a['strategy']}")
    return cfg


def make_client(cfg: dict, signed: bool) -> BinanceClient:
    key, secret = os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", "")
    if signed and not (key and secret):
        raise SystemExit("BINANCE_API_KEY / BINANCE_API_SECRET missing (see .env.example)")
    return BinanceClient(key, secret, testnet=cfg["mode"] == "testnet")


def symbols_for(cfg: dict, screen: HalalScreen, bases: list[str], info: dict | None) -> list[str]:
    q = cfg["quote_asset"]
    allowed, rejected = screen.resolve_universe(bases, q, info)
    for base, reason in rejected.items():
        log.warning("skipping %s%s: %s", base, q, reason)
    return [b + q for b in allowed]


# -- data --------------------------------------------------------------------
def history_path(cfg: dict, symbol: str) -> Path:
    return Path(cfg["data_dir"]) / f"{symbol}_{cfg['interval']}.csv"


def load_history(cfg: dict, symbols: list[str]) -> pd.DataFrame:
    frames = {}
    for sym in symbols:
        path = history_path(cfg, sym)
        if not path.exists():
            raise SystemExit(f"no history for {sym}; run `download` first")
        frames[sym] = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    return pd.DataFrame(frames).dropna(how="any")


def synthetic_history(symbols: list[str], bars: int, seed: int = 7) -> pd.DataFrame:
    """Random-walk prices for an offline dry run of the pipeline (not real data)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("4h"), periods=bars, freq="4h")
    market = rng.normal(0.0002, 0.012, bars)
    data = {}
    for sym in symbols:
        r = market + rng.normal(0.0, 0.015, bars)
        data[sym] = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame(data, index=idx)


# -- commands ----------------------------------------------------------------
def cmd_screen(cfg, args):
    screen = HalalScreen.from_config(cfg.get("halal"))
    info = None
    if not args.offline:
        info = make_client(cfg, signed=False).exchange_info()
    for name, a in cfg["agents"].items():
        allowed, rejected = screen.resolve_universe(a["universe"], cfg["quote_asset"], info)
        print(f"\n[{name}] {a['strategy']}")
        print("  trades:  " + (", ".join(allowed) or "(nothing)"))
        for base, reason in rejected.items():
            print(f"  blocked: {base} - {reason}")


def cmd_audit(cfg, args):
    """Flag anything in your Binance balances that fails the halal screen."""
    screen = HalalScreen.from_config(cfg.get("halal"))
    acct = make_client(cfg, signed=True).account()
    print(f"{'asset':<10}{'free':>18}{'locked':>18}  status")
    for b in acct["balances"]:
        free, locked = float(b["free"]), float(b["locked"])
        if free + locked == 0:
            continue
        asset = b["asset"]
        if asset in screen.quote_assets:
            status = "cash (quote asset)"
        else:
            ok, reason = screen.check_asset(asset)
            status = "halal-approved" if ok else f"REVIEW: {reason}"
        print(f"{asset:<10}{free:>18.8f}{locked:>18.8f}  {status}")


def cmd_download(cfg, args):
    screen = HalalScreen.from_config(cfg.get("halal"))
    client = make_client(cfg, signed=False)
    info = client.exchange_info()
    bases = sorted({b for a in cfg["agents"].values() for b in a["universe"]})
    for sym in symbols_for(cfg, screen, bases, info):
        s = client.history(sym, cfg["interval"], cfg["history_days"])
        path = history_path(cfg, sym)
        path.parent.mkdir(parents=True, exist_ok=True)
        s.to_csv(path)
        print(f"{sym}: {len(s)} bars -> {path}")


def cmd_train(cfg, args):
    screen = HalalScreen.from_config(cfg.get("halal"))
    t = cfg.get("training", {})
    state_dir = Path(cfg["state_dir"])
    if cfg["interval"] not in INTERVAL_MS:
        raise SystemExit(f"unsupported interval {cfg['interval']}")
    for name, a in cfg["agents"].items():
        if args.agent and name != args.agent:
            continue
        symbols = symbols_for(cfg, screen, a["universe"], None)
        if args.synthetic:
            closes = synthetic_history(symbols, bars=6 * 365 * 3)
        else:
            closes = load_history(cfg, symbols)
        res = walk_forward(
            name, a["strategy"], closes, cfg["interval"], a["capital_usd"],
            a["monthly_target_usd"], cfg["fee_rate"], cfg["slippage"],
            n_splits=t.get("n_splits", 3), min_trades=t.get("min_trades", 5),
            min_sharpe=t.get("min_sharpe", 0.5), max_drawdown=t.get("max_drawdown", 0.35),
        )
        if not args.synthetic:
            res.save(state_dir / "params" / f"{name}.json")
        print_training(res, synthetic=args.synthetic)


def print_training(res, synthetic=False):
    o, b = res.oos, res.benchmark_oos
    tag = " (SYNTHETIC DATA - pipeline check only, not saved)" if synthetic else ""
    print(f"\n=== {res.agent} ({res.strategy}) on {', '.join(res.universe)}{tag}")
    print(f"  chosen params:        {res.params}")
    print(f"  out-of-sample return: {o['total_return']:+.1%}  (buy & hold {b['total_return']:+.1%})")
    print(f"  out-of-sample Sharpe: {o['sharpe']:.2f}   max drawdown {o['max_drawdown']:.1%}   trades {o['trades']}")
    print(f"  avg monthly return:   {o['monthly_mean']:+.2%}   positive months {o['positive_months']:.0%}")
    need = res.required_monthly_return
    print(f"  subscription needs:   {need:.2%}/month (${res.monthly_target_usd:g} on ${res.capital_usd:g})")
    if o["monthly_mean"] < need:
        print("  NOTE: historical average is below what the subscription needs; "
              "expect some months to fall short or raise capital_usd.")
    print(f"  APPROVED TO TRADE:    {'yes' if res.approved else 'NO'}")
    for r in res.reasons:
        print(f"    - {r}")


def build_agents(cfg, client, info, force: bool):
    screen = HalalScreen.from_config(cfg.get("halal"))
    state_dir = Path(cfg["state_dir"])
    rules = SymbolRules.from_exchange_info(info)
    r = cfg.get("risk", {})
    if cfg["mode"] == "paper":
        broker = PaperBroker(screen, cfg["quote_asset"], rules, cfg["fee_rate"], cfg["slippage"])
    else:
        broker = BinanceBroker(client, screen, cfg["quote_asset"], rules)
    agents = []
    for name, a in cfg["agents"].items():
        trained = load_params(state_dir, name)
        if trained is None:
            log.warning("[%s] not trained yet; run `train` first. skipping", name)
            continue
        if not trained["approved"] and not force:
            log.warning("[%s] failed training gate (%s). skipping (use --force-unapproved in paper mode)",
                        name, "; ".join(trained["reasons"]))
            continue
        symbols = symbols_for(cfg, screen, a["universe"], info)
        strategy = STRATEGIES[a["strategy"]](**trained["params"])
        risk = RiskManager(RiskConfig.from_config(r, a["monthly_target_usd"]))
        sleeve = Sleeve.load(state_dir, name, a["capital_usd"])
        agents.append(TradingAgent(name, strategy, symbols, broker, risk, sleeve,
                                   r.get("rebalance_threshold", 0.05), r.get("min_trade_usd", 10)))
    return agents


def preflight_live(cfg, client):
    if os.environ.get("HALAL_TRADER_CONFIRM_LIVE") != "yes":
        raise SystemExit("live mode places REAL orders. Set HALAL_TRADER_CONFIRM_LIVE=yes in .env to proceed.")
    restr = client.api_restrictions()
    if restr.get("enableWithdrawals"):
        raise SystemExit("refusing to run: this API key can WITHDRAW funds. Disable withdrawals on the key.")
    for flag in ("enableMargin", "enableFutures"):
        if restr.get(flag):
            raise SystemExit(f"refusing to run: API key has {flag} on. Spot-only keys are required (no margin/futures).")
    if not restr.get("ipRestrict"):
        log.warning("API key is not IP-restricted; strongly recommended in Binance API settings.")


def check_funding(cfg, client, agents):
    q = cfg["quote_asset"]
    acct = client.account()
    free = next((float(b["free"]) for b in acct["balances"] if b["asset"] == q), 0.0)
    needed = sum(ag.sleeve.cash for ag in agents)
    if free + 1e-6 < needed:
        raise SystemExit(f"agents need {needed:.2f} {q} in cash but only {free:.2f} is free on Binance")


def run_once(cfg, client, agents):
    symbols = sorted({s for ag in agents for s in ag.symbols})
    limit = max(ag.strategy.warmup for ag in agents) + 50
    closes = pd.DataFrame({s: client.closed_closes(s, cfg["interval"], limit=min(limit, 1000))
                           for s in symbols})
    prices = client.prices(symbols)
    now = datetime.now(timezone.utc)
    for ag in agents:
        try:
            _, events = ag.step(closes, prices, now)
        except Exception:
            log.exception("[%s] step failed; state not saved for this agent", ag.name)
            continue
        for e in events:
            log.info("[%s] %s", ag.name, e)
        ag.sleeve.save(Path(cfg["state_dir"]))
        log.info("[%s] equity $%.2f (cash $%.2f, reserved $%.2f)", ag.name,
                 ag.sleeve.equity(prices), ag.sleeve.cash, ag.sleeve.reserved_usd)


def cmd_run(cfg, args):
    if args.force_unapproved and cfg["mode"] != "paper":
        raise SystemExit("--force-unapproved is only allowed in paper mode")
    client = make_client(cfg, signed=cfg["mode"] != "paper")
    if cfg["mode"] == "live":
        preflight_live(cfg, client)
    info = client.exchange_info()
    agents = build_agents(cfg, client, info, args.force_unapproved)
    if not agents:
        raise SystemExit("no agents are approved to trade (see `train` output)")
    if cfg["mode"] != "paper" and not any(Path(cfg["state_dir"], "sleeves", f"{a.name}.json").exists()
                                         for a in agents):
        check_funding(cfg, client, agents)
    log.info("running %s in %s mode", ", ".join(a.name for a in agents), cfg["mode"].upper())
    step_s = INTERVAL_MS[cfg["interval"]] / 1000
    while True:
        run_once(cfg, client, agents)
        if args.once:
            return
        # wake shortly after the next candle closes
        sleep_for = step_s - (time.time() % step_s) + 15
        log.info("next check in %.0f minutes", sleep_for / 60)
        time.sleep(sleep_for)


def cmd_report(cfg, args):
    state_dir = Path(cfg["state_dir"])
    for name, a in cfg["agents"].items():
        trained = load_params(state_dir, name)
        print(f"\n[{name}] {a['strategy']}  target ${a['monthly_target_usd']}/month")
        if trained:
            print(f"  training: {'approved' if trained['approved'] else 'NOT approved'}; "
                  f"OOS return {trained['oos']['total_return']:+.1%}, Sharpe {trained['oos']['sharpe']:.2f}")
        else:
            print("  training: not run")
        path = state_dir / "sleeves" / f"{name}.json"
        if not path.exists():
            print("  trading: not started")
            continue
        s = Sleeve.load(state_dir, name, a["capital_usd"])
        print(f"  cash ${s.cash:.2f}, positions {', '.join(f'{k} {v.qty:.6g}' for k, v in s.positions.items()) or 'none'}")
        print(f"  reserved for subscription: ${s.reserved_usd:.2f}")
        if s.halted:
            print(f"  HALTED: {s.halt_reason}")
        for m in s.month_history[-6:]:
            mark = "met" if m["target_met"] else "missed"
            print(f"  {m['month']}: profit ${m['profit_usd']:+.2f} / target ${m['target_usd']} ({mark})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="halal_trader", description=__doc__)
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("screen", help="show which coins each agent may trade")
    s.add_argument("--offline", action="store_true", help="skip the Binance listing check")
    sub.add_parser("audit", help="flag non-approved assets in your Binance balances")
    sub.add_parser("download", help="download price history for training")
    t = sub.add_parser("train", help="walk-forward train and gate each agent")
    t.add_argument("--agent")
    t.add_argument("--synthetic", action="store_true", help="dry run on random data (nothing saved)")
    r = sub.add_parser("run", help="start trading")
    r.add_argument("--once", action="store_true", help="one cycle then exit (for cron)")
    r.add_argument("--force-unapproved", action="store_true", help="paper mode only")
    sub.add_parser("report", help="show each agent's progress against its subscription")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env()
    cfg = load_config(args.config)
    {"screen": cmd_screen, "audit": cmd_audit, "download": cmd_download, "train": cmd_train,
     "run": cmd_run, "report": cmd_report}[args.cmd](cfg, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
