# Candidate Rule v1 -- "corrected low-no"  (2026-08-10)

Status: HYPOTHESIS. Paper only. Scored nightly as `corrected_G4_floor90`
in shadow_summary.json alongside the frozen gate. Not for live capital.

## The rule
Enter NO on a bottom-ladder rung iff ALL of:
1. G_corrected = (guide - station_bias) - ceiling >= 4          [bias from settlements ledger + weatherbot priors]
2. 90 <= no_ask <= 98 cents                                     [floor kills the 0-50c graveyard: 14 units, 0 wins]
3. Model-market divergence <= 15 pts                            [market won 7/8 disputes in this ledger]
4. PoP <= 20                                                    [convective days: Gaussian unfit, frozen-gate rule kept]
5. Station distribution fit: not marine (SFO/LAX), prior exists [non-normal stations excluded until empirical fit, n>=20]
6. Entry window 09:00-13:00 local                               [band inventory peaks 10:00-11:00, gone by 14:00]
7. Size = min(half-Kelly on pWin LCB, hard cap 5% bankroll)     [half-Kelly at 96-98c says 40%+; the cap is the seatbelt]

## Promotion criteria (what would make this live)
- >= 60 independent city-day units passing rules 1-6 in shadow
- Wilson 95% LCB on hit rate > fee breakeven at mean entry price
- corrected_G4_floor90 LCB separated from frozen_G4 LCB
- No attribution category (MECHANISM, DATA_GAP) exceeding 10% of misses
Earliest possible: ~mid-October 2026 at current flag rates. The date cannot
be negotiated with; only the flag rate moves it.

## Kill criteria
- Any 3-loss run at 96-98c (posterior collapses below breakeven)
- Station bias drift > 2F between weekly refits (priors stale)

---

# WHEN THIS PROJECT STOPS (written 2026-08-31, while nothing is at stake)

The $100 pilot has quit lines. The research programme has never had one. That
asymmetry is how a measurement project turns into a hobby: every null result
suggests one more slice, and there is no number at which the answer is "no."

This section supplies the number. It is written now, before H4a has run, for
the same reason the quit lines were written at $0: a stopping rule authored
after a drawdown is not a stopping rule.

## The test: futility is promotion, inverted

Promotion requires the Wilson 95% LOWER bound to clear fee breakeven -- the
data must rule OUT a true rate too low to profit.

**Retirement requires the Wilson 95% UPPER bound to fall BELOW fee breakeven**
-- the data has ruled OUT any true rate high enough to profit. Same interval,
same confidence, other end. Nothing new to argue about, and it is already the
project's vocabulary: the live pilot retires on "UCB < breakeven after 30 live
units."

A retired avenue is not "unproven." It is refuted at 95%. It does not come back
by adding days, because more days narrow the interval further in the same
direction.

## Applied to the record as it stands, 2026-08-31, 405 units

**CORRECTED THE SAME DAY.** This section first reported EIGHT of eleven bands
retired. That was wrong, and the way it was wrong matters more than the number.

NO-side grading deliberately stays on the LOGGED cap so history is not
rewritten mid-measurement. For pre-fix rows that cap is the raw threshold, so a
settle exactly AT it reads as a NO-loss when it was truly a NO-win. The grading
is pessimistic at the boundary BY DESIGN -- and **18 of the 26 days in this
record are pre-fix**, with 87 rung-observations sitting exactly on that
boundary.

Pessimism is harmless for "not proven": it can only delay a promotion. It is
NOT harmless for "refuted", which is permanent and one-way. Judging futility on
a knowingly pessimistic number retires bands that are merely unproven, which is
exactly what happened. Retirement is now computed on cap-corrected outcomes
(`ucb_capfix` in the nightly), and the table is:

```
band     n    hit    breakeven   UCB(raw)  UCB(capfix)   verdict
1-10    25    0.0%      5.5%       13.3%      13.3%      open
11-20   21    4.8%     16.3%       22.7%      22.7%      open
21-30   17   11.8%     27.1%       34.3%      47.3%      open
31-40   21    4.8%     37.4%       22.7%      40.0%      open
41-50   19   21.1%     47.3%       43.3%      54.0%      open
51-60   16   31.2%     56.5%       55.6%      76.9%      open
61-70   21   38.1%     67.2%       59.1%      71.7%      open
71-80   24   50.0%     78.2%       68.6%      82.0%      open
81-90   51   76.5%     88.2%       86.0%      90.4%      open
91-95   76   85.5%     94.4%       91.7%      94.6%      open
96-98  110   92.7%     98.2%       96.3%      96.9%      RETIRED
```

**One band is retired, not eight: 96-98c.** Its 95% upper bound is 96.9%
against a 98.2% breakeven even after the correction, on the largest sample in
the record. Buying the band this strategy is built around, unconditionally, is
still refuted at 95%.

The other seven were never refuted. They are unproven -- which is what they
were before this section existed, and the difference between "the strategy is
dead" and "the strategy is dead at the top of the book" is the whole finding.

The lesson generalises past this table, and it is the fourth instance this
week: **a measurement chosen to be conservative in one direction cannot be
reused for a decision that runs the other way.** The pessimistic grading was a
good choice for protecting the promotion bar and a bad one for driving a
retirement, and nothing flagged the switch because both used the word "win".

## What retirement does NOT mean -- read this before applying the rule

A band's UCB retires the band **unconditionally traded**. It does not retire
every conditional rule inside it. A subset selected on information the band
average does not contain can have a higher true rate, and the interval above is
computed on the pooled population precisely to say nothing about subsets.

This is the whole reason H4a, H4b, H5 and the two pilots remain alive after the
table above. It is also the reason they are the LAST avenues: the unconditional
strategy is finished, and what remains is the claim that conditioning helps.

Anyone applying this rule to kill a conditional hypothesis using a band-level
interval has misread it.

## When the programme stops

It stops at the FIRST of:

1. **Every registered avenue retired or promoted.** As of today the live list
   is H4a, H4b, H5, PILOT-A, PILOT-B, and the five variants not yet retired.
   No new avenue may be added after 2026-10-31 -- an open-ended registration
   queue defeats the whole point of a stopping rule.

2. **2026-12-31.** This is the one judgement call here, and it is derived, not
   picked: H4a resolves within days, H4b around 09-15, and H5's universe supplies
   **1.00 city-day per day**, so its 60-unit bar needs at least 60 days of
   collection and cannot start until H4a passes. December 31 gives the last and
   slowest registered hypothesis roughly two months of margin beyond its floor.
   Change this date now if it is wrong. It cannot be changed once passed.

## What "stops" means

Collection stops. The nightly runs are disabled. The repository stays, the data
stays, CANDIDATE.md stays -- the negative result is the product and it is worth
more intact than deleted. What ends is the search.

It does not mean the $0 stays $0 by accident. It means the standing commitment
holds by default: **no seed ever happens** unless something clears its
promotion bar before the programme stops.

## Anti-gaming, in the same spirit as the quit lines

* The futility test may not be weakened after an avenue fails it. Moving to 99%
  to keep something alive is the same act as widening a gate after a drawdown.
* A retired avenue may not be revived by re-slicing the same days. Reopening
  requires a mechanism written down BEFORE testing and out-of-sample days, the
  same bar H1 has to clear and has not.
* The 2026-12-31 date may be shortened at any time. Extending it requires a
  hypothesis that has actually PASSED and needs live confirmation -- not one
  that is merely still pending.
* Editing this section after a promising interim result is itself a kill signal,
  exactly as it is for the pilot quit lines.

## The honest expectation

Nothing has cleared a promotion bar in 24 days and 405 units, the unconditional
strategy is now refuted at 95%, and the remaining hypotheses are three
conditional claims of which one has passed an information test and none has
passed a trading test. The most likely outcome of this programme is a
well-documented no. That was always the most likely outcome; writing the date
down just means it will be recognised when it arrives.

# AUTONOMOUS PILOT ACTIVATION (registered 2026-08-27, BEFORE either test ran)

Michael's instruction: start paper trading without further input once H4a or
H4b is ready; if both, run two distinct paper traders. Implemented with one
deliberate reading, stated here so it is not a silent choice:

**"READY" IS THE DATA BAR. THE TRIGGER IS "PASSED".** A bar being met only
means a test can finally run. Activating a trader on a hypothesis whose test
has not PASSED is precisely the H1 failure -- SAT took a real position on an
unvalidated premise. So the nightly runs the registered test when its bar is
met, and the pilot activates only on a pass. A failed test is recorded and the
pilot stays dark. No human step is required in either branch.

Both rules are fixed HERE, before either test has produced a number, so that
nothing can be invented to fit whatever the data turns out to say.

## PILOT-A (activates iff H4a PASSES: held-out Brier improvement)
What H4a would establish: the shape-conditioned model produces BETTER
probabilities than level+hour alone. That is a model claim, so the rule trades
model-vs-market disagreement using the validated model.
  * Universe: bottom rungs, peak window 13:00-16:00 local only (the effect
    inverts outside it), real ask 1-98c, shape cell earned (n >= 12).
  * Enter NO when p_shape - (no_ask/100) >= 0.10.
  * One unit per city-day, first qualifying cycle, entry at the ASK, held to
    settlement, Kalshi fees. Bankroll $100, half-Kelly on p_shape, 5% cap.

## PILOT-B (activates iff H4b PASSES: lag correlation CI excludes zero)
What H4b would establish: the market reprices AFTER the deviation, not with it.
  * Universe: bottom rungs, real ask 1-98c, consecutive cycles 0.5-2.5h apart.
  * Event: d(curve_dev) >= +1.0F (day running hotter than its own forecast).
  * Enter NO at that cycle's ask, one unit per city-day, held to settlement.
  * Bankroll $100, half-Kelly on the realized event hit rate, 5% cap.

## Rules binding BOTH pilots
* Paper only. No orders. The constitution is unchanged and unchangeable here.
* Separate bankrolls, separately reported. They are different hypotheses and
  must never be pooled -- including if both activate.
