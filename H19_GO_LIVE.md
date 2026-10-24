# H19 go-live checklist (written 2026-10-24, BEFORE the verdict)

Written in advance so a pass does not turn into improvised real-money trading.
Nothing here changes the constitution: paper only until every precondition holds.
H19 rules are in `h19_late.py` and CANDIDATE.md HYPOTHESIS 19; they do not change.

## 1. Preconditions (all required)

- [ ] `docs/frozen/h19_verdict.json` says `passed: true` (read once, at >= 60 units / 20 days).
- [ ] Fill reality from `logs/h19_depth/`: at the chosen size, the median extra cost per
      contract over the quoted price is **less than half** the frozen mean P&L, per leg.
      A leg that fails this is not traded. (First dry run, 10/24 midday, B leg: +0.8 to
      +2.1c at 10 contracts, +5 to +7c at 100. 100 contracts would erase the edge.)
- [ ] Michael's explicit written go-ahead, including the loss limit below.
- [ ] Order code exists, reviewed, and tested against Kalshi's demo environment. low-no has
      NO order placement today, by design; adding it is a separate, approved change.

## 2. Size

- Start at **10 contracts per signal**, never more than the contracts within +2c of the best
  price on the book at that moment.
- About 13 signals a day x 10 contracts x ~75c average = **~$100 a day at risk**, settled
  nightly. Respect the constitution's 5% position cap against the account balance.

## 3. Execution

- One limit order per signal at the quoted price (+1c at most), immediate-or-cancel.
  Not filled = skipped. Never chase, never re-enter later the same day.
- Log every attempt: signal time, quoted price, limit, filled quantity, fill price, fee.
- No discretion: no skipping signals that "look wrong", no extra trades.

## 4. Kill switch (any one stops trading; restart needs a new decision)

- Cumulative live loss reaches **$200**.
- Average fill is more than **3c** worse than the paper price over any 3 trading days.
- After 20 live trading days, the day-clustered 95% upper bound of live P&L per contract is
  below 0.
- Anything in the pipeline breaks (collection, settlement, order logging). Fix first, then decide.

## 5. Scale-up (only after 20 live days)

- Live mean P&L per contract > 0 AND average slippage < 2c: size may double, never above the
  depth limit in section 2. Re-check the depth logs before each step up.

## 6. If H19 fails

Stop. Per the programme stopping rule (CANDIDATE.md "WHEN THIS PROJECT STOPS"), a failed H19
with no other avenue left ends the project; the date may be pulled earlier than 12/31, never
pushed later without a hypothesis that actually passed.
