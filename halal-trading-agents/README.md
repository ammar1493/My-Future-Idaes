# Halal Trading Agents for Binance

Three automated spot-trading agents. Each one gets its own slice of your USDT,
trades only Shariah-screened coins, and aims to earn its monthly subscription
cost (`monthly_target_usd`).

| Agent       | Strategy            | Idea                                                         |
|-------------|---------------------|--------------------------------------------------------------|
| `trend`     | `trend_following`   | Hold coins in confirmed uptrends (EMA cross + 200-bar trend filter), cash otherwise |
| `reversion` | `mean_reversion`    | Buy oversold dips (RSI + Bollinger) inside an uptrend, sell on the bounce |
| `rotation`  | `momentum_rotation` | Every rebalance, hold the top-K strongest halal coins; cash if none are rising |

## What keeps it halal

* **Spot only.** The code has no margin, futures, options, or lending endpoints at all.
  Live mode refuses to start if the API key has margin or futures enabled.
* **Approved list only.** A coin is traded only if it's on `halal.approved`.
  Lending/interest protocols (AAVE, COMP, MKR…), gambling tokens and leveraged
  tokens (`*UP`, `*DOWN`, `*BULL`, `*BEAR`) are hard-blocked even if you add them by mistake.
* **Checked twice.** Every order is screened again right before it's sent.
* **Training uses only halal coins.** Agents learn and are tested only on the coins they're allowed to trade.
* **No interest.** Idle cash stays as plain USDT. Nothing is put in Earn, staking or lending.
  Profits set aside for subscriptions are just kept as cash.

The default approved list (BTC, ETH, SOL, ADA, DOT, LINK, AVAX, ATOM, NEAR, ALGO, XLM, LTC)
is **a starting point, not a fatwa**. Check each coin with a scholar or screening service you trust
(e.g. Islamicly, Sharlife, Shariyah Review Bureau) and edit `config.yaml`. Using stablecoins as the
quote currency is the common position but some scholars differ, so check that too.
`python -m halal_trader audit` flags anything already in your Binance balances that isn't on your approved list.

## How "training" works

`train` runs a **walk-forward** test on 3 years of history for each agent:

1. Try every parameter set on past data and pick the best (by Sharpe ratio, after 0.1% fees + slippage).
2. Test that pick on the **next, unseen** stretch of data. Repeat across 3 folds.
3. Combine the unseen results. That's the honest estimate of how the agent would have done.

An agent is **approved to trade** only if its unseen results have positive return, Sharpe ≥ 0.5,
drawdown no worse than −35%, and enough trades. Agents that fail are skipped by `run`.
The output also shows the monthly return the subscription needs (e.g. $20 on $400 = 5%/month)
next to what the agent actually averaged.

## Risk controls (per agent)

* Spends only its own `capital_usd` and only sells coins it bought itself. The rest of your portfolio is never touched.
* Stop-loss 8% below entry, then a 24h cooldown before buying that coin again.
* Max 50% of a sleeve in one coin.
* No new buys after a −5% day.
* **Kill switch:** halts and goes to cash at −25% from peak. Stays halted until you reset it.
* **Subscription lock:** once a month's profit reaches the target, the agent goes to cash for the rest of the month.
  At month end that amount is moved into `reserved_usd`, so it isn't put at risk again.

## Setup

```bash
cd halal-trading-agents
pip install -r requirements.txt
cp config.example.yaml config.yaml     # set capital_usd / monthly_target_usd per agent
cp .env.example .env                   # add API key + secret
```

**Binance API key:** turn on *Enable Reading* and *Enable Spot & Margin Trading* (Binance groups them; the bot
only uses spot). **Never** turn on withdrawals. Restrict the key to your IP. Live mode will not start if withdrawals are enabled.

## Usage

```bash
python -m halal_trader screen            # which coins each agent may trade, and why others are blocked
python -m halal_trader audit             # check your current Binance balances against the halal list
python -m halal_trader download          # fetch price history
python -m halal_trader train             # walk-forward train + approve/reject each agent
python -m halal_trader run               # trade (mode from config.yaml); --once for cron
python -m halal_trader report            # each agent's month-by-month profit vs. its subscription
```

**Roll it out in stages:** `mode: paper` (real prices, fake orders) for at least a few weeks →
`mode: testnet` (real orders, fake money: get keys at testnet.binance.vision) → `mode: live`
with small `capital_usd` and `HALAL_TRADER_CONFIRM_LIVE=yes`.

Re-run `download` + `train` about once a month so agents adapt. To reset a halted agent, look into why it halted,
then delete `state/sleeves/<agent>.json`. Note that this also clears its trade history.

`python -m halal_trader train --synthetic` runs the whole pipeline on random data as a quick self-check (nothing is saved).
Tests: `python -m pytest`.

## Honest expectations

* **No strategy guarantees profit.** Crypto can fall 50%+ and agents can lose money, including the subscription amount.
  Only use money you can afford to lose.
* The target is the hard part. $20/month on $400 is 5%/month (~80%/year), which very few strategies keep up for long.
  The `train` output shows whether history supports your target. If it doesn't, raise `capital_usd` or lower the target.
  Don't loosen the risk limits to chase it.
* The backtest doesn't simulate the stop-loss, daily-limit or target-lock rules, so live results will differ from it.
* Binance is not available in every country (e.g. the US uses Binance.US, which has a different API host).
  Follow your local regulations and tax rules.