* Same quit lines as YES Pilot v1: $40 down (stop, no reseed), $5,000 up.
* Same promotion bar: >= 60 units, Wilson LCB > fee breakeven, out-of-sample.
* p_hyp equivalents are NOT re-tuned after activation. A sizing constant
  fitted post hoc is how H1 died.
* Activation, deactivation and every trade are written to `docs/pilots.json`
  and printed nightly, so an autonomous start is never a silent one.

---

# HYPOTHESIS 7 -- SHAPE ON TEMPERATURE, NOT ON THE MAXIMUM
# (registered 2026-08-31, BEFORE any test. This text does not change.)

n = 0 at registration. The hybrid of H4a and H6 that Michael asked for, and it
turns out to be a correction to H4a rather than an extension of it.

## What was found

H4a buckets a day by rate = delta(run_max) / delta(hours). run_max is a MAXIMUM,
so it moves only when a new high is set. Measured over the peak window:
**47% of all intervals have delta(run_max) = 0 and are therefore labelled
STALLED**, at every station equally -- the hourly pair KNYC/KDEN sit at 48% and
51% against a 5-minute-station range of 18% to 87%, so this is NOT the
publication-timing artifact that was suspected first and tested.

It is the monotonicity. Among those 111 flat-run_max intervals the ACTUAL
temperature tendency, from the `temp_now` already logged, runs:

```
p10 -3.18   p25 -1.74   p50 +0.00   p75 +0.00   p90 +1.77   F/hr
mean -0.55, sd 2.54

re-bucketed on temp_now:   stalled 79%   mid 3%   climbing 18%
```

**One interval in five that H4a calls stalled is actually climbing**, and a
large share are actively COOLING -- which run_max cannot distinguish from flat-
at-peak although they mean opposite things for whether the day clears a cap.

Since H4a measures stalled at +1.05F remaining against climbing at +2.53F,
contaminating the stalled bucket with genuinely climbing days pulls those two
numbers TOGETHER. So H4a is most likely UNDERSTATING its own effect.

## Mechanism

`temp_now` is not monotone, so a tendency computed from it separates three
states run_max collapses into one: cooling (the day is over), flat at the peak
(the day is over, differently), and flat but about to resume (the day is not
over). The third is the only one where remaining climb is large, and it is
currently pooled with the other two.

Where H6 enters: at KNYC and KDEN the logged `temp_now` is up to an hour stale,
so their tendency is the worst-measured of the 23. `run_max_nowcast` and its
`nowcast_detail` (logged from 2026-08-31) give a fresher and less quantized
temperature at exactly those two, which should repair the tendency there
specifically. That is the hybrid: H4a's mechanism, H6's data.

## The rule to be tested (fixed now)

Identical to H4a in every respect -- peak window 13-16 local, same rate_bucket
thresholds, same MIN_N_RATE, same held-out Brier comparison -- with ONE change:
the rate is computed from `temp_now` instead of `run_max`. At KNYC and KDEN,
and only there, `nowcast_detail.nowcast_f` substitutes for `temp_now` on days
from 2026-09-01, since that is when it starts being logged.

**H4a IS NOT MODIFIED.** shape_eval.py stays exactly as written and keeps
scoring on run_max. H7 gets its own harness. Changing a registered test's signal
definition mid-flight would invalidate every day already collected, and the
whole point of registering it was that the measurement does not move.

## STRATIFIED: KNYC and KDEN broken out, the other 21 as control

Michael's design point, and it upgrades H7 from a pooled result to a
difference-in-differences. Two effects are in play and pooling them would make
the answer uninterpretable:

```
effect A   temp_now instead of run_max          all 23 stations
effect B   nowcast instead of a stale temp_now  KNYC and KDEN only
```

The 21 five-minute stations already carry a fresh `temp_now`, so **effect B is
zero there by construction**. That makes them a genuine control rather than a
convenience grouping: the hourly pair gets A + B, the control gets A alone, and
the difference isolates B.

`verdict()` therefore reports the two strata SEPARATELY and requires
MIN_SCORED in EACH before it will report at all. Pooled n is printed for
context and is explicitly not the verdict.

Three outcomes, all informative:

* **Both strata improve, hourly by more.** Monotonicity was costing something
  everywhere, and the nowcast adds on top at the two stale stations. The
  difference-in-differences is the size of the nowcast's contribution.
* **Both improve equally.** The nowcast added nothing; only monotonicity
  mattered. A real answer, and it would retire the H6 line of work as far as
  p_exceed is concerned.
* **Only the hourly pair improves.** Suspicious rather than encouraging -- with
  two stations against twenty-one, that pattern is more likely small-sample
  noise than a real effect, and it should not be promoted without the control
  moving too.

## Prediction (falsifiable)

H7's held-out Brier beats H4a's on the same days. If it does not, monotonicity
was not costing anything and run_max is an adequate shape proxy. Separately, the
stalled/climbing separation should be WIDER than H4a's +1.48F once the
mislabelled climbing days are removed from the stalled cell -- if it is not, the
18% contamination is not where the loss is.

## How it fails (named in advance)

1. `temp_now` is a single instantaneous reading and run_max is an extremum, so
   the tendency may simply be noisier than the thing it replaces.
2. Only ~234 usable intervals exist -- `temp_now` has been logged since
   2026-08-27. Accrual is ~47/day, which is fast, but the cells still need
   MIN_N_RATE per (city, hour, bucket) and that is the bar that has H4a stuck.
3. A three-way split on a noisier variable may populate cells more evenly and
   still predict worse.
4. The nowcast substitution touches 2 of 23 stations, so it cannot move a
   pooled result much even if it is right.

## Bar for promotion

Unchanged: >= 60 independent city-day units, Wilson 95% LCB above fee breakeven,
out-of-sample confirmation on post-registration days. As an information claim it
reports the Brier comparison first, like H4a, and no pilot activates on it.

# THE STALE-STATION LEAD (measured 2026-08-31) -- a fact, and a hypothesis

## The fact: two settlement stations publish an hour behind their neighbours

Cadence checked live on all 23 stations. **21 publish every 4-5 minutes. Two do
not: KNYC and KDEN, both hourly.** At 17:35Z on 2026-08-31, KNYC's most recent
observation was 16:51Z -- 44 minutes stale -- while KLGA 13km east and KEWR 16km
west were current. The station the market settles on is the slow one.

`nowcast.py` predicts the host's NEXT print from its neighbours' movement since
its last print. The estimator has **no fitted parameters**: predicted next print
= last print + the MEAN change of the neighbours over the same interval. If a
parameter-free estimator cannot beat persistence, a fitted one beating it would
be a fitting result.

Backtested on 140-142 hourly transitions over 7 days, paired against
persistence, Bonferroni-corrected over the 10 comparisons run:

```
city  lead    n   persistence  nowcast   gain    corrected 95% CI   verdict
NYC    10m  140      1.12F      0.82F   +0.30F   [+0.08, +0.51]     SURVIVES
NYC    20m  140      1.12F      0.83F   +0.29F   [+0.09, +0.49]     SURVIVES
NYC    30m  140      1.12F      0.89F   +0.23F   [+0.05, +0.41]     SURVIVES
NYC    40m  140      1.12F      0.95F   +0.17F   [+0.03, +0.31]     SURVIVES
NYC    50m  138      1.12F      1.11F   +0.01F   [-0.10, +0.12]     no
DEN    10m  142      2.55F      1.85F   +0.70F   [+0.24, +1.15]     SURVIVES
DEN    20m  142      2.55F      1.89F   +0.66F   [+0.32, +1.00]     SURVIVES
DEN    30m  142      2.55F      1.97F   +0.58F   [+0.27, +0.90]     SURVIVES
DEN    40m  140      2.56F      2.24F   +0.32F   [+0.13, +0.52]     SURVIVES
DEN    50m  134      2.61F      2.37F   +0.24F   [+0.06, +0.41]     SURVIVES
```

This is the first thing in this project to beat its baseline and survive a
correction. It is an INFORMATION claim: the next print is predictable. It is not
a trading claim.

## The stated mechanism was FALSIFIED, and that matters

`nowcast.py` was written with a specific mechanism: Central Park sits between
KLGA on Flushing Bay and KEWR/KTEB in New Jersey, so an onshore easterly should
cool LGA first and the EAST-WEST gradient should lead KNYC. Written before the
test, so it could be wrong -- and it is.

Splitting NYC's 20-minute cases by whether the E-W differential moved:

```
gradient MOVING   n=71   gain +0.19F   [-0.03, +0.42]
gradient still    n=69   gain +0.40F   [+0.20, +0.60]
difference        -0.21F [-0.51, +0.10]
```

Skill does not concentrate on gradient movement. If anything it is higher when
the gradient is still. **The sea breeze is not what is doing the work.**

What is doing the work is duller and more robust: KNYC is stale and its
neighbours are not, so averaging four current stations estimates Central Park's
unpublished present better than assuming it has not moved. That is a
publication-latency effect, not a weather-regime effect, which means it should
hold year-round rather than only on sea-breeze days -- and it explains DEN, a
thousand miles from any ocean, showing a LARGER gain than NYC.

DEN also demonstrates the cost of a bad input: scored with KAPA alone it showed
nothing, and adding KGXY (5-minute) plus KEIK/KLMO/KBDU (20-minute) took it from
null to the strongest result in the table. The neighbour set was
under-specified, not the physics. Recorded because it was a second look, so
DEN's numbers need confirmation on days after 2026-08-31 before they count.

## The max-recovery route: TRIED AND FAILED (2026-08-31)

Obvious next step, and it does not work. A NO position wins on the settled MAX,
not the current temperature, so the tempting move is to use the neighbours to
reconstruct the peaks an hourly station hides between prints.

The gap is real and remarkably steady -- CLI minus our hourly-print max is
**+1.16F at NYC (sd 0.45, n=5)** and **+1.01F at DEN (sd 0.54, n=7)**, so our
running max is systematically about a degree low at exactly these two stations,
and our p_exceed with it.

