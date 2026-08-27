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
