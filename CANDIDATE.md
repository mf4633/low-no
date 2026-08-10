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