But reconstructing it from neighbours OVERSHOOTS badly. First attempt took a max
over each neighbour's own reconstruction and landed 6-7F high. Averaging across
neighbours first -- which is what `nowcast.py` does, and which I should have done
from the start -- halves the error and still overshoots: **+1.16F becomes -3.22F
at NYC, +1.01F becomes -3.06F at DEN.** Worse than doing nothing.

Two reasons, and both are structural rather than fixable by tuning:

1. **A max over noisy estimates is biased upward by construction.** Roughly 280
   reconstructed ticks a day means the max selects the largest positive error,
   not the true peak. The short-horizon nowcast avoids this because it predicts
   ONE value, not the extreme of many.
2. **Neighbours have different diurnal amplitudes.** KGXY on the plains climbs
   far more than KDEN; assuming equal deltas is fine over one hour and wrong
   over a day. DEN 08-25 reconstructed to 98.7F against a CLI of 85F.

**The nowcast's validated use is short-horizon next-print prediction. It does NOT
transfer to daily-max reconstruction.** Different problem, different error
structure, and the transfer was assumed rather than tested until it was tested.

The simpler candidate -- a flat +1.0F offset at these two stations, leaving a
~0.5F residual instead of a ~1.0F bias -- is NOT adopted. n=5 and n=7 days, and
a station-level constant fitted on a handful of days is precisely the shape of
the H1 failure. It needs the archive to grow and a registration first.

## HYPOTHESIS 6 -- does the market price off the stale print?
## (registered 2026-08-31, BEFORE any test. This text does not change.)

n = 0 at registration.

**Mechanism.** Between prints at KNYC and KDEN, the true current temperature is
knowable to within ~0.8F and ~1.9F from neighbours, while the last published
value can be up to an hour old. If the market prices off the stale print, a
predictable revision arrives WITH the print, and the 40 minutes before it are
mispriced. If the market already nowcasts -- and any participant can, from the
same free API -- there is nothing there and the price will have moved first.

**Why this is not H4b.** H4b asks whether the market lags a deviation from the
diurnal curve, at all 23 stations, from our own scan trace. This asks whether
the market lags a PUBLICATION SCHEDULE, at the only two stations that have one,
against an external data source. Different signal, different population,
different failure mode.

**The rule to be tested (fixed now).** At KNYC and KDEN only. In the 40 minutes
before an expected host print, compute the nowcast. Enter when the nowcast
implies a bottom-rung outcome the current price does not, by a margin exceeding
the nowcast's own measured MAE at that lead. Exit at the print. One unit per
city-day. Real logged asks only.

**Prediction, falsifiable.** Price movement across the print correlates with
(nowcast - last print). If it does not, the market already knows.

**How it fails, named in advance.**
1. The market nowcasts too. The data is free and the asymmetry is obvious once
   seen; the most likely outcome is that this is priced.
2. 0.3F at NYC is small against a 1.12F baseline error, and most contracts are
   not decided within 0.3F.
3. Two stations, ~1 unit/day each. The 60-unit bar needs ~30 days of BOTH
   firing, which runs past the 2026-12-31 stop.
4. The gain decays to nothing by 50 minutes at NYC, so the tradeable window is
   narrow and depends on knowing when the next print is due.

**BLOCKED ON INSTRUMENTATION, and this is the honest obstacle.** The scan
samples every ~55 minutes. The effect lives inside a 40-minute window, so the
current price series CANNOT see it: we would be sampling the market at the same
frequency as the thing we claim is mispriced. Testing H6 requires denser price
sampling at two stations around the top of the hour, and that must NOT be done
by speeding up the main scan -- cadence is load-bearing for H4a's 0.5-2.5h
pairing band, and compressing it would zero the day exactly as 2026-08-26 did.
It needs a separate poller writing to a separate file.

Until that exists, H6 is registered and unscored. The information claim above
stands on its own and needs nothing further.

## H6 ADDENDUM -- the instrument exists, the harness now does too (2026-09-02)
## (the registered text above is unchanged; this records what was added and
##  the one place this registration is weaker than the others)

**The poller landed 2026-08-31** (`poll.py`, workflow `lowno-poll.yml`): KNYC
and KDEN only, every 5 minutes, its own concurrency group, writing to
`logs/poll/<day>.jsonl` -- a subdirectory that `glob("logs/2*.jsonl")` does not
match, so nothing it collects can reach a ladder, a band, a variant or the
gate. The main scan's cadence was not touched.

**The harness is `h6_eval.py`, written 2026-09-02, and it is the weakest
registration in this file.** Every other harness here -- `shape_eval`,
`curve_lag`, `band_eval`, `shape_temp_eval` -- was written before its data
existed. This one was written after two days of poll data existed. That is a
real difference in kind and it is not going to be dressed up: the file carries
a DISCLOSURE block listing every single thing about the poll data that had been
looked at when its rules were fixed (row counts, city split, field presence,
clock coverage, and the raw schema of one row). No pairing, no price move
across any print, and no correlation had been computed. The exposure is that
knowledge of the *instrument* could have shaped the rules; the mitigation is
that the exposure is enumerated rather than asserted to be zero.

**The bar, fixed now: >= 200 print transitions AND >= 20 distinct days.** This
is H4b's bar, taken deliberately rather than chosen. Same class of claim (does
the market lag an observable we compute), same instrument (the bottom-rung NO
price), so it inherits the bar instead of getting one calibrated to how fast H6
events happen to accrue. The days leg binds.

**The decision rule, fixed now.** An event is a PRINT TRANSITION: two
consecutive poll cycles whose `last_print_at` differs, same ticker, <= 15
minutes apart (the poller steps at 5, so that is two missed cycles), with a
real NO offer on both sides and a non-null deviation on the earlier one.
Pearson correlation between `nowcast_minus_print` on the cycle BEFORE the print
and the NO price change ACROSS it; PASSES only if that correlation is positive
with a Fisher 95% CI excluding zero. Pooled over the two cities is the verdict;
the per-city split is context, and it is pre-declared here that "it works at
DEN but not NYC" is SUSPICIOUS, not encouraging -- a one-city result on two
cities is what a null looks like half the time. The move in the cycles BEFORE
the print is reported beside it: if the market moved just as much with the
information, the print resolved nothing and the correlation is a shared trend,
not a lag.

**Verified on SYNTHETIC worlds, not on real history** (`test_h6_eval.py`, 13
checks): it must find a planted lag, report null on noise, refuse below the bar
however large the planted effect, and drop every unclean pair -- no print
between the rows, no real offer, a rung change, a poll outage, a null
deviation, and a `move_before` that would reach back across a different print.
Backtesting it on the poll data would be the peek this registration exists to
prevent.

**Two instrumentation facts found while wiring it. Both bound what H6 can ever
say, and neither was fixed here.**

1. **There is no morning.** The workflow has two cold starts, 13:02Z and
   18:02Z. The 13:02Z fire has never delivered: 2026-08-31 ran 18:20-23:39Z,
   2026-09-01 ran 17:15-23:36Z. Same GitHub non-delivery that cost the scan
   5-of-11 and 0-of-14 days. The morning is where the nowcast's own measured
   bias is largest (flat runs +0.56 to +2.33F low at 8-12 local), so the window
   most likely to carry a mispricing is the one being missed.
2. **The bottom rung stops carrying a price on exactly the days the claim is
   about.** `na == 100` is "no offer", and it was 100 on every polled row for
   DEN on both days and for NYC on 08-31 -- 3 of the first 4 city-days. DEN
   2026-09-01: bottom rung cap 80 while the host printed up to 87.08F. The
   bucket was dead by mid-afternoon, `yes_bid` went to nothing, and a rung that
   cannot reprice cannot show a lag. **15 usable print transitions out of 248
   poll rows, all of them NYC on one day.** The harness is right to drop them;
   the input is under-specified, which is the same diagnosis as DEN's nowcast
   before KGXY was added. Capturing a rung that still has two live sides (or
   the whole ladder) is an instrumentation decision, not a test change, and it
   is Michael's call -- flagged, not made.

Note also that none of this changes failure mode 3 above: even a pass here
cannot promote anything before the 2026-12-31 stop. H6 has no pilot, like H5.

# THE UNCONSTRAINED SWEEP (2026-08-31) -- 300 slices, nothing survives

Asked to find the edge anywhere, with any entry and any exit. So: every
instrument (NO and YES), every contract type (bottom, range, top), all eleven
price bands, crossed with every conditioner in the data -- hour bucket, rate
bucket, coast, PoP, G -- one unit per city-day, real logged asks only.

**300 slices with n >= 20.** A sweep this wide manufactures winners: at a
nominal one-sided 95%, one slice in twenty clears by chance, so ~15 hits are
the null expectation. The only number worth reading is the one corrected for
how many slices were actually run (Bonferroni, 0.05/300, z = 3.59).

## First pass: 13 nominal hits, and they were not scattered

Thirteen slices cleared at nominal 95% -- fewer than the ~15 chance predicts,
so as a group they were already indistinguishable from noise. But noise
scatters, and these did not: **all thirteen were the same instrument**, cheap
YES on TOP rungs, and one survived the Bonferroni correction.

Concentration is not confirmation. It is a fingerprint. A single systematic
error reproduces across every slice of the population it touches, which is
exactly what "13 of 13 in one instrument" looks like.

## The boundary check, which has now caught three bugs

63% of those "wins" settled EXACTLY at the floor.

Kalshi's rules text, fetched live: `KXHIGHAUS-26AUG31-T104` reads "is **greater
than** 104 degrees". The inclusive floor is therefore 105. We were grading YES
as `settle >= 104`, counting every boundary day as a win.

This is the 2026-08-24 cap fix, at the other end, never applied. The comment in
`sources.py` asserted "range and top rungs' strikes are already inclusive and
correct" -- half right. The identical proof it used for the bottom applies:

* Bottom: raw `cap_strike` == the FIRST range bucket's floor. Overlap.
* Top: raw `floor_strike` == the LAST range bucket's inclusive cap. Overlap.
  Checked on **23 of 23** stations. AUS is typical: a "103-104" bucket and a
  top rung we labelled ">=104", both containing 104.

