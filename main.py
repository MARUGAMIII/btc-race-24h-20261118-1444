"""Momentum-pullback BTC trading bot for make.fun's btc-race-24h-20261118-1444.

Strategy in one paragraph: the bot only trades when the market is actually
moving, and only buys a strong 45-minute up-move that has just paused. Two
entry setups share one exit discipline (take profit, or cut the loss, or time
out); every trade is full-size, long only, and the bot never holds more than
one position.

Why this shape: on the frozen 24h dev window a full-size round trip costs
about 26-32 bps in fee, slippage and price impact, so a trade has to catch a
move far larger than that. Short-horizon returns (5-15 min) are slightly
mean-reverting on that window while 60-minute momentum is positively
predictive, so the bot buys the pause inside an up-move instead of chasing
spikes, and it takes profit at a fixed target instead of trailing a stop
through the 1-minute noise. A 60-minute range filter keeps it out of dead,
flat hours where the same signals only bleed fees.

Setup A - momentum pullback (the main signal):
  * the 60-minute high-low range is at least 100 bps (the market is moving),
  * the return from 60 to 15 minutes ago is at least +60 bps (a real leg up),
  * the last 15 minutes pulled back at least -10 bps (the pause),
  * then buy everything, take profit at +120 bps, stop at -30 bps.

Setup B - washout bounce (the secondary signal):
  * the same 100 bps range filter,
  * the last 30 minutes fell at least -80 bps (a washout),
  * the last 5 minutes are already turning back up at least +5 bps,
  * then buy everything, take profit at +80 bps, stop at -25 bps.

Risk controls: at most one open position, full size only (never leveraged,
never short), a 360-bar (6h) maximum hold, and a 30-bar cooldown after every
exit so a whipsaw cannot be re-entered immediately. Two more guards protect
the race window, where conditions are unknown: a momentum entry needs 120
bars left in the 1,440-bar window (75-272 bars to reach its target on dev)
and a bounce entry 15, so a late trade is not flattened before it can pay;
and an entry is skipped when the latest close's pool depth implies a fill
impact above 50 bps (about 12-13 bps on the dev window). All decisions use integer
basis-point arithmetic on the bars the harness sends; there is no randomness,
no wall clock, no network and no file access, so two runs on the same data
answer identically.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 300  # fills move at most ~28 bps from the latest close here

# Entry filters, all in basis points.
RANGE_MIN_BPS = 100     # 60-minute high-low range must clear this to trade
MOM_MIN_BPS = 60        # return from 60 to 15 minutes ago
PULLBACK_MAX_BPS = -10  # last-15-minute return must be at or below this
MOM_TP_BPS = 120        # momentum take profit
MOM_SL_BPS = 30         # momentum stop loss
DIP_MIN_BPS = -80       # last-30-minute return at or below this (washout)
BOUNCE_MIN_BPS = 5      # last-5-minute return at or above this (turning up)
DIP_TP_BPS = 80         # washout-bounce take profit
DIP_SL_BPS = 25         # washout-bounce stop loss

MAX_HOLD_BARS = 360     # longest a position is held, in bars
COOLDOWN_BARS = 30      # bars to wait after an exit before a new entry
HISTORY_BARS = 61       # bars of history an entry needs (now back to 60 ago)

# Both windows of this competition are 1,440 one-minute bars. A trade
# entered too late cannot reach its target before the window ends and is
# flattened at the last close, paying the round-trip cost for nothing: the
# momentum setup took 75-272 bars to reach its target on the dev window,
# the washout bounce 8. So a momentum entry needs 120 bars left and a
# bounce entry 15; with a warm-up the seq counts warm-up batches too, which
# only makes this guard cut off earlier, never later.
WINDOW_BARS = 1440
MOM_MIN_BARS_LEFT = 120
DIP_MIN_BARS_LEFT = 15

# A full-size buy moves its own fill by about 7 bps at the dev window's
# depth. If the latest close's depth implies far worse impact the pool has
# gone thin and the trade is not worth its cost, so the entry is skipped.
MAX_ENTRY_IMPACT_BPS = 50


def bps_change(now, then):
    """Return of `now` against `then`, in integer basis points."""
    return (now - then) * 10000 // then


class Bot:
    def __init__(self):
        self.closes = []   # latest close per batch, None when the bar is missing
        self.highs = []
        self.lows = []
        self.entry = None       # {"close", "seq", "tp_bps", "sl_bps"} once a buy fills
        self.pending_buy = None  # the buy just sent, waiting for its fill
        self.pending_sell = None  # seq of the sell just sent, waiting to clear
        self.last_exit_seq = -10 ** 9

    def on_batch(self, state, batch):
        bar = None
        for candidate in batch.get("bars", []):
            if candidate.get("symbol") == SYMBOL:
                bar = candidate
                break
        if bar is None:
            self.closes.append(None)
            self.highs.append(None)
            self.lows.append(None)
        else:
            self.closes.append(int(bar["c"]))
            self.highs.append(int(bar["h"]))
            self.lows.append(int(bar["l"]))

        position = state.positions.get(SYMBOL)
        seq = state.seq
        close = self.closes[-1]

        # --- bookkeeping: turn sent orders into state once the account shows it.
        if position is not None:
            if self.pending_buy is not None:
                self.entry = dict(self.pending_buy)
                self.pending_buy = None
            if self.entry is None and close is not None:
                # Defensive fallback (a position with no remembered buy):
                # measure from the current close with the momentum exits.
                self.entry = {
                    "close": close,
                    "seq": seq,
                    "tp_bps": MOM_TP_BPS,
                    "sl_bps": MOM_SL_BPS,
                }
        else:
            if self.pending_buy is not None and seq > self.pending_buy["seq"]:
                self.pending_buy = None  # the buy was rejected; nothing filled
            if self.pending_sell is not None:
                self.last_exit_seq = self.pending_sell
                self.pending_sell = None
            self.entry = None

        if state.warming_up or bar is None or close is None:
            return []

        # --- exit: one open position, sold whole when any exit trips.
        if position is not None and self.entry is not None:
            change = bps_change(close, self.entry["close"])
            held = seq - self.entry["seq"]
            if (
                change >= self.entry["tp_bps"]
                or change <= -self.entry["sl_bps"]
                or held >= MAX_HOLD_BARS
            ):
                self.pending_sell = seq
                return [
                    {
                        "side": "sell",
                        "symbol": SYMBOL,
                        "qty": position.qty,
                        "max_slippage_bps": MAX_SLIPPAGE_BPS,
                    }
                ]
            return []

        # --- entry: flat, cooled down, with a full clean hour of history.
        if seq - self.last_exit_seq < COOLDOWN_BARS:
            return []
        if len(self.closes) < HISTORY_BARS:
            return []
        window = self.closes[-HISTORY_BARS:]
        if any(c is None for c in window):
            return []
        highs = self.highs[-HISTORY_BARS:]
        lows = self.lows[-HISTORY_BARS:]
        if any(h is None for h in highs) or any(l is None for l in lows):
            return []

        range_bps = (max(highs) - min(lows)) * 10000 // close
        if range_bps < RANGE_MIN_BPS:
            return []

        momentum = bps_change(window[-16], window[-61])
        pullback = bps_change(close, window[-16])
        dip = bps_change(close, window[-31])
        bounce = bps_change(close, window[-6])

        plan = None
        bars_left = WINDOW_BARS - 1 - seq
        if (
            momentum >= MOM_MIN_BPS
            and pullback <= PULLBACK_MAX_BPS
            and bars_left >= MOM_MIN_BARS_LEFT
        ):
            plan = (MOM_TP_BPS, MOM_SL_BPS)
        elif (
            dip <= DIP_MIN_BPS
            and bounce >= BOUNCE_MIN_BPS
            and bars_left >= DIP_MIN_BARS_LEFT
        ):
            plan = (DIP_TP_BPS, DIP_SL_BPS)
        if plan is None:
            return []

        room = state.weight_room(SYMBOL)
        spend = state.cash if state.cash < room else room
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if spend < min_notional:
            return []
        impact = state.impact_bps(SYMBOL, spend)
        if impact is None or impact > MAX_ENTRY_IMPACT_BPS:
            return []
        tp_bps, sl_bps = plan
        self.pending_buy = {
            "close": close,
            "seq": seq,
            "tp_bps": tp_bps,
            "sl_bps": sl_bps,
        }
        return [
            {
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": spend,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]


BOT = Bot()


def on_batch(state, batch):
    return BOT.on_batch(state, batch)


makefun_bars.run(on_batch)
