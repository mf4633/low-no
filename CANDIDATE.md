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