Corrected, that population wins **3.2%** (10 of 314) against an 8.8c mean ask
and a ~9.5% breakeven -- a heavy loss, not an edge.

## Second pass, after the fix

```
slices with n >= 20                        300
clearing breakeven at NOMINAL 95%            0     (chance alone predicts ~15)
clearing breakeven AFTER correction          0
```

**Zero.** Not "nothing significant after correction" -- nothing clears even the
uncorrected threshold, on any instrument, at any price, under any conditioner
available, on 405 units and 26 days.

Getting fewer nominal hits than chance predicts is itself informative. It is
what a systematically overpriced book looks like from the buy side: the errors
do not straddle breakeven, they sit below it everywhere.

## What this does and does not settle

**Settles:** there is no simple slice-defined edge in this data. Any rule of the
form "buy instrument X in band Y when condition Z" has been tested across the
enumerable space and none clears. Adding more slices of the same kind is not
research, it is sampling until something looks good.

**Does not settle:** conditional rules that use information the slices do not
contain -- H4a's trajectory shape, H4b's repricing lag, H5's cell-level lower
bound. Those are not in this space because they are not slices; they condition
on a model. They remain the only live avenues, and now the only ones that were
ever going to be live.

**Does not settle exits.** "Any exit" was in the brief, and H2 already answered
it: expectancy is set at entry, and the best exit rule tested still lost. A
sweep over exits on top of a sweep over entries would only multiply the
correction against a population where no entry clears.

## The rule this earns

An unconstrained sweep may be RUN at any time -- `hunt.py` is committed for
exactly that -- but its output is never a registration. A slice that clears is
a candidate for a mechanism, and the mechanism has to be written before the
slice is tested again on new days. This paragraph exists because the sweep did
produce a survivor, and the survivor was a bug.

# THE FEE TAX (measured 2026-08-31) -- a structural fact, not a hypothesis

Kalshi charges `ceil(0.07 * C * P * (1-P))` cents per contract. In absolute
terms that is small and roughly flat across the book. As a share of what the
position can actually WIN, it is not flat at all:

```
band      fee   upside   fee as % of upside
96-98c     1c      3c            33%
91-95c     1c      7c            14%
81-90c     1c     15c             7%
61-80c     2c     30c             7%
```

At 97c you risk 97 to win 3, and Kalshi takes a third of the gross. **The
band this strategy was built around pays five times the fee tax of the band
H5 targets.** That is arithmetic, not a weather claim: an identical
forecasting skill earns far more at 85c than at 97c, and a skill that is
merely good is taxed out of existence at the top of the book.

Two consequences worth keeping.

**It is a second, independent argument for H5's band.** H5 chose 81-95c because
a 1.48F shape signal can only move a decision where 1.48F is decisive. The fee
table says the same thing from a different direction, with no reference to
weather at all. Two unrelated mechanisms pointing at the same band is the
closest this project has come to a prior.

**It puts a cost on the constitution's own premise.** CLAUDE.md says "the
strategy buys near-certainties at 96-98c" and "no lottery scanner." The first
half of that is the most expensive place on the board to be right. The rule
stays -- the gate is frozen and the lottery end is genuinely a different,
losing instrument (1-10c: 26 units, 0 wins) -- but "near-certainty" should be
read as a constraint the strategy pays for, not a free good.

## What this does NOT say

It does not say the 81-95c band has an edge. Every band's realised rate is
below its own breakeven, and 81-90c is short by 11.2 points against 96-98c's
5.4. A cheaper tax on a worse hit rate is not obviously a better trade, which
is exactly why H5 is registered as a hypothesis rather than adopted as a rule.

## An execution idea, checked and DISCARDED (recorded so it is not re-proposed)

The mean NO spread at 96-98c is 15.7c. Half of that is 7.85c, which exceeds the
5.34c mean shortfall -- so entering at the mid rather than the ask looked like
it could close the entire gap on its own, with no forecasting edge at all.

It is a fat-tail artifact. The distribution:

```
p10 1c   p25 1c   p50 1c   p75 3c   p90 79c   p95 88c   p99 93c
72% of rungs sit at <= 2c;  18% sit at >= 20c
```

The typical rung has a **1c** spread, so the realistic half-spread is 0.5c and
execution recovers about 9% of the shortfall. The mean is entirely the 18% tail
of rungs where an ask of 97 faces a bid of 4 -- quotes nobody could trade
against in either direction.

That tail is not an opportunity, it is a **fidelity problem**: KNOWN FIDELITY
GAPS already records that fills are assumed full at the logged ask, and this
quantifies which slice of the ledger is fantasy. Scored as the `*_twosided`
variants (spread <= the position's own upside, a derived threshold with no free
parameter), which keep 77% of 96-98c rung-obs and 96 city-day units.

The general lesson, and the third time it has cost something this week: **a mean
over a distribution with an untradeable tail is not a measure of what you can
trade.** Look at the median before believing an opportunity.

# HYPOTHESIS 5 -- THE CONTESTED BAND, PRICED AGAINST BREAKEVEN
# (registered 2026-08-31, BEFORE any test. This text does not change.)

n = 0 at registration. No variant, no pilot, no capital.

## Where it comes from

Michael asked whether optimal entry and exit timing had been determined per
city. Exit is closed (H2, refuted: expectancy is set at entry). Entry was still
one global 10:30-13:30 window for all 23 stations.

The first framing was checked and DISCARDED before registration, and the reason
is recorded here so it is not proposed again: "enter before the station's
earned convergence hour, while the price is still under 98c" keeps **98 of 109**
qualifying city-days. It is 90% of the population `floor96_only` already scores
at n=111, 92.8% hit, LCB 86.4% against a 98.1% breakeven -- short by 11.7
points. A filter that removes eleven days is not a hypothesis, it is a rounding
error on an existing negative result.

Two facts survived that check and motivate this one.

## What was already known when this was written -- DISCLOSURE

This hypothesis is written after a full review of 24 days of data, so it cannot
claim the innocence of H4, which was written before its telemetry existed.
Every number that informed it is listed so the contamination is auditable
rather than hidden:

* NO bands, realised hit vs breakeven: 81-90c 76.9% vs 88.1%; 91-95c 85.3% vs
  94.4%; 96-98c 92.8% vs 98.2%. Every band short, shortfall smallest at the
  extremes.
* The frozen gate's 18 flags: all 7 at 96-98c won (+15c). The 8 at 86-95c went
  5W-3L for **-238c**, which is 91% of the -261c total. The 3 at <=85c lost 38c.
* H4a's information claim: in the peak window 13-16 local, STALLED days carry
  +1.05F remaining vs CLIMBING +2.53F, a **1.48F** separation; at the boundary
  (0-2F needed) +1.49+/-0.40 vs +3.06+/-0.26. The effect INVERTS pre-peak.
* H3: the settlement gap is real (+0.21F pooled) but worth ~3 probability
  points and already priced.
* Minimum n for a PERFECT record to clear its own breakeven: 96-98c needs 210
  units, 90-95c needs 62, 81-90c needs 29.

No threshold below is fitted to any of these. Where a constant would have been
needed, the rule uses a bound the data computes for itself instead.

## Mechanism

`p_exceed` conditions on (city, hour, run_max). run_max is a MAXIMUM, so it is
monotone and shape-blind: a day stalled since 10:00 and a day still climbing
3F/hr present identically. H4a measured what that blindness costs -- 1.48F of
remaining climb inside the peak window.

**A 1.48F shift matters only where 1.48F can change the answer.** At 96-98c the
needed climb is already essentially zero and the outcome is all but settled;
the market is 5.4 points from correct and a signal worth a few probability
points cannot close that (H3 established exactly this, with a real effect that
was nonetheless priced). In the 81-95c band the needed climb is the same order
as the signal, and the market is pricing a genuinely open question. That is the
only place a shape signal of the measured magnitude can move a decision.

So the band is not chosen because it looks good in a table -- it looks *bad* in
the table, and it is where the frozen gate loses 91% of its money. It is chosen
because it is the only band where the mechanism has room to operate.

## Why this is not PILOT-A, and a property of PILOT-A worth recording

PILOT-A (registered 2026-08-27) enters when `p_shape - no_ask/100 >= 0.10`.
That is a FLAT ABSOLUTE edge, and it has a structural consequence nobody noted
at registration: at an ask of 90c it requires p_shape >= 1.00, and above 90c it
requires a probability greater than one. **PILOT-A can never fire above 89c.**
It is already a de-facto 81-89c rule.

PILOT-A is registered and stays exactly as written -- its constants are not to
be re-tuned. This records the property, it does not change it.

The consequence is that the 90-95c slice is unreachable by any flat absolute
edge and is genuinely unclaimed. The reason is that the required edge SCALES
WITH PRICE: at 85c a position must beat 86.2% including fees, at 94c it must
beat 94.4%. Measuring edge against the ask instead of against breakeven is a
unit error, and it is what confines PILOT-A to the cheap end.

## The rule to be tested (fixed now)

* **Universe.** Bottom rungs. Real logged `no_ask` in **81-95c** inclusive --
  never derived from `100 - yes_ask`. Local hour inside PEAK_WINDOW 13-16, the
  only range where H4a's effect has the sign it claims. Shape cell earned at
  `n >= MIN_N_RATE`.
* **Entry.** Enter NO when the shape cell's **Wilson 95% LOWER bound** on
  P(exceed) exceeds the breakeven implied by the ask, `(no_ask + fee)/100`.
  Not the point estimate -- the lower bound. This has **no fitted constant**:
  the required margin is whatever the cell's own sample size demands, so a thin
  cell must show a larger effect than a deep one to qualify.
* **One unit per city-day**, first qualifying cycle, entry at the ask, held to
  settlement, Kalshi fees. No exit rule -- H2 settled that.
