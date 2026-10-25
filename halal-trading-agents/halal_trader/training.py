"""Walk-forward training on halal coins only.

For each fold the best parameters are chosen on past data and then scored on
the following unseen window. The stitched-together unseen windows are the
honest estimate of how the agent would have done. An agent is only approved
for trading when that out-of-sample result clears the configured bar.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from .backtest import buy_and_hold, count_entries, metrics, net_returns
from .strategies import STRATEGIES


@dataclass
class TrainingResult:
    agent: str
    strategy: str
    params: dict
    approved: bool
    reasons: list[str]
    oos: dict
    benchmark_oos: dict
    in_sample: dict
    folds: list[dict]
    universe: list[str]
    interval: str
    capital_usd: float
    monthly_target_usd: float
    required_monthly_return: float

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))


def _sharpe_score(rets: pd.Series, weights: pd.DataFrame, interval: str, min_trades: int) -> float:
    if count_entries(weights.loc[rets.index]) < min_trades:
        return float("-inf")
    return metrics(rets, interval)["sharpe"]


def walk_forward(agent: str, strategy_name: str, closes: pd.DataFrame, interval: str,
                 capital_usd: float, monthly_target_usd: float, fee_rate: float = 0.001,
                 slippage: float = 0.0005, n_splits: int = 3, min_trades: int = 5,
                 min_sharpe: float = 0.5, max_drawdown: float = 0.35) -> TrainingResult:
    cls = STRATEGIES[strategy_name]
    closes = closes.dropna(how="any")
    grid = cls.grid()
    runs = []
    for params in grid:
        strat = cls(**params)
        rets, w = net_returns(strat, closes, fee_rate, slippage)
        runs.append((params, strat.warmup, rets, w))

    n = len(closes)
    test_size = n // (n_splits + 2)
    if test_size < 30:
        raise ValueError(f"not enough history ({n} bars) for {n_splits} walk-forward folds")

    folds, oos_parts = [], []
    for k in range(n_splits):
        train_end = n - (n_splits - k) * test_size
        best = None
        for params, warmup, rets, w in runs:
            score = _sharpe_score(rets.iloc[warmup:train_end], w, interval, min_trades)
            if best is None or score > best[0]:
                best = (score, params, rets, w)
        score, params, rets, w = best
        test = rets.iloc[train_end:train_end + test_size]
        oos_parts.append(test)
        folds.append({
            "train_end": str(closes.index[train_end - 1]),
            "test_end": str(closes.index[min(train_end + test_size, n) - 1]),
            "params": params,
            "train_sharpe": score,
            "test": metrics(test, interval, w),
        })

    oos_rets = pd.concat(oos_parts)
    # weights for trade counting in the stitched OOS window come from each fold's pick
    oos_trades = sum(f["test"].get("trades", 0) for f in folds)
    oos = metrics(oos_rets, interval)
    oos["trades"] = oos_trades
    bench = metrics(buy_and_hold(closes).loc[oos_rets.index], interval)

    # final parameters: refit on everything available
    final = max(runs, key=lambda r: _sharpe_score(r[2].iloc[r[1]:], r[3], interval, min_trades))
    in_sample = metrics(final[2].iloc[final[1]:], interval, final[3])

    reasons = []
    if oos["total_return"] <= 0:
        reasons.append(f"out-of-sample return {oos['total_return']:.1%} is not positive")
    if oos["sharpe"] < min_sharpe:
        reasons.append(f"out-of-sample Sharpe {oos['sharpe']:.2f} < required {min_sharpe}")
    if oos["max_drawdown"] < -max_drawdown:
        reasons.append(f"out-of-sample drawdown {oos['max_drawdown']:.1%} worse than -{max_drawdown:.0%}")
    if oos_trades < min_trades:
        reasons.append(f"only {oos_trades} out-of-sample trades (< {min_trades})")

    return TrainingResult(
        agent=agent, strategy=strategy_name, params=final[0], approved=not reasons,
        reasons=reasons, oos=oos, benchmark_oos=bench, in_sample=in_sample, folds=folds,
        universe=list(closes.columns), interval=interval, capital_usd=capital_usd,
        monthly_target_usd=monthly_target_usd,
        required_monthly_return=monthly_target_usd / capital_usd if capital_usd else float("inf"),
    )


def load_params(state_dir: Path, agent: str) -> dict | None:
    path = state_dir / "params" / f"{agent}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
