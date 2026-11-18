# btc-race-24h-20261118-1444

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/marugamiii/btc-race-24h-20261118-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/marugamiii/btc-race-24h-20261118-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

**Momentum-pullback BTC bot** for make.fun's "Race a BTC trading bot live for 24 hours" bounty. It trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute on-chain bars from an Orca Whirlpool, starting with $1,000 of paper money, long only, one position at a time.

The bot only trades when the market is actually moving (the 60-minute high-low range must clear 100 bps) and only buys a strong 45-minute up-move that has just paused: the return from 60 to 15 minutes ago is at least +60 bps while the last 15 minutes pulled back at least -10 bps. A second setup buys a washout bounce (30 minutes down at least -80 bps, the last 5 minutes already turning up at least +5 bps). Every trade is full-size with a fixed take profit (+120 bps momentum / +80 bps bounce), a tight stop (-30 / -25 bps), a 6-hour maximum hold, and a 30-minute cooldown after each exit. No leverage, no shorts, no randomness, no wall clock, no network — two runs on the same data answer identically.

Backtested on the frozen 24-hour dev window with the kit's own replay rules (fill at the next open, 4 bps fee, 2 bps slippage, pool price impact): **net PnL +$23.37, 3 round trips, 3 wins, maximum drawdown 0.65%** — verified by running the real bot through a local driver that speaks the exact `agent-fun/bars-replay/v1` protocol and scores fills with the harness's own fill math (that math was checked against the kit's `grade-local` to 6 decimals on all six baseline bots; `grade-local` itself cannot run a Python bot on this machine — its process sandbox is Node-only and no Docker is installed).

## Run it

```sh
PYTHONHASHSEED=0 python3 -P -s main.py
```

Grade it locally on the dev window (from the unpacked kit directory):

```sh
node cli/makefun.mjs grade-local --kit . --bot /path/to/btc-race-24h-20261118-1444 --driver process
```

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