* **Subordinate to H4a.** This may not be scored until H4a PASSES. It rests on
  the shape cells being validated out of sample; scoring it first would be
  building on the unvalidated premise that killed H1.
* **Days from registration only.** Scored on days >= 2026-09-01. The 24 days
  above informed the framing and are disqualified as evidence.

## Prediction (falsifiable, and the cross-band form is the real test)

If the mechanism is right, the shape edge is **concentrated in 81-95c and
absent at 96-98c**. Scoring the same rule at 96-98c must show no improvement
over the market. A result that looks equally good in both bands falsifies the
mechanism even if it makes money, because it would mean something other than
"1.48F matters where 1.48F is decisive" is driving it.

## How it fails (named in advance, so a null is legible)

1. **The gap is too wide.** 81-90c must move 76.9% -> 88.1%, over eleven points.
   A 1.48F shift is unlikely to be worth eleven points. This is the most likely
   failure and it is an honest one.
2. **The band is contested for a reason.** The market prices 81-95c as open
   because it IS open; the residual may be irreducible weather, not a blind
   spot. The base rate is that the market wins ~7 of 8 model-market disputes.
3. **Shape is a proxy for hour**, and hour is already in the model. The cell
   banding is there to catch this.
4. **The LCB gate is too strict to ever fire.** Requiring the cell's lower bound
   to clear breakeven may yield n=0 for months. If so this is not a null result,
   it is an untested hypothesis, and it must be reported as such.
5. **Survivorship.** Conditioning on a large needed climb late in the day may
   select doomed days regardless of rate.

## Bar for promotion

Unchanged from everything else here: **>= 60 independent city-day units**,
Wilson 95% LCB above fee breakeven at mean entry price, >= 90% of units priced
from a real logged ask, and out-of-sample confirmation on post-registration
days. Note the arithmetic that makes this band worth the attempt at all: 62
units at a perfect record clears 90-95c, and 29 clears 81-90c, against the 210
that 96-98c would demand.

No pilot activates on this. If it proves, it comes back here for a separate
pilot registration with its own $100 and the same quit lines -- $40 down, no
reseed. Nothing about this hypothesis changes the standing commitment that no
new money moves until the paper trader works.

# HYPOTHESIS 4 -- DIURNAL-CURVE DEVIATION (SHAPE, NOT LEVEL)
# (registered 2026-08-27, BEFORE any test. This text does not change.)

## Where it comes from
An observation from the trading desk, not from a table: markets reprice midday
when the temperature trajectory departs from the day's expected diurnal curve.

## Mechanism
Every probability in this repo conditions on LEVEL and TIME:
`p_exceed(city, local_hour, run_max, cap)`. But `run_max` is a MAXIMUM, so it
is monotone and shape-blind. A day sitting at 85F because it stalled at 10:00
and a day sitting at 85F while still climbing 3F/hr are the same input to the
model and wildly different days. The information the model discards is exactly
the information a human trader watches.

Two separable claims:
  (a) SHAPE ADDS INFORMATION. Deviation from the day's own predicted curve --
      or, as a proxy, the recent climb RATE -- predicts the remaining climb
      beyond what (level, hour) already says.
  (b) THE MARKET LAGS IT. Repricing follows the deviation rather than leading
      it, leaving a window.

## Why this is not just H2 again
H2 failed because its exit signal (`p_exceed`) only fires once the day is
plainly lost, by which time the bid has collapsed -- failure mode 2, confirmed
with DEN's late bids running 19c, 3c, 3c. A deviation signal is different in
KIND: a stall is visible at 13:00, hours before the level-based model concedes
anything. If an exit is ever worth making, this is the signal that could make
it in time. So H4 subsumes the exit question rather than repeating it.

## What is testable NOW vs LATER
* NOW (proxy): recent climb rate, reconstructed from consecutive `run_max`
  readings. 1,911 usable rate samples exist across 227 city-days, and the
  distribution is not degenerate (44% stalled <=0.2F/hr, 44% climbing
  >=1.5F/hr, median 1.10).
* LATER (direct): `curve_dev` = temp_now - predicted_curve(hour), logged from
  2026-08-27 onward. Neither the instantaneous temperature nor the forecast
  curve as it stood at scan time can be reconstructed after the fact, which is
  why logging starts before the test.

## The test to be run (fixed now)
H4a, the information claim, on existing data:
  * rate = d(run_max)/dt over a 0.5-2.5h gap between consecutive cycles
  * buckets: STALLED <=0.2 F/hr | MID 0.2-1.5 | CLIMBING >=1.5 -- these three
    only, no others
  * control for what the model already knows: compare within HOUR BANDS
    (pre-peak <13, peak 13-16, post-peak >16) and within NEEDED-CLIMB bands
  * outcome measured: realized remaining climb (settle - run_max)
  * CLAIM PASSES only if mean remaining climb differs by >= 0.5F between
    STALLED and CLIMBING within the same band, with non-overlapping standard
    errors
H4b, the market-lag claim, is DEFERRED until the data bar below is met. It is
not tested today and no result may be claimed for it.

**Threshold correction, 2026-08-27, made BEFORE any H4b test and in the
TIGHTENING direction.** As first written the bar was ">= 200 logged
`curve_dev` cycles". That unit is wrong: 23 cities x ~11 scans is ~250 cycles
per DAY, so the bar could be cleared by a single day's weather -- 200
observations that are almost entirely one synoptic event. Corrected bar:

    >= 200 (city, cycle) events AND >= 20 DISTINCT DAYS

The event is per-cycle because the test is an event study -- a material change
in `curve_dev` followed by the price change in the NEXT cycle -- but the day
count is what stops a single hot afternoon from masquerading as a sample. This
is the same class of correction as the `na == 100` price filter: fixing a
mis-specified measurement, not moving a bar to obtain a result. It makes the
requirement strictly harder.

**Meter correction, 2026-08-29 (display only; the bar above is unchanged).**
The threshold correction landed in `curve_lag.py` but NOT in the progress meter
`shadow_run._hypothesis_progress`, which kept counting the retired unit --
every cycle with a non-null `curve_dev`. It read **984/200 events, ready:
true** with a full bar on the site and in the nightly line, while the gate read
**52/200 events, 3/20 days, "data bar not met"**. `docs/status.json.blocking`
therefore omitted H4b, contradicting its own documented contract that an empty
`blocking` means a test is ready. No test, gate or bar was touched and the
activation interlock was never affected -- pilots key off `verdict()`, not the
meter -- but a status feed that reports a bar as met is exactly the kind of
number a future session would act on. Fixed by having the meter call
`curve_lag._events()` so it cannot drift from the test again; a two-leg bar now
fills to its shortest leg and carries `also` + an explicit `ready`.

**The same bug, on H4a, caught before it fired -- 2026-09-02 (display only; the
28-day bar is unchanged).** H4a's registered bar is 28 logged days. Its meter
had no explicit `ready`, so `_status` fell back to `have >= need`. The day count
was about to reach 28 on the 2026-09-03 nightly while `shape_eval.verdict()`
still reads `n=0/50`, because the operative constraint was never the day count:
a decision only scores when its `(city, peak-hour, rate-bucket)` train cell
reaches `MIN_N_RATE = 12`, and the deepest cell inside the 13-16 local window
is at 10. H4a would therefore have dropped out of `docs/status.json.blocking`
around 2026-09-03 -- reporting "a test is ready" against its own gate -- and
stayed wrong across the 2026-09-05 check-in. Fixed the same way as H4b:
`ready` is taken from `shape_eval.verdict()`, and the real constraint rides
along as a second leg (`held-out scored decisions`, 0/50) so the bar fills to
the shortest one. **No bar was moved.** The 28 days stays registered and stays
displayed; `MIN_SCORED = 50` was registered 2026-08-27 in the same breath, so
surfacing it adds no requirement. Counts only: `n` and `ready` are read from
the verdict, never `passed` and never the Brier values.

Measured while fixing it, and worth recording because it dates the answer: the
leading peak-window cells fill at **exactly +1 per settled even-dated day**
(traced 08-06 through 09-02; the only misses are 2026-08-26, the coverage-cliff
day, which contributed 0 to every one of them). Four cells sit at 10. So 09-02
takes them to 11 and 09-04 takes them to 12, and H4a can first score on or
about the **2026-09-05** nightly -- the check-in date, unchanged. It will not
trickle: at four qualifying cells the held-out count is ~126 decisions against
a bar of 50, so H4a gets a verdict rather than another "still short", and one
more coverage-cliff day moves that to 09-07. The cells deeper than 10
(`PHL|18|stalled` and `NYC|18|stalled`, both at 11) are outside the peak window
and can never score -- they are decoys in the raw table.

**H6 and H7 were absent from the meter entirely** until 2026-09-02: their gates
were computed into `docs/gates.json` and H7 refused correctly, but neither
appeared in `hypotheses.json`, in `status.json.hypotheses`, in `blocking`, or
in the nightly progress block. A registered hypothesis that no meter counts is
one nobody notices becoming ready. Both now delegate to their own tests --
H6 to `h6_eval._events()`, H7 to `shape_temp_eval.verdict()` for its two
strata, with the hourly pair named as the binding leg.

## How it fails (named in advance)
1. Rate is a proxy for hour, and hour is already in the model -- the banding
   is there to catch this; if the effect vanishes within bands, it was time.
2. Rate is noise at hourly sampling: 5-minute obs are quantized from whole
   degrees C, and dropped cron fires widen the gaps.
3. Shape adds information but the market already has it -- the H3 outcome, and
   the base case in this ledger (market wins 7 of 8 disputes).
4. The effect is real but smaller than the fee drag at 96-98c, where breakeven
   needs 98.2%.
5. Survivorship in the banding: conditioning on a large needed-climb late in
   the day may select doomed days regardless of rate.

## Bar for promotion
Unchanged: >= 60 independent city-day units, Wilson 95% LCB above fee
breakeven, out-of-sample confirmation on post-registration days.

## RESULT H4a (2026-08-27, `shape_backtest.py`) -- INFORMATION CLAIM PASSES,
## in the peak window only. 1,877 rate observations with settled outcomes.

Mean REALIZED remaining climb (F) by rate bucket, within hour band:

    band        STALLED          MID              CLIMBING          gap
    pre<13     +11.50 n=181     +6.96 n=87       +8.84  n=533      -2.66
    peak13-16   +1.05 n=217     +1.69 n=102      +2.53  n=261      +1.48
    post>16     +0.39 n=430     +0.62 n=24       +0.24  n=42       -0.15

Controlling ALSO for needed climb -- the model's other input -- the two cells
that clear the registered bar (>=0.5F apart, non-overlapping SEs):

    peak13-16  need 0-2F   STALLED +1.49+-0.40 (n=17)   CLIMBING +3.06+-0.26 (n=46)
    peak13-16  need 5F+    STALLED +3.70+-0.99 (n=8)    CLIMBING +6.38+-0.78 (n=14)

**Shape carries information that level+hour does not.** During peak heating a
stalled day delivers ~1.5F more; a day still climbing delivers ~3.1F. At the
boundary (0-2F needed) that difference is the whole outcome -- and the boundary
is precisely where every loss in this ledger lives (H2 result).

**Failure mode 1/5 also confirmed, and it bounds the claim.** Pre-peak the
effect INVERTS (-2.66): a "stall" at 09:00 usually means the day has not begun
climbing, which selects days with the most climb remaining. The signal is
therefore NOT general -- it is specific to the peak window, and any use of it
must be time-gated. A rule applied all day would trade the inversion.

**What this does NOT establish.** Information is not edge. The market may hold
the same signal -- that is exactly how H3 died, and this ledger's base case is
that the market wins 7 of 8 disputes. Whether repricing LAGS the deviation is
H4b, which stays DEFERRED until >=200 `curve_dev` cycles are logged. Nothing
here may be traded on.

Caveats on the numbers themselves: in-sample; the separated cells are small
(n=17/46 and n=8/14); six cells were examined, so two separations are partly a
multiple-comparisons artifact. The peak-window aggregate (+1.48 over n=217 vs
n=261) is the durable part and does not depend on the needed-climb banding.

**Immediate use that requires no trading claim:** `p_exceed` conditions on
(city, hour, run_max) and is shape-blind. Conditioning it on rate inside the
peak window is a model improvement worth making on its own merits, since better
probabilities improve every downstream measurement whether or not anything is
ever traded.

### Shape conditioning: BUILT, GATED, AND NOT YET VALIDATED (2026-08-27)
`empirical.p_exceed` now accepts an optional `rate`. Properties, deliberate:
* **Dormant by default.** Callers that omit `rate` get byte-identical results
  (verified: 120 identical, 0 differing), so every recorded H2/H3 number stays
  reproducible. No production caller passes it -- `live.py` and `prob.py` are
  untouched.
* **Peak-gated.** Conditioning applies only inside 13:00-16:00 local, because
  the measured effect INVERTS pre-peak. Outside the window `rate` is ignored.
* **Sample-gated.** A conditioned cell is used only at n >= 12; otherwise it
  falls through to the existing behaviour.

**Out-of-sample validation is NOT yet possible, and it was attempted.**
`shape_eval.py` splits days by parity, builds samples from TRAIN only and
scores Brier on TEST only. With 22 logged days a half-split leaves at most 9
samples per (city, hour, bucket) against the threshold of 12, so zero cells
qualify and the harness correctly reports "no comparable cycles".

Lowering `MIN_N_RATE` to force a number would be fitting a constant to obtain
a result -- the exact move that produced H1. It is not being done. Roughly
28-30 logged days are needed before a half-split can earn cells; at current
coverage that is about a week away, and the harness is already written and
will run unchanged.

Until then: the effect is measured (H4a), the mechanism is implemented, and
the improvement is UNPROVEN. It must not be switched on in `prob.py` or
`live.py` before `shape_eval.py` reports a Brier improvement on held-out days.

---

# HYPOTHESIS 3 -- THE SETTLEMENT GAP ON BOUNDARY DAYS
# (registered 2026-08-27, BEFORE any test. This text does not change.)

## Where it comes from
Not from scanning a table. From a structural fact plus an observation:
every loss in the 96-98c band was a BOUNDARY day, settling within 1F of the
cap (H2 result: margins -1, 0, -1). This strategy is never blown out; it loses
only to the final degree. So the only question that matters is what decides
that degree.

## Mechanism
Settlement is the NWS CLI maximum, which is derived from **1-minute** data.
The intraday signal every participant watches -- METAR and the 5-minute
automated obs -- is coarser and cannot see a brief peak between samples.
The two are not interchangeable: gotcha 10 establishes 5-minute obs and :53
METARs agree with each other (-0.17F over 26 pairs), while the settlement
product is a different, finer instrument that can only ever be >= what those
samples caught.

So there is a real, per-station quantity:

    G = CLI_settle - (our final observed max for that city-day)

If G is systematically positive, then a day whose visible max sits just BELOW
a cap still settles ABOVE it more often than the visible number implies. On a
boundary day that is the entire outcome.

Note what this hypothesis does NOT need: any claim that forecasts are biased
(they are not -- nbm +0.08F over n=785), and any claim about exit timing
(refuted in H2). It needs only that settlement is measured on a finer
instrument than the one the market watches.

## Why an edge could survive
Our empirical remaining-climb tables are built as (CLI settle - observed
run_max), so they ALREADY carry G implicitly. A participant reasoning from
visible obs alone would under-estimate exceedance on boundary days. The edge
exists only if enough of the market does that. It may not -- see failure 2.

## Precondition (if this fails, the hypothesis is dead on arrival)
Measure G on CLEAN post-parser-fix settlements, per station and pooled. If the
pooled mean G is not materially positive, stop and record the null. No rule
below is worth running.

## The rule to be tested (fixed now)
* Universe: bottom-rung cycles at/after the station's measured convergence
  hour with 0 <= (cap - run_max) <= 3 -- the boundary zone.
* p_emp = `empirical.p_exceed(...)` (gap-aware by construction).
  p_mkt = no_ask / 100 (what the NO buyer is charged is the market's implied
  P(exceed)).
* Enter NO when p_emp - p_mkt >= D, for D in {0.05, 0.10, 0.15} ONLY.
* One unit per city-day, first qualifying cycle. Entry at the ASK, held to
  settlement, Kalshi fees applied. Compare against the same universe untraded.

## How it fails (named in advance)
1. G is ~0 on clean data -> dead on arrival, no edge to have.
2. The market already prices the finer instrument -> no systematic
   disagreement in the boundary zone.
3. Disagreement exists and the MARKET is right. This is the base case in this
   ledger: the market has won 7 of 8 model-market disputes.
4. Boundary cycles are too rare to reach 60 units this season.
5. IN-SAMPLE CONTAMINATION: the empirical tables are built from the same
   settled days being tested. Any positive result MUST be re-confirmed on
   post-2026-08-27 days alone before it means anything.
6. The rungs are not fillable at the prices used (check yes/no depth).

## Bar for promotion
Unchanged: >= 60 independent city-day units, Wilson 95% LCB above fee
breakeven, plus out-of-sample confirmation per failure 5.

## RESULT (2026-08-27, `boundary_backtest.py`) -- NOT SUPPORTED
**Precondition PASSED.** On 127 clean post-parser-fix city-days:

    pooled G = +0.21F  (median +0.08, sd 0.64, SE 0.057 -> t ~ 3.7)
    CLI above our observed max 57% of days, below 32%
    per station: SEA +0.87, DEN +0.72, NYC +0.71 ... SFO -0.29, SAN -0.22

So the settlement gap is REAL: CLI does read above the coarser obs, reliably.
But +0.21F is worth only ~3 points of probability on a boundary day, and the
rest of the test says the market already has it.

**Failure mode 2 confirmed -- no exploitable disagreement.** In the boundary
zone the model and the market broadly agree: mean(p_emp - p_mkt) = **-0.056**,
with the model higher on only 48% of cycles. There is no systematic direction
to trade.

**The rule, as registered:** D>=0.05 -> 7 units, 0 wins, -4.71c/unit.
D>=0.10 and D>=0.15 -> 5 units, 0 wins, -6.00c. Losing, but n=5-7 proves
nothing: 0 wins in 7 tries at an implied ~10% is a 48% likely outcome. This is
absence of evidence, not evidence of absence.

**Failure mode 4 is the decisive one.** The boundary zone yields just 29
TRADEABLE cycles in 20 days, and after one-per-city-day dedup the rule fires
~0.35 times per day. Reaching the 60-unit bar would take **~170 days**. Even
if the edge were real, it cannot be demonstrated to this project's standard
within any horizon that matters. Out-of-sample cycles available today: 0.

**A measurement error in the first run, recorded because it is the same class
of bug this repo keeps finding:** `na == 100` is not a price -- Kalshi returns
it when NO ask exists, and buying NO at 100c cannot profit. Treating it as
"market implies 100%" put 46 phantom cycles into the calibration table and
made the market look catastrophically miscalibrated (99-100c bucket: implied
100%, realized 41%). With the artifact removed the zone holds 29 real cycles
and the apparent mispricing disappears. The registered rule was not changed;
only the price filter was corrected.

## Verdict
Three hypotheses, three nulls, and the reasons differ -- which is itself the
finding:
  H1 hot-bias      REFUTED   -- premise was a parser artifact
  H2 early exit    REFUTED   -- expectancy is set at entry; exits redistribute
  H3 settlement gap NOT SUPPORTED -- gap is real (+0.21F) but priced, and the
                                    universe is too thin to ever prove it

The through-line: at 96-98c the market is well calibrated, the forecasts are
unbiased, and the residual uncertainty is genuinely irreducible tenths of a
degree. Nothing found so far survives contact with fees.

---

# HYPOTHESIS 2 -- EARLY EXIT (registered 2026-08-27, BEFORE any test)

Registered under the reopening rules above: the mechanism is written here in
full, and the test is run only afterwards. Whatever the numbers say, this text
does not change.

## Mechanism (structural, not fitted)
Everything in this repo scores HOLD-TO-SETTLEMENT P&L. But these contracts
trade continuously, and the bottom-rung NO position is unusually asymmetric in
time:

* **The win locks early.** A daily maximum is monotone non-decreasing, so the
  instant the observed running max exceeds the cap, the outcome is arithmetic,
  not probabilistic. The contract should mark ~100c immediately and carries no
  residual risk. (`gate.py` already names this state DEAD_SCAVENGE.)
* **The loss does NOT lock.** A position that is nearly certain to lose still
  has bid-side value hours before settlement, because the market prices
  residual probability, not certainty. Holding surrenders that value.

Buying at 96-98c makes the payoff profile brutally asymmetric: +2 to +4c when
right, -96 to -98c when wrong. Hold-to-settlement forces the full left tail on
every miss. If a doomed position can be sold for materially more than zero,
expectancy improves WITHOUT any claim about forecast skill -- this is a claim
about the instrument and about time, not about the weather.

This is why it is worth testing after Hypothesis 1 died: it does not depend on
guidance being biased. It survives the fact that guidance is unbiased.

## Prediction (falsifiable)
For historical bottom-rung NO units that LOST, the best no_bid available after
entry, at or after the station's measured convergence hour, is materially
above 0; and a fixed exit rule yields higher mean P&L than holding, on the
same units, after fees and at the BID (never the ask).

## The rule to be tested (fixed now)
Exit at the first scan cycle where the empirical P(exceed cap) falls below a
threshold T, using the existing station/hour remaining-climb distribution.
T is swept over {0.05, 0.10, 0.20} ONLY -- three values, declared in advance --
plus one naive baseline (exit at a fixed 16:00 local) for comparison.
Exits execute at the logged `nb` (NO bid), entries at `na` (NO ask). Winners
that would have been exited early count as losses of the exit price. No
lookahead: the exit decision uses only data available at that cycle.

## How it fails (named in advance, so a null result is legible)
1. No bid exists exactly when it is needed (one-sided book on doomed days).
2. The bid is already ~0 once the day is clearly decided -- the market
   reprices faster than an hourly scanner can act.
3. Exiting also cuts eventual WINNERS that cross late; those must be counted.
4. Hourly granularity plus dropped cron fires means the modelled exit cycle
   may not have existed in reality (check `scan_coverage`).
5. Salvage is real but smaller than the fee drag, leaving expectancy negative.

## Bar for promotion
Same as always: >= 60 independent city-day units, Wilson 95% LCB above fee
breakeven, and the improvement must hold on post-2026-08-27 settlements alone,
not only on the repaired history.

## RESULT (2026-08-27, `exit_backtest.py`) -- NOT SUPPORTED
65 units, 62 eventual wins (95%), mean entry ask 97.2c.

    strategy              exits  mean P&L   total   winners cut
    hold_to_settlement        0    -2.77c    -180c        0
    exit_p<0.05               0    -2.77c    -180c        0   (never fires)
    exit_p<0.10               3    -2.89c    -188c        2   WORSE than holding
    exit_p<0.20               4    -1.95c    -127c        3
    exit_hour>=16             7    -0.82c     -53c        4   best, still negative

No variant reaches positive expectancy. Failure modes 2 and 3, both named in
advance, are what killed it: the information-based rules fire only once the
day is obviously lost, by which time the bid has collapsed (DEN's late bids ran
19c, 3c, 3c), and they pay for those late exits by cutting eventual winners --
p<0.10 cut two winners to salvage one loser and finished WORSE than doing
nothing.

The arithmetic says it could never have been close. At a 97.2c entry, fee
breakeven needs ~98.2% and the band delivers 95%. That 3-point calibration gap
costs ~180c across 65 units; the most aggressive exit harvested 127c of it, and
most of that came from clipping winners' upside rather than from salvage.

**The honest read: an exit rule cannot repair a calibration gap.** Expectancy
is set at entry. Selling earlier only redistributes the same edge.

## What the losers actually showed (worth its own hypothesis, NOT tested here)
All three losses were BOUNDARY days -- settle within 1F of the cap:

    2026-08-18 DEN  cap 89  settle 88  (-1)   best bid after entry 95c
    2026-08-19 NYC  cap 85  settle 85  ( 0)   best bid after entry 99c
    2026-08-25 MSP  cap 83  settle 82  (-1)   best bid after entry 96c

At 96-98c this strategy does not suffer blowouts; it loses only to the tenths.
And on NYC the market bid 99c all afternoon and was simply WRONG -- salvage
existed, but no rule built on our own P(exceed) can find it, because a boundary
day is indistinguishable from a winner until it settles.

That points somewhere specific: the losses live entirely in a subset where the
deciding quantity is the FINAL DEGREE, and where this repo already knows
something the market may not -- CLI runs ~+1F above the hourly METAR max
(gotcha 6), and 1-minute ASOS data is available via `sources.asos_1min_max`.
Any such rule must be registered in advance, with a mechanism, before it is
tested. It is NOT registered yet, and nothing above should be read as evidence
for it -- three boundary days is an observation, not a sample.

---

# YES Pilot v1 -- REFUTED 2026-08-27. DO NOT SEED. DO NOT REVIVE AS WRITTEN.

The rule below is preserved verbatim as the record of a pre-registration that
was honoured and then killed by its own data. Its premise -- "some stations'
guidance runs >3F hot, so the cheap YES side is underpriced there" -- was an
artifact of the CLI parser defect documented above. Both legs failed:

    hot-bias stations   SAT +5.5 -> +0.8   OKC +3.67 -> +1.8
                        HOU +3.5  -> +1.4  DAL +4.0  -> +0.4
      => NO station clears +3F. The rule selects nothing, on any day.

    cheap YES 1-10c     6.8% -> 3.1% hit (7/224), breakeven 2.6%,
                        Wilson LCB 1.5% -- BELOW breakeven.
      => no edge; the old rate was inflated because corrupted settlements
         read too LOW and YES is the bet on low.

    forecaster bias     nbm +0.80 -> +0.08 over n=785 (mae 2.83 -> 1.57)
      => guidance is not warm-biased. It never was.

Nothing is registered to replace it. The clean bias table above is exactly the
kind of thing that invites a fresh rule fitted to whatever now looks large
(TTN +2.0 on a handful of days); doing that would repeat the original error
with better data. A replacement hypothesis needs a MECHANISM argued in advance
and then tested, not a threshold chosen to fit the current leaderboard.

To reopen the question, ALL of these must hold, and they must be observed on
post-2026-08-27 settlements (everything older than the 7-day CLI window may
still carry the parser's low bias and cannot be re-derived):
  1. a stated mechanism, written down BEFORE looking at whether it pays
  2. >= 20 settled days per candidate station under the fixed parser
  3. the effect visible in a held-out period, not only in the fitting one
  4. the cheap-YES band's Wilson LCB above breakeven on clean data alone

Until then this system is a measurement instrument with no live hypothesis,
which is an honest state to be in and is not the same as being broken.

---

# YES Pilot v1 -- pre-committed 2026-08-25, BEFORE any live capital exists

Instrument: `PREREG_yes10_hotbias3` (shadow_run.py). YES <= 10c on bottom
rungs at stations with measured guide bias > +3F, real logged yes_ask only,
graded on days >= 2026-08-26 (cap-corrected logs only).

These rules are written while the account holds $0 and the variant holds
n=0, so that neither greed nor a drawdown can author them later. Editing
this section after money exists is itself a kill signal.

## Promotion (ALL required, then seed EXACTLY $100 -- not more)
1. >= 60 independent city-day units in shadow
2. Wilson 95% LCB on hit rate > fee breakeven at mean entry price
3. >= 90% of qualifying units priced from a real logged yes_ask
4. Liquidity re-probed at promotion: >= $50 of YES stake fillable <= 10c
   across gate-passing stations on a typical day (2026-08-25 probe:
   $8,218 across all 21 bottom rungs; HOU $47, OKC $649, SAT $0)
Execution stays manual: the scanner flags, the human places orders.
scan.py grows no order code, per its own header. Ever.

## THE TWC-VS-CLI GAP, MEASURED (2026-08-31) -- NO DIVERGENCE ON RECORD

The KNOWN FIDELITY GAPS section below says Kalshi settles on The Weather
Company while we grade on the NWS CLI product, and that a divergence on a
boundary day means the paper ledger records a win a real account did not get.
That was written as a risk. It is now measured.

Rather than scrape TWC, ask Kalshi: those markets are SETTLED, and the settled
result IS TWC's answer. Every boundary day in the record, checked against the
market we would actually have traded:

```
day        city cap  ticker                   CLI  our NO  kalshi  agree
2026-08-19 SFO   69  KXHIGHTSFO-26AUG19-T69    68   loses    yes    yes
2026-08-25 MSP   82  KXHIGHTMIN-26AUG25-T83    82   loses    yes    yes
2026-08-25 SFO   67  KXHIGHTSFO-26AUG25-T68    68    wins     no    yes
2026-08-26 BOS   78  KXHIGHTBOS-26AUG26-T79    78   loses    yes    yes
2026-08-28 SFO   65  KXHIGHTSFO-26AUG28-T66    65   loses    yes    yes
2026-08-29 TTN   78  KXHIGHTTTN-26AUG29-T79    78   loses    yes    yes
```

**Six for six, including the four that settled EXACTLY at the cap.** The two
authorities have not diverged on a single day where it could have mattered.
This does not retire the gap -- one divergence is still possible and the
pre-seed spot-check stays in the promotion list -- but the ledger's loss column
is not an artefact of reading the wrong thermometer.

Bonus confirmation of the cap-1 fix, from the market itself: 2026-08-25 SFO
settled at 68, ticker T68 ("max < 68") resolved NO, and our grading called it a
NO-side WIN at cap 67. The threshold really is `< cap_strike`, and the boundary
lands where the fix says it lands.

## LAX CLEARED, AND A SECOND BLIND SPOT (2026-08-31)

**LAX is not a station mismatch.** It carries the largest guide bias in the
record (-2.42F over 24 days, cool-busting >=3F on 13 of them) and is the only
one of the eight full-history stations where the bias exceeds its own error
spread, so the Houston-style question had to be asked. Two independent checks
say the plumbing is right:

* Kalshi's own rules text for `KXHIGHLAX` reads "the maximum temperature
  recorded at Los Angeles (**CLILAX**) ... according to The Weather Company" --
  the same product `sources.cli_max` fetches (KLAX -> site LAX -> CLILAX).
* CLI minus our OWN observed max at LAX averages **-0.12F** over 24 days, dead
  centre of the 23-station spread. A downtown-vs-airport mismatch would show as
  a large positive gap; it does not exist.

So the -2.42F is a real NBM cool bias in the LA marine regime, not a grading
error. It still gets no special treatment: reopening it needs a mechanism
written down BEFORE testing, like everything else.

**The check that cleared LAX found a hole in the quarantine.** Comparing every
settlement against our own observed max -- our obs are a lower bound, so CLI
below them is arithmetically impossible -- turned up four suspects. Two are
inside the documented 1F tolerance and correctly left alone. The other two,
SFO and SEA on 2026-08-07, are real and should have been quarantined.

Cause: the quarantine loop filtered rows on `verdict == "LADDER"`, a label the
early collector never wrote. **2026-08-06 through 08-09 carry 360 rows with
`run_max` and ZERO ladder rows**, so the one integrity check protecting those
days could not see them -- while `build()`, `shape_eval` and the bias tables
all consumed them happily. Worse, those are the OLDEST days, hence outside the
7-day CLI window and unrepairable: the blind spot was total exactly where the
damage is permanent. SFO 2026-08-07 stood at CLI 68 against an observed 72.0,
at the marine station that supplies most of the loss column.

Fixed by making the quarantine read the same rows the graders read -- any row
with a numeric `detail.run_max` that is not a world market. The next nightly
run drops both entries. Effect on the station most exposed: SFO guide bias
+1.50 -> +1.30 over 23 clean days.

Same lesson as the H4b meter and the coverage count, a third time: **an
integrity check that reads a different slice of the data than the consumers do
is not protecting them.** Match the consumer's filter, not a convenient label.

## THE UNPUSHED-CYCLE INCIDENT (2026-08-30) -- read before trusting a coverage number

The 16:16Z scan run started at 16:33 and scanned six cycles straight through the
eastern peak window: 16:33, 17:36, 18:38, 19:40, 20:42, 21:44. Every cycle
collected correctly. **Every cycle failed to push.** The day yielded 7 usable
peak-window rate samples against a normal 78-84, and 16 of 23 stations
contributed nothing to H4a.

Mechanism: the run checked out one commit behind the previous run's final push,
so its own commit had to rebase and conflicted on the whole-file snapshots
(`docs/active.json`, `docs/edge.json`, `docs/traps.json`, `logs/_kalshi_probe.json`,
`logs/_ob_probe.json`). The recovery was `git rebase --abort` then retry -- which
restores the IDENTICAL state, so five retries produced five identical failures,
and every later cycle inherited the same doomed base. The run burned its full
5.3 hours and only failed at the end.

Three things were wrong at once, and all three are now fixed:

1. **The retry could not resolve, only abort.** `.github/push_retry.sh` now takes
   the freshest side for exactly the regenerable snapshots (they are
   deterministic regenerations, so newest-wins is arithmetic, not judgement) and
   still refuses to guess on anything else. Verified both ways against a
   synthetic diverged remote, including that `logs/*.jsonl` union-merge still
   preserves BOTH sides' observations.
2. **Nothing alarmed.** `health.py` only tested for ZERO samples, so 7-of-84
   passed in silence and no issue was opened. It now alarms on the SHARE of live
   stations producing a pairable peak observation (below 60%), which is
   comparable across the roster growth from 10 to 23 stations, and separately on
   any cycle that scanned but could not commit -- that data leaves no trace in
   the logs, so the count has to be handed out of the scan step's environment.
   It also alerts on the FIRST rejected push over the REST API rather than at
   the end of the run (08-30's first rejection was 16:41Z; the job did not go
   red until 21:50Z), and any commits still unpushed when a run ends are kept
   as a git bundle in the run's `unpushed-commits` artifact, so the data is
   recoverable instead of dying with the runner.
3. **Too many writers.** Two crons per hour, an hourly external trigger and the
   end-of-run chain all fed one concurrency group where only one run may sit
   pending, so runs cancelled each other -- 12 on 2026-08-30 -- and overlapped at
   the edges, which is what manufactured the divergence. The `:35` backup cron is
   removed; the scan loop now also hard-resets to `origin/main` before its first
   cycle so a chained run never starts from a stale base.

The generalisable lesson, and the reason this sits next to the settlement-cache
incident: **a coverage number that counts attempts is not a measure of data.**
08-30 logged the highest cycle count of the month while starving the only
hypothesis still alive. Count the thing the test consumes, not the thing the
scheduler produces.

## KNOWN FIDELITY GAPS (measured 2026-08-26, before any capital)
* **Settlement source differs from our grader.** Kalshi's rules read: "the
  maximum temperature recorded at San Antonio (CLISAT) ... according to
  **The Weather Company**". We grade on the NWS CLI product directly. They
  usually agree (TWC reads the same climate report) but they are not the same
  authority, and a divergence on a boundary day means the paper ledger records
  a win a real account did not get. Before any seed, spot-check TWC against
  CLI on the boundary days this pilot actually trades.
* **The threshold is `< cap_strike`, not `<= cap`.** Same arithmetic as the
  cap-1 fix (T101 = "less than 101" = "at most 100"), and the API rules text
  independently confirms that fix. Boundary days are decided by the TENTHS and
  by how the source rounds: an observed 100.4 max reports as 100 and WINS;
  100.5 reports as 101 and LOSES.
* **Fills are assumed full at the logged ask.** No queue, no partials. This is
  the optimism the FILL REALITY quit line exists to test.
* **Scan coverage is not guaranteed.** GitHub drops scheduled cron fires under
  load (2026-08-26: 5 of 11 hours; the nightly scorecard itself was dropped on
  2026-08-27, the first miss in 31 runs). Both the pilot and the prereg variant
  take a city's FIRST qualifying cycle, so a sparse day samples a later price
  than a full day. `scan_coverage` in shadow_summary.json records this per day;
  check it before comparing across days.
* **The pilot and the prereg variant gate on DIFFERENT bias estimators.**
  The variant uses `adaptive.bias_sigma` evaluated at SCORING time (contains
  lookahead -- acknowledged at registration). `paper_pilot` uses a
  point-in-time mean over settled days strictly BEFORE each trade, minimum 3
  days, because a followed bankroll cannot borrow tomorrow's refit. They will
  disagree on which stations qualify and their n will diverge (2026-08-26:
  variant 1 unit, pilot 2). The pilot is the honest live simulation; the
  variant is the pre-registered statistic. Do not pool them.

## THE SETTLEMENT-CACHE INCIDENT (2026-08-27) -- read before trusting any bias
`docs/settlements.json` never re-fetched a non-null value, so any settlement
written by an INTRADAY run froze that day's max-SO-FAR as permanent truth.
Seven entries were provably wrong; the worst read 71F on a Denver day we
watched reach 98F. The damage was not academic:

    SAT bias as cached : +5.0F  -> passed the +3F gate, was traded 2026-08-26
    SAT bias corrected : +0.25F -> never qualified at all

One frozen mid-morning reading manufactured a "hot-biased station" and put a
real (paper) position on it. Three defenses now exist, in order of strength:

1. **Never write a settlement for a day that is not over** (same-day guard).
2. **Re-verify inside the window.** api.weather.gov serves CLI for exactly
   **7 days back, then the product is gone** (measured 2026-08-27). An error
   not caught inside that window is permanent, because nothing can re-derive
   it. Entries are now re-fetched until confirmed post-close, then recorded in
   `settlements_verified.json` and never fetched again. This also picks up
   NWS's own corrected climate reports.
3. **Quarantine the impossible.** A poisoned value is a max-so-far, therefore
   always too LOW, and our own observations are a valid lower bound on the
   true max. Any cached settlement below what we observed is dropped. This is
   arithmetic, not judgment, so it works even outside the 7-day window.

The general lesson, which outlives this bug: **a cache of values that can only
be verified for a limited time needs provenance, not trust.** Anything derived
from settled data -- station bias, the empirical climb tables, every variant --
inherits the errors silently and gives no sign that it has.

## Sizing
Half-Kelly on the LCB hit rate (not the point estimate), hard cap 5% of
bankroll per unit -- the same seatbelt as the frozen gate. No martingale,
no averaging down, no "one more to get even."

## Quit lines (symmetric, non-negotiable)
- QUIT UP:      bankroll >= $5,000 -> close everything, withdraw, stop.
- QUIT DOWN:    bankroll <= $40 -> close everything, stop, NO RESEED.
                Post-mortem in this file before any future proposal.
- FUTILITY:     after 30 live units, if the Wilson 95% UCB on the LIVE hit
                rate < fee breakeven -> stop. The edge did not survive
                contact with real fills.
- FILL REALITY: over the first 20 attempted units, if fewer than 10 fill at
                or under the modeled price -> pause and re-measure. The
                shadow P&L was counterfactual by construction.
- GATE DECAY:   a station leaving the +3F bias gate stops qualifying
                immediately. If fewer than 2 stations remain, accrual
                pauses. The gate is NOT widened to keep trading.

## Expected timeline, stated now so it can't be renegotiated later
IF promoted and IF the observed ~6.8% hit rate is real: ~100 trading days
to 50x at half-Kelly -- months, not weeks, passing through multiple
account halvings (P(30-loss streak) ~ 12% at any time). If the true rate
is <= 4%, the quit lines end the pilot with roughly $60 lost and a clean
answer. Both outcomes are acceptable; an unbounded middle is not.
